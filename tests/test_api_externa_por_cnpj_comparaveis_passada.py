"""As contas dos comparáveis numa passada só sobre o grupo (linha 1015, item d, PR 4).

Pelo log de produção de 25/11 às 03h09, o bloco dos comparáveis atrasou em 5 de 6 pedidos: 18 s, dos quais só 3 s
em consultas. O resto é Python, que fazia as contas companhia a companhia, com filtros do pandas sobre o DFP de
cada uma (103 companhias num grupo da base do ensaio). Agora as mesmas contas são feitas uma vez para o grupo
inteiro.

O risco é o número mudar. Aqui fica a conta antiga, copiada como estava em `comparaveis.py` antes do PR 4, como
referência. A conta nova tem de dar exatamente o mesmo, na base de mentira dos comparáveis e em milhares de DFP
gerados pelo Hypothesis:
- grupo consolidado ou só individual;
- versões e entregas repetidas;
- conta que falta e valor vazio;
- descrições com e sem acento;
- exercício velho demais.
"""

import math
import unicodedata
from datetime import date

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base import cnpj as cnpj_
from base import indicadores_de_caixa as caixa
from base.porta import Porta
from base.regras import LINHA_DO_LUCRO
from src.api_externa.conjuntos import comparaveis
from tests import test_api_externa_por_cnpj_comparaveis as de_mentira

CONSOLIDADO, INDIVIDUAL = "con", "ind"

# ---------------------------------------------------------------- a conta antiga (a referência), sem mudança


def _simples(texto: object) -> str:
    sem = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower().strip()


def _profundidade(conta: str) -> int:
    return conta.count(".")


def _um(linhas: pd.DataFrame) -> float | None:
    """O valor da primeira linha achada; a linha com o valor vazio (NaN na base) conta como conta que falta."""
    valores = linhas["valor"].dropna()
    return None if valores.empty else float(valores.iloc[0])


def _soma(*valores: float | None) -> float | None:
    presentes = [v for v in valores if v is not None]
    return sum(presentes) if presentes else None


def _do_balanco(
    linhas: pd.DataFrame, demonstracao: str, conta: str, comeco: str
) -> float | None:
    """A conta do balanço pelo código e pelo começo da descrição (as regras de `src.demonstracoes`)."""
    achadas = linhas[
        (linhas["demonstracao"] == demonstracao)
        & (linhas["conta"] == conta)
        & linhas["s"].str.startswith(comeco)
    ]  # fmt: skip
    return _um(achadas)


def _patrimonio(linhas: pd.DataFrame) -> float | None:
    bpp = linhas[linhas["demonstracao"] == "BPP"]
    return _um(
        bpp[
            (bpp["conta"].map(_profundidade) == 1)
            & bpp["s"].str.startswith("patrimonio liquido")
        ]
    )


def _lucro(linhas: pd.DataFrame) -> float | None:
    dre = linhas[
        (linhas["demonstracao"] == "DRE") & (linhas["conta"].map(_profundidade) == 1)
    ]
    return _um(
        dre[dre["descricao"].map(lambda d: bool(LINHA_DO_LUCRO.match(str(d).strip())))]
    )


def _ebitdas(exercicios: list[pd.DataFrame]) -> dict[tuple[str, pd.Timestamp], float]:
    """O EBITDA de cada (cnpj, fim) pela mesma conta da ficha de caixa (`base.indicadores_de_caixa`: EBIT +
    D&A), numa conta só para todas as companhias (o período lá já separa por cnpj e grupo)."""
    if not exercicios:
        return {}
    tabela = caixa.indicadores_de_caixa(pd.concat(exercicios, ignore_index=True))
    tabela = tabela[tabela["ebitda"].notna()]
    return {
        (str(linha.cnpj), pd.Timestamp(linha.fim)): float(linha.ebitda)
        for linha in tabela.itertuples(index=False)
    }


