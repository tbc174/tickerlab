"""Agentes do setor elétrico e fiscalização da ANEEL (meta das 300 tabelas pelo CNPJ, lote 2): o cadastro dos
agentes com a atividade de cada um (fonte `aneel-agentes`), os autos de infração e os termos de notificação
(fonte `aneel-fiscalizacao`). A ANEEL publica cada arquivo inteiro a cada vez (um retrato);
`base/retratos.py` junta os retratos numa tabela que só cresce.

- **Formato** (conferido em 13/11/2026 nos arquivos do portal): o mesmo dos indicadores
  (`base/aneel_indicadores.py`): `;`, tudo entre aspas, linha CRLF, datas `AAAA-MM-DD`, vírgula decimal.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): o auto de infração traz CPF ou CNPJ na mesma coluna;
  CPF e CNPJ que não fecha o DV saem e são contados. Ficam de fora o nome do agente (`NomRazaoSocial`,
  `NomAgenteFiscalizado`), a descrição do objeto fiscalizado (`DscObjeto`, `DscObjetoFiscalizado`) e o texto
  das decisões (`DscDecisaoCompleta*`, `DscAto*`, `DscEnquadramentoAI`): texto livre, que pode citar pessoa.
- **Sem olhar o futuro** (`disponivel_no_primeiro` dos indicadores): o primeiro retrato vale desde a data de
  geração do conjunto, nunca depois do dia do retrato; o que aparece ou muda depois vale desde o retrato em
  que apareceu. A data de lavratura do auto é anterior à publicação: não é usada como `disponivel_em`.

Sem Streamlit; pandas só.
"""

from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as comum
from base import cadastros_em_retrato
from base import retratos as motor

FONTE_DOS_AGENTES = "aneel-agentes"
FONTE_DA_FISCALIZACAO = "aneel-fiscalizacao"
TABELA_DOS_AGENTES = "aneel_agentes"
TABELA_DOS_AUTOS = "aneel_autos_de_infracao"
TABELA_DOS_TERMOS = "aneel_termos_de_notificacao"
ARQUIVO_DOS_AGENTES = "/agentes-setor-eletrico.csv"
ARQUIVO_DOS_AUTOS = "/auto-infracao.csv"
ARQUIVO_DOS_TERMOS = "/termo-notificacao.csv"
AGENTE_ATIVO = "A"
AGENTE_INATIVO = "I"


def _data(texto: pd.Series) -> pd.Series:
    """`AAAA-MM-DD` em data; vazio ou fora do calendário vira nulo."""
    return pd.to_datetime(texto, format=comum.FORMATO_DA_DATA, errors="coerce")


def _gerado_em(tabela: pd.DataFrame) -> pd.Series:
    return _data(tabela["DatGeracaoConjuntoDados"])


def _textos(tabela: pd.DataFrame, colunas: dict[str, str]) -> dict[str, pd.Series]:
    """As colunas de texto da fonte com o nosso nome; vazio vira nulo."""
    return {
        nosso: motor.sem_vazio(tabela[da_fonte]) for da_fonte, nosso in colunas.items()
    }


def _datas(tabela: pd.DataFrame, colunas: dict[str, str]) -> dict[str, pd.Series]:
    return {nosso: _data(tabela[da_fonte]) for da_fonte, nosso in colunas.items()}


def _pronta(
    pronta: pd.DataFrame,
    contagem: dict[str, int],
    textos: tuple[str, ...],
    tipos: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, int]]:
    todos = {**dict.fromkeys(textos, "string"), **tipos}
    return comum.sem_repetir(pronta, contagem).astype(todos).reset_index(
        drop=True
    ), contagem


# --- agentes do setor elétrico ----------------------------------------------------------------------
ATIVIDADES = {
    "IdcGeracao": "geracao",
    "IdcTransmissao": "transmissao",
    "IdcDistribuicao": "distribuicao",
    "IdcComercializacao": "comercializacao",
}
COLUNAS_DOS_AGENTES = (
    "id_na_fonte", "cnpj", "cnpj_basico", "sigla_do_agente", "ativo", *ATIVIDADES.values(),
)  # fmt: skip
VALORES_DOS_AGENTES = [c for c in COLUNAS_DOS_AGENTES if c != "id_na_fonte"] + [
    "consta"
]
TEXTOS_DOS_AGENTES = ("id_na_fonte", "cnpj", "cnpj_basico", "sigla_do_agente")


