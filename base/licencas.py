"""Licenças e registros por CNPJ (linha 525 da fila; Ficha Clara, etapa 2b): os cadastros que a coleta
da etapa 2a guarda (`base/arquivo/fontes.py`) em seis tabelas, uma por órgão, com as mesmas colunas:
`anvisa_registros` (AFE, boas práticas e produtos registrados), `antt_rntrc` (transportadores de
carga), `mapa_sipeagro` (produto veterinário e aviação agrícola), `anatel_outorgas`, `anm_titulos`
(Cadastro Mineiro) e `ancine_agentes`. A ficha da empresa lê todas do mesmo jeito.

Lê os arquivos que o arquivista já guardou (não baixa nada); cada um é um **retrato** do cadastro no
dia em que foi baixado, e o motor de `base/retratos.py` os junta numa tabela que só cresce (uma linha
por valor diferente de cada registro; o que some do arquivo ganha `consta=False`).

- **Só pessoa jurídica** com CNPJ de dígito certo, com letras ou não: a coleta já tirou o CPF e o CNPJ
  mascarado, e aqui a conferência se repete. Coluna de nome, endereço, contato ou responsável técnico
  nem chega ao acervo (a coleta guarda só as colunas da lista). Empresário individual e MEI ficam com
  `trata_como_pessoa`, como na PGFN (ADR 0075).
- **Sem olhar o futuro** (`disponivel_em`): o dia do retrato, para toda linha, também no primeiro.
  A fonte publica o estado de hoje (ativo, vencido, cancelado) sem dizer desde quando: dar a uma licença
  cancelada hoje a data em que ela foi concedida poria o cancelamento no passado. As datas da fonte
  (concessão, publicação, vencimento, cancelamento) ficam nas colunas delas, para ler, nunca como
  `disponivel_em`.

Limites conhecidos: o arquivista começou a guardar estes cadastros em 29/10/2026, então nada aqui vale
antes do primeiro retrato; a situação "Sim/Não" do Cadastro Mineiro fica de fora (o sentido não está
no dicionário da ANM); vários registros da mesma chave (as apresentações de um medicamento, a linha
repetida do SIPEAGRO) ficam com o primeiro do arquivo (`id_repetido` no resumo).
"""

import io
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.arquivo.fontes import ARQUIVOS_DO_CADASTRO_MINEIRO
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

# a coleta grava todos os cadastros com ";" (o da ANM vem com "," da fonte) e sem BOM
SEPARADOR = ";"
LATIN1 = "latin-1"
UTF8 = "utf-8"
TAMANHO_DA_DATA = 10  # "24/01/2011 00:00:00": só o dia conta
DIA_MES_ANO = "%d/%m/%Y"
MES_DIA_ANO = "%m/%d/%Y"  # a AFE e o CBPF da Anvisa escrevem as datas à americana
MES_ANO = (
    "%m%Y"  # o vencimento dos alimentos da Anvisa vem como "022009" (o 1º dia do mês)
)
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum retrato novo desde a última montagem

TEXTOS = [
    "registro",
    "processo",
    "categoria",
    "descricao",
    "complemento",
    "situacao",
    "uf",
    "municipio",
]
DATAS = ["concedido_em", "publicado_em", "vence_em", "cancelado_em", "situacao_desde"]
VALORES = ["cnpj", *TEXTOS, *DATAS, "consta"]
COLUNAS = [
    "cadastro",
    "id_na_fonte",
    "cnpj",
    "cnpj_basico",
    *TEXTOS,
    *DATAS,
    "consta",
    "trata_como_pessoa",
    "visto_em",
    "disponivel_em",
]
ORDEM = ["id_na_fonte", "visto_em"]

Colunas = dict[
    str, tuple[str, ...]
]  # nossa coluna -> as da fonte, e vale a 1ª que não vier vazia


@dataclass(frozen=True)
class Cadastro:
    """Um cadastro de licenças: de que fonte vem, para que tabela vai e como ler as colunas."""

    nome: str
    fonte: str
    tabela: str
    cnpj_em: str  # a coluna do documento na fonte
    colunas: Colunas
    chave: tuple[
        str, ...
    ]  # nossas colunas que identificam o registro dentro de um retrato
    formatos: tuple[str, ...] = (DIA_MES_ANO,)
    codificacao: str = LATIN1
    url_termina_em: str | None = None  # a fonte guarda outros arquivos além deste


