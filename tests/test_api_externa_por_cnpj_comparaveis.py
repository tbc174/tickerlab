"""Os comparáveis de uma companhia aberta na API externa (linha 736, PR 3): o leitor `conjuntos/comparaveis.py`.

Base de mentira, sem internet; os CNPJs são de ninguém. A ALFA é de energia elétrica e tem nove pares no
grupo; há também um banco (outro grupo), um par cujo FCA só chegou depois do dia, um par sem DFP recente e
um par que a rede trata como pessoa. Riscos: olhar o futuro (o DFP de 2024 do par 9 só veio depois do dia;
o setor vale pelo FCA já entregue) e vazar pessoa (quem a rede não conhece como empresa não sai, nem como
par).
"""

import math
import statistics
from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpj_
from base.ponto_no_tempo import COLUNAS_DA_BASE
from base.porta import Porta
from src import setores
from src.api_externa.conjuntos import comparaveis

DIA = date(2025, 6, 30)
CVM_FCA, CVM_DFP = "cvm-hist-fca", "cvm-hist-dfp"
ENERGIA = "Energia Elétrica"
HOLDING_DE_ENERGIA = "Emp. Adm. Part. - Energia Elétrica"


def _cnpj(raiz: str) -> str:
    primeiros = f"{raiz}0001"
    return primeiros + cnpj_.digitos_verificadores(primeiros)


ALFA = _cnpj("11111111")
PARES = [_cnpj(f"2000000{i}") for i in range(1, 10)]
BANCO = _cnpj("30000001")
FCA_DEPOIS = _cnpj("30000002")  # de energia, mas o primeiro FCA chegou depois de DIA
SEM_DFP_RECENTE = _cnpj("30000003")  # de energia, o último DFP é de 2021
TRATADA_COMO_PESSOA = _cnpj("30000004")  # de energia, a rede a trata como pessoa
FORA_DA_REDE = _cnpj("30000005")  # de energia, a rede não a conhece
TODAS = [
    ALFA,
    *PARES,
    BANCO,
    FCA_DEPOIS,
    SEM_DFP_RECENTE,
    TRATADA_COMO_PESSOA,
    FORA_DA_REDE,
]


# ---------------------------------------------------------------- a base de mentira


def _fca() -> pd.DataFrame:
    """Um FCA por companhia: (cnpj, empresa, referência, entregue em, setor)."""
    linhas = [
        (ALFA, "ALFA ENERGIA S.A.", "2024-01-01", "2024-05-20", ENERGIA),
        *(
            (par, f"PAR {i} S.A.", "2024-01-01", "2024-05-20", HOLDING_DE_ENERGIA if i == 1 else ENERGIA)
            for i, par in enumerate(PARES, start=1)
        ),
        (BANCO, "BANCO S.A.", "2024-01-01", "2024-05-20", "Bancos"),
        (FCA_DEPOIS, "TARDIA S.A.", "2025-01-01", "2025-07-15", ENERGIA),
        (SEM_DFP_RECENTE, "VELHA S.A.", "2024-01-01", "2024-05-20", ENERGIA),
        (TRATADA_COMO_PESSOA, "PESSOA S.A.", "2024-01-01", "2024-05-20", ENERGIA),
        (FORA_DA_REDE, "FORA S.A.", "2024-01-01", "2024-05-20", ENERGIA),
        # o FCA mais novo da ALFA, entregue depois de DIA, a muda de setor: em DIA ela ainda é de energia
        (ALFA, "ALFA ENERGIA S.A.", "2025-01-01", "2025-08-01", "Comércio (Atacado e Varejo)"),
    ]  # fmt: skip
    tabela = pd.DataFrame(
        linhas, columns=["cnpj", "empresa", "referencia", "conhecido_em", "setor"]
    )
    tabela["cnpj"] = tabela["cnpj"].map(cnpj_.formatar)
    for coluna in ("referencia", "conhecido_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela.assign(
        versao=1, id_documento="1", categoria="A", controle_acionario="Privado",
        mes_fim_do_exercicio=12,
    )  # fmt: skip


def _numeros_do_par(i: int) -> dict[str, float]:
    """Os números do par i: a margem líquida cresce com i² (média ≠ mediana)."""
    return {
        "receita": 100.0 * i,
        "ebit": 10.0 * i,
        "da": 10.0 * i,
        "lucro": float(i**3),
        "pl": 50.0 * i,
        "caixa": 5.0 * i,
        "aplicacoes": 5.0 * i,
        "divida_cp": 20.0 * i,
        "divida_lp": 30.0 * i,
    }


