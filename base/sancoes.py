"""Sanções por CNPJ (linha 525 da fila; o "PR 4" do plano dos sinais de risco): os cadastros da CGU
(CEIS, CNEP, CEPIM e leniência) na tabela `sancoes_cgu` e as penalidades aplicadas às operadoras de
plano de saúde na `ans_penalidades`. Uma tabela por família de licença (`src/banco/coletas.py`), com as
mesmas colunas: a ficha da empresa lê as duas do mesmo jeito.

Lê os arquivos que o arquivista já guardou (não baixa nada). Cada arquivo guardado é um **retrato** do
cadastro no dia em que foi baixado: a CGU publica um por dia, a ANS reescreve o mesmo CSV todo mês.

- **Só pessoa jurídica** com CNPJ de dígito certo: a linha de pessoa física (tipo "F", ou documento que
  não é um CNPJ de 14 caracteres) sai antes de qualquer conta, e coluna de nome nenhuma é lida (nem a
  do sancionado, nem a razão social, nem as observações). Empresário individual e MEI ficam com
  `trata_como_pessoa`, como na PGFN (ADR 0075).
- **Uma linha por valor diferente** de cada sanção (`id_na_fonte`), como `base/setoriais/revisoes.py`:
  o valor que muda num retrato seguinte (fim prorrogado, situação da ANS) vira linha nova, e a sanção
  que some do arquivo ganha uma linha `consta=False` no dia em que sumiu (e outra `True` se voltar).
  `revisoes.como_era_em` devolve o estado num dia. A tabela só cresce: o passado não é regravado.
- **Sem olhar o futuro** (`disponivel_em`): no primeiro retrato guardado, a data de publicação ou a
  data em que o órgão informou a CGU, a que for depois (nunca o início da sanção, que pode ser anterior à
  publicação), e nunca depois do dia do retrato; sem data, o dia do retrato. O que aparece ou muda num
  retrato seguinte vale desde o dia dele.

Limites conhecidos: o arquivista começou em 14/10/2026, então o valor de uma sanção antiga é o do
primeiro retrato, com a data da publicação (se o órgão mudou o fim antes disso, não se sabe); retrato com
menos da metade das sanções do anterior é tratado como arquivo cortado e pulado; a cada retrato novo os
retratos são todos relidos (a CGU tem ~35 MB por dia: a leitura incremental é uma linha da fila se o
tempo crescer). Os efeitos dos acordos de leniência (outro CSV do mesmo ZIP) e as multas do BCB
(`SGM/ObterMultas`, só agregadas por ano, sem CNPJ) ficam de fora.
"""

import gzip
import io
import re
import unicodedata
import zipfile
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src import acervo
from src.banco.coletas import originais_mais_recentes, versoes_guardadas
from src.versao_do_codigo import versao_do_codigo

CODIFICACAO = "latin-1"
SEPARADOR = ";"
FORMATO_DA_DATA = "%d/%m/%Y"
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum retrato novo desde a última montagem
FRACAO_MINIMA = (
    0.5  # retrato com menos que isto das sanções do anterior é arquivo cortado
)
TIPO_PESSOA_JURIDICA = "J"
SEPARADOR_DA_CHAVE = "|"
FORA_DO_NOME = re.compile(r"[^A-Z0-9]")

TEXTOS = [
    "categoria",
    "situacao",
    "assunto",
    "orgao",
    "uf_do_orgao",
    "esfera_do_orgao",
    "origem_da_informacao",
    "fundamentacao_legal",
    "abrangencia",
    "processo",
]
DATAS = ["inicio", "fim", "publicado_em", "transito_em_julgado", "informado_em"]
VALORES = ["cnpj", *TEXTOS, *DATAS, "valor_multa", "consta"]
COLUNAS = [
    "cadastro",
    "id_na_fonte",
    "cnpj",
    "cnpj_basico",
    *TEXTOS,
    *DATAS,
    "valor_multa",
    "consta",
    "trata_como_pessoa",
    "visto_em",
    "disponivel_em",
]
ORDEM = ["id_na_fonte", "visto_em"]
# o que cada linha ganha do retrato onde foi vista (não conta para saber se o valor mudou)
_CARIMBOS = ["disponivel_em", "visto_em", "origem_sha256", "origem_coletada_em"]