_AFE: Colunas = {
    "registro": ("NU_AUTORIZACAO",),
    "processo": ("NU_PROCESSO",),
    "categoria": ("TIPO_PRODUTO",),
    "descricao": ("ATIVIDADES", "CO_TIPO_ATIVIDADES"),
    "complemento": ("NU_AUTORIZACAO_NOVO",),
    "situacao": ("ATIVO",),
    "uf": ("UF",),
    "municipio": ("CIDADE",),
    "concedido_em": ("DT_AUTORIZACAO",),
    "publicado_em": ("DT_PUBLICACAO",),
    "cancelado_em": ("DT_CANCELAMENTO",),
}
_CBPF: Colunas = {
    "registro": ("CO_DOCUMENTO_PETICAO",),
    "processo": ("NU_PROCESSO",),
    "categoria": ("NO_TIPO_CERTIFICADO",),
    "descricao": ("ASSUNTO",),
    "complemento": ("NO_PAIS_INSPECIONADA",),  # a fábrica inspecionada pode ser de fora
    "situacao": ("STATUS", "SITUACAO"),
    "publicado_em": ("DT_PUBLICACAO",),
    "vence_em": ("DT_VALIDADE",),
}
# os cinco arquivos de produtos trazem colunas diferentes para a mesma coisa
_PRODUTOS: Colunas = {
    "id": ("CO_SEQ_PRODUTO",),
    "registro": (
        "NU_REGISTRO_PRODUTO",
        "NU_REGISTRO",
        "NU_REGISTRO_NOTIFICACAO_PRODUTO",
    ),
    "processo": ("NU_PROCESSO",),
    "categoria": (
        "DS_TIPO_CATEGORIA_REGULATORIA",
        "DS_CATEGORIA_PRODUTO",
        "TIPO_AUTORIZACAO",
        "TIPO_REGULARIZACAO",
        "SG_RISCO_PRODUTO",
    ),
    "descricao": ("NO_PRODUTO",),
    "situacao": (
        "VALIDADE_SITUACAO",
        "SITUACAO_REGISTRO",
        "ST_PRODUTO_ATIVO",
        "ST_SITUACAO_PRODUTO",
        "TP_SITUACAO_PRODUTO",
    ),
    "concedido_em": ("DT_REGULARIZACAO",),
    "publicado_em": ("DATA_PUBLICACAO", "DT_PUBLICACAO"),
    "vence_em": (
        "DT_VENCIMENTO_PRODUTO",
        "DT_VENCIMENTO",
        "DT_VENCIMENTO_REGISTRO",
    ),
    "cancelado_em": ("DATA_CANCELAMENTO", "DT_CANCELAMENTO"),
}
_RNTRC: Colunas = {
    "registro": ("numero_rntrc",),
    "categoria": ("categoria_transportador",),
    "complemento": ("equiparado",),
    "situacao": ("situacao_rntrc",),
    "uf": ("uf",),
    "municipio": ("municipio",),
    "concedido_em": ("data_primeiro_cadastro",),
    "situacao_desde": ("data_situacao_rntrc",),
}
# a aviação agrícola tem uma linha por aeronave; o produto veterinário, uma por classificação
_SIPEAGRO: Colunas = {
    "registro": ("NUMERO_REGISTRO_ESTABELECIMENTO",),
    "categoria": ("ATIVIDADE",),
    "descricao": ("CLASSIFICACAO",),
    "complemento": ("CARACTERISTICA_ADICIONAL", "NUMERO_REGISTRO_AERONAVE"),
    "situacao": ("STATUS_DO_REGISTRO", "STATUS_REGISTRO_ESTABELECIMENTO"),
    "uf": ("UNIDADE_DA_FEDERACAO",),
    "municipio": ("MUNICIPIO",),
}
# uma linha por serviço notificado dentro de cada outorga
_ANATEL: Colunas = {
    "registro": ("Fistel da Outorga",),
    "processo": ("Processo SEI da Outorga",),
    "categoria": ("Tipo de Outorga",),
    "descricao": ("Código e Nome do Serviço da Notificação",),
    "complemento": ("Fistel da Notificação",),
    "situacao": ("Tipo de Entidade",),
    "uf": ("UF do Endereço Sede",),
    "municipio": ("Nome do Munícipio do Endereço Sede",),
    "concedido_em": ("Data Inclusão da Outorga",),
}
_ANM: Colunas = {
    "processo": ("Processo",),
    "categoria": ("Tipo de requerimento",),
    "descricao": ("Substância(s)",),
    "complemento": ("Tipo(s) de Uso",),
    "situacao": ("Fase Atual",),
    "municipio": ("Municipio(s)",),
}
_ANCINE: Colunas = {
    "registro": ("REGISTRO_ANCINE",),
    "categoria": ("CLASSIFICACAO_AGENTE_ECONOMICO",),
    "descricao": ("NATUREZA_JURIDICA",),
    "complemento": ("BRASILEIRO_INDEPENDENTE",),
    "uf": ("UF",),
    "municipio": ("MUNICIPIO",),
    "concedido_em": ("DATA_REGISTRO",),
}


