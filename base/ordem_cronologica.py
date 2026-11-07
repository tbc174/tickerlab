"""Ordem cronológica de pagamentos de Pernambuco e do Espírito Santo por CNPJ (linha 755 da fila; motor de
risco cedente/sacado, linha 754).

As tabelas `sefaz_pe_ordem_cronologica` e `es_ordem_cronologica`: cada pagamento do estado a um fornecedor,
com a data em que a despesa foi liquidada (o estado reconheceu que devia), a data em que pagou e o valor
pago. `dias_ate_pagar` é o intervalo entre as duas: o prazo real de pagamento do governo, que diz mais do
cedente de uma duplicata de órgão público do que o prazo escrito no contrato. Lê o que o arquivista já
guardou (`base/arquivo/lote_ordem_cronologica.py`), sem baixar nada.

- **Uma série por ano, por estado:** o arquivo é o do ano (PE troca o nome todo dia, ES mantém o nome), e os
  retratos do mesmo ano formam uma série só (o motor de `base/retratos.py`). Pagamento novo, ou com data ou
  valor diferente, vira linha nova desde o dia em que foi visto; o que some do arquivo (o estado corrigiu)
  ganha `consta` falso. Ano novo é arquivo novo: o ano velho para de crescer sem perder linha.
- **Só pessoa jurídica (ADR 0075 e 0088):** a coleta já tirou o nome do credor e o texto livre, e as
  linhas com CPF; aqui o CNPJ se confere de novo (dígito certo). Empresário individual e MEI não se
  distinguem na fonte, então ficam com `trata_como_pessoa` pela Receita guardada.
- **Sem olhar o futuro** (`disponivel_em`): o dia em que o TickerLab viu a linha. As datas do pagamento
  (`liquidado_em`, `pago_em`) contam quando aconteceu, nunca quando a base soube; a história guardada
  começa no dia da primeira coleta.
- **Identidade do pagamento:** empenho, ordem bancária, CNPJ e valor juntos (o número da ordem bancária
  sozinho se repete quando uma ordem paga vários documentos). Linha repetida de verdade (mesmos campos)
  fica uma vez e entra na contagem `id_repetido`.

Limites conhecidos: a fonte não diz a data em que o dinheiro caiu na conta (ES dá a da emissão da ordem
bancária; PE, a do pagamento), nem a data de vencimento combinada com o fornecedor; só o que o Poder
Executivo estadual paga, não as prefeituras; a licença é CC BY, citando a fonte.
"""

import gzip
import re
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cnpj as cnpjs
from base import retratos as motor
from base.parquet import LINHAGEM, gravar_se_mudou, origens_gravadas
from base.pgfn import pessoas_pela_receita
from src.versao_do_codigo import versao_do_codigo

SEPARADOR = ";"  # a coleta grava todo CSV com ";"
UTF8 = "utf-8"
LINHAS_POR_PEDACO = 200_000
JA_MONTADO = {"ja_montado": 1}  # no resumo: nenhum arquivo novo desde a última montagem
ORDEM = ["id_na_fonte", "visto_em"]
_CARIMBOS = ["consta", "trata_como_pessoa", "visto_em", "disponivel_em"]
FORMATO_DA_DATA_DE_PE = "%Y/%m/%d"  # "2025/12/22 00:00:00.000"
FORMATO_DA_DATA_DE_ES = "%d/%m/%Y"  # "12/03/2026 00:00:00"
TAMANHO_DA_DATA = 10  # só o dia: a hora da fonte é sempre meia-noite

_DERIVADAS = ("dias_ate_pagar",)


@dataclass(frozen=True)
class Tabela:
    """Uma fonte (um estado): de onde lê, como chama cada coluna e o que identifica um pagamento."""

    fonte: str  # id no registro de coletas
    tabela: str
    como_chamar: Mapping[
        str, str
    ]  # nosso nome → nome da coluna na fonte (em minúsculas)
    chave: tuple[str, ...]
    datas: tuple[str, ...]
    reais: tuple[str, ...]
    formato_da_data: str
    ano_pelo_nome: Callable[[str], str]

    @property
    def textos(self) -> list[str]:
        return [
            c
            for c in self.como_chamar
            if c not in (*self.datas, *self.reais, "cnpj", *_DERIVADAS)
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
            *_DERIVADAS,
            *_CARIMBOS,
        ]

    @property
    def valores(self) -> list[str]:
        """O que, mudando, faz do pagamento uma linha nova (o resto é a chave ou deriva dela)."""
        return [*self.datas, *self.reais, "consta"]


