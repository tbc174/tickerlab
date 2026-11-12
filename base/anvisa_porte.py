"""Registros da Anvisa por empresa (linha 860): `anvisa_por_empresa`, a contagem que serve de sinal de porte.

Quem fabrica ou vende produto regulado pela Anvisa precisa registrá-lo, e quem tem muito produto registrado
costuma ser grande. A tabela conta, por raiz de CNPJ e por tipo (cosméticos, produtos para saúde, saneantes,
alimentos, medicamentos, autorização de funcionamento e certificado de boas práticas), os registros (total) e
os que estão em vigor (ativos), a partir de `anvisa_registros`. **É uma aproximação do porte, não faturamento:**
um registro não diz quanto se vende, e empresa pequena pode ter muitos produtos.

Regras que têm teste (`tests/test_anvisa_porte.py`):

- **Só pessoa jurídica.** A raiz que tem qualquer linha marcada `trata_como_pessoa` (ou sem a marca: na dúvida é
  pessoa, ADR 0075), em qualquer versão e em qualquer cadastro, sai inteira, nos totais, nos ativos e em todos os
  retratos. A tabela de saída carrega `trata_como_pessoa` sempre
  falso, para a porta também recusar uma linha que um dia vier diferente.
- **Cada registro conta uma vez.** De cada registro (`cadastro` + `id_na_fonte`) vale a versão mais nova já
  vista no dia do retrato; o que saiu do arquivo (`consta` falso) não conta. Quem lê a pasta de medicamentos
  guardada por versão (`medicamentos.v1.parquet`) contaria o medicamento em dobro: aqui só entra o que a porta
  serve.
- **Sem olhar o futuro.** Um retrato por dia de arquivo (`disponivel_em`), e cada um conta só o que a base tinha
  visto até aquele dia. A tabela herda a regra de data do cadastro de origem (público a partir do último dia
  do mês do retrato, como as outras fontes de governo): o leitor escolhe o retrato mais novo público no dia
  pedido.
- **"Ativo" muda de nome por tipo** (`ATIVAS`): `S` nos cosméticos e saneantes, `Ativo` nos alimentos e
  medicamentos, `Válido` nos produtos para saúde e no certificado, `SIM` na autorização. Medicamento com
  apresentações de situações diferentes (`Ativo / Inativo`) conta como ativo: o produto continua registrado
  enquanto uma apresentação estiver. Situação vazia ou fora do vocabulário nunca conta como ativa, e o resumo
  diz quantas linhas ficaram sem classificar, para ninguém descobrir isso só no número.
"""

import unicodedata
from datetime import datetime

import pandas as pd

TABELA = "anvisa_por_empresa"
FONTE = "anvisa-produtos"  # a família que a busca cita (licença e revenda vêm de lá)
CADASTRO_DA_TABELA = "anvisa_registros"
RETRATO = "disponivel_em"
SEPARADOR_DAS_SITUACOES = " / "

# o cadastro da fonte -> o tipo que a tabela conta (o CBPF de medicamento é um certificado de boas práticas)
TIPO_DO_CADASTRO = {
    "cosmeticos": "cosmeticos",
    "produtos_saude": "produtos_saude",
    "saneantes": "saneantes",
    "alimentos": "alimentos",
    "medicamentos": "medicamentos",
    "afe": "afe",
    "cbpf": "cbpf",
    "cbpf_medicamento": "cbpf",
}
TIPOS_DE_PRODUTO = (
    "cosmeticos",
    "produtos_saude",
    "saneantes",
    "alimentos",
    "medicamentos",
)
TIPOS = (*TIPOS_DE_PRODUTO, "afe", "cbpf")
PRODUTOS = "produtos"  # a soma dos cinco tipos de produto (não entram a autorização nem o certificado)
# situação (sem acento nem caixa) -> ativa? Os valores de cada tipo, como a fonte os escreve
ATIVAS = {
    "cosmeticos": {"s"},
    "saneantes": {"s"},
    "alimentos": {"ativo"},
    "medicamentos": {"ativo"},
    "produtos_saude": {"valido"},
    "afe": {"sim"},
    "cbpf": {"valido"},
}
NAO_ATIVAS = {
    "cosmeticos": {"n"},
    "saneantes": {"n"},
    "alimentos": {"inativo"},
    "medicamentos": {"inativo"},
    "produtos_saude": {"invalido", "em validacao"},
    "afe": {"nao"},
    "cbpf": {
        "vencido",
        "indeferido",
        "cancelado",
        "publicado deferimento",
        "revalidacao automatica",
    },
}
COLUNAS_DE_ENTRADA = (
    "cadastro",
    "id_na_fonte",
    "cnpj_basico",
    "situacao",
    "consta",
    "trata_como_pessoa",
    "visto_em",
    RETRATO,
)
TAMANHO_DA_RAIZ = 8


