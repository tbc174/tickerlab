"""Contratos, sanções e cadastro de fornecedores dos estados por CNPJ (linha 1075, lote 1 dos estados).

Um molde só para as tabelas estaduais que o arquivista guarda como CSV inteiro (`base/arquivo/
lote_contratos_estaduais.py`): cada `Tabela` diz de que fonte lê, como chama cada coluna, o que identifica a
linha e quais colunas são data e valor em reais. Lê o que já está no acervo, sem baixar nada.

| Tabela | Fonte | O que é |
|---|---|---|
| `rj_contratos` | SIGA do RJ (SEPLAG) | Contratos do governo do RJ com o fornecedor: valores contratado, empenhado, liquidado e pago |
| `rj_sancoes_fornecedores` | SIGA do RJ (SEPLAG) | Penalidades que os órgãos do RJ aplicaram ao fornecedor: motivo, órgão e situação |
| `rj_fornecedores` | SIGA do RJ (SEPLAG) | Cadastro de fornecedores do estado: porte (ME/EPP), situação, tipo empresarial, cidade |

- **Uma série por arquivo:** os retratos do mesmo arquivo (o mesmo nome no fim do endereço) formam uma série
  (o motor de `base/retratos.py`). Linha nova, ou com qualquer valor diferente, vira versão nova desde o dia em
  que foi vista; o que some do arquivo ganha `consta` falso. Retrato com menos da metade das linhas do anterior
  é arquivo cortado e é pulado.
- **Só pessoa jurídica (ADR 0075 e 0088):** a coleta já tirou o nome, o texto livre e as linhas com CPF; aqui o
  CNPJ se confere de novo (dígito certo) e o que não fecha sai e é contado. Empresário individual e MEI ficam
  com `trata_como_pessoa` pela Receita guardada, e a porta os esconde.
- **Sem olhar o futuro** (`disponivel_em`): o dia do arquivo em que a linha (ou a mudança) apareceu. As datas da
  fonte (assinatura, publicação no Diário Oficial, efetivação da sanção) contam quando aconteceu, nunca quando a
  base soube: os valores pagos de hoje não existiam no dia da publicação do contrato.

Limites conhecidos: só os órgãos que usam o SIGA (o RJ não publica por aqui as empresas estatais que compram
por sistema próprio); a fonte não diz quando cada linha entrou no arquivo.
"""

import gzip
import re
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM
from src.versao_do_codigo import versao_do_codigo

SEPARADOR = ";"  # a coleta grava todo CSV com ";"
UTF8 = "utf-8"
LINHAS_POR_PEDACO = 200_000
ORDEM = ["id_na_fonte", "visto_em"]
CARIMBOS_DA_LINHA = ["consta", "trata_como_pessoa", "visto_em", "disponivel_em"]
FORMATO_DA_DATA_BR = "%d/%m/%Y"
TAMANHO_DA_DATA = 10  # só o dia: a hora, quando vem, é sempre meia-noite


@dataclass(frozen=True)
class Tabela:
    """Uma tabela estadual: de onde lê, como chama cada coluna e o que identifica a linha."""

    fonte: str  # id no registro de coletas
    tabela: str
    como_chamar: Mapping[
        str, str
    ]  # nosso nome → nome da coluna no arquivo guardado (em minúsculas)
    chave: tuple[str, ...]
    datas: tuple[str, ...] = ()
    reais: tuple[str, ...] = ()
    formato_da_data: str = FORMATO_DA_DATA_BR

    @property
    def textos(self) -> list[str]:
        return [
            c for c in self.como_chamar if c not in (*self.datas, *self.reais, "cnpj")
        ]

    @property
    def colunas(self) -> list[str]:
        """As colunas da tabela gravada, na ordem do dicionário."""
        return [
            "id_na_fonte",
            "arquivo",
            "cnpj",
            "cnpj_basico",
            *self.textos,
            *self.datas,
            *self.reais,
            *CARIMBOS_DA_LINHA,
        ]

    @property
    def valores(self) -> list[str]:
        """O que, mudando, faz da linha uma versão nova: tudo menos a chave e o CNPJ (que vêm nela)."""
        return [*self.textos, *self.datas, *self.reais, "consta"]