def _produto(nome: str, arquivo: str, chave: tuple[str, ...]) -> Cadastro:
    return Cadastro(
        nome,
        "anvisa-produtos",
        "anvisa_registros",
        "NU_CNPJ_EMPRESA",
        _PRODUTOS,
        chave,
        formatos=(DIA_MES_ANO, MES_ANO),
        url_termina_em=f"/TA_CONSULTA_{arquivo}.CSV",
    )


CADASTROS: dict[str, Cadastro] = {
    c.nome: c
    for c in (
        Cadastro(
            "afe",
            "anvisa-empresas",
            "anvisa_registros",
            "NU_CNPJ",
            _AFE,
            ("registro", "processo"),
            formatos=(MES_DIA_ANO,),
            url_termina_em="/TA_CONSULTA_FUNCIONAMENTO_EMPRESA_NACIONAL.CSV",
        ),
        *(
            Cadastro(
                nome,
                "anvisa-empresas",
                "anvisa_registros",
                "NU_CNPJ_SOLICITANTE",
                _CBPF,
                ("registro",),
                formatos=(MES_DIA_ANO,),
                url_termina_em=f"/{arquivo}.CSV",
            )
            for nome, arquivo in (
                ("cbpf", "TA_CONSULTA_CBPF"),
                ("cbpf_medicamento", "TA_CONSULTA_CBPF_MEDICAMENTO"),
            )
        ),
        _produto("medicamentos", "MEDICAMENTOS", ("id",)),
        # saneantes e cosméticos não têm o código do produto: o processo e o nome
        _produto("saneantes", "SANEANTES", ("processo", "descricao")),
        _produto("cosmeticos", "COSMETICOS", ("processo", "descricao")),
        _produto("produtos_saude", "PRODUTOS_SAUDE", ("id",)),
        _produto("alimentos", "ALIMENTOS", ("id",)),
        # um endereço novo por mês, e cada um é o cadastro inteiro: todos são retratos
        Cadastro(
            "rntrc",
            "antt-rntrc",
            "antt_rntrc",
            "cpfcnpjtransportador",
            _RNTRC,
            ("registro",),
        ),
        Cadastro(
            "produto_veterinario",
            "mapa-sipeagro",
            "mapa_sipeagro",
            "CNPJ",
            _SIPEAGRO,
            ("registro", "categoria", "descricao", "complemento"),
            formatos=(),
            codificacao=UTF8,
            url_termina_em="/sipeagroprodutoveterinario.csv",
        ),
        Cadastro(
            "aviacao_agricola",
            "mapa-sipeagro",
            "mapa_sipeagro",
            "CPF_CNPJ",
            _SIPEAGRO,
            ("registro", "categoria", "descricao", "complemento"),
            formatos=(),
            codificacao=UTF8,
            url_termina_em="/sipeagroaviacaoagricolaregistro.csv",
        ),
        Cadastro(
            "outorgas",
            "anatel-outorgas",
            "anatel_outorgas",
            "CNPJ ou CPF",
            _ANATEL,
            ("registro", "complemento"),
            codificacao=UTF8,
        ),
        *(
            Cadastro(
                arquivo.lower(),
                "anm-cadastro-mineiro",
                "anm_titulos",
                "CPF/CNPJ do titular",
                _ANM,
                ("processo", "categoria"),
                formatos=(),
                url_termina_em=f"/{arquivo}.csv",
            )
            for arquivo in ARQUIVOS_DO_CADASTRO_MINEIRO
        ),
        Cadastro(
            "agentes",
            "ancine-agentes",
            "ancine_agentes",
            "CNPJ",
            _ANCINE,
            ("registro",),
            codificacao=UTF8,
        ),
    )
}
TABELAS = tuple(dict.fromkeys(c.tabela for c in CADASTROS.values()))