NUMEROS_DA_ALFA = {
    "receita": 1000.0, "ebit": 200.0, "da": 50.0, "lucro": 100.0, "pl": 500.0, "caixa": 80.0,
    "aplicacoes": 20.0, "divida_cp": 300.0, "divida_lp": 400.0,
}  # fmt: skip


def _dfp(
    cnpj: str, ano: int, numeros: dict[str, float], divulgado_em: str
) -> list[dict]:
    """As linhas de um DFP consolidado (o exercício que termina em 31/12 de `ano`), como na base."""
    inicio, fim = f"{ano}-01-01", f"{ano}-12-31"
    # (demonstração, conta, descrição, valor, tem início)
    contas = [
        ("DRE", "3.01", "Receita de Venda de Bens e/ou Serviços", numeros["receita"], True),
        ("DRE", "3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", numeros["ebit"], True),
        ("DRE", "3.11", "Lucro/Prejuízo Consolidado do Período", numeros["lucro"], True),
        ("DVA", "7.04.01", "Depreciação, Amortização e Exaustão", -numeros["da"], True),
        ("DFC_MI", "6.01", "Caixa Líquido Atividades Operacionais", numeros["ebit"], True),
        ("BPA", "1", "Ativo Total", 10 * numeros["receita"], False),
        ("BPA", "1.01.01", "Caixa e Equivalentes de Caixa", numeros["caixa"], False),
        ("BPA", "1.01.02", "Aplicações Financeiras", numeros["aplicacoes"], False),
        ("BPP", "2.01.04", "Empréstimos e Financiamentos", numeros["divida_cp"], False),
        ("BPP", "2.02.01", "Empréstimos e Financiamentos", numeros["divida_lp"], False),
        ("BPP", "2.03", "Patrimônio Líquido Consolidado", numeros["pl"], False),
    ]  # fmt: skip
    return [
        {
            "cnpj": cnpj_.formatar(cnpj),
            "empresa": "X",
            "grupo": "con",
            "demonstracao": demonstracao,
            "conta": conta,
            "descricao": descricao,
            "inicio": inicio if tem_inicio else None,
            "fim": fim,
            "valor": valor,
            "documento": "DFP",
            "referencia": fim,
            "versao": 1,
            "ordem": "ultimo",
            "origem": "dados_abertos",
            "divulgado_em": divulgado_em,
            "ate": None,
        }
        for demonstracao, conta, descricao, valor, tem_inicio in contas
    ]


def _demonstracoes() -> pd.DataFrame:
    linhas = _dfp(ALFA, 2024, NUMEROS_DA_ALFA, "2025-03-20")
    for i, par in enumerate(PARES, start=1):
        if i == 9:
            # o par 9 entregou o DFP de 2024 depois de DIA: em DIA vale o de 2023 (números do par 1)
            linhas += _dfp(par, 2023, _numeros_do_par(1), "2024-03-20")
            linhas += _dfp(par, 2024, _numeros_do_par(9), "2025-08-01")
        else:
            linhas += _dfp(par, 2024, _numeros_do_par(i), "2025-03-20")
    linhas += _dfp(BANCO, 2024, _numeros_do_par(3), "2025-03-20")
    linhas += _dfp(FCA_DEPOIS, 2024, _numeros_do_par(3), "2025-03-20")
    linhas += _dfp(SEM_DFP_RECENTE, 2021, _numeros_do_par(3), "2022-03-20")
    linhas += _dfp(TRATADA_COMO_PESSOA, 2024, _numeros_do_par(3), "2025-03-20")
    linhas += _dfp(FORA_DA_REDE, 2024, _numeros_do_par(3), "2025-03-20")
    tabela = pd.DataFrame(linhas)[list(COLUNAS_DA_BASE)]
    for coluna in ("inicio", "fim", "referencia", "divulgado_em", "ate"):
        tabela[coluna] = pd.to_datetime(tabela[coluna])
    return tabela


def _rede() -> pd.DataFrame:
    """Quem a rede conhece: todas, menos FORA_DA_REDE; a TRATADA_COMO_PESSOA é tratada como pessoa."""
    conhecidas = [c for c in TODAS if c != FORA_DA_REDE]
    return pd.DataFrame(
        {
            "id_entidade": [f"E{c[:8]}{'0' * 12}" for c in conhecidas],
            "valor": [c[:8] for c in conhecidas],
            "sistema": "cnpj_raiz",
            "tipo": "empresa",
            "mei": False,
            "trata_como_pessoa": [c == TRATADA_COMO_PESSOA for c in conhecidas],
        }
    )