RJ_CONTRATOS = Tabela(
    fonte="govrj-contratos",
    tabela="rj_contratos",
    como_chamar={
        "cnpj": "cpf/cnpj",
        "codigo_contrato": "código do contrato",
        "id_processo": "id processo",
        "contratacao": "contratação",
        "situacao": "status contratação",
        "unidade": "unidade",
        "codigo_ug": "codug",
        "tipo_de_aquisicao": "tipo de aquisição",
        "criterio_de_julgamento": "critério de julgamento",
        "regime_juridico": "regimejuridico",
        "emergencial": "emergencial",
        "contratado_em": "data contratação",
        "assinado_em": "data_assinatura",
        "publicado_em": "data public deorj",
        "vigencia_inicio": "data início vigência",
        "vigencia_fim": "data fim vigência",
        "valor_contratado": "valor total contrato/valor estimado para contratação (r$)",
        "valor_empenhado": "valor total empenhado (r$)",
        "valor_liquidado": "valor total liquidado (r$)",
        "valor_pago": "valor total pago (r$)",
    },
    chave=("codigo_contrato", "cnpj"),
    datas=(
        "contratado_em",
        "assinado_em",
        "publicado_em",
        "vigencia_inicio",
        "vigencia_fim",
    ),
    reais=("valor_contratado", "valor_empenhado", "valor_liquidado", "valor_pago"),
)
RJ_SANCOES = Tabela(
    fonte="govrj-sancoes",
    tabela="rj_sancoes_fornecedores",
    como_chamar={
        "cnpj": "cpf/cnpj",
        "orgao_apenador": "órgão/entidade apenadora",
        "enquadramento_legal": "enquadramento legal",
        "motivo": "motivo",
        "contrato": "contrato",
        "situacao": "status da penalidade",
        "efetivada_em": "data de efetivação",
    },
    # o motivo entra: no arquivo de 25/11/2026 três penalidades do mesmo órgão, contrato, enquadramento e
    # dia só se distinguiam por ele (revisão cruzada do #1316); a situação fica fora da chave, para que
    # "Vigente" → "Encerrada" seja versão nova da mesma penalidade, não uma que sumiu (revisão de segurança)
    chave=(
        "cnpj",
        "orgao_apenador",
        "contrato",
        "enquadramento_legal",
        "efetivada_em",
        "motivo",
    ),
    datas=("efetivada_em",),
)
RJ_FORNECEDORES = Tabela(
    fonte="govrj-fornecedores",
    tabela="rj_fornecedores",
    como_chamar={
        "cnpj": "cpf/cnpj",
        "crc": "crc",
        "tipo_empresarial": "tipo empresarial",
        "me_epp": "me/epp",
        "situacao": "situação da empresa",
        "cidade": "cidade",
        "uf": "uf",
        "cadastrado_em": "data de cadastro",
    },
    chave=("cnpj",),
    datas=("cadastrado_em",),
)
RJ_COMPRAS_DIRETAS = Tabela(
    fonte="govrj-compras-diretas",
    tabela="rj_compras_diretas",
    como_chamar={
        "cnpj": "cnpj_cpf",
        "unidade": "unidade",
        "id_processo": "id processo",
        "afastamento": "afastamento",
        "codigo_item": "id item",
        "unidade_de_medida": "unidade de medida",
        "pedido": "ped",
        "regime_juridico": "regime",
        "temporalidade": "temporalidade",
        "aprovado_em": "data de aprovação",
        "valor_do_processo": "valor do processo (r$)",
        "quantidade": "qtd.",
        "valor_unitario": "vl. unitário (r$)",
    },
    # no arquivo de 25/11/2026, processo, item e CNPJ repetem com quantidade e preço diferentes (164 casos);
    # com os dois na chave, o que repete é cópia idêntica
    chave=("id_processo", "codigo_item", "cnpj", "quantidade", "valor_unitario"),
    datas=("aprovado_em",),
    reais=("valor_do_processo", "quantidade", "valor_unitario"),
)
ES_CONTRATOS = Tabela(
    fonte="esdados-contratos",
    tabela="es_contratos",
    como_chamar={
        "cnpj": "cnpjfornecedor",
        "id_contrato": "id",
        "codigo_orgao": "idorgao",
        "orgao": "nomeorgao",
        "processo": "numeroprocesso",
        "modalidade": "modalidadeprocesso",
        "edital": "numeroedital",
        "documento": "numerodocumento",
        "tipo_de_documento": "tipodocumento",
        "tipo_de_aquisicao": "tipoaquisicao",
        "situacao": "situacao",
        "registro_de_preco": "eregistropreco",
        "celebrado_em": "datacelebracao",
        "vigencia_inicio": "datainiciovigencia",
        "vigencia_fim": "datafimvigencia",
        "valor_inicial": "valorinicial",
        "valor_final": "valorfinal",
    },
    chave=("id_contrato", "cnpj"),
    datas=("celebrado_em", "vigencia_inicio", "vigencia_fim"),
    reais=("valor_inicial", "valor_final"),
)
ES_EMPENHOS = Tabela(
    fonte="esdados-empenhos",
    tabela="es_empenhos",
    como_chamar={
        "cnpj": "cnpjfornecedor",
        "id_empenho": "id",
        "processo": "numeroprocesso",
        "documento": "numerodocumento",
        "tipo_de_documento": "tipodocumento",
        "empenho": "numeroempenho",
        "valor_global": "valorglobal",
    },
    chave=("id_empenho", "cnpj"),
    reais=("valor_global",),
)
TABELAS = (
    RJ_CONTRATOS,
    RJ_SANCOES,
    RJ_FORNECEDORES,
    RJ_COMPRAS_DIRETAS,
    ES_CONTRATOS,
    ES_EMPENHOS,
)


