"""Relatórios do RAPP do IBAMA pelo CNPJ (meta das 300 tabelas, linha 1074, PR 1): emissões de poluentes
atmosféricos, efluentes líquidos, fontes de energia (consumo e CO2) e a cadeia dos resíduos sólidos
(destinador, transportador e armazenador). Fontes `ibama-rapp-*` do arquivista (`base/arquivo/lote_ibama_rapp.py`).

O RAPP (Relatório Anual de Atividades Potencialmente Poluidoras) é o que cada estabelecimento inscrito no
Cadastro Técnico Federal **declara** ao IBAMA a cada ano. É dado declarado, nunca veredito: quem não declarou não
aparece, e não declarar não é o mesmo que zero.

- **Formato** (conferido em 25/11/2026 nos arquivos do portal, regravados pelo IBAMA em 04/05/2026): CSV UTF-8 sem
  BOM, separado por `;`, fim de linha CRLF, um arquivo por relatório (`relatorio.csv`), sempre inteiro. O CNPJ vem
  com máscara. **O número muda de formato de um relatório para outro**: emissões e energia escrevem `1,234.5`
  (milhar com vírgula, decimal com ponto); efluentes e resíduos escrevem `1.234,5`. O Excel deixou `#####` em
  algumas células: vira nulo e é contado. Nas fontes de energia, 510 linhas do arquivo vêm quebradas (a observação
  com quebra de linha fora das aspas) e 478.797 fecham as colunas: a linha que não fecha sai e é contada.
- **O último dado:** emissões, efluentes, energia e resíduos trazem declarações até 2025 (o transportador e o
  armazenador já têm 2026). O ano mais novo de cada tabela vai no dicionário; a coluna `ano` diz de que ano é
  cada linha.
- **Só pessoa jurídica** (ADR 0075): o CNPJ do estabelecimento que declara tem de fechar o DV (CPF e DV errado saem
  e são contados). O CNPJ da outra ponta (quem gerou o resíduo, de onde o transporte saiu, para onde foi) fica só
  quando é CNPJ de DV certo; o CPF dessa ponta (115 linhas no destinador, 159 no transportador e 34 no armazenador
  em 25/11/2026) vira nulo e é contado. MEI e empresário individual, nas duas pontas, são marcados por
  `trata_como_pessoa` na montagem.
- **Ficam de fora** a razão social (a Receita tem; no empresário individual é o nome da pessoa), o estado e o
  município por extenso (a Receita tem, pelo CNPJ do estabelecimento), a latitude e a longitude dos efluentes (no
  MEI o estabelecimento costuma ser a casa), o nome da empresa receptora do efluente e os campos de texto livre
  (observações, justificativas, "qual?"). Das fontes de energia ficam de fora os fatores técnicos (densidade, poder
  calorífico, carbono, oxidação) e as justificativas.
- **Sem olhar o futuro:** o arquivo não diz quando cada linha foi publicada, e o ano da declaração não é data de
  publicação (o RAPP do ano X é entregue até 31 de março de X+1). A linha vale desde o dia em que o arquivista a
  viu: o dia do retrato.

Sem Streamlit; pandas só.
"""

import csv
import io
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import aneel_indicadores as comum
from base import bcb_cadastros as base
from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

SEPARADOR = ";"
CODIFICACAO = "utf-8-sig"  # sem BOM em 25/11/2026; com BOM também lê
PORTAL = "https://dadosabertos.ibama.gov.br/dados/RAPP"
ILEGIVEL = "#"  # o Excel escreve `#####` quando o número não cabe na célula
MILHAR_COM_VIRGULA = "1,234.5"  # emissões e energia
MILHAR_COM_PONTO = "1.234,5"  # efluentes e resíduos
CARIMBO = ("id_na_fonte", "cnpj", "cnpj_basico")
OCORRENCIA = "ocorrencia"


