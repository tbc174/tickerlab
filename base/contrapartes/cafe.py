"""Ficha pública das cooperativas e tradings de café: só fatos datados com fonte (PR 12 do plano do café).

A ficha não dá nota, cor nem conselho: lista o que fontes públicas disseram, com a data e o link, e o
que **não** sabemos. As regras (testes em `tests/test_base_contrapartes_cafe.py`):

- **Só a entidade:** CNPJ e nome da cooperativa ou empresa. Nada de pessoa física (nem diretoria, nem
  associado): a tabela não tem coluna para isso e o texto não cita cargo nem nome de gente.
- **Todo fato tem fonte e data:** endereço público (`https://`), veículo, data do fato e data em que
  ficou público (`divulgado_em`). Fato sem isso não entra; o que falta vira "o que não sabemos", sem
  estimativa.
- **Fato de risco** (pedido de recuperação judicial, fechamento, apuração pública) só com documento
  oficial ou notícia de veículo identificado, e a página guardada pelo arquivista
  (`base/arquivo/contrapartes.py`).
- **Palavras vedadas** (`VEDADAS`): a ficha descreve, não julga.
- **Sem olhar o futuro:** `em` corta pelo `divulgado_em` (cortar o futuro não muda o passado).

Os fatos vêm da tabela conferida `base/conferidas/contrapartes_cafe.csv` (notícias e documentos lidos à
mão, ditos com as nossas palavras e "segundo <veículo>"), mais dois cruzamentos com a base: a
situação especial do cadastro aberto do CNPJ (Receita) e os informes de CRA da CVM (cedente ou devedor).
"""

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from base.fidc import documento_de_empresa

CAMINHO = (
    Path(__file__).resolve().parent.parent / "conferidas" / "contrapartes_cafe.csv"
)
COLUNAS = (
    "id",
    "cnpj",
    "nome",
    "tipo",
    "uf",
    "fato",
    "descricao",
    "valor",
    "unidade",
    "data",
    "divulgado_em",
    "fonte",
    "veiculo",
    "tipo_de_fonte",
    "conferido_em",
)
OBRIGATORIAS = ("id", "nome", "tipo", "fato", "descricao", "data", "divulgado_em")
OBRIGATORIAS_DA_FONTE = ("fonte", "veiculo", "tipo_de_fonte")
TIPOS = ("cooperativa", "trading", "exportadora")
TIPOS_DE_FONTE = (
    "documento_oficial",
    "demonstracao_financeira",
    "relatorio_da_entidade",
    "noticia",
)
FATOS_DE_RISCO = (
    "pedido_de_recuperacao_judicial",
    "situacao_especial_na_receita",
    "encerramento",
    "apuracao_publica",
)
# a ficha descreve, não julga: estas palavras não aparecem em nenhum texto dela (comparação sem
# acento nem caixa, palavra inteira)
VEDADAS = (
    "quebrou",
    "quebrada",
    "calote",
    "golpe",
    "fraude",
    "não confiável",
    "evite",
    "recomendamos",
    "seguro",
    "confiável",
)
ENDERECO_DO_CNPJ = (
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
)
VEICULO_DO_CNPJ = "Receita Federal (cadastro aberto do CNPJ)"
ENDERECO_DO_CRA = "https://dados.cvm.gov.br/dataset/securit-doc-inf_mensal_cra"
VEICULO_DO_CRA = "CVM (informe mensal de CRA)"
CNPJ_FORMATADO = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")

# o que falta, por tipo de fato: a frase entra em "o que não sabemos" quando nenhum dos fatos aparece
FALTAS = (
    (
        ("patrimonio_liquido",),
        "Patrimônio líquido: não lemos demonstração financeira publicada.",
    ),
    (
        ("sacas_recebidas",),
        "Sacas recebidas dos produtores: sem número publicado nas fontes lidas.",
    ),
)
SEM_CNPJ = "CNPJ: não confirmado no cadastro aberto da Receita."
SEM_RECEITA = "Situação especial na Receita: o cadastro aberto do CNPJ não foi cruzado nesta ficha."
SEM_CRA = "CRA: os informes das securitizadoras na CVM não foram cruzados nesta ficha."
SEM_CRA_NOS_INFORMES = (
    "CRA: não aparece como cedente ou devedor nos informes lidos (isso não quer dizer que não tenha "
    "dívida)."
)
SITUACAO_CADASTRAL = "Situação cadastral (ativa ou baixada): a base ainda não lê essa coluna do cadastro da Receita."
AUSENCIA_NAO_PROVA = (
    "A falta de registro de recuperação judicial ou de fechamento nas fontes lidas não prova que não "
    "exista."
)


@dataclass(frozen=True)
class Fato:
    fato: str  # o tipo do fato ("faturamento", "pedido_de_recuperacao_judicial")
    descricao: str  # com as nossas palavras, "segundo <veículo>"
    valor: float | None
    unidade: str | None
    data: date  # quando o fato aconteceu (fim do exercício, dia do pedido)
    divulgado_em: date  # quando ficou público
    fonte: str  # endereço público
    veiculo: str
    tipo_de_fonte: str


