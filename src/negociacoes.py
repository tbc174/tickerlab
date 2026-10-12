"""Negociações de pessoas de dentro (Research R2): o formato comum, os eventos e os resumos.

"Pessoas de dentro" são quem conhece a empresa por dentro: controladores, diretores, conselheiros
(e, nos EUA, quem tem 10% ou mais). A lei obriga essas pessoas a informar quando compram ou
vendem ações da própria empresa:

- **B3** (`src/negociacoes_cvm.py`): o formulário da CVM (VLMO, art. 11 da Resolução CVM 44), um
  por empresa e por **mês**, entregue até o dia 10 do mês seguinte, somado por cargo.
- **EUA** (`src/negociacoes_sec.py`): o Form 4 da SEC, um por pessoa e por negociação, entregue
  em até **2 dias úteis**; mostra se a venda seguiu um **plano 10b5-1** (programada com
  antecedência, o que a torna menos informativa).

O que a pesquisa diz (resumo honesto): nos EUA, as **compras** de pessoas de dentro costumam
carregar informação (Lakonishok e Lee, 2001; Cohen, Malloy e Pomorski, 2012, que separam as
compras "rotineiras" das "oportunistas"); as **vendas** dizem pouco, porque se vende para
diversificar, pagar impostos ou comprar uma casa. No Brasil o tema foi pouco estudado. Nada aqui é
recomendação: é um fato público, com a fonte.

Privacidade (decisão 0018): guardamos só o **cargo**, nunca o nome da pessoa.
"""

import pandas as pd

FONTE_VLMO = "cvm_vlmo"
FONTE_FORM4 = "sec_form4"
COMPRA, VENDA = "compra", "venda"
CARGOS = {
    "controlador": "Controlador",
    "diretoria": "Diretoria",
    "conselho": "Conselho de administração",
    "conselho_fiscal": "Conselho fiscal",
    "outros_orgaos": "Outros órgãos",
    "companhia": "A própria empresa",
    "dez_por_cento": "Acionista com 10%+",
    "outros": "Outros",
}
COLUNAS = [
    "fonte", "documento", "versao", "cnpj", "empresa", "cargo", "cargo_descricao", "operacao",
    "ativo", "data", "referencia", "entregue_em", "quantidade", "preco", "valor", "moeda",
    "plano_10b5_1", "link",
]  # fmt: skip
COLUNAS_DE_EVENTO = [
    "protocolo", "versao", "cnpj", "empresa", "categoria", "tipo", "assunto", "rotulo", "tema",
    "materialidade", "referencia", "publicado_em", "link",
]  # fmt: skip
SIMBOLOS = {"BRL": "R$", "USD": "US$"}
MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro",
)  # fmt: skip
# materialidade editorial (só ordena a leitura): compra de quem decide pesa mais que venda
MATERIALIDADE_DA_COMPRA = 70
MATERIALIDADE_DA_RECOMPRA = 50
MATERIALIDADE_DA_VENDA = 30
MATERIALIDADE_DA_VENDA_PROGRAMADA = 20


def tabela_vazia() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUNAS)


def _numero_br(valor: float, casas: int) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "#").replace(".", ",").replace("#", ".")


def formatar_valor(valor: float | None, moeda: str) -> str:
    """R$ 25,9 mil, US$ 1,2 mi; "valor não informado" quando a fonte não traz preço."""
    if valor is None or pd.isna(valor):
        return "valor não informado"
    simbolo = SIMBOLOS.get(moeda, moeda)
    for limite, sufixo in ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if abs(valor) >= limite:
            return f"{simbolo} {_numero_br(valor / limite, 1)} {sufixo}"
    return f"{simbolo} {_numero_br(valor, 0)}"


def _quando(grupo: pd.DataFrame) -> str:
    """Mês (CVM, que informa por mês) ou dia(s) da negociação (SEC)."""
    linha = grupo.iloc[0]
    if linha["fonte"] == FONTE_VLMO:
        return f"em {MESES[linha['referencia'].month - 1]}/{linha['referencia'].year}"
    dias = sorted(d for d in grupo["data"] if pd.notna(d))
    if not dias:
        return ""
    return f"em {dias[0]:%d/%m/%Y}" + (
        f" a {dias[-1]:%d/%m/%Y}" if dias[-1] != dias[0] else ""
    )