@dataclass(frozen=True)
class Relatorio:
    """Um relatório do RAPP: de onde vem, que colunas a tabela guarda e como se lê o número.

    `cnpj` é a coluna da fonte com o CNPJ de quem declara; `outras_pontas` liga a coluna da fonte com o CNPJ da
    outra ponta ao sufixo da nossa coluna (`gerador` → `cnpj_gerador` e `cnpj_basico_gerador`)."""

    tabela: str
    nome: str
    fonte: str
    pasta_no_portal: str
    cnpj: str
    ano: str
    textos: dict[str, str]
    numeros: dict[str, str] = field(default_factory=dict)
    formato_do_numero: str = MILHAR_COM_PONTO
    percentuais: dict[str, str] = field(default_factory=dict)
    outras_pontas: dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"{PORTAL}/{self.pasta_no_portal}/relatorio.csv"

    @property
    def colunas_da_fonte(self) -> list[str]:
        return [
            self.cnpj,
            self.ano,
            *self.textos,
            *self.numeros,
            *self.percentuais,
            *self.outras_pontas,
        ]

    @property
    def colunas(self) -> tuple[str, ...]:
        pontas = [
            c
            for sufixo in self.outras_pontas.values()
            for c in (f"cnpj_{sufixo}", f"cnpj_basico_{sufixo}")
        ]
        return (
            *CARIMBO,
            *pontas,
            "ano",
            *self.textos.values(),
            *self.numeros.values(),
            *self.percentuais.values(),
        )

    @property
    def raizes_de_pessoa(self) -> tuple[str, ...]:
        return (
            "cnpj_basico",
            *(f"cnpj_basico_{s}" for s in self.outras_pontas.values()),
        )


def _csv(conteudo: bytes, relatorio: Relatorio) -> tuple[pd.DataFrame, int]:
    """O CSV como texto, e quantas linhas vieram quebradas (com mais ou menos campos que o cabeçalho).

    O pandas completaria a linha curta com vazio, e o pedaço de uma observação quebrada viraria uma linha com
    energia e CO2 vazios: por isso cada linha é contada pelo `csv`, que respeita as aspas. Coluna que o IBAMA
    tirou é erro, não coluna vazia."""
    leitor = csv.reader(
        io.TextIOWrapper(io.BytesIO(conteudo), encoding=CODIFICACAO, newline=""),
        delimiter=SEPARADOR,
    )
    cabecalho = [c.strip() for c in next(leitor, [])]
    faltam = sorted(set(relatorio.colunas_da_fonte) - set(cabecalho))
    if faltam:
        raise KeyError(f"o IBAMA deixou de trazer: {', '.join(faltam)}")
    # só as colunas usadas ficam na memória (o de energia tem o dobro de colunas e passava de 2 GB inteiro)
    posicoes = [cabecalho.index(c) for c in relatorio.colunas_da_fonte]
    usadas: list[list[str]] = []
    quebradas = 0
    for linha in leitor:
        if len(linha) == len(cabecalho):
            usadas.append([linha[i].strip() for i in posicoes])
        elif linha:  # a linha em branco do fim do arquivo não conta
            quebradas += 1
    return pd.DataFrame(
        usadas, columns=relatorio.colunas_da_fonte, dtype="string"
    ), quebradas


def numero(texto: pd.Series, formato: str) -> pd.Series:
    """O número no formato do relatório (`1,234.5` ou `1.234,5`); vazio e `#####` viram nulo."""
    if formato == MILHAR_COM_VIRGULA:
        limpo = texto.str.replace(",", "", regex=False)
    else:
        limpo = texto.str.replace(".", "", regex=False).str.replace(
            ",", ".", regex=False
        )
    return pd.to_numeric(limpo.str.rstrip("%"), errors="coerce")


def _ilegiveis(bruta: pd.DataFrame, colunas: Collection[str]) -> int:
    return int(
        sum(bruta[c].str.startswith(ILEGIVEL).sum() for c in colunas if len(bruta))
    )


def _outra_ponta(texto: pd.Series) -> tuple[pd.Series, int]:
    """O CNPJ de 14 caracteres da outra ponta (nulo se não for CNPJ de DV certo) e quantos eram CPF."""
    digitos = texto.str.replace(r"\D", "", regex=True)
    cnpj14, de_cpf = comum.documentos(digitos)
    return cnpj14, int(de_cpf.sum())