def _divida_liquida(linhas: pd.DataFrame) -> float | None:
    """Empréstimos e financiamentos (curto e longo prazo) menos caixa e aplicações; sem a dívida ou sem o
    caixa, não há conta (a falta não vira zero)."""
    divida = _soma(
        _do_balanco(linhas, "BPP", "2.01.04", "emprestimos e financiamentos"),
        _do_balanco(linhas, "BPP", "2.02.01", "emprestimos e financiamentos"),
    )
    caixa_ = _do_balanco(linhas, "BPA", "1.01.01", "caixa")
    if divida is None or caixa_ is None:
        return None
    return (
        divida - caixa_ - (_do_balanco(linhas, "BPA", "1.01.02", "aplicacoes") or 0.0)
    )


def _dividir(numerador: float | None, denominador: float | None) -> float | None:
    """A razão só com o denominador positivo: sobre receita, patrimônio ou EBITDA negativos ela engana."""
    if numerador is None or denominador is None or denominador <= 0:
        return None
    return numerador / denominador


def numeros_do_exercicio(
    linhas: pd.DataFrame, ebitda: float | None
) -> dict[str, float]:
    """Os números e as razões de um exercício, a partir das linhas do DFP de um grupo (con ou ind) e do
    EBITDA já calculado (`_ebitdas`)."""
    linhas = linhas.assign(s=linhas["descricao"].map(_simples))
    dre = linhas[linhas["demonstracao"] == "DRE"]
    receita = _um(dre[dre["conta"] == "3.01"])
    lucro = _lucro(linhas)
    patrimonio = _patrimonio(linhas)
    divida = _divida_liquida(linhas)
    valores = {
        "receita": receita,
        "ebitda": ebitda,
        "lucro_liquido": lucro,
        "patrimonio_liquido": patrimonio,
        "divida_liquida": divida,
        "margem_ebitda": _dividir(ebitda, receita),
        "margem_liquida": _dividir(lucro, receita),
        "roe": _dividir(lucro, patrimonio),
        "divida_liquida_sobre_ebitda": _dividir(divida, ebitda),
    }
    # só número finito sai: o JSON da API não leva NaN nem infinito
    return {
        nome: valor
        for nome, valor in valores.items()
        if valor is not None and math.isfinite(valor)
    }


def _do_exercicio(linhas: pd.DataFrame) -> pd.DataFrame:
    """As linhas do grupo consolidado (sem ele, do individual), uma por conta: a da entrega mais nova."""
    grupo = CONSOLIDADO if (linhas["grupo"] == CONSOLIDADO).any() else INDIVIDUAL
    linhas = linhas[linhas["grupo"] == grupo]
    chave = ["demonstracao", "conta", "inicio"]
    return linhas.sort_values(["divulgado_em", "versao"]).drop_duplicates(
        chave, keep="last"
    )


def _exercicios_recentes(
    dfps: pd.DataFrame, mais_velho: pd.Timestamp
) -> dict[str, tuple[pd.Timestamp, pd.DataFrame]]:
    """O último exercício de cada companhia (cnpj formatado), se não for mais velho que `mais_velho`: o fim e
    as linhas dele (`_do_exercicio`)."""
    exercicios = {}
    for formatado, linhas in (
        {} if dfps.empty else dict(tuple(dfps.groupby("cnpj")))
    ).items():
        fim = pd.Timestamp(linhas["fim"].max())
        if fim >= mais_velho:
            exercicios[str(formatado)] = (
                fim,
                _do_exercicio(linhas[linhas["fim"] == fim]),
            )
    return exercicios


def conta_antiga(dfps: pd.DataFrame, mais_velho: pd.Timestamp) -> dict:
    """O que `LeitorDeComparaveis._companhias` calculava antes do PR 4, por cnpj formatado: (fim, números,
    dia público dos números)."""
    exercicios = _exercicios_recentes(dfps, mais_velho)
    ebitdas = _ebitdas([linhas for _fim, linhas in exercicios.values()])
    return {
        formatado: (
            fim,
            numeros_do_exercicio(linhas, ebitdas.get((formatado, fim))),
            pd.Timestamp(linhas["divulgado_em"].max()),
        )
        for formatado, (fim, linhas) in exercicios.items()
    }