# colunas da CGU no CEIS e no CNEP (nome sem acento, só letras e números -> coluna da tabela)
_CGU = {
    "CODIGODASANCAO": "id",
    "TIPODEPESSOA": "tipo_de_pessoa",
    "CPFOUCNPJDOSANCIONADO": "cnpj",
    "CATEGORIADASANCAO": "categoria",
    "NUMERODOPROCESSO": "processo",
    "DATAINICIOSANCAO": "inicio",
    "DATAFINALSANCAO": "fim",
    "DATAPUBLICACAO": "publicado_em",
    "DATADOTRANSITOEMJULGADO": "transito_em_julgado",
    "ABRAGENCIADASANCAO": "abrangencia",  # assim mesmo, com a letra trocada, no arquivo da CGU
    "ORGAOSANCIONADOR": "orgao",
    "UFORGAOSANCIONADOR": "uf_do_orgao",
    "ESFERAORGAOSANCIONADOR": "esfera_do_orgao",
    "FUNDAMENTACAOLEGAL": "fundamentacao_legal",
    "DATAORIGEMINFORMACAO": "informado_em",
    "ORIGEMINFORMACOES": "origem_da_informacao",
}


@dataclass(frozen=True)
class Cadastro:
    """Um cadastro de sanções: de que fonte vem, para que tabela vai e como ler as colunas."""

    nome: str
    fonte: str
    tabela: str
    colunas: dict[
        str, str
    ]  # nome da coluna na fonte (sem acento, só letras e números) -> nossa
    chave: tuple[str, ...] = (
        "id",
    )  # colunas que identificam a sanção dentro de um retrato
    membro: str | None = (
        None  # trecho do nome do CSV dentro do ZIP (None: o primeiro CSV)
    )
    url_termina_em: str | None = None  # a fonte guarda outros arquivos além deste
    fixas: dict[str, str] = field(default_factory=dict)


CADASTROS: dict[str, Cadastro] = {
    c.nome: c
    for c in (
        Cadastro("ceis", "cgu-ceis", "sancoes_cgu", _CGU),
        Cadastro(
            "cnep", "cgu-cnep", "sancoes_cgu", {**_CGU, "VALORDAMULTA": "valor_multa"}
        ),
        Cadastro(
            "cepim",
            "cgu-cepim",
            "sancoes_cgu",
            {
                "CNPJENTIDADE": "cnpj",
                "NUMEROCONVENIO": "processo",
                "ORGAOCONCEDENTE": "orgao",
                "MOTIVODOIMPEDIMENTO": "categoria",
            },
            chave=(
                "cnpj",
                "processo",
            ),  # o CEPIM não tem código: a entidade e o convênio
        ),
        Cadastro(
            "leniencia",
            "cgu-leniencia",
            "sancoes_cgu",
            {
                "IDDOACORDO": "id",
                "CNPJDOSANCIONADO": "cnpj",
                "DATADEINICIODOACORDO": "inicio",
                "DATADEFIMDOACORDO": "fim",
                "SITUACAODOACORDODELENIENICA": "situacao",
                "DATADAINFORMACAO": "informado_em",
                "NUMERODOPROCESSO": "processo",
                "ORGAOSANCIONADOR": "orgao",
            },
            membro="acordos",
            fixas={"categoria": "Acordo de leniência"},
        ),
        Cadastro(
            "penalidades",
            "ans-qualidade",
            "ans_penalidades",
            {
                "NRDEMANDA": "id",
                "NRPROCESSO": "processo",
                "TIPOPROCESSO": "assunto",
                "CNPJ": "cnpj",
                "STATUSDEMANDA": "situacao",
                "DTDECISAO1A": "inicio",
                "DTPUBLICACAO1A": "publicado_em",
                "VLMULTAFINALAPLICADA": "valor_multa",
                "TIPOPENALIDADE": "categoria",
            },
            url_termina_em="/penalidades_aplicadas_a_operadoras.csv",
            fixas={"orgao": "ANS"},
        ),
    )
}
TABELAS = tuple(dict.fromkeys(c.tabela for c in CADASTROS.values()))