def _gravar_rede(base) -> None:
    rede = _rede()
    (base / "rede").mkdir(parents=True, exist_ok=True)
    rede[["id_entidade", "tipo", "mei", "trata_como_pessoa"]].assign(
        nome=None, natureza_juridica="2046", natureza_fonte="receita", fontes="cvm-cadastro",
        publico_em=date(2020, 1, 1),
    ).to_parquet(base / "rede" / "entidades.parquet", index=False)  # fmt: skip
    rede[["id_entidade", "sistema", "valor"]].assign(
        desde=None, ate=None, publico_em=date(2020, 1, 1), regra=2, conferido_por="regra",
        fontes="cvm-cadastro",
    ).to_parquet(base / "rede" / "identificadores.parquet", index=False)  # fmt: skip


def gravar_base(
    base, fca: pd.DataFrame | None = None, demonstracoes: pd.DataFrame | None = None
):
    """A base de mentira dos comparáveis (também a da rota, em `..._comparaveis_rota.py`)."""
    _gravar_rede(base)
    (base / "fca_geral").mkdir(parents=True)
    (_fca() if fca is None else fca).to_parquet(
        base / "fca_geral" / "2024.parquet", index=False
    )
    (base / "demonstracoes").mkdir(parents=True)
    tabela = _demonstracoes() if demonstracoes is None else demonstracoes
    tabela.to_parquet(base / "demonstracoes" / "2024.parquet", index=False)
    return base


@pytest.fixture
def pasta(tmp_path):
    return gravar_base(tmp_path / "base")


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(
    pasta,
    cnpj: str = ALFA,
    dia: date = DIA,
    permitido=_tudo,
    linhas_maximas: int = 1000,
):
    with Porta(pasta) as porta:
        return comparaveis.LeitorDeComparaveis(
            porta, permitido, linhas_maximas
        ).comparaveis(cnpj, dia)


def _corpo(pasta, **pedido) -> dict:
    servida = _ler(pasta, **pedido)
    assert servida is not None
    return servida.corpo


def _valores(linha: dict) -> dict:
    return {nome: envelope["valor"] for nome, envelope in linha.items()}


def _pares(corpo: dict) -> list[str]:
    return [linha["cnpj"]["valor"] for linha in corpo["pares"]]


# ---------------------------------------------------------------- o que sai


def test_a_empresa_pedida_sai_com_os_numeros_do_ultimo_dfp_e_as_razoes(pasta):
    corpo = _corpo(pasta)
    assert corpo["cnpj"] == ALFA and corpo["como_era_em"] == "2025-06-30"
    assert corpo["grupo_de_setores"]["valor"] == "electric_power"
    pedida = _valores(corpo["empresa_pedida"])
    assert pedida == {
        "cnpj": ALFA,
        "empresa": "ALFA ENERGIA S.A.",
        "setor": ENERGIA,
        "exercicio": "2024-12-31",
        "receita": 1000.0,
        "ebitda": 250.0,
        "lucro_liquido": 100.0,
        "patrimonio_liquido": 500.0,
        "divida_liquida": 600.0,
        "margem_ebitda": pytest.approx(0.25),
        "margem_liquida": pytest.approx(0.1),
        "roe": pytest.approx(0.2),
        "divida_liquida_sobre_ebitda": pytest.approx(2.4),
    }
    assert corpo["limites"] == list(comparaveis.LIMITES)


def test_cada_campo_tem_a_fonte_e_o_dia_em_que_ficou_publico(pasta):
    pedida = _corpo(pasta)["empresa_pedida"]
    assert (
        pedida["setor"]["fonte"] == CVM_FCA
        and pedida["setor"]["publico_em"] == "2024-05-20"
    )
    assert (
        pedida["receita"]["fonte"] == CVM_DFP
        and pedida["receita"]["publico_em"] == "2025-03-20"
    )
    assert pedida["margem_ebitda"]["publico_em"] == "2025-03-20"
    assert all(envelope["visto_em"] is None for envelope in pedida.values())