# --- leitura de um arquivo guardado --------------------------------------------------------------------------
def _abrir(caminho: Path) -> IO[bytes]:
    """O arquivo guardado sem pôr tudo na memória (o acervo guarda em `.gz` o que não veio comprimido)."""
    return gzip.open(caminho) if caminho.name.endswith(".gz") else caminho.open("rb")


def _pedacos(caminho: Path, colunas: Collection[str]) -> Iterator[pd.DataFrame]:
    """O CSV guardado em pedaços, só com as `colunas` que vierem, como texto aparado."""
    with _abrir(caminho) as entrada:
        lidos = pd.read_csv(
            entrada,
            sep=SEPARADOR,
            encoding=UTF8,
            dtype=str,
            keep_default_na=False,
            usecols=lambda coluna: coluna in colunas,
            chunksize=LINHAS_POR_PEDACO,
        )  # type: ignore[call-overload]
        for pedaco in lidos:
            yield pedaco.apply(lambda serie: serie.str.strip())


def data(texto: pd.Series, formato: str = FORMATO_DA_DATA_BR) -> pd.Series:
    """ "25/11/2026" (com ou sem hora depois) em data; vazio e data impossível ficam nulos."""
    return pd.to_datetime(texto.str[:TAMANHO_DA_DATA], format=formato, errors="coerce")


def reais(texto: pd.Series) -> pd.Series:
    """ "1.234,50" e "59,64" em número (a fonte usa vírgula decimal); vazio e lixo viram nulo."""
    com_virgula = texto.str.contains(",", regex=False)
    sem_milhar = texto.where(~com_virgula, texto.str.replace(".", "", regex=False))
    return pd.to_numeric(sem_milhar.str.replace(",", ".", regex=False), errors="coerce")


def _bruta(caminho: Path, tabela: Tabela) -> pd.DataFrame:
    """O arquivo com os nossos nomes; coluna que a fonte tirou é erro, não coluna vazia."""
    nomes = set(tabela.como_chamar.values())
    pedacos = list(_pedacos(caminho, nomes))
    if not pedacos:
        return pd.DataFrame(columns=list(tabela.como_chamar), dtype=str)
    bruta = pd.concat(pedacos, ignore_index=True)
    faltam = sorted(nomes - set(bruta.columns))
    if faltam:
        raise KeyError(
            f"{tabela.tabela}: o arquivo deixou de trazer {', '.join(faltam)}"
        )
    return pd.DataFrame({c: bruta[f] for c, f in tabela.como_chamar.items()})