def colunas_de_contagem() -> list[str]:
    """As colunas de contagem da tabela, na ordem em que saem (total e ativos de cada tipo e da soma de produtos)."""
    return [
        f"{nome}_{medida}"
        for nome in (*TIPOS_DE_PRODUTO, PRODUTOS, "afe", "cbpf")
        for medida in ("total", "ativos")
    ]


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def situacao_normalizada(situacao: object) -> str:
    """A situação da fonte sem acento, sem caixa e sem espaço sobrando (`Válido` vira `valido`); vazia, texto vazio."""
    if situacao is None or pd.isna(situacao):  # type: ignore[arg-type]
        return ""
    return _sem_acento(str(situacao)).strip().casefold()


def e_ativa(tipo: str, situacao: object) -> bool:
    """O registro está em vigor? Em medicamento com várias situações (`Ativo / Inativo`), basta uma ativa."""
    partes = situacao_normalizada(situacao).split(SEPARADOR_DAS_SITUACOES.casefold())
    return any(parte.strip() in ATIVAS[tipo] for parte in partes)


def _classificada(tipo: str, situacao: object) -> bool:
    """A situação é uma das conhecidas do tipo (ativa ou não)? Vazia e desconhecida não são."""
    partes = situacao_normalizada(situacao).split(SEPARADOR_DAS_SITUACOES.casefold())
    conhecidas = ATIVAS[tipo] | NAO_ATIVAS[tipo]
    return all(parte.strip() in conhecidas for parte in partes)


def _vigentes_no_retrato(registros: pd.DataFrame, retrato: object) -> pd.DataFrame:
    """De cada registro a versão mais nova vista até o `retrato` (nada do que veio depois entra)."""
    ate_la = registros[registros[RETRATO] <= retrato]
    return ate_la.sort_values("visto_em", kind="stable").drop_duplicates(
        ["cadastro", "id_na_fonte"], keep="last"
    )


def _raizes_de_pessoa(versoes: pd.DataFrame) -> set[str]:
    """As raízes com alguma linha de pessoa ou sem a marca (na dúvida é pessoa); olha todas as versões, `consta` ou não.

    Olha a história inteira, não só até o retrato: a raiz que um dia foi vista como pessoa não aparece em retrato
    nenhum (o futuro só pode tirar uma raiz, nunca pôr um número que o passado não tinha).
    """
    marca = versoes["trata_como_pessoa"]
    sem_certeza = marca.isna() | marca.astype(object).ne(False)
    return set(versoes.loc[sem_certeza, "cnpj_basico"])