@dataclass(frozen=True)
class Retrato:
    """Um arquivo guardado do cadastro: o conteúdo de um endereço baixado pela primeira vez num dia."""

    url: str
    sha256: str
    caminho: Path
    baixado_em: datetime

    @property
    def dia(self) -> date:
        return pd.Timestamp(self.baixado_em).date()


def nome_da_coluna(coluna: str) -> str:
    """O nome da coluna sem acento, maiúsculo, só letras e números (a CGU troca travessão e espaço)."""
    sem_acento = (
        unicodedata.normalize("NFKD", coluna).encode("ascii", "ignore").decode()
    )
    return FORA_DO_NOME.sub("", sem_acento.upper())


def _csv_do_zip(arquivo: zipfile.ZipFile, membro: str | None) -> str:
    csvs = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
    if membro is not None:
        csvs = [n for n in csvs if membro in n.lower()]
    if not csvs:
        raise ValueError(f"nenhum CSV com {membro!r} no ZIP")
    return csvs[0]


def _original(caminho: Path) -> bytes:
    """O arquivo como veio da fonte: o acervo guarda em `.gz` o que não vem comprimido (o endereço da
    CGU não termina em `.zip`, então o ZIP dela fica dentro de um `.bin.gz`). Os maiores têm dezenas
    de MB: cabem na memória."""
    guardado = caminho.read_bytes()
    return gzip.decompress(guardado) if caminho.name.endswith(".gz") else guardado


def _ler_csv(caminho: Path, cadastro: Cadastro) -> pd.DataFrame:
    """Só as colunas do cadastro, como texto: as de nome nem chegam à memória."""

    def lida(coluna: str) -> bool:
        return nome_da_coluna(coluna) in cadastro.colunas

    opcoes = {
        "sep": SEPARADOR,
        "encoding": CODIFICACAO,
        "dtype": str,
        "keep_default_na": False,
        "usecols": lida,
    }
    conteudo = io.BytesIO(_original(caminho))
    if zipfile.is_zipfile(conteudo):
        with (
            zipfile.ZipFile(conteudo) as arquivo,
            arquivo.open(_csv_do_zip(arquivo, cadastro.membro)) as csv,
        ):
            tabela = pd.read_csv(csv, **opcoes)  # type: ignore[call-overload]
    else:
        conteudo.seek(0)  # o `is_zipfile` deixa o arquivo lido até o fim
        tabela = pd.read_csv(conteudo, **opcoes)  # type: ignore[call-overload]
    tabela = tabela.rename(columns=lambda c: cadastro.colunas[nome_da_coluna(c)])
    for coluna in set(cadastro.colunas.values()) - set(tabela.columns):
        tabela[coluna] = ""  # coluna que a fonte deixou de mandar fica vazia
    return tabela.apply(lambda serie: serie.str.strip())


def _valor(texto: pd.Series) -> pd.Series:
    """'7986,15' (CGU) e '47520' ou '47520.5' (ANS) em número."""
    com_virgula = texto.str.contains(",", regex=False)
    decimal = texto.where(
        ~com_virgula, texto.str.replace(".", "", regex=False).str.replace(",", ".")
    )
    return pd.to_numeric(_sem_vazio(decimal), errors="coerce").astype("float64")


def _sem_vazio(texto: pd.Series) -> pd.Series:
    """O texto vazio da fonte vira nulo (o `replace("", None)` do pandas preenche com o de cima)."""
    return texto.where(texto.ne(""), None)


def _chave(tabela: pd.DataFrame, colunas: tuple[str, ...]) -> pd.Series:
    primeira, *outras = colunas
    if not outras:
        return tabela[primeira].astype(str)
    return tabela[primeira].str.cat([tabela[c] for c in outras], sep=SEPARADOR_DA_CHAVE)