def _ano_no_nome(url: str) -> str:
    """O ano do arquivo pelo fim do endereço ("..._2026_06112026.csv" e "...-2025.csv" → o ano)."""
    nome = url.rstrip("/").rsplit("/", 1)[-1].lower()
    achado = re.search(r"(?<!\d)(20\d{2})(?!\d)", nome)
    if achado is None:
        raise ValueError(f"{url}: sem o ano no nome do arquivo")
    return achado.group(1)


PERNAMBUCO = Tabela(
    fonte="sefazpe-ordem-cronologica",
    tabela="sefaz_pe_ordem_cronologica",
    como_chamar={
        "cnpj": "cnpj",
        "codigo_ug": "codigo_ug",
        "unidade_gestora": "descicao_unidade_gestora",
        "empenho": "numero_empenho",
        "documento": "numero_documento",
        "ordem_bancaria": "numero_ordem_bancaria",
        "categoria_contrato": "categoria_contrato",
        "liquidado_em": "data_liquidacao",
        "ordem_bancaria_em": "data_ordem_bancaria",
        "pago_em": "data_pagamento",
        "valor_documento": "valor_documento",
        "valor_pago": "valor_liquido_pagamento",
    },
    chave=("empenho", "documento", "ordem_bancaria", "cnpj", "valor_pago"),
    datas=("liquidado_em", "ordem_bancaria_em", "pago_em"),
    reais=("valor_documento", "valor_pago"),
    formato_da_data=FORMATO_DA_DATA_DE_PE,
    ano_pelo_nome=_ano_no_nome,
)
ESPIRITO_SANTO = Tabela(
    fonte="esdados-ordem-cronologica",
    tabela="es_ordem_cronologica",
    como_chamar={
        "cnpj": "credor",
        "codigo_ug": "codigoug",
        "unidade_gestora": "unidadegestora",
        "empenho": "codigone",
        "nota_de_liquidacao": "codigonl",
        "ordem_bancaria": "codigoob",
        "categoria_contrato": "nomecategoriacontrato",
        "ordem_cronologica_em": "datacronologica",
        "liquidado_em": "dataemissaonl",
        "pago_em": "dataemissaoob",
        "valor_pago": "valorob",
    },
    chave=("empenho", "nota_de_liquidacao", "ordem_bancaria", "cnpj", "valor_pago"),
    datas=("ordem_cronologica_em", "liquidado_em", "pago_em"),
    reais=("valor_pago",),
    formato_da_data=FORMATO_DA_DATA_DE_ES,
    ano_pelo_nome=_ano_no_nome,
)
TABELAS = (PERNAMBUCO, ESPIRITO_SANTO)


def _abrir(caminho: Path) -> IO[bytes]:
    """O arquivo guardado sem carregar tudo na memória (o acervo guarda em `.gz` o que não veio
    comprimido)."""
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


def _data(texto: pd.Series, formato: str) -> pd.Series:
    """ "2025/12/22 00:00:00.000" em data; vazio e data impossível ficam nulos."""
    return pd.to_datetime(texto.str[:TAMANHO_DA_DATA], format=formato, errors="coerce")


def _reais(texto: pd.Series) -> pd.Series:
    """ "24403,6000" e "1.234,50" em número (a fonte usa vírgula decimal); lixo vira nulo."""
    com_virgula = texto.str.contains(",", regex=False)
    sem_milhar = texto.where(~com_virgula, texto.str.replace(".", "", regex=False))
    return pd.to_numeric(sem_milhar.str.replace(",", ".", regex=False), errors="coerce")


def _dias(depois: pd.Series, antes: pd.Series) -> pd.Series:
    """Dias inteiros de `antes` a `depois` (nulo se faltar uma das datas)."""
    return (depois - antes).dt.days.astype("Int64")