def ler(relatorio: Relatorio, conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas de pessoa jurídica de um retrato do relatório e a contagem do que saiu ou ficou nulo.

    Duas linhas iguais em tudo o que a tabela guarda continuam duas (a fonte declara, por exemplo, dois
    lançamentos do mesmo poluente no mesmo ano): a `ocorrencia` as numera, e só a repetida por inteiro na fonte
    é contada em `id_repetido`."""
    bruta, quebradas = _csv(conteudo, relatorio)
    tabela, contagem = comum.so_pessoa_juridica(
        bruta.assign(
            **{relatorio.cnpj: bruta[relatorio.cnpj].str.replace(r"\D", "", regex=True)}
        ),
        relatorio.cnpj,
    )
    contagem["linha_quebrada"] = quebradas
    contagem["numero_ilegivel"] = _ilegiveis(
        tabela, [*relatorio.numeros, *relatorio.percentuais]
    )
    colunas: dict[str, pd.Series] = {**comum.com_cnpj(tabela["cnpj14"])}
    contagem["outra_ponta_pessoa_fisica"] = 0
    for da_fonte, sufixo in relatorio.outras_pontas.items():
        cnpj14, de_cpf = _outra_ponta(tabela[da_fonte])
        contagem["outra_ponta_pessoa_fisica"] += de_cpf
        colunas[f"cnpj_{sufixo}"] = cnpj14.map(cnpjs.formatar, na_action="ignore")
        colunas[f"cnpj_basico_{sufixo}"] = cnpj14.str[: cnpjs.TAMANHO_DA_RAIZ]
    colunas["ano"] = pd.to_numeric(tabela[relatorio.ano], errors="coerce").astype(
        "Int64"
    )
    colunas |= base.renomeadas(tabela, relatorio.textos)
    colunas |= {
        nosso: numero(tabela[da_fonte], relatorio.formato_do_numero)
        for da_fonte, nosso in relatorio.numeros.items()
    }
    colunas |= {
        nosso: numero(tabela[da_fonte], MILHAR_COM_PONTO)
        for da_fonte, nosso in relatorio.percentuais.items()
    }
    pronta = pd.DataFrame(colunas, index=tabela.index)
    guardadas = [c for c in relatorio.colunas if c != "id_na_fonte"]
    chave = motor.chave(pronta.astype("string").fillna(""), guardadas)
    pronta.insert(
        0,
        "id_na_fonte",
        motor.chave(
            pd.DataFrame(
                {"c": chave, OCORRENCIA: chave.groupby(chave).cumcount().astype(str)}
            ),
            ["c", OCORRENCIA],
        ),
    )
    tipos = {
        "ano": "Int64",
        **{
            c: "Float64"
            for c in [*relatorio.numeros.values(), *relatorio.percentuais.values()]
        },
    }
    return base.pronta(pronta[list(relatorio.colunas)], contagem, tipos)


# --- os relatórios do PR 1 -------------------------------------------------------------------------------
_ATIVIDADE = {
    "Código da Categoria": "categoria_codigo",
    "Categoria de Atividade": "categoria",
    "Código do Detalhe": "detalhe_codigo",
    "Detalhe": "detalhe",
}
_SITUACAO = {"Situação Cadastral": "situacao_cadastral"}

EMISSOES = Relatorio(
    tabela="ibama_rapp_emissoes_atmosfericas",
    nome="emissoes",
    fonte="ibama-rapp-emissoes-atmosfericas",
    pasta_no_portal="emissoesPoluentesAtmosfericos",
    cnpj="CNPJ",
    ano="Ano",
    textos={**_ATIVIDADE, "Poluente emitido": "poluente", **_SITUACAO},
    numeros={"Quantidade": "quantidade"},
    formato_do_numero=MILHAR_COM_VIRGULA,
)
EFLUENTES = Relatorio(
    tabela="ibama_rapp_efluentes_liquidos",
    nome="efluentes",
    fonte="ibama-rapp-efluentes-liquidos",
    pasta_no_portal="efluentesLiquidos",
    cnpj="CNPJ",
    ano="Ano",
    textos={
        **_ATIVIDADE,
        "Tipo de Tratamento": "tipo_de_tratamento",
        "Nível de Tratamento": "nivel_de_tratamento",
        "Compart. Ambiental da Emissão": "compartimento_ambiental",
        "Tipo de Emissão": "tipo_de_emissao",
        "Tipo Corpo Receptor": "tipo_do_corpo_receptor",
        "Classe do Corpo Receptor": "classe_do_corpo_receptor",
        "Corpo Receptor": "corpo_receptor",
        "Tipo de Emissão Para o Solo": "tipo_de_emissao_para_o_solo",
        **_SITUACAO,
    },
    numeros={"Quantidade": "quantidade"},
    percentuais={"Eficiência do tratamento": "eficiencia_do_tratamento"},
)
ENERGIA = Relatorio(
    tabela="ibama_rapp_fontes_de_energia",
    nome="energia",
    fonte="ibama-rapp-fontes-energeticas",
    pasta_no_portal="fontesEnergeticas",
    cnpj="CNPJ",
    ano="Ano",
    textos={
        **_ATIVIDADE,
        "Tipo de Fonte Energética": "fonte_de_energia",
        "Unidade de Medida": "unidade",
        **_SITUACAO,
    },
    numeros={
        "Quantidade Consumida": "quantidade_consumida",
        "Energia": "energia",
        "Emissões de CO2": "emissoes_de_co2",
    },
    formato_do_numero=MILHAR_COM_VIRGULA,
)
_RESIDUO = {"Cód. Resíduo": "residuo_codigo", "Desc. Resíduo": "residuo"}
RESIDUOS_DESTINADOS = Relatorio(
    tabela="ibama_rapp_residuos_destinados",
    nome="destinados",
    fonte="ibama-rapp-residuos-destinador",
    pasta_no_portal="residuoSolidosDestinador",
    cnpj="CNPJ do destinador",
    ano="Ano - destinação",
    textos={
        **_ATIVIDADE,
        **_RESIDUO,
        "Unidade": "unidade",
        "Tipo de destinação": "tipo_de_destinacao",
        **_SITUACAO,
    },
    numeros={"Quant. destinada": "quantidade"},
    outras_pontas={"CNPJ do gerador do resíduo": "gerador"},
)
RESIDUOS_TRANSPORTADOS = Relatorio(
    tabela="ibama_rapp_residuos_transportados",
    nome="transportados",
    fonte="ibama-rapp-residuos-transportador",
    pasta_no_portal="residuoSolidosTransportador",
    cnpj="CNPJ do transportador",
    ano="Ano",
    textos=_SITUACAO,
    outras_pontas={"CNPJ da origem": "origem"},
)
RESIDUOS_ARMAZENADOS = Relatorio(
    tabela="ibama_rapp_residuos_armazenados",
    nome="armazenados",
    fonte="ibama-rapp-residuos-armazenador",
    pasta_no_portal="residuoSolidosArmazenador",
    cnpj="CNPJ do armazenador",
    ano="Ano da destinação",
    textos={
        **_RESIDUO,
        "Unidade": "unidade",
        "Tipo de armazenamento/destin.": "tipo_de_armazenamento_ou_destinacao",
        "Situação": "armazenado_ou_destinado",
        **_SITUACAO,
    },
    numeros={"Qtd armaz/enviada p/dest final": "quantidade"},
    outras_pontas={
        "CNPJ da emp. ger. do resíduo": "gerador",
        "CNPJ Armazenamento/Destinação": "destino",
    },
)
RELATORIOS = (
    EMISSOES,
    EFLUENTES,
    ENERGIA,
    RESIDUOS_DESTINADOS,
    RESIDUOS_TRANSPORTADOS,
    RESIDUOS_ARMAZENADOS,
)


def _cadastro(relatorio: Relatorio) -> cadastros_em_retrato.Cadastro:
    return base.cadastro(
        relatorio.tabela,
        relatorio.nome,
        relatorio.fonte,
        lambda conteudo: ler(relatorio, conteudo),
        relatorio.colunas,
        raizes_de_pessoa=relatorio.raizes_de_pessoa,
    )


CADASTROS = tuple(_cadastro(r) for r in RELATORIOS)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/ibama_rapp_<relatório>/<nome>.parquet` para cada relatório com arquivo guardado (só CNPJ)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