def conta_nova(dfps: pd.DataFrame, mais_velho: pd.Timestamp) -> dict:
    return {
        formatado: (exercicio.fim, dict(exercicio.numeros), exercicio.publicos_em)
        for formatado, exercicio in comparaveis.numeros_do_grupo(
            dfps, mais_velho
        ).items()
    }


COLUNAS = [
    "cnpj",
    "grupo",
    "demonstracao",
    "conta",
    "descricao",
    "inicio",
    "fim",
    "valor",
    "versao",
    "divulgado_em",
]


def _como_na_porta(tabela: pd.DataFrame) -> pd.DataFrame:
    """As colunas e os tipos que `LeitorDeComparaveis._dfps` lê da porta."""
    tabela = tabela[COLUNAS].copy()
    for coluna in ("inicio", "fim", "divulgado_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela.reset_index(drop=True)


# ---------------------------------------------------------------- na base de mentira dos comparáveis


@pytest.mark.parametrize(
    "dia",
    [
        date(2024, 6, 1),
        date(2025, 3, 20),
        de_mentira.DIA,
        date(2025, 9, 1),
        date(2027, 1, 1),
    ],
)
@pytest.mark.parametrize(
    "numeros_do_par", [de_mentira._numeros_do_par, de_mentira._numeros_quebrados]
)
def test_a_passada_unica_da_o_mesmo_que_a_conta_por_companhia(dia, numeros_do_par):
    dfps = _como_na_porta(de_mentira._demonstracoes(numeros_do_par=numeros_do_par))
    dfps = dfps[dfps["divulgado_em"] <= pd.Timestamp(dia)]
    mais_velho = pd.Timestamp(dia) - comparaveis.IDADE_MAXIMA_DO_EXERCICIO
    assert conta_nova(dfps, mais_velho) == conta_antiga(dfps, mais_velho)


def test_sem_dfp_nenhuma_companhia_tem_numeros():
    vazio = _como_na_porta(pd.DataFrame(columns=COLUNAS))
    corte = pd.Timestamp("2024-01-01")
    assert conta_nova(vazio, corte) == {} == conta_antiga(vazio, corte)
    assert comparaveis.numeros_do_grupo(pd.DataFrame(), corte) == {}


def test_os_numeros_saem_so_de_leitura():
    dfps = _como_na_porta(de_mentira._demonstracoes())
    exercicio = next(
        iter(comparaveis.numeros_do_grupo(dfps, pd.Timestamp("2023-01-01")).values())
    )
    with pytest.raises(TypeError):
        exercicio.numeros["receita"] = 0.0  # type: ignore[index]


# ---------------------------------------------------------------- em DFP gerados


# (demonstração, conta, descrição, tem início): as contas que as razões usam, variantes de descrição que entram e
# que não entram, e contas vizinhas de outra profundidade
CONTAS = [
    ("DRE", "3.01", "Receita de Venda de Bens e/ou Serviços", True),
    ("DRE", "3.01", "Receitas da Intermediação Financeira", True),
    ("DRE", "3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", True),
    ("DRE", "3.11", "Lucro/Prejuízo Consolidado do Período", True),
    ("DRE", "3.11", "Lucro ou Prejuizo Liquido do Periodo", True),
    ("DRE", "3.09", "Lucro/Prejuízo do Período", True),
    ("DRE", "3.11.01", "Lucro/Prejuízo do Período", True),
    ("DVA", "7.04.01", "Depreciação, Amortização e Exaustão", True),
    ("DFC_MI", "6.01", "Caixa Líquido Atividades Operacionais", True),
    ("DFC_MI", "6.01.01.02", "Depreciação e amortização", True),
    ("DFC_MI", "6.02.01", "Aquisição de imobilizado", True),
    ("BPA", "1", "Ativo Total", False),
    ("BPA", "1.01.01", "Caixa e Equivalentes de Caixa", False),
    ("BPA", "1.01.01", "Disponibilidades", False),
    ("BPA", "1.01.02", "Aplicações Financeiras", False),
    ("BPA", "1.01.02", "Aplicacoes Financeiras de Curto Prazo", False),
    ("BPP", "2.01.04", "Empréstimos e Financiamentos", False),
    ("BPP", "2.02.01", "Empréstimos e Financiamentos", False),
    ("BPP", "2.02.01", "Debêntures", False),
    ("BPP", "2.03", "Patrimônio Líquido Consolidado", False),
    ("BPP", "2.03", "Patrimonio Liquido", False),
    ("BPP", "2.03.01", "Patrimônio Líquido Atribuído aos Controladores", False),
]
CNPJS = [cnpj_.formatar(de_mentira._cnpj(f"4000000{i}")) for i in range(4)]
FINS = ["2022-12-31", "2023-12-31", "2024-12-31"]
ENTREGAS = ["2023-03-20", "2024-03-20", "2024-04-30", "2025-03-20"]
VALORES = st.one_of(
    st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.just(0.0),
    st.just(float("nan")),
)
LINHA = st.tuples(
    st.sampled_from(CNPJS),
    st.sampled_from([CONSOLIDADO, INDIVIDUAL]),
    st.sampled_from(CONTAS),
    st.sampled_from(FINS),
    VALORES,
    st.integers(min_value=1, max_value=3),
    st.sampled_from(ENTREGAS),
)


def _tabela(linhas: list[tuple]) -> pd.DataFrame:
    registros = [
        {
            "cnpj": cnpj,
            "grupo": grupo,
            "demonstracao": demonstracao,
            "conta": conta,
            "descricao": descricao,
            "inicio": f"{fim[:4]}-01-01" if tem_inicio else None,
            "fim": fim,
            "valor": valor,
            "versao": versao,
            "divulgado_em": entrega,
        }
        for cnpj, grupo, (
            demonstracao,
            conta,
            descricao,
            tem_inicio,
        ), fim, valor, versao, entrega in linhas
    ]
    return _como_na_porta(pd.DataFrame(registros, columns=COLUNAS))


def _iguais(nova: dict, antiga: dict) -> bool:
    """Igualdade exata, com NaN igual a NaN (a conta não deixa sair NaN, mas a prova não pode depender disso)."""
    if nova.keys() != antiga.keys():
        return False
    for formatado, (fim, numeros, publicos_em) in nova.items():
        fim_a, numeros_a, publicos_a = antiga[formatado]
        if (fim, publicos_em) != (
            fim_a,
            publicos_a,
        ) or numeros.keys() != numeros_a.keys():
            return False
        for nome, valor in numeros.items():
            if not (
                valor == numeros_a[nome]
                or (math.isnan(valor) and math.isnan(numeros_a[nome]))
            ):
                return False
    return True


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    linhas=st.lists(LINHA, min_size=0, max_size=60),
    mais_velho=st.sampled_from(
        [
            pd.Timestamp("2022-06-01"),
            pd.Timestamp("2023-06-30"),
            pd.Timestamp("2024-06-30"),
        ]
    ),
)
def test_a_passada_unica_da_o_mesmo_em_dfp_gerados(linhas, mais_velho):
    dfps = _tabela(linhas)
    # a conta antiga quebrava com linhas da DRE sem nenhuma de profundidade 1 (o filtro vazio do pandas vira seleção
    # de colunas): só a companhia em que ela quebra sai da comparação (o caso fica no teste abaixo); as outras
    # seguem juntas, porque a ordem entre companhias é parte do que se prova
    quebradas = []
    for cnpj in dfps["cnpj"].unique():
        try:
            conta_antiga(dfps[dfps["cnpj"] == cnpj], mais_velho)
        except KeyError:
            quebradas.append(cnpj)
    dfps = dfps[~dfps["cnpj"].isin(quebradas)].reset_index(drop=True)
    antiga, nova = conta_antiga(dfps, mais_velho), conta_nova(dfps, mais_velho)
    assert _iguais(nova, antiga), (nova, antiga)


