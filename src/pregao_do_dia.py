"""O pregão do dia (linha 444 da fila; plano `2026-10-28-raio-x-todo-dia`): os números do relatório curto
que o site mostra todo dia útil, a partir do fechamento oficial da B3.

Entradas (montadas pelo gerador, que lê o acervo; aqui só se faz conta):

- o COTAHIST da véspera e do dia, como `base.intradiario_b3.ler_cotahist` devolve (código → `fechamento`
  e `volume_financeiro`, em reais; o `volume` de lá é a quantidade de papéis e não entra aqui);
- `papeis`: código, CNPJ, nome curto da empresa e setor (FCA da CVM, só o que era público na véspera);
- a série do Ibovespa (estatísticas do índice da B3) e os contratos do boletim PR da B3 (DI1 e dólar
  futuro, com o ajuste do dia e o da véspera).

A saída de `resumo_do_pregao` é um `dict` de tipos simples (vai para JSON e para a API), em que cada
bloco leva a fonte e a data. Variações são frações (−0,10 é queda de 10%). Nada aqui diz por que o
mercado se mexeu: só o que ele fez.
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

# O mesmo corte do Raio-X de 26/10: papel com menos que isto negociado na véspera não entra nas contas.
LIQUIDEZ_MINIMA = 20_000_000
# Dia ex de evento societário: a B3 aumenta o número de distribuição (DISMES) do papel a cada evento,
# inclusive dividendo comum. Medido em 704 pregões (2024 a 2026): o número mudou no dia ex em todos os 60
# desdobramentos, grupamentos e bonificações da B3; entre os papéis líquidos, a variação mediana no dia da
# troca é de 1,5% (dividendo). Só a troca com variação de 5% ou mais fica "a conferir" (128 dias em 704).
VARIACAO_MINIMA_DO_EVENTO = 0.05
# Mediana de um ou dois papéis não descreve um setor.
EMPRESAS_POR_SETOR_MINIMO = 3
MAIORES_POR_LISTA = 5
# Juros: o DI1 de janeiro mais perto deste prazo (o mesmo vértice do Raio-X, juros de 2 anos).
PRAZO_DOS_JUROS_EM_DIAS = 730
PONTOS_BASE_POR_PONTO_PERCENTUAL = 100
# O dólar futuro da B3 é cotado em reais por mil dólares.
DOLARES_POR_CONTRATO = 1000
# Letra do mês de vencimento dos futuros da B3 (janeiro = F ... dezembro = Z).
LETRAS_DOS_MESES = "FGHJKMNQUVXZ"

FONTE_DAS_ACOES = "B3, série histórica de cotações (COTAHIST), fechamento oficial"
FONTE_DO_INDICE = "B3, estatísticas do índice Ibovespa"
FONTE_DOS_JUROS = (
    "B3, boletim de preços de referência (BVBG.086), taxa de ajuste do DI1"
)
FONTE_DO_DOLAR = (
    "B3, boletim de preços de referência (BVBG.086), ajuste do dólar futuro"
)
FONTE_DOS_SETORES = FONTE_DAS_ACOES + "; setor do Formulário Cadastral (FCA) da CVM"

# Os papéis do relatório: ações e units da B3 do catálogo de ativos.
BOLSA_DOS_PAPEIS = "B3"
TIPOS_DE_PAPEL = ("Ação", "Unit")
SEM_SETOR = "Sem setor"
# O FCA põe as holdings num setor "Emp. Adm. Part. - <setor>": vale o setor de baixo.
PREFIXO_DO_SETOR_DE_HOLDING = "Emp. Adm. Part. - "
# Nomes do FCA abreviados demais para uma tabela pública.
SETORES_ABREVIADOS = {
    "Const. Civil, Mat. Const. e Decoração": "Construção Civil, Mat. Constr. e Decoração",
    "Máqs., Equip., Veíc. e Peças": "Máquinas, Equipamentos, Veículos e Peças",
}
_SOCIEDADE_E_CLASSE_NO_FIM = re.compile(
    r"\s+(?:S[./]?[Aa]\.?\s*)?(?:ON|PN[AB]?|UNT|UNIT)?$"
)


class FaltaNoBoletimError(ValueError):
    """Um número de que o relatório precisa não está nos arquivos do dia."""


@dataclass(frozen=True)
class EntradasDoPregao:
    """Tudo o que o resumo de um pregão usa, já lido do acervo."""

    dia: date
    vespera: date
    empresas: pd.DataFrame  # saída de `variacoes_das_empresas`
    ibovespa: pd.Series  # data → pontos; precisa do dia e de pelo menos um pregão antes
    contratos: pd.DataFrame  # código → `ajuste` e `ajuste_vespera` (boletim PR)


# --- os papéis -----------------------------------------------------------------------------------


def nome_do_catalogo_sem_classe(nome: str) -> str:
    """O nome do catálogo sem o "S.A." e sem a classe do papel ("Renova Energia S.A. PN" → "Renova
    Energia"): é o que aparece quando o papel não tem nome curto."""
    return _SOCIEDADE_E_CLASSE_NO_FIM.sub("", nome.strip()).strip()


def _setor_para_a_tabela(setor: str) -> str:
    setor = setor.removeprefix(PREFIXO_DO_SETOR_DE_HOLDING)
    return SETORES_ABREVIADOS.get(setor, setor)


def tabela_de_papeis(
    catalogo: pd.DataFrame,
    tickers: pd.DataFrame,
    cadastro: pd.DataFrame,
    nomes_curtos: Mapping[str, str],
    ate: date,
) -> pd.DataFrame:
    """Código, CNPJ, nome da empresa e setor de cada ação e unit da B3, com o que era público em `ate`.

    - `catalogo`: o catálogo de ativos (`codigo` da B3, `nome`, `bolsa`, `tipo`);
    - `tickers`: código → CNPJ do FCA (`codigo`, `cnpj`, `inicio_negociacao`, `fim_negociacao`); vale o
      papel ainda negociado;
    - `cadastro`: o FCA geral (`cnpj`, `setor`, `conhecido_em`); vale a última versão conhecida até
      `ate`, para o setor não vir do futuro;
    - `nomes_curtos`: código → nome pelo qual a empresa é conhecida (`conteudo/nomes_curtos_b3.csv`).
    """
    acoes = catalogo[
        (catalogo["bolsa"] == BOLSA_DOS_PAPEIS) & catalogo["tipo"].isin(TIPOS_DE_PAPEL)
    ]
    negociados = tickers[tickers["fim_negociacao"].isna()].assign(
        simbolo=lambda t: t["codigo"].str.strip().str.upper()
    )
    negociados = negociados.sort_values("inicio_negociacao").drop_duplicates(
        "simbolo", keep="last"
    )
    conhecido = cadastro[pd.to_datetime(cadastro["conhecido_em"]) <= pd.Timestamp(ate)]
    setores = conhecido.sort_values("conhecido_em").drop_duplicates("cnpj", keep="last")
    papeis = (
        acoes[["codigo", "nome"]]
        .rename(columns={"codigo": "simbolo"})
        .merge(negociados[["simbolo", "cnpj"]], on="simbolo")
    )
    papeis = papeis.merge(setores[["cnpj", "setor"]], on="cnpj", how="left")
    papeis["setor"] = papeis["setor"].fillna(SEM_SETOR).map(_setor_para_a_tabela)
    papeis["empresa"] = papeis["simbolo"].map(nomes_curtos)
    sem_nome_curto = papeis["empresa"].isna()
    papeis.loc[sem_nome_curto, "empresa"] = papeis.loc[sem_nome_curto, "nome"].map(
        nome_do_catalogo_sem_classe
    )
    return papeis[["simbolo", "cnpj", "empresa", "setor"]].reset_index(drop=True)


# --- as ações ------------------------------------------------------------------------------------


def codigos_com_evento(vespera: pd.DataFrame, dia: pd.DataFrame) -> set[str]:
    """Os papéis em dia ex de evento societário com preço que andou: número de distribuição novo e
    variação de pelo menos `VARIACAO_MINIMA_DO_EVENTO`.

    A B3 muda o número a cada evento (desdobramento, grupamento, bonificação, provento) e o COTAHIST
    não ajusta o preço, então a variação desses papéis não é comparável. Sem a troca do número a queda
    é de verdade, por maior que seja: no circuit breaker de 26/10/2026, MGLU3 caiu 58%.
    """
    juntos = dia[["fechamento", "distribuicao"]].join(
        vespera[["fechamento", "distribuicao"]], rsuffix="_vespera", how="inner"
    )
    juntos = juntos[(juntos["fechamento_vespera"] > 0) & (juntos["fechamento"] > 0)]
    variacao = juntos["fechamento"] / juntos["fechamento_vespera"] - 1
    evento = (juntos["distribuicao"] != juntos["distribuicao_vespera"]) & (
        variacao.abs() >= VARIACAO_MINIMA_DO_EVENTO
    )
    return set(juntos.index[evento])


def variacoes_das_empresas(
    vespera: pd.DataFrame,
    dia: pd.DataFrame,
    papeis: pd.DataFrame,
    com_evento_no_dia: Collection[str] = (),
) -> pd.DataFrame:
    """Uma linha por empresa: o papel mais negociado na véspera, com o fechamento dos dois dias, a
    variação (fração), os volumes (reais) e se a variação está "a conferir".

    `com_evento_no_dia`: a saída de `codigos_com_evento`. Esses papéis ficam "a conferir" e fora das
    contas.
    """
    em_reais = {"volume_financeiro": "volume"}
    precos = papeis.merge(
        vespera[["fechamento", "volume_financeiro"]]
        .rename(columns=em_reais)
        .add_suffix("_vespera"),
        left_on="simbolo",
        right_index=True,
    ).merge(
        dia[["fechamento", "volume_financeiro"]].rename(columns=em_reais),
        left_on="simbolo",
        right_index=True,
    )
    precos = precos[(precos["fechamento_vespera"] > 0) & (precos["fechamento"] > 0)]
    um_por_empresa = precos.sort_values(
        "volume_vespera", ascending=False
    ).drop_duplicates("cnpj")
    tabela = um_por_empresa.assign(
        variacao=um_por_empresa["fechamento"] / um_por_empresa["fechamento_vespera"] - 1
    )
    tabela["a_conferir"] = tabela["simbolo"].isin(list(com_evento_no_dia))
    return tabela.reset_index(drop=True)


def liquidas(tabela: pd.DataFrame) -> pd.DataFrame:
    """As empresas que entram nas contas: liquidez mínima na véspera e variação fora do "a conferir"."""
    return tabela[(tabela["volume_vespera"] >= LIQUIDEZ_MINIMA) & ~tabela["a_conferir"]]


def amplitude(tabela: pd.DataFrame) -> dict[str, int]:
    """Quantas empresas líquidas subiram, caíram e ficaram no mesmo preço."""
    variacao = liquidas(tabela)["variacao"]
    return {
        "subiram": int((variacao > 0).sum()),
        "cairam": int((variacao < 0).sum()),
        "estaveis": int((variacao == 0).sum()),
    }


def _linha_da_lista(linha: pd.Series) -> dict[str, object]:
    return {
        "simbolo": str(linha["simbolo"]),
        "empresa": str(linha["empresa"]),
        "setor": str(linha["setor"]),
        "variacao": float(linha["variacao"]),
        "fechamento": float(linha["fechamento"]),
    }


def maiores_altas_e_quedas(
    tabela: pd.DataFrame, quantas: int = MAIORES_POR_LISTA
) -> dict[str, list[dict[str, object]]]:
    """As maiores altas e quedas entre as líquidas; no empate, a mais negociada na véspera primeiro."""
    contas = liquidas(tabela)
    altas = contas[contas["variacao"] > 0].sort_values(
        ["variacao", "volume_vespera"], ascending=[False, False]
    )
    quedas = contas[contas["variacao"] < 0].sort_values(
        ["variacao", "volume_vespera"], ascending=[True, False]
    )
    return {
        "altas": [
            _linha_da_lista(linha) for _, linha in altas.head(quantas).iterrows()
        ],
        "quedas": [
            _linha_da_lista(linha) for _, linha in quedas.head(quantas).iterrows()
        ],
    }


def setores_contra_o_indice(
    tabela: pd.DataFrame, variacao_do_indice: float
) -> list[dict[str, object]]:
    """A mediana de cada setor e a diferença para o índice (fração), do melhor setor ao pior. Setor
    com menos de `EMPRESAS_POR_SETOR_MINIMO` empresas líquidas fica de fora."""
    por_setor = liquidas(tabela).groupby("setor")["variacao"].agg(["median", "size"])
    por_setor = por_setor[por_setor["size"] >= EMPRESAS_POR_SETOR_MINIMO]
    por_setor = por_setor.sort_values("median", ascending=False)
    return [
        {
            "setor": str(setor),
            "empresas": int(linha["size"]),
            "mediana": float(linha["median"]),
            "contra_o_indice": float(linha["median"] - variacao_do_indice),
        }
        for setor, linha in por_setor.iterrows()
    ]


# --- juros e dólar (boletim PR) ------------------------------------------------------------------


def _codigo_do_vencimento(prefixo: str, ano: int, mes: int) -> str:
    return f"{prefixo}{LETRAS_DOS_MESES[mes - 1]}{ano % 100:02d}"


def _contrato(contratos: pd.DataFrame, simbolo: str) -> pd.Series:
    if simbolo not in contratos.index:
        raise FaltaNoBoletimError(f"{simbolo} não está no boletim PR do dia.")
    return contratos.loc[simbolo]


def taxa_do_di(contratos: pd.DataFrame, dia: date) -> dict[str, object]:
    """A taxa de ajuste (% ao ano) do DI1 de janeiro mais perto de dois anos e a mudança desde a véspera,
    em pontos-base."""
    alvo = pd.Timestamp(dia) + pd.Timedelta(days=PRAZO_DOS_JUROS_EM_DIAS)
    ano = min(
        (alvo.year, alvo.year + 1),
        key=lambda candidato: abs(pd.Timestamp(candidato, 1, 1) - alvo),
    )
    simbolo = _codigo_do_vencimento("DI1", ano, 1)
    contrato = _contrato(contratos, simbolo)
    return {
        "simbolo": simbolo,
        "taxa": float(contrato["ajuste"]),
        "taxa_vespera": float(contrato["ajuste_vespera"]),
        "variacao_em_pontos_base": float(
            (contrato["ajuste"] - contrato["ajuste_vespera"])
            * PONTOS_BASE_POR_PONTO_PERCENTUAL
        ),
    }


def dolar_futuro(contratos: pd.DataFrame, dia: date) -> dict[str, object]:
    """O dólar futuro do 1º vencimento (o mês seguinte: o contrato vence no 1º dia útil do mês), em
    reais por dólar, e a variação desde a véspera (fração)."""
    mes_seguinte = pd.Timestamp(dia.year, dia.month, 1) + pd.DateOffset(months=1)
    simbolo = _codigo_do_vencimento("DOL", mes_seguinte.year, mes_seguinte.month)
    contrato = _contrato(contratos, simbolo)
    return {
        "simbolo": simbolo,
        "reais_por_dolar": float(contrato["ajuste"] / DOLARES_POR_CONTRATO),
        "variacao": float(contrato["ajuste"] / contrato["ajuste_vespera"] - 1),
    }


# --- o dia na história ---------------------------------------------------------------------------


def lugar_na_historia(ibovespa: pd.Series, dia: date) -> dict[str, object]:
    """Onde a variação do Ibovespa no dia fica entre todas as anteriores: quantos pregões variaram
    tanto quanto ou mais, no mesmo sentido, e quando foi a última vez. Só usa a série até o dia."""
    serie = ibovespa.sort_index()
    serie = serie[serie.index <= pd.Timestamp(dia)]
    if serie.empty or serie.index[-1] != pd.Timestamp(dia) or len(serie) < 2:
        raise FaltaNoBoletimError(
            f"O Ibovespa de {dia:%d/%m/%Y} ou da véspera não está na série."
        )
    variacoes = serie.pct_change().dropna()
    variacao_do_dia = float(variacoes.iloc[-1])
    antes = variacoes.iloc[:-1]
    tao_extremos = (
        antes[antes <= variacao_do_dia]
        if variacao_do_dia < 0
        else antes[antes >= variacao_do_dia]
    )
    return {
        "variacao": variacao_do_dia,
        "pregoes_comparados": len(antes),
        "pregoes_tao_extremos": len(tao_extremos),
        "ultima_vez": tao_extremos.index[-1].date().isoformat()
        if len(tao_extremos)
        else None,
        "desde": antes.index[0].date().isoformat() if len(antes) else None,
    }


# --- o resumo ------------------------------------------------------------------------------------


def resumo_do_pregao(entradas: EntradasDoPregao) -> dict[str, object]:
    """Os números do relatório do dia, um bloco por assunto, cada bloco com a fonte e a data."""
    data = entradas.dia.isoformat()
    historia = lugar_na_historia(entradas.ibovespa, entradas.dia)
    tabela = entradas.empresas
    # só as líquidas: papel sem liquidez não entra no relatório, nem como "a conferir"
    a_conferir = tabela[
        tabela["a_conferir"] & (tabela["volume_vespera"] >= LIQUIDEZ_MINIMA)
    ].sort_values("simbolo")
    return {
        "pregao": data,
        "vespera": entradas.vespera.isoformat(),
        "ibovespa": {
            "pontos": float(entradas.ibovespa[pd.Timestamp(entradas.dia)]),
            **historia,
            "fonte": FONTE_DO_INDICE,
            "data": data,
        },
        "amplitude": {
            **amplitude(tabela),
            "liquidez_minima": LIQUIDEZ_MINIMA,
            "fonte": FONTE_DAS_ACOES,
            "data": data,
        },
        "setores": {
            "lista": setores_contra_o_indice(tabela, historia["variacao"]),
            "empresas_por_setor_minimo": EMPRESAS_POR_SETOR_MINIMO,
            "fonte": FONTE_DOS_SETORES,
            "data": data,
        },
        "maiores": {
            **maiores_altas_e_quedas(tabela),
            "fonte": FONTE_DAS_ACOES,
            "data": data,
        },
        "juros": {
            **taxa_do_di(entradas.contratos, entradas.dia),
            "fonte": FONTE_DOS_JUROS,
            "data": data,
        },
        "dolar": {
            **dolar_futuro(entradas.contratos, entradas.dia),
            "fonte": FONTE_DO_DOLAR,
            "data": data,
        },
        "a_conferir": [_linha_da_lista(linha) for _, linha in a_conferir.iterrows()],
    }