def test_os_pares_sao_as_empresas_do_mesmo_grupo_pela_maior_receita(pasta):
    """A holding de energia é par; o banco, o FCA tardio, o DFP velho e quem não é empresa não são."""
    corpo = _corpo(pasta)
    # o par 9 vale pelo DFP de 2023 (receita 100), empatado com o par 1: desempata pelo CNPJ
    assert _pares(corpo) == [*reversed(PARES[1:8]), PARES[0], PARES[8]]
    assert ALFA not in _pares(corpo)
    servida = _ler(pasta)
    assert servida is not None
    assert servida.linhas == 1 + len(PARES)
    assert servida.fontes == {CVM_FCA, CVM_DFP}


def test_o_par_vale_pelo_ultimo_dfp_ja_publico_no_dia(pasta):
    antes = next(p for p in _corpo(pasta)["pares"] if p["cnpj"]["valor"] == PARES[8])
    assert _valores(antes)["exercicio"] == "2023-12-31"
    assert _valores(antes)["receita"] == 100.0
    depois = next(
        p
        # em 01/09 a ALFA já é do comércio: o par 9 aparece entre os pares do par 1
        for p in _corpo(pasta, cnpj=PARES[0], dia=date(2025, 9, 1))["pares"]
        if p["cnpj"]["valor"] == PARES[8]
    )
    assert _valores(depois)["exercicio"] == "2024-12-31"
    assert _valores(depois)["receita"] == 900.0


def test_as_medianas_sao_dos_pares_sem_a_empresa_pedida(pasta):
    corpo = _corpo(pasta)
    margens = [_valores(p)["margem_liquida"] for p in corpo["pares"]]
    medianas = corpo["medianas_dos_pares"]
    assert medianas["margem_liquida"]["valor"] == pytest.approx(
        statistics.median(margens)
    )
    assert medianas["margem_liquida"]["valor"] != pytest.approx(
        statistics.mean(margens)
    )
    assert medianas["margem_ebitda"]["valor"] == pytest.approx(0.2)
    assert medianas["roe"]["valor"] == pytest.approx(statistics.median(
        _valores(p)["roe"] for p in corpo["pares"]
    ))  # fmt: skip
    assert medianas["margem_liquida"]["fonte"] == CVM_DFP
    assert medianas["margem_liquida"]["publico_em"] == "2025-03-20"


def test_sem_pares_suficientes_nao_ha_mediana(tmp_path):
    poucos = _fca()
    poucos = poucos[~poucos["cnpj"].isin([cnpj_.formatar(p) for p in PARES[:3]])]
    corpo = _corpo(gravar_base(tmp_path / "base", fca=poucos))
    assert len(corpo["pares"]) == len(PARES) - 3 < setores.MINIMO_DE_EMPRESAS
    assert "medianas_dos_pares" not in corpo


@pytest.mark.parametrize(
    "dia", [date(2024, 5, 20), date(2025, 3, 20), DIA, date(2025, 9, 1)]
)
def test_nada_publicado_depois_do_dia_sai(pasta, dia):
    corpo = _corpo(pasta, dia=dia)
    envelopes = [
        corpo["grupo_de_setores"],
        *corpo["empresa_pedida"].values(),
        *(e for linha in corpo["pares"] for e in linha.values()),
        *corpo.get("medianas_dos_pares", {}).values(),
    ]
    assert all(date.fromisoformat(e["publico_em"]) <= dia for e in envelopes)


def test_o_setor_vale_pelo_fca_ja_entregue(pasta):
    """Em 01/09/2025 o FCA novo da ALFA (comércio) já foi entregue: ela sai do grupo de energia."""
    corpo = _corpo(pasta, dia=date(2025, 9, 1))
    assert corpo["grupo_de_setores"]["valor"] == "trade"
    assert corpo["pares"] == []


def test_todo_grupo_de_setores_tem_codigo_de_fora():
    assert set(comparaveis.GRUPOS_DE_FORA) == set(setores.GRUPOS)
    assert len(set(comparaveis.GRUPOS_DE_FORA.values())) == len(setores.GRUPOS)


# ---------------------------------------------------------------- o que não sai


def test_antes_do_dfp_a_empresa_sai_so_com_o_cadastro(pasta):
    pedida = _valores(_corpo(pasta, dia=date(2024, 6, 1))["empresa_pedida"])
    assert pedida == {"cnpj": ALFA, "empresa": "ALFA ENERGIA S.A.", "setor": ENERGIA}