def _ativo(indicador: pd.Series) -> pd.Series:
    """`A` ativo, `I` inativo; outro valor fica nulo (a fonte não documenta outro)."""
    return indicador.map({AGENTE_ATIVO: True, AGENTE_INATIVO: False}).astype("boolean")


def ler_agentes(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os agentes de pessoa jurídica de um retrato e a contagem do que saiu.

    As atividades ficam como o código da fonte (0 não atua, 1 atua; o portal tem um `2` sem documentação
    em 13/11/2026): número inteiro, sem interpretar."""
    tabela, contagem = comum.so_pessoa_juridica(comum.ler_csv(conteudo), "NumCnpj")
    pronta = pd.DataFrame(
        {
            "id_na_fonte": tabela["cnpj14"],
            **comum.com_cnpj(tabela["cnpj14"]),
            "sigla_do_agente": motor.sem_vazio(tabela["SigPessoa"]),
            "ativo": _ativo(tabela["IdcAtivo"]),
            **{
                nosso: pd.to_numeric(tabela[da_fonte], errors="coerce")
                for da_fonte, nosso in ATIVIDADES.items()
            },
            comum.GERADO_EM: _gerado_em(tabela),
        }
    )
    return _pronta(
        pronta, contagem, TEXTOS_DOS_AGENTES, dict.fromkeys(ATIVIDADES.values(), "Int8")
    )


# --- autos de infração ------------------------------------------------------------------------------
TEXTOS_DO_AUTO = {
    "NumAutoInfracao": "numero_do_auto",
    "SigAgenteFiscalizador": "fiscalizador",
    "NomNaturezaFiscalizacao": "natureza_da_fiscalizacao",
    "CodObjetoFiscalizado": "codigo_do_objeto",
    "NumProcessoPunitivo": "processo_punitivo",
    "NumProcessoPunitivoANEEL": "processo_punitivo_na_aneel",
    "DscTipoPenalidade": "tipo_de_penalidade",
    "NumTermoEncerramento": "numero_do_termo_de_encerramento",
    "NumTermoNotificacao": "numero_do_termo_de_notificacao",
    "NumProcessoFiscalizacao": "processo_de_fiscalizacao",
}
DATAS_DO_AUTO = {
    "DatLavraturaAutoInfracao": "lavrado_em",
    "DatRecebimentoAutoInfracao": "recebido_em",
    "DtRecebimentoRecurso": "recurso_recebido_em",
    "DatDecisaoJuizo": "decidido_em_juizo",
    "DatDecisaoDiretoria": "decidido_pela_diretoria_em",
    "DatLavraturaTE": "encerrado_em",
}
VALORES_EM_REAIS_DO_AUTO = {
    "VlrPenalidade": "valor_da_penalidade",
    "VlrMultaAposJuizo": "multa_apos_juizo",
    "VlrMultaAposDiretoria": "multa_apos_diretoria",
}
COLUNAS_DOS_AUTOS = (
    "id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS_DO_AUTO.values(), *DATAS_DO_AUTO.values(),
    *VALORES_EM_REAIS_DO_AUTO.values(),
)  # fmt: skip
VALORES_DOS_AUTOS = [c for c in COLUNAS_DOS_AUTOS if c != "id_na_fonte"] + ["consta"]
DATAS_DOS_AUTOS = tuple(DATAS_DO_AUTO.values())


def ler_autos(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os autos de infração de pessoa jurídica de um retrato e a contagem do que saiu (o CPF sai)."""
    tabela, contagem = comum.so_pessoa_juridica(
        comum.ler_csv(conteudo), "NumCPFCNPJAgenteFiscalizado"
    )
    sem_numero = tabela["NumAutoInfracao"].eq("")
    contagem["sem_numero_do_auto"] = int(sem_numero.sum())
    tabela = tabela[~sem_numero]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": motor.chave(tabela, ["NumAutoInfracao", "cnpj14"]),
            **comum.com_cnpj(tabela["cnpj14"]),
            **_textos(tabela, TEXTOS_DO_AUTO),
            **_datas(tabela, DATAS_DO_AUTO),
            **{
                nosso: comum.numero(tabela[da_fonte])
                for da_fonte, nosso in VALORES_EM_REAIS_DO_AUTO.items()
            },
            comum.GERADO_EM: _gerado_em(tabela),
        }
    )
    textos = ("id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS_DO_AUTO.values())
    return _pronta(
        pronta,
        contagem,
        textos,
        dict.fromkeys(VALORES_EM_REAIS_DO_AUTO.values(), "float64"),
    )


# --- termos de notificação --------------------------------------------------------------------------
TEXTOS_DO_TERMO = {
    "NumTermoNotificacao": "numero_do_termo",
    "SigAgenteFiscalizador": "fiscalizador",
    "NomNaturezaFiscalizacao": "natureza_da_fiscalizacao",
    "SigArea": "area",
    "SigSubArea": "subarea",
    "CodObjeto": "codigo_do_objeto",
    "NumProcesso": "processo",
    "SigDecisao": "decisao",
    "NumDocumentoDecisao": "documento_da_decisao",
}
DATAS_DO_TERMO = {
    "DatLavraturaTN": "lavrado_em",
    "DatAvisoRecebimento": "recebido_em",
    "DatManifestacao": "manifestado_em",
    "DatLavraturaDecisao": "decidido_em",
}
COLUNAS_DOS_TERMOS = (
    "id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS_DO_TERMO.values(), *DATAS_DO_TERMO.values(),
)  # fmt: skip
VALORES_DOS_TERMOS = [c for c in COLUNAS_DOS_TERMOS if c != "id_na_fonte"] + ["consta"]
DATAS_DOS_TERMOS = tuple(DATAS_DO_TERMO.values())
# um termo notifica um agente sobre um ou mais objetos, e cada objeto pode ter mais de uma decisão
CHAVE_DO_TERMO = ["NumTermoNotificacao", "cnpj14", "CodObjeto", "NumDocumentoDecisao"]


def ler_termos(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os termos de notificação de pessoa jurídica de um retrato e a contagem do que saiu."""
    tabela, contagem = comum.so_pessoa_juridica(comum.ler_csv(conteudo), "NumCNPJ")
    sem_numero = tabela["NumTermoNotificacao"].eq("")
    contagem["sem_numero_do_termo"] = int(sem_numero.sum())
    tabela = tabela[~sem_numero]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": motor.chave(tabela, CHAVE_DO_TERMO),
            **comum.com_cnpj(tabela["cnpj14"]),
            **_textos(tabela, TEXTOS_DO_TERMO),
            **_datas(tabela, DATAS_DO_TERMO),
            comum.GERADO_EM: _gerado_em(tabela),
        }
    )
    textos = ("id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS_DO_TERMO.values())
    return _pronta(pronta, contagem, textos, {})


# --- junção e montagem ------------------------------------------------------------------------------
def _cadastro(
    tabela: str, nome: str, fonte: str, arquivo: str, ler: Callable[[bytes], tuple[pd.DataFrame, dict[str, int]]], valores: list[str],
    colunas: tuple[str, ...], datas: tuple[str, ...],
) -> cadastros_em_retrato.Cadastro:  # fmt: skip
    return cadastros_em_retrato.Cadastro(
        tabela=tabela,
        nome=nome,
        fonte=fonte,
        ler=lambda retrato: ler(motor.original(retrato.caminho)),
        juntar=lambda lidos: motor.juntar(lidos, valores, comum.disponivel_no_primeiro),
        colunas=colunas,
        datas=datas,
        url_termina_em=arquivo,
    )


CADASTRO_DOS_AGENTES = _cadastro(
    TABELA_DOS_AGENTES, "agentes", FONTE_DOS_AGENTES, ARQUIVO_DOS_AGENTES, ler_agentes,
    VALORES_DOS_AGENTES, COLUNAS_DOS_AGENTES, (),
)  # fmt: skip
CADASTRO_DOS_AUTOS = _cadastro(
    TABELA_DOS_AUTOS, "autos", FONTE_DA_FISCALIZACAO, ARQUIVO_DOS_AUTOS, ler_autos,
    VALORES_DOS_AUTOS, COLUNAS_DOS_AUTOS, DATAS_DOS_AUTOS,
)  # fmt: skip
CADASTRO_DOS_TERMOS = _cadastro(
    TABELA_DOS_TERMOS, "termos", FONTE_DA_FISCALIZACAO, ARQUIVO_DOS_TERMOS, ler_termos,
    VALORES_DOS_TERMOS, COLUNAS_DOS_TERMOS, DATAS_DOS_TERMOS,
)  # fmt: skip
CADASTROS = (CADASTRO_DOS_AGENTES, CADASTRO_DOS_AUTOS, CADASTRO_DOS_TERMOS)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/aneel_agentes/agentes.parquet`, `<pasta>/aneel_autos_de_infracao/autos.parquet` e
    `<pasta>/aneel_termos_de_notificacao/termos.parquet` (um retrato por baixada, só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