def _materialidade(cargo: str, operacao: str, programada: bool) -> int:
    if operacao == COMPRA:
        return (
            MATERIALIDADE_DA_RECOMPRA
            if cargo == "companhia"
            else MATERIALIDADE_DA_COMPRA
        )
    return MATERIALIDADE_DA_VENDA_PROGRAMADA if programada else MATERIALIDADE_DA_VENDA


def _evento(grupo: pd.DataFrame) -> dict:
    linha = grupo.iloc[0]
    cargo, operacao = linha["cargo"], linha["operacao"]
    programada = bool(grupo["plano_10b5_1"].fillna(False).astype(bool).all())
    valor = grupo["valor"].sum(min_count=1)
    quantidade = grupo["quantidade"].sum()
    verbo = "comprou" if operacao == COMPRA else "vendeu"
    nome = CARGOS[cargo]
    detalhe = f" ({linha['cargo_descricao']})" if linha["cargo_descricao"] else ""
    assunto = (
        f"{nome}{detalhe}: {operacao} de {_numero_br(quantidade, 0)} ações "
        f"({formatar_valor(valor, linha['moeda'])}) {_quando(grupo)}"
    ).rstrip() + "."
    if programada:
        assunto += " Venda dentro de um plano 10b5-1 (programada com antecedência)."
    rotulo = f"{nome} {verbo} ações" + (" (plano 10b5-1)" if programada else "")
    return {
        "protocolo": f"{linha['documento']}|{cargo}|{operacao}"[:60],
        "versao": int(linha["versao"]),
        "cnpj": linha["cnpj"],
        "empresa": linha["empresa"],
        "categoria": "Negociação de pessoas de dentro",
        "tipo": f"{cargo} {operacao}",
        "assunto": assunto,
        "rotulo": rotulo[:60],
        "tema": "participacoes",
        "materialidade": _materialidade(cargo, operacao, programada),
        "referencia": linha["referencia"],
        "publicado_em": linha["entregue_em"],
        "link": linha["link"],
    }


def eventos_das_negociacoes(tabela: pd.DataFrame) -> pd.DataFrame:
    """Um evento por documento, cargo e operação, no formato da tabela de eventos do Research."""
    if tabela.empty:
        return pd.DataFrame(columns=COLUNAS_DE_EVENTO)
    linhas = [
        _evento(grupo)
        for _, grupo in tabela.groupby(["documento", "cargo", "operacao"], sort=False)
    ]
    eventos = pd.DataFrame(linhas, columns=COLUNAS_DE_EVENTO)
    return eventos.sort_values("publicado_em", ascending=False).reset_index(drop=True)


def resumo_por_mes(tabela: pd.DataFrame) -> pd.DataFrame:
    """Compras e vendas (em dinheiro) por mês de entrega; vendas em negativo, para o gráfico."""
    if tabela.empty:
        return pd.DataFrame(columns=["mes", "compras", "vendas"])
    base = tabela.assign(
        mes=pd.to_datetime(tabela["entregue_em"]).dt.to_period("M").dt.to_timestamp()
    )
    compras = base[base["operacao"] == COMPRA].groupby("mes")["valor"].sum(min_count=1)
    vendas = base[base["operacao"] == VENDA].groupby("mes")["valor"].sum(min_count=1)
    resumo = pd.DataFrame({"compras": compras, "vendas": -vendas}).fillna(0.0)
    return resumo.sort_index().rename_axis("mes").reset_index()


def saldo_por_empresa(tabela: pd.DataFrame) -> pd.DataFrame:
    """Por empresa: compras, vendas e saldo (compras − vendas) em dinheiro, e quantos documentos.

    Só entram os cargos de quem decide (a própria empresa, a tesouraria, fica de fora). Ordenado
    do maior saldo comprador para o maior vendedor.
    """
    colunas = ["cnpj", "empresa", "moeda", "compras", "vendas", "saldo", "documentos"]
    pessoas = tabela[tabela["cargo"] != "companhia"]
    if pessoas.empty:
        return pd.DataFrame(columns=colunas)
    valor = pessoas["valor"].fillna(0.0)
    base = pessoas.assign(
        compras=valor.where(pessoas["operacao"] == COMPRA, 0.0),
        vendas=valor.where(pessoas["operacao"] == VENDA, 0.0),
    )
    saldo = base.groupby(["cnpj", "empresa", "moeda"], as_index=False).agg(
        compras=("compras", "sum"),
        vendas=("vendas", "sum"),
        documentos=("documento", "nunique"),
    )
    saldo["saldo"] = saldo["compras"] - saldo["vendas"]
    return saldo.sort_values("saldo", ascending=False)[colunas].reset_index(drop=True)