def ler(caminho: Path, tabela: Tabela) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas de CNPJ inteiro de um arquivo guardado e a contagem do que ficou de fora."""
    nossas = _bruta(caminho, tabela)
    completo = nossas["cnpj"].map(cnpjs.completo)
    valido = completo.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(
        bool
    )
    nossas = nossas[valido.to_numpy()].assign(cnpj=completo[valido])
    convertidas = {
        **{c: data(nossas[c], tabela.formato_da_data) for c in tabela.datas},
        **{c: reais(nossas[c]) for c in tabela.reais},
    }
    nossas = nossas.assign(**convertidas)
    nossas["id_na_fonte"] = motor.chave(
        nossas.assign(**{c: nossas[c].astype(str) for c in tabela.chave}), tabela.chave
    )
    repetido = nossas["id_na_fonte"].duplicated(keep="first")
    nossas = nossas[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": nossas["id_na_fonte"],
            "cnpj": nossas["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": nossas["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: motor.sem_vazio(nossas[c]) for c in tabela.textos},
            **{c: nossas[c] for c in (*tabela.datas, *tabela.reais)},
        }
    ).reset_index(drop=True)
    contagem = {
        "linhas": len(valido),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


# --- montagem ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Serie:
    """Os retratos de um arquivo de uma tabela (o que `retratos.montar_cadastros` pede)."""

    nome: str  # o nome do Parquet: o arquivo da fonte sem a extensão, em minúsculas
    fonte: str
    tabela: str
    url_termina_em: str


def nome_do_arquivo(url: str) -> str:
    """O arquivo da fonte pelo fim do endereço, sem a extensão e em minúsculas ("CONTRATOS.CSV" → "contratos")."""
    ultimo = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.[a-z0-9]+$", "", ultimo.lower())


def series(conexao: sa.Connection, tabela: Tabela) -> list[Serie]:
    """Uma série por arquivo que a fonte já teve guardado (o arquivista guarda cada endereço à parte)."""
    finais = {
        r.url.rstrip("/").rsplit("/", 1)[-1]
        for r in motor.retratos(conexao, tabela.fonte)
    }
    return [
        Serie(nome_do_arquivo(final), tabela.fonte, tabela.tabela, f"/{final}")
        for final in sorted(finais)
    ]


def _disponivel_no_dia(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do arquivo: a fonte não diz quando cada linha entrou nele."""
    return pd.Series(dia, index=novos.index)


def _para_gravar(
    tabela: pd.DataFrame,
    pessoas: np.ndarray,
    agora: datetime,
    *,
    spec: Tabela,
    arquivo: str,
) -> pd.DataFrame:
    basico = tabela["cnpj_basico"].astype(str)
    return (
        tabela.assign(
            arquivo=arquivo,
            trata_como_pessoa=cnpjs.contem(pessoas, cnpjs.raizes_em_numeros(basico))
            if len(tabela)
            else pd.Series(dtype=bool),
            **{
                c: pd.to_datetime(tabela[c]).dt.date
                for c in [*spec.datas, "visto_em", "disponivel_em"]
            },
            consta=tabela["consta"].astype(bool),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )[[*spec.colunas, *LINHAGEM]]
        .sort_values(ORDEM, kind="stable")
        .reset_index(drop=True)
    )


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
    tabelas: Collection[Tabela] = TABELAS,
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/<arquivo>.parquet` de cada arquivo guardado de cada tabela, e o resumo da montagem.

    Sem retrato novo desde a última montagem, o arquivo é pulado (`refazer` relê mesmo assim, para código
    novo). `pessoas`: as raízes de pessoa já sabidas; sem elas, pergunta à Receita guardada."""
    resumo: dict[str, dict[str, int]] = {}
    for spec in tabelas:
        for serie in series(conexao, spec):
            feito = motor.montar_cadastros(
                conexao,
                pasta,
                agora,
                [serie],
                ler=lambda caminho, _serie, spec=spec: ler(caminho, spec),
                juntar=partial(
                    motor.juntar,
                    valores=spec.valores,
                    disponivel_no_primeiro=_disponivel_no_dia,
                ),
                para_gravar=partial(_para_gravar, spec=spec, arquivo=serie.nome),
                ordem=ORDEM,
                pessoas=pessoas,
                refazer=refazer,
            )
            resumo |= {
                f"{spec.tabela}/{nome}": contagem for nome, contagem in feito.items()
            }
    return resumo