def ler(caminho: Path, tabela: Tabela) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os pagamentos de CNPJ inteiro de um retrato e a contagem do que ficou de fora."""
    nomes = set(tabela.como_chamar.values())
    pedacos = list(_pedacos(caminho, nomes))
    bruta = (
        pd.concat(pedacos, ignore_index=True)
        if pedacos
        else pd.DataFrame(columns=sorted(nomes), dtype=str)
    )
    nossas = pd.DataFrame(
        {
            c: bruta.get(f, pd.Series("", index=bruta.index))
            for c, f in tabela.como_chamar.items()
        }
    )
    completo = nossas["cnpj"].map(cnpjs.completo)
    valido = completo.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(
        bool
    )
    nossas = nossas[valido.to_numpy()].assign(cnpj=completo[valido])
    datas = {c: _data(nossas[c], tabela.formato_da_data) for c in tabela.datas}
    reais = {c: _reais(nossas[c]) for c in tabela.reais}
    nossas = nossas.assign(**datas, **reais)
    nossas["id_na_fonte"] = motor.chave(
        nossas.assign(**{c: nossas[c].astype(str) for c in tabela.reais}), tabela.chave
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
            "dias_ate_pagar": _dias(nossas["pago_em"], nossas["liquidado_em"]),
        }
    ).reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "cnpj_invalido": int((~valido).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def _disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O dia do arquivo: a fonte não diz quando publicou cada pagamento."""
    return pd.Series(dia, index=novos.index)


@dataclass(frozen=True)
class _Montagem:
    """A série de retratos de um ano de um estado a gravar."""

    tabela: Tabela
    destino: Path
    achados: list[motor.Retrato]
    ano: str


def _origens(achados: list[motor.Retrato]) -> list[dict[str, str]]:
    return [{"url": r.url, "sha256": r.sha256} for r in achados]


def _montagens(conexao: sa.Connection, pasta: Path) -> Iterator[tuple[str, _Montagem]]:
    """Um Parquet por estado e ano: o nome do arquivo (e não o endereço, que PE muda todo dia) junta os
    retratos do mesmo ano."""
    for tabela in TABELAS:
        por_ano: dict[str, list[motor.Retrato]] = {}
        for retrato in motor.retratos(conexao, tabela.fonte):
            por_ano.setdefault(tabela.ano_pelo_nome(retrato.url), []).append(retrato)
        for ano, achados in sorted(por_ano.items()):
            nome = f"{tabela.tabela}/{ano}"
            yield (
                nome,
                _Montagem(
                    tabela,
                    pasta / tabela.tabela / f"ordem-cronologica-{ano}",
                    achados,
                    ano,
                ),
            )


def _como_numeros(pessoas: Collection[str] | np.ndarray) -> np.ndarray:
    if isinstance(pessoas, np.ndarray):
        return pessoas
    return cnpjs.ordenados(cnpjs.raizes_em_numeros(pd.Series(list(pessoas), dtype=str)))


def _para_gravar(
    tabela: pd.DataFrame, montagem: _Montagem, pessoas: np.ndarray, agora: datetime
) -> pd.DataFrame:
    basico = tabela["cnpj_basico"].astype(str)
    spec = montagem.tabela
    return (
        tabela.assign(
            arquivo=montagem.ano,
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
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/ordem-cronologica-<ano>.parquet` com todos os retratos guardados de cada ano.

    Sem arquivo novo desde a última montagem, é pulado (`refazer` relê mesmo assim, para código novo).
    `pessoas`: as raízes de pessoa já sabidas; sem elas, pergunta à Receita guardada.
    """
    resumo: dict[str, dict[str, int]] = {}
    for nome, montagem in _montagens(conexao, pasta):
        if not refazer and origens_gravadas(montagem.destino) == _origens(
            montagem.achados
        ):
            resumo[nome] = JA_MONTADO
            continue
        contagem: dict[str, int] = {}
        lidos = []
        for retrato in montagem.achados:
            tabela, contou = ler(retrato.caminho, montagem.tabela)
            for chave, valor in contou.items():
                contagem[chave] = contagem.get(chave, 0) + valor
            lidos.append((retrato, tabela))
        tabela, pulados = motor.juntar(
            lidos, montagem.tabela.valores, _disponivel_no_primeiro
        )
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
            _para_gravar(tabela, montagem, de_pessoa, agora),
            montagem.destino,
            _origens(montagem.achados),
            ORDEM,
            carimbos=LINHAGEM,
        )
        resumo[nome] = {
            **contagem,
            "retratos": len(montagem.achados),
            "retratos_pulados": pulados,
            "na_tabela": len(tabela),
        }
    return resumo