@dataclass(frozen=True)
class FichaDaContraparte:
    id: str
    cnpj: str | None
    nome: str
    tipo: str
    uf: str | None
    fatos: list[Fato] = field(default_factory=list)
    o_que_nao_sabemos: list[str] = field(default_factory=list)


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in normal if not unicodedata.combining(c))


def palavras_vedadas_em(texto: str) -> list[str]:
    """As palavras de `VEDADAS` que aparecem no texto (palavra inteira, sem acento nem caixa)."""
    limpo = _sem_acento(texto)
    return [v for v in VEDADAS if re.search(rf"\b{re.escape(_sem_acento(v))}\b", limpo)]


def cnpj_valido(valor: str) -> bool:
    """CNPJ formatado com dígitos que conferem e que não pode ser um CPF."""
    return (
        bool(CNPJ_FORMATADO.fullmatch(valor)) and documento_de_empresa(valor) == valor
    )


def _vazio(valor: object) -> bool:
    return valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor == ""


def validar(fatos: pd.DataFrame) -> pd.DataFrame:
    """Confere as regras da tabela; erro (`ValueError`) diz a linha e a coluna."""
    if list(fatos.columns) != list(COLUNAS):
        raise ValueError(
            f"colunas da tabela: {list(fatos.columns)} (esperadas {COLUNAS})"
        )
    for posicao, linha in fatos.iterrows():
        for coluna in (*OBRIGATORIAS, *OBRIGATORIAS_DA_FONTE):
            if _vazio(linha[coluna]):
                raise ValueError(f"linha {posicao}: falta `{coluna}`")
        if not str(linha["fonte"]).startswith("https://"):
            raise ValueError(f"linha {posicao}: `fonte` não é endereço público")
        if linha["tipo"] not in TIPOS or linha["tipo_de_fonte"] not in TIPOS_DE_FONTE:
            raise ValueError(f"linha {posicao}: `tipo` ou `tipo_de_fonte` desconhecido")
        if not _vazio(linha["cnpj"]) and not cnpj_valido(str(linha["cnpj"])):
            raise ValueError(f"linha {posicao}: `cnpj` inválido")
        if linha["data"] > linha["divulgado_em"]:
            raise ValueError(f"linha {posicao}: `data` depois de `divulgado_em`")
        vedadas = palavras_vedadas_em(str(linha["descricao"]))
        if vedadas:
            raise ValueError(
                f"linha {posicao}: `descricao` com palavra vedada {vedadas}"
            )
    return fatos


def ler(caminho: Path = CAMINHO) -> pd.DataFrame:
    """A tabela conferida, com as datas como `date` e o valor como número, já validada."""
    fatos = pd.read_csv(
        caminho, sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
    ).replace("", None)
    for coluna in ("data", "divulgado_em", "conferido_em"):
        fatos[coluna] = pd.to_datetime(fatos[coluna], format="%Y-%m-%d").dt.date
    fatos["valor"] = pd.to_numeric(fatos["valor"])
    return validar(fatos)


def _numero(valor: object) -> float | None:
    return None if _vazio(valor) else float(valor)  # type: ignore[arg-type]


def _fatos_conferidos(linhas: pd.DataFrame) -> list[Fato]:
    return [
        Fato(
            fato=linha["fato"],
            descricao=linha["descricao"],
            valor=_numero(linha["valor"]),
            unidade=linha["unidade"],
            data=linha["data"],
            divulgado_em=linha["divulgado_em"],
            fonte=linha["fonte"],
            veiculo=linha["veiculo"],
            tipo_de_fonte=linha["tipo_de_fonte"],
        )
        for _, linha in linhas.iterrows()
    ]


def _como_data(valor: object) -> date:
    return pd.Timestamp(valor).date()  # type: ignore[arg-type]


def _fato_da_receita(cnpj: str, situacao: pd.DataFrame, em: date | None) -> list[Fato]:
    """A situação especial da matriz no cadastro aberto do CNPJ (a última, pelo `disponivel_em`)."""
    basico = re.sub(r"\D", "", cnpj)[:8]
    linhas = situacao[(situacao["cnpj_basico"] == basico) & situacao["matriz"]]
    if em is not None:
        linhas = linhas[linhas["disponivel_em"].map(_como_data) <= em]
    if linhas.empty:
        return []
    linha = linhas.sort_values("disponivel_em").iloc[-1]
    desde = _como_data(linha["data_situacao_especial"])
    return [
        Fato(
            fato="situacao_especial_na_receita",
            descricao=(
                f'O cadastro aberto do CNPJ registra a situação especial "{linha["situacao_especial"]}" '
                f"desde {desde:%d/%m/%Y}, segundo a Receita Federal"
            ),
            valor=None,
            unidade=None,
            data=desde,
            divulgado_em=_como_data(linha["disponivel_em"]),
            fonte=ENDERECO_DO_CNPJ,
            veiculo=VEICULO_DO_CNPJ,
            tipo_de_fonte="documento_oficial",
        )
    ]