def test_dre_sem_linha_de_profundidade_1_nao_quebra_e_fica_sem_lucro():
    """A conta antiga levantava KeyError neste caso; a nova serve o que tem e não inventa o lucro."""
    dfps = _tabela(
        [
            (CNPJS[0], CONSOLIDADO, CONTAS[6], "2024-12-31", 7.0, 1, "2025-03-20"),
            (CNPJS[0], CONSOLIDADO, CONTAS[19], "2024-12-31", 50.0, 1, "2025-03-20"),
        ]
    )
    with pytest.raises(KeyError):
        conta_antiga(dfps, pd.Timestamp("2024-01-01"))
    (exercicio,) = comparaveis.numeros_do_grupo(
        dfps, pd.Timestamp("2024-01-01")
    ).values()
    assert dict(exercicio.numeros) == {"patrimonio_liquido": 50.0}


# ---------------------------------------------------------------- só o DFP dos exercícios recentes


def test_a_porta_le_a_partir_de_um_valor(tmp_path):
    pasta = de_mentira.gravar_base(tmp_path / "base")
    corte = date(2024, 1, 1)
    with Porta(pasta) as porta:
        tudo = porta.ler(comparaveis.TABELA_DAS_DEMONSTRACOES)
        recentes = porta.ler(
            comparaveis.TABELA_DAS_DEMONSTRACOES, a_partir_de={"fim": corte}
        )
    assert (tudo["fim"] < pd.Timestamp(corte)).any()
    assert (recentes["fim"] >= pd.Timestamp(corte)).all()
    assert len(recentes) == (tudo["fim"] >= pd.Timestamp(corte)).sum()


