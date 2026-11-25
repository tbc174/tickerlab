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
  `trata_como_pessoa` na montagem. Campo de texto com onze dígitos seguidos (cara de CPF, valha o DV ou não) vira
  nulo e é contado (`texto_com_cara_de_cpf`).
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
import re
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
MILHAR_COM_PONTO = (
    "1.234,5"  # efluentes, resíduos e os relatórios florestais e minerais
)
FORMATO_DA_DATA = "%d/%m/%Y"  # `31/12/2018`; a hora, quando vem, fica de fora
TAMANHO_DA_DATA = len("31/12/2018")
# ano declarado fora desta faixa (há `5279` e `0002` nos arquivos de 25/11/2026) é erro de digitação: vira nulo contado
ANO_MINIMO, ANO_MAXIMO = 1900, 2100
# onze dígitos seguidos (com ou sem a pontuação do CPF) num campo de texto: no decreto de lavra de 25/11/2026, 10 dos
# 117 assim fecham o DV de CPF (ao acaso seria 1 em 100). O texto inteiro vira nulo contado, valha o DV ou não
CARA_DE_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
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
    anos: dict[str, str] = field(default_factory=dict)
    datas: dict[str, str] = field(default_factory=dict)
    # números com ponto decimal num relatório escrito em `1.234,5` (o número de árvores da silvicultura)
    numeros_com_ponto: dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"{PORTAL}/{self.pasta_no_portal}/relatorio.csv"

    @property
    def colunas_da_fonte(self) -> list[str]:
        return [
            self.cnpj,
            self.ano,
            *self.textos,
            *self.anos,
            *self.datas,
            *self.numeros,
            *self.numeros_com_ponto,
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
            *self.anos.values(),
            *self.datas.values(),
            *self.numeros.values(),
            *self.numeros_com_ponto.values(),
            *self.percentuais.values(),
        )

    @property
    def colunas_de_numero(self) -> tuple[str, ...]:
        return (
            *self.numeros.values(),
            *self.numeros_com_ponto.values(),
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


def _sem_pontuacao(texto: pd.Series) -> pd.Series:
    """O documento sem ponto, barra, traço e espaço, em maiúsculas: as letras do CNPJ alfanumérico (IN RFB
    2.229/2024) ficam; o teste de CPF de `comum.documentos` olha só os dígitos."""
    return texto.str.replace(cnpjs.SEPARADORES.pattern, "", regex=True).str.upper()


def _outra_ponta(texto: pd.Series) -> tuple[pd.Series, int, int]:
    """O CNPJ de 14 caracteres da outra ponta (nulo se não for CNPJ de DV certo), quantos eram CPF e quantos
    vieram preenchidos sem ser CNPJ de DV certo nem CPF."""
    documento = _sem_pontuacao(texto)
    cnpj14, de_cpf = comum.documentos(documento)
    cnpj14 = cnpj14.astype("string")  # sem nenhum CNPJ a série viria como número
    invalido = cnpj14.isna() & ~de_cpf & documento.fillna("").ne("")
    return cnpj14, int(de_cpf.sum()), int(invalido.sum())


def _ano(texto: pd.Series) -> tuple[pd.Series, int]:
    """O ano como inteiro; fora de `ANO_MINIMO`..`ANO_MAXIMO` vira nulo, e devolve quantos eram assim."""
    ano = pd.to_numeric(texto, errors="coerce").astype("Int64")
    fora = ano.notna() & ~ano.between(ANO_MINIMO, ANO_MAXIMO)
    return ano.mask(fora), int(fora.sum())


def _data(texto: pd.Series) -> tuple[pd.Series, int]:
    """O dia em `dd/mm/aaaa` (a hora sai); vazio fica nulo, e o preenchido que não é data (ou cai fora da faixa
    de anos) vira nulo contado."""
    dia = base.dia_br(texto.str[:TAMANHO_DA_DATA], FORMATO_DA_DATA)
    dia = dia.mask(dia.notna() & ~dia.dt.year.between(ANO_MINIMO, ANO_MAXIMO))
    invalida = dia.isna() & texto.fillna("").ne("")
    return dia, int(invalida.sum())


def _sem_cara_de_cpf(texto: pd.Series) -> tuple[pd.Series, int]:
    """O texto, com nulo onde há onze dígitos seguidos (`CARA_DE_CPF`), e quantos eram assim."""
    com_cpf = (
        texto.astype("string").str.contains(CARA_DE_CPF).fillna(False).astype(bool)
    )
    return texto.mask(com_cpf), int(com_cpf.sum())


def _pontas(
    tabela: pd.DataFrame, relatorio: Relatorio, contagem: dict[str, int]
) -> dict[str, pd.Series]:
    """O CNPJ e a raiz de cada outra ponta, contando o CPF e o documento inválido que ficaram de fora."""
    colunas: dict[str, pd.Series] = {}
    contagem["outra_ponta_pessoa_fisica"] = 0
    contagem["outra_ponta_invalida"] = 0
    for da_fonte, sufixo in relatorio.outras_pontas.items():
        cnpj14, de_cpf, invalidos = _outra_ponta(tabela[da_fonte])
        contagem["outra_ponta_pessoa_fisica"] += de_cpf
        contagem["outra_ponta_invalida"] += invalidos
        colunas[f"cnpj_{sufixo}"] = cnpj14.map(cnpjs.formatar, na_action="ignore")
        colunas[f"cnpj_basico_{sufixo}"] = cnpj14.str[: cnpjs.TAMANHO_DA_RAIZ]
    return colunas


def _valores(
    tabela: pd.DataFrame, relatorio: Relatorio, contagem: dict[str, int]
) -> dict[str, pd.Series]:
    """O ano, os textos, os anos e as datas, e os números de cada formato, já com o nome da tabela."""
    anos = {relatorio.ano: "ano", **relatorio.anos}
    colunas: dict[str, pd.Series] = {}
    contagem["ano_fora_da_faixa"] = 0
    for da_fonte, nosso in anos.items():
        colunas[nosso], fora = _ano(tabela[da_fonte])
        contagem["ano_fora_da_faixa"] += fora
    contagem["texto_com_cara_de_cpf"] = 0
    for nosso, texto in base.renomeadas(tabela, relatorio.textos).items():
        colunas[nosso], com_cpf = _sem_cara_de_cpf(texto)
        contagem["texto_com_cara_de_cpf"] += com_cpf
    contagem["data_invalida"] = 0
    for da_fonte, nosso in relatorio.datas.items():
        colunas[nosso], invalidas = _data(tabela[da_fonte])
        contagem["data_invalida"] += invalidas
    formatos = (
        (relatorio.numeros, relatorio.formato_do_numero),
        (relatorio.numeros_com_ponto, MILHAR_COM_VIRGULA),
        (relatorio.percentuais, MILHAR_COM_PONTO),
    )
    for colunas_da_fonte, formato in formatos:
        colunas |= {
            nosso: numero(tabela[da_fonte], formato)
            for da_fonte, nosso in colunas_da_fonte.items()
        }
    return colunas


def _com_chave(pronta: pd.DataFrame, relatorio: Relatorio) -> pd.DataFrame:
    """A tabela com `id_na_fonte` na frente: as colunas guardadas mais a ocorrência delas no arquivo."""
    guardadas = [c for c in relatorio.colunas if c != "id_na_fonte"]
    chave = motor.chave(pronta.astype("string").fillna(""), guardadas)
    ocorrencia = chave.groupby(chave).cumcount().astype(str)
    return pronta.assign(
        id_na_fonte=motor.chave(
            pd.DataFrame({"c": chave, OCORRENCIA: ocorrencia}), ["c", OCORRENCIA]
        )
    )[list(relatorio.colunas)]


def ler(relatorio: Relatorio, conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas de pessoa jurídica de um retrato do relatório e a contagem do que saiu ou ficou nulo.

    Duas linhas iguais em tudo o que a tabela guarda continuam duas (a fonte declara, por exemplo, dois
    lançamentos do mesmo poluente no mesmo ano): a `ocorrencia` as numera, e só a repetida por inteiro na fonte
    é contada em `id_repetido`."""
    bruta, quebradas = _csv(conteudo, relatorio)
    tabela, contagem = comum.so_pessoa_juridica(
        bruta.assign(**{relatorio.cnpj: _sem_pontuacao(bruta[relatorio.cnpj])}),
        relatorio.cnpj,
    )
    contagem["linha_quebrada"] = quebradas
    contagem["numero_ilegivel"] = _ilegiveis(
        tabela,
        [*relatorio.numeros, *relatorio.numeros_com_ponto, *relatorio.percentuais],
    )
    colunas = {
        **comum.com_cnpj(tabela["cnpj14"]),
        **_pontas(tabela, relatorio, contagem),
        **_valores(tabela, relatorio, contagem),
    }
    pronta = _com_chave(pd.DataFrame(colunas, index=tabela.index), relatorio)
    tipos = {
        **dict.fromkeys(("ano", *relatorio.anos.values()), "Int64"),
        **dict.fromkeys(relatorio.colunas_de_numero, "Float64"),
    }
    return base.pronta(pronta, contagem, tipos)


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
# --- os relatórios do PR 2: florestais, minerais e certificados -----------------------------------------
CERTIFICADOS = Relatorio(
    tabela="ibama_rapp_certificados_ambientais",
    nome="certificados",
    fonte="ibama-rapp-certificados-ambientais",
    pasta_no_portal="certificadosAmbientais",
    cnpj="CNPJ",
    ano="Ano",
    textos={
        "Tipo Certificado": "tipo_de_certificado",
        "Certificador": "certificador",
        **_SITUACAO,
    },
    datas={"Validade": "valido_ate"},
)
MADEIRA_E_LENHA = Relatorio(
    tabela="ibama_rapp_madeira_e_lenha",
    nome="madeira",
    fonte="ibama-rapp-madeira-lenha",
    pasta_no_portal="expEcoMadProdSubprodFl",
    cnpj="CNPJ",
    ano="Ano",
    textos=_SITUACAO,
    numeros={
        "Lenha (estéreo ou m³)": "lenha",
        "Tora (m³)": "tora_m3",
        "Área Total Explorada (ha)": "area_explorada_ha",
    },
)
EXTRACAO_MINERAL = Relatorio(
    tabela="ibama_rapp_extracao_mineral",
    nome="minerais",
    fonte="ibama-rapp-extracao-mineral",
    pasta_no_portal="extTratProdMinerais",
    cnpj="CNPJ",
    ano="Ano",
    textos={
        "Nome do Produto": "produto",
        "Unidade de Medida": "unidade",
        "Nº Decreto da Lavra": "decreto_de_lavra",
        **_SITUACAO,
    },
    anos={
        "Ano de início da exploração": "inicio_da_exploracao",
        "Ano de término da exploração": "fim_da_exploracao",
    },
    datas={
        "Data do Decreto": "data_do_decreto",
        "Data de Aprovação do PRA": "pra_aprovado_em",
    },
    numeros={"Quantidade Explorada": "quantidade", "Tamanho da Área": "area"},
)
PRODUTOS_FLORESTAIS = Relatorio(
    tabela="ibama_rapp_produtos_florestais",
    nome="florestais",
    fonte="ibama-rapp-produtos-florestais",
    pasta_no_portal="utilMatPrimaOriFlorestal",
    cnpj="CNPJ",
    ano="Ano",
    textos={"Nome do Produto": "produto", "Unidade de Medida": "unidade", **_SITUACAO},
    numeros={
        "Quantidade recebida": "recebida",
        "Quantidade comercializada": "comercializada",
        "Quantidade processada": "processada",
        "Quantidade estocada": "estocada",
        "Capacidade de Processamento": "capacidade_de_processamento",
        "Qtd. de Doc. Estad. recebidos": "documentos_estaduais_recebidos",
        "Qtd. de Doc. Estad. utilizados": "documentos_estaduais_utilizados",
        "Quantidade Transportada": "transportada",
    },
)
SILVICULTURA = Relatorio(
    tabela="ibama_rapp_silvicultura",
    nome="silvicultura",
    fonte="ibama-rapp-silvicultura",
    pasta_no_portal="silvicultura",
    cnpj="CNPJ",
    ano="Ano",
    textos={
        "Nome Científico": "nome_cientifico",
        "Nome Popular": "nome_popular",
        "Espaçamento": "espacamento",
        "Unidade de medida": "unidade",
        **_SITUACAO,
    },
    anos={"Ano do plantio": "ano_do_plantio", "Ano de corte": "ano_de_corte"},
    numeros={
        "Área efetivo plantio (ha)": "area_plantada_ha",
        "Volume/Quantidade explorado": "volume_explorado",
    },
    numeros_com_ponto={"Nº de árvores total": "arvores"},
)
RELATORIOS = (
    EMISSOES,
    EFLUENTES,
    ENERGIA,
    RESIDUOS_DESTINADOS,
    RESIDUOS_TRANSPORTADOS,
    RESIDUOS_ARMAZENADOS,
    CERTIFICADOS,
    MADEIRA_E_LENHA,
    EXTRACAO_MINERAL,
    PRODUTOS_FLORESTAIS,
    SILVICULTURA,
)


def _cadastro(relatorio: Relatorio) -> cadastros_em_retrato.Cadastro:
    return base.cadastro(
        relatorio.tabela,
        relatorio.nome,
        relatorio.fonte,
        lambda conteudo: ler(relatorio, conteudo),
        relatorio.colunas,
        datas=tuple(relatorio.datas.values()),
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