def _contar(vigentes: pd.DataFrame) -> pd.DataFrame:
    """Total e ativos de cada tipo por raiz, a partir dos registros que constam do arquivo."""
    tipos = vigentes["cadastro"].map(TIPO_DO_CADASTRO)
    ativos = [e_ativa(t, s) for t, s in zip(tipos, vigentes["situacao"], strict=True)]
    linhas = pd.DataFrame(
        {
            "cnpj_basico": vigentes["cnpj_basico"].to_numpy(),
            "tipo": tipos.to_numpy(),
            "ativo": ativos,
        }
    )
    contagem = linhas.groupby(["cnpj_basico", "tipo"]).agg(
        total=("ativo", "size"), ativos=("ativo", "sum")
    )
    largo = contagem.unstack("tipo", fill_value=0)
    saida = pd.DataFrame(index=largo.index)
    for tipo in TIPOS:
        for medida in ("total", "ativos"):
            coluna = (medida, tipo)
            saida[f"{tipo}_{medida}"] = largo.get(coluna, 0)
    for medida in ("total", "ativos"):
        saida[f"{PRODUTOS}_{medida}"] = saida[
            [f"{t}_{medida}" for t in TIPOS_DE_PRODUTO]
        ].sum(axis=1)
    return saida[colunas_de_contagem()].astype("int64").reset_index()


def contar(registros: pd.DataFrame) -> pd.DataFrame:
    """A tabela `anvisa_por_empresa`: uma linha por raiz de CNPJ (só pessoa jurídica) e por retrato.

    `registros` traz as colunas de `COLUNAS_DE_ENTRADA` de `anvisa_registros`, todas as versões. Sai vazio (com as
    colunas certas) se nada sobra. As colunas `disponivel_em` (o dia do retrato), `trata_como_pessoa` (sempre
    falso) e as contagens vêm nesta ordem; `montado_em` e `versao_do_codigo` são do montador.
    """
    faltam = set(COLUNAS_DE_ENTRADA) - set(registros.columns)
    if faltam:
        raise ValueError(f"colunas ausentes em anvisa_registros: {sorted(faltam)}")
    dados = registros[list(COLUNAS_DE_ENTRADA)].copy()
    dados = dados[dados["cadastro"].isin(TIPO_DO_CADASTRO)]
    dados[RETRATO] = pd.to_datetime(dados[RETRATO])
    dados = dados[dados["cnpj_basico"].astype(str).str.len() == TAMANHO_DA_RAIZ]
    pessoas = _raizes_de_pessoa(dados)
    partes = []
    for retrato in sorted(dados[RETRATO].dropna().unique()):
        versoes = _vigentes_no_retrato(dados, retrato)
        vigentes = versoes[
            versoes["consta"].astype(bool) & ~versoes["cnpj_basico"].isin(pessoas)
        ]
        if vigentes.empty:
            continue
        contagem = _contar(vigentes)
        contagem.insert(1, RETRATO, retrato)
        contagem.insert(2, "trata_como_pessoa", False)
        partes.append(contagem)
    if not partes:
        return _vazia()
    return pd.concat(partes, ignore_index=True)


def _vazia() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj_basico": pd.Series(dtype="object"),
            RETRATO: pd.Series(dtype="datetime64[ns]"),
            "trata_como_pessoa": pd.Series(dtype="bool"),
            **{c: pd.Series(dtype="int64") for c in colunas_de_contagem()},
        }
    )


def situacoes_sem_classificar(registros: pd.DataFrame) -> dict[str, int]:
    """Quantas linhas que constam têm situação vazia ou fora do vocabulário, por tipo (para o resumo da montagem)."""
    constam = registros[registros["consta"].astype(bool)]
    fora: dict[str, int] = {}
    for cadastro, situacao in zip(
        constam["cadastro"], constam["situacao"], strict=True
    ):
        tipo = TIPO_DO_CADASTRO.get(cadastro)
        if tipo is not None and not _classificada(tipo, situacao):
            fora[tipo] = fora.get(tipo, 0) + 1
    return fora


def com_carimbo(
    tabela: pd.DataFrame, agora: datetime, versao_do_codigo: str
) -> pd.DataFrame:
    """A tabela com `montado_em` e `versao_do_codigo` (exigência de linhagem da ADR 0055)."""
    return tabela.assign(
        montado_em=pd.Timestamp(agora), versao_do_codigo=versao_do_codigo
    )