def test_a_porta_recusa_a_partir_de_sem_valor(tmp_path):
    pasta = de_mentira.gravar_base(tmp_path / "base")
    with Porta(pasta) as porta, pytest.raises(ValueError, match="sem valor"):
        porta.ler(comparaveis.TABELA_DAS_DEMONSTRACOES, a_partir_de={"fim": None})


def test_a_porta_recusa_coluna_que_nao_existe_no_a_partir_de(tmp_path):
    pasta = de_mentira.gravar_base(tmp_path / "base")
    with Porta(pasta) as porta, pytest.raises(ValueError, match="não existe"):
        porta.ler(
            comparaveis.TABELA_DAS_DEMONSTRACOES,
            a_partir_de={"fim; DROP": date(2024, 1, 1)},
        )


@pytest.mark.parametrize(
    "dia",
    [
        date(2024, 6, 1),
        date(2025, 3, 20),
        de_mentira.DIA,
        date(2025, 9, 1),
        date(2027, 1, 1),
    ],
)
def test_o_dfp_lido_so_dos_exercicios_recentes_da_os_mesmos_numeros(tmp_path, dia):
    """O exercício mais novo de cada companhia, quando passa do corte, está inteiro depois dele; quando não
    passa, a companhia já ficava sem números. Ler só a partir do corte dá o mesmo."""
    pasta = de_mentira.gravar_base(tmp_path / "base")
    mais_velho = pd.Timestamp(dia) - comparaveis.IDADE_MAXIMA_DO_EXERCICIO
    with Porta(pasta) as porta:
        leitor = comparaveis.LeitorDeComparaveis(porta, lambda *_: True, 1000)
        cnpjs = list(leitor._cadastros(dia)["cnpj"])
        so_recentes = leitor._dfps(cnpjs, dia)
        filtros = {"cnpj": [cnpj_.formatar(c) for c in cnpjs], "documento": "DFP"}
        historico = porta.ler(
            comparaveis.TABELA_DAS_DEMONSTRACOES,
            como_era_em=dia,
            filtros=filtros,
            colunas=COLUNAS,
        )
    assert len(so_recentes) < len(
        historico
    )  # o DFP de 2021 da SEM_DFP_RECENTE fica de fora
    assert conta_nova(so_recentes, mais_velho) == conta_nova(historico, mais_velho)
    assert conta_nova(so_recentes, mais_velho) == conta_antiga(historico, mais_velho)