def _fato_do_cra(cnpj: str, cra: pd.DataFrame, em: date | None) -> list[Fato]:
    """Cedente ou devedor de CRA: quantos certificados, do primeiro ao último mês nos informes."""
    linhas = cra[cra["CNPJ"] == cnpj]
    if em is not None:
        linhas = linhas[linhas["disponivel_em"].map(_como_data) <= em]
    if linhas.empty:
        return []
    meses = pd.to_datetime(linhas["competencia"])
    primeiro, ultimo = meses.min(), meses.max()
    certificados = linhas["codigo_certificado"].nunique()
    return [
        Fato(
            fato="cedente_ou_devedor_de_cra",
            descricao=(
                f"Aparece como cedente ou devedor em {certificados} certificado(s) de CRA nos informes "
                f"mensais entregues à CVM, de {primeiro:%Y-%m} a {ultimo:%Y-%m}, segundo a CVM"
            ),
            valor=float(certificados),
            unidade="certificados",
            data=ultimo.date(),
            divulgado_em=_como_data(linhas["disponivel_em"].max()),
            fonte=ENDERECO_DO_CRA,
            veiculo=VEICULO_DO_CRA,
            tipo_de_fonte="documento_oficial",
        )
    ]


def _o_que_nao_sabemos(
    cnpj: str | None,
    fatos: list[Fato],
    situacao_especial: pd.DataFrame | None,
    cra: pd.DataFrame | None,
) -> list[str]:
    tipos = {f.fato for f in fatos}
    faltas = [frase for do_fato, frase in FALTAS if not tipos.intersection(do_fato)]
    if cnpj is None:
        faltas.append(SEM_CNPJ)
    else:
        if situacao_especial is None:
            faltas.append(SEM_RECEITA)
        if cra is None:
            faltas.append(SEM_CRA)
        elif "cedente_ou_devedor_de_cra" not in tipos:
            faltas.append(SEM_CRA_NOS_INFORMES)
    return [*faltas, SITUACAO_CADASTRAL, AUSENCIA_NAO_PROVA]


def montar_ficha(
    chave: str,
    fatos: pd.DataFrame,
    em: date | None = None,
    situacao_especial: pd.DataFrame | None = None,
    cra: pd.DataFrame | None = None,
) -> FichaDaContraparte | None:
    """A ficha da contraparte `chave` (o `id` da tabela) como estava em `em`; None se nada era público.

    `situacao_especial`: a tabela `cnpj_situacao_especial`; `cra`: o quadro `cedente_devedor` dos
    informes de CRA (com `disponivel_em`). Sem elas, a ficha diz que o cruzamento não foi feito.
    """
    linhas = fatos[fatos["id"] == chave]
    if linhas.empty:
        raise KeyError(f"contraparte desconhecida: {chave}")
    entidade = linhas.iloc[0]
    if em is not None:
        linhas = linhas[linhas["divulgado_em"] <= em]
    cnpj = None if _vazio(entidade["cnpj"]) else str(entidade["cnpj"])
    lista = _fatos_conferidos(linhas)
    if cnpj is not None and situacao_especial is not None:
        lista += _fato_da_receita(cnpj, situacao_especial, em)
    if cnpj is not None and cra is not None:
        lista += _fato_do_cra(cnpj, cra, em)
    if not lista:
        return None
    lista.sort(key=lambda f: (f.divulgado_em, f.data))
    return FichaDaContraparte(
        id=chave,
        cnpj=cnpj,
        nome=entidade["nome"],
        tipo=entidade["tipo"],
        uf=None if _vazio(entidade["uf"]) else entidade["uf"],
        fatos=lista,
        o_que_nao_sabemos=_o_que_nao_sabemos(cnpj, lista, situacao_especial, cra),
    )


def fichas(
    fatos: pd.DataFrame,
    em: date | None = None,
    situacao_especial: pd.DataFrame | None = None,
    cra: pd.DataFrame | None = None,
) -> list[FichaDaContraparte]:
    """As fichas de todas as contrapartes da tabela, na ordem dela (só as que já tinham fato em `em`)."""
    montadas = (
        montar_ficha(chave, fatos, em, situacao_especial, cra)
        for chave in dict.fromkeys(fatos["id"])
    )
    return [ficha for ficha in montadas if ficha is not None]


def ficha_em_dicionario(ficha: FichaDaContraparte) -> dict[str, object]:
    """A ficha em tipos simples (datas em ISO), pronta para virar JSON numa rota da API."""
    dado = asdict(ficha)
    for fato in dado["fatos"]:
        fato["data"] = fato["data"].isoformat()
        fato["divulgado_em"] = fato["divulgado_em"].isoformat()
    return dado