def test_conta_que_falta_nao_vira_zero(tmp_path):
    sem_divida = _demonstracoes()
    sem_divida = sem_divida[
        ~(
            (sem_divida["cnpj"] == cnpj_.formatar(ALFA))
            & sem_divida["conta"].isin(["2.01.04", "2.02.01"])
        )
    ]
    pedida = _valores(
        _corpo(gravar_base(tmp_path / "base", demonstracoes=sem_divida))[
            "empresa_pedida"
        ]
    )
    assert (
        "divida_liquida" not in pedida and "divida_liquida_sobre_ebitda" not in pedida
    )
    assert pedida["receita"] == 1000.0


def test_valor_vazio_na_linha_do_dfp_some_e_nao_vira_nan(tmp_path):
    """A base de verdade tem linhas do DFP com o valor vazio (NaN): o campo some, e o NaN não chega às razões
    nem às medianas (o JSON da API não aceita NaN)."""
    com_vazio = _demonstracoes()
    vazias = com_vazio["cnpj"].isin(
        [cnpj_.formatar(ALFA), cnpj_.formatar(PARES[0])]
    ) & com_vazio["conta"].isin(["3.11", "2.03"])
    com_vazio.loc[vazias, "valor"] = float("nan")
    corpo = _corpo(gravar_base(tmp_path / "base", demonstracoes=com_vazio))
    pedida = _valores(corpo["empresa_pedida"])
    assert not {"lucro_liquido", "patrimonio_liquido", "margem_liquida", "roe"} & set(
        pedida
    )
    assert pedida["receita"] == 1000.0
    par = next(p for p in corpo["pares"] if p["cnpj"]["valor"] == PARES[0])
    assert "margem_liquida" not in _valores(par)
    numeros = [
        e["valor"]
        for e in [
            *(e for linha in corpo["pares"] for e in linha.values()),
            *corpo["medianas_dos_pares"].values(),
        ]
        if isinstance(e["valor"], float)
    ]
    assert all(math.isfinite(n) for n in numeros)


@pytest.mark.parametrize(
    "cnpj", [TRATADA_COMO_PESSOA, FORA_DA_REDE, FCA_DEPOIS, _cnpj("40000001")]
)
def test_quem_nao_e_empresa_ou_nao_tem_fca_no_dia_nao_sai(pasta, cnpj):
    assert _ler(pasta, cnpj=cnpj) is None


def test_setor_que_nao_cai_em_grupo_nao_sai(tmp_path):
    fca = _fca()
    fca.loc[fca["cnpj"] == cnpj_.formatar(ALFA), "setor"] = "Setor que ninguém conhece"
    assert _ler(gravar_base(tmp_path / "base", fca=fca)) is None


def test_portao_que_nega_o_setor_nao_serve_nada(pasta):
    assert _ler(pasta, permitido=lambda _f, campo, _d: campo != "setor") is None


def test_portao_que_nega_a_dfp_serve_so_o_cadastro(pasta):
    corpo = _corpo(pasta, permitido=lambda fonte, _c, _d: fonte == CVM_FCA)
    assert set(corpo["empresa_pedida"]) == {"cnpj", "empresa", "setor"}
    assert all(set(par) == {"cnpj", "empresa", "setor"} for par in corpo["pares"])
    assert "medianas_dos_pares" not in corpo


def test_portao_que_nega_um_campo_tira_so_ele(pasta):
    corpo = _corpo(pasta, permitido=lambda _f, campo, _d: campo != "roe")
    assert "roe" not in corpo["empresa_pedida"]
    assert all("roe" not in par for par in corpo["pares"])
    assert "roe" not in corpo["medianas_dos_pares"]


def test_sem_direito_a_receita_a_ordem_dos_pares_nao_a_entrega(pasta):
    """A ordem pela receita contaria o ranking de um campo negado: sem ele, os pares vão pela ordem do CNPJ."""
    corpo = _corpo(pasta, permitido=lambda _f, campo, _d: campo != "receita")
    assert all("receita" not in par for par in corpo["pares"])
    assert _pares(corpo) == sorted(_pares(corpo))
    assert _pares(_corpo(pasta)) != sorted(
        _pares(corpo)
    )  # com a receita, a ordem é outra


def test_pares_cortados_no_limite_do_plano(pasta):
    servida = _ler(pasta, linhas_maximas=4)
    assert servida is not None
    assert len(servida.corpo["pares"]) == 3 and servida.corpo["cortada"] is True
    assert servida.linhas == 4
    assert _corpo(pasta)["cortada"] is False


def test_cnpj_invalido_e_erro_de_quem_chama(pasta):
    with pytest.raises(ValueError):
        _ler(pasta, cnpj="123")