def _datas(texto: pd.Series) -> pd.Series:
    return pd.to_datetime(texto, format=FORMATO_DA_DATA, errors="coerce")


def ler_retrato(
    caminho: Path, cadastro: Cadastro
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As sanções de pessoa jurídica de um arquivo e a contagem do que ficou de fora."""
    bruta = _ler_csv(caminho, cadastro)
    fisica = pd.Series(False, index=bruta.index)
    if "tipo_de_pessoa" in bruta:
        fisica = bruta["tipo_de_pessoa"].str.upper() != TIPO_PESSOA_JURIDICA
    cnpj = bruta["cnpj"].map(cnpjs.completo)
    fisica |= cnpj.isna() & bruta["cnpj"].str.replace(
        r"\D", "", regex=True
    ).str.len().eq(cnpjs.TAMANHO_DO_CPF)
    juridica = bruta.loc[~fisica].assign(cnpj=cnpj[~fisica])
    del bruta  # o CPF da pessoa física não passa daqui
    valido = juridica["cnpj"].map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c))
    tabela = juridica[valido.astype(bool)].copy()
    for coluna, valor in cadastro.fixas.items():
        tabela[coluna] = valor
    tabela["id_na_fonte"] = _chave(tabela, cadastro.chave)
    repetido = tabela["id_na_fonte"].duplicated(keep="first")
    tabela = tabela[~repetido]
    padrao = tabela.reindex(columns=[*TEXTOS, *DATAS, "valor_multa"], fill_value="")
    pronta = pd.DataFrame(
        {
            "cadastro": cadastro.nome,
            "id_na_fonte": tabela["id_na_fonte"],
            "cnpj": tabela["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": tabela["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: _sem_vazio(padrao[c].fillna("")) for c in TEXTOS},
            **{c: _datas(padrao[c].fillna("")) for c in DATAS},
            "valor_multa": _valor(padrao["valor_multa"].fillna("")),
        }
    ).reset_index(drop=True)
    contagem = {
        "linhas": len(fisica),
        "pessoa_fisica": int(fisica.sum()),
        "cnpj_invalido": int((~valido.astype(bool)).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def retratos(conexao: sa.Connection, cadastro: Cadastro) -> list[Retrato]:
    """Os arquivos do cadastro guardados no acervo, do mais antigo ao mais novo."""
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        return []
    achados = [
        Retrato(original.url, versao.sha256, pasta / versao.caminho, versao.baixado_em)
        for original in originais_mais_recentes(conexao, cadastro.fonte)
        if not cadastro.url_termina_em or original.url.endswith(cadastro.url_termina_em)
        for versao in versoes_guardadas(conexao, original.url)
        if (pasta / versao.caminho).is_file()
    ]
    return sorted(achados, key=lambda r: (pd.Timestamp(r.baixado_em), r.url))


def _assinatura(tabela: pd.DataFrame) -> pd.Series:
    return pd.util.hash_pandas_object(tabela[VALORES], index=False)


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """Publicação ou informação ao órgão (a que for depois), nunca depois do retrato; sem data, ele."""
    datas = novos[["publicado_em", "informado_em"]].max(axis=1)
    return datas.where(datas <= dia, dia).fillna(dia)


def _novos(atual: pd.DataFrame, ultimo: pd.DataFrame) -> pd.DataFrame:
    """O que mudou desde o último valor de cada sanção, com as que saíram como `consta=False`."""
    presentes = ultimo[ultimo["consta"]]
    saidas = presentes[~presentes["id_na_fonte"].isin(atual["id_na_fonte"])].assign(
        consta=False
    )
    candidatos = pd.concat([atual, saidas[atual.columns]], ignore_index=True)
    # compara os números de 64 bits como vieram: um `map` com sanção nova os passaria a decimal
    anterior = pd.Series(_assinatura(ultimo).to_numpy(), index=ultimo["id_na_fonte"])
    assinaturas = _assinatura(candidatos).to_numpy()
    conhecida = candidatos["id_na_fonte"].isin(anterior.index).to_numpy()
    mudou = ~conhecida
    posicoes = np.flatnonzero(conhecida)
    mudou[posicoes] = (
        anterior.loc[candidatos["id_na_fonte"].iloc[posicoes]].to_numpy()
        != assinaturas[posicoes]
    )
    return candidatos[mudou]


def juntar_retratos(
    lidos: list[tuple[Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados.

    O primeiro retrato nunca é pulado: é ele que dá a régua dos seguintes."""
    if not lidos:
        raise ValueError("nenhum retrato para juntar")
    eventos: list[pd.DataFrame] = []
    ultimo: pd.DataFrame | None = None
    pulados = 0
    for retrato, tabela in lidos:
        dia = pd.Timestamp(retrato.dia)
        atual = tabela.assign(consta=True)
        if ultimo is None:
            novos = atual.assign(disponivel_em=_disponivel_no_primeiro(atual, dia))
        else:
            if len(atual) < FRACAO_MINIMA * int(ultimo["consta"].sum()):
                pulados += 1
                continue
            novos = _novos(atual, ultimo.drop(columns=_CARIMBOS)).assign(
                disponivel_em=dia
            )
        novos = novos.assign(
            visto_em=dia,
            origem_sha256=retrato.sha256,
            origem_coletada_em=pd.Timestamp(retrato.baixado_em).isoformat(),
        )
        eventos.append(novos)
        ultimo = (
            novos
            if ultimo is None
            else pd.concat([ultimo, novos], ignore_index=True).drop_duplicates(
                "id_na_fonte", keep="last"
            )
        )
    return pd.concat(eventos, ignore_index=True), pulados


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _destino(pasta: Path, cadastro: Cadastro) -> Path:
    return pasta / cadastro.tabela / cadastro.nome


def _origens(achados: list[Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _para_gravar(
    tabela: pd.DataFrame, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in [*DATAS, "visto_em", "disponivel_em"]
            },
            consta=tabela["consta"].astype(bool),
            valor_multa=tabela["valor_multa"].astype("float64"),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*COLUNAS, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def _lidos(
    achados: list[Retrato], cadastro: Cadastro, resumo: dict[str, int]
) -> Iterator[tuple[Retrato, pd.DataFrame]]:
    for retrato in achados:
        tabela, contagem = ler_retrato(retrato.caminho, cadastro)
        for chave, valor in contagem.items():
            resumo[chave] = resumo.get(chave, 0) + valor
        yield retrato, tabela


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/sancoes_cgu/<cadastro>.parquet` e `<pasta>/ans_penalidades/penalidades.parquet`.

    Cadastro sem arquivo guardado fica de fora do resumo; sem retrato novo desde a última montagem, é
    pulado (`refazer` relê mesmo assim, para código novo). `pessoas`: as raízes de pessoa já sabidas;
    sem elas, pergunta à Receita guardada (`base/pgfn.py`).
    """
    resumo: dict[str, dict[str, int]] = {}
    for cadastro in CADASTROS.values():
        achados = retratos(conexao, cadastro)
        if not achados:
            continue
        destino = _destino(pasta, cadastro)
        if not refazer and origens_gravadas(destino) == _origens(achados):
            resumo[cadastro.nome] = JA_MONTADO
            continue
        contagem: dict[str, int] = {}
        tabela, pulados = juntar_retratos(list(_lidos(achados, cadastro, contagem)))
        if pessoas is None:
            raizes = cnpjs.ordenados(
                cnpjs.raizes_em_numeros(
                    tabela["cnpj_basico"].drop_duplicates().astype(str)
                )
            )
            de_pessoa = pessoas_pela_receita(conexao, raizes)
        else:
            de_pessoa = _como_numeros(pessoas)
        gravar_se_mudou(
            _para_gravar(tabela, de_pessoa, agora),
            destino,
            _origens(achados),
            ORDEM,
            carimbos=LINHAGEM,
        )
        resumo[cadastro.nome] = {
            **contagem,
            "retratos": len(achados),
            "retratos_pulados": pulados,
            "na_tabela": len(tabela),
        }
    return resumo