def _ler_csv(caminho: Path, cadastro: Cadastro) -> pd.DataFrame:
    """Só as colunas do cadastro, como texto, com o nome da fonte sem acento (`motor.nome_da_coluna`)."""
    lidas = {
        motor.nome_da_coluna(c)
        for c in (
            cadastro.cnpj_em,
            *(f for fs in cadastro.colunas.values() for f in fs),
        )
    }
    tabela = pd.read_csv(
        io.BytesIO(motor.original(caminho)),
        sep=SEPARADOR,
        encoding=cadastro.codificacao,
        dtype=str,
        keep_default_na=False,
        usecols=lambda coluna: motor.nome_da_coluna(coluna) in lidas,
    )  # type: ignore[call-overload]
    tabela = tabela.rename(columns=motor.nome_da_coluna)
    return tabela.apply(lambda serie: serie.str.strip())


def _primeira_cheia(bruta: pd.DataFrame, fontes: tuple[str, ...]) -> pd.Series:
    """O valor da primeira coluna da fonte que não vier vazia (coluna que a fonte não manda conta
    como vazia)."""
    valor = pd.Series("", index=bruta.index, dtype=object)
    for coluna in map(motor.nome_da_coluna, fontes):
        if coluna in bruta:
            valor = valor.where(valor.ne(""), bruta[coluna])
    return valor


def _datas(texto: pd.Series, formatos: tuple[str, ...]) -> pd.Series:
    """O texto da fonte em data, no primeiro formato que servir; o que não servir em nenhum fica nulo."""
    curto = texto.str[:TAMANHO_DA_DATA]
    datas = pd.Series(pd.NaT, index=texto.index, dtype="datetime64[ns]")
    for formato in formatos:
        datas = datas.fillna(pd.to_datetime(curto, format=formato, errors="coerce"))
    return datas


def ler_retrato(
    caminho: Path, cadastro: Cadastro
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os registros de CNPJ inteiro de um arquivo e a contagem do que ficou de fora."""
    bruta = _ler_csv(caminho, cadastro)
    cnpj = bruta[motor.nome_da_coluna(cadastro.cnpj_em)].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    nossas = pd.DataFrame(
        {c: _primeira_cheia(bruta, fs) for c, fs in cadastro.colunas.items()},
        index=bruta.index,
    )
    linhas = len(bruta)
    del (
        bruta
    )  # o documento que não é CNPJ (um CPF que escapou da coleta) não passa daqui
    tabela = nossas[valido].assign(cnpj=cnpj[valido])
    tabela["id_na_fonte"] = motor.chave(tabela, cadastro.chave)
    repetido = tabela["id_na_fonte"].duplicated(keep="first")
    tabela = tabela[~repetido]
    padrao = tabela.reindex(columns=[*TEXTOS, *DATAS], fill_value="")
    pronta = pd.DataFrame(
        {
            "cadastro": cadastro.nome,
            "id_na_fonte": tabela["id_na_fonte"],
            "cnpj": tabela["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": tabela["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: motor.sem_vazio(padrao[c].fillna("")) for c in TEXTOS},
            **{c: _datas(padrao[c].fillna(""), cadastro.formatos) for c in DATAS},
        }
    ).reset_index(drop=True)
    contagem = {
        "linhas": linhas,
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do retrato: a fonte não diz desde quando vale o estado que publica."""
    return pd.Series(dia, index=novos.index)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, _disponivel_no_primeiro)


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _destino(pasta: Path, cadastro: Cadastro) -> Path:
    return pasta / cadastro.tabela / cadastro.nome


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
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
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*COLUNAS, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def _lidos(
    achados: list[motor.Retrato], cadastro: Cadastro, resumo: dict[str, int]
) -> Iterator[tuple[motor.Retrato, pd.DataFrame]]:
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
    """`<pasta>/<tabela>/<cadastro>.parquet` para cada cadastro com arquivo guardado.

    Cadastro sem arquivo guardado fica de fora do resumo; sem retrato novo desde a última montagem, é
    pulado (`refazer` relê mesmo assim, para código novo). `pessoas`: as raízes de pessoa já sabidas;
    sem elas, pergunta à Receita guardada (`base/pgfn.py`).
    """
    resumo: dict[str, dict[str, int]] = {}
    for cadastro in CADASTROS.values():
        achados = motor.retratos(conexao, cadastro.fonte, cadastro.url_termina_em)
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
