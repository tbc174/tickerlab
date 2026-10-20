"""Leitor dos pacotes antigos do ENET: o `.dfp` com o `InfoFinaDFin.xml` (série 1 da base de ML).

Os pacotes de ~2020 para trás não trazem o XML novo (`base/enet.py`). Trazem um arquivo
`<número>.dfp`, que é um zip dentro do zip, com uns doze XMLs. Formato conferido em 20/10/2026 com a
Cia Mineira de Açúcar e Álcool (DFP de 03/2015, versão 2) e a CEB (DFP de 12/2016), comparando com os
dados abertos da CVM:

- **Só três arquivos importam:** `Documento.xml` (CNPJ, versão, data, escala, motivo),
  `PeriodoDemonstracaoFinanceira.xml` (o fim de cada exercício) e `InfoFinaDFin.xml` (as contas). O
  resto é o PDF, anexos e `ResponsavelEsclarecimentoDuvidas.xml` (nome e e-mail de quem entregou):
  `enxugar` guarda só os três, num zip sempre igual para o mesmo conteúdo.
- **Uma conta por bloco `InfoFinaDFin`:** `CodigoTipoDemonstracaoFinanceira` (2 = BPA, 3 = BPP,
  4 = DRE, 5 = DRA, 6 = DFC direto, 7 = DFC indireto, 8 = DMPL, 9 = DVA), `CodigoTipoInformacaoFinanceira`
  (1 = individual, 2 = consolidado), o código em `NumeroConta` e a descrição em `DescricaoConta1`.
- **Valores:** `ValorConta1` é o último exercício, `ValorConta2` o penúltimo e `ValorConta3` o
  antepenúltimo (que os dados abertos não trazem e fica de fora, como no formato novo). Ponto é
  decimal ("85832.0000000000"), diferente do formato novo. A escala é `CodigoEscalaMoeda`: 1 = unidade,
  2 = mil.
- **O que este leitor não traz:** a **DMPL** fica vazia. As colunas de uma conta da DMPL vêm sem nome
  (`ValorConta1` a `ValorConta12`) e a ordem muda de um período para outro no mesmo pacote, então não
  há como saber qual coluna é qual sem inventar. O **ITR** antigo (`.itr`) também não é lido: as colunas
  de valor dele misturam trimestre e acumulado sem rótulo (`FormatoNaoLido`).
- **Conferido contra os dados abertos:** as 1.142 linhas da Cia Mineira (DFC indireto) e as 1.228 da CEB
  (DFC direto) saíram iguais, uma a uma (valor, datas, descrição e escala).
"""

import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass

import pandas as pd
from defusedxml.ElementTree import iterparse

from base.cnpj import formatar, normalizar_cnpj
from base.contas_cvm import COLUNAS
from base.dmpl import COLUNAS_DA_DMPL
from base.enet import ESCALAS, UM_ANO, UM_DIA, DocumentoEnet, montar_tabela

NOME_DO_DFP = re.compile(r"^\d+\.dfp$", re.IGNORECASE)
NOME_DO_ITR = re.compile(r"^\d+\.itr$", re.IGNORECASE)
DOCUMENTO, PERIODOS, CONTAS = (
    "Documento.xml",
    "PeriodoDemonstracaoFinanceira.xml",
    "InfoFinaDFin.xml",
)
ARQUIVOS_GUARDADOS = (DOCUMENTO, PERIODOS, CONTAS)
DEMONSTRACOES = {
    "2": "BPA",
    "3": "BPP",
    "4": "DRE",
    "5": "DRA",
    "6": "DFC_MD",
    "7": "DFC_MI",
    "9": "DVA",
}
DMPL = "8"
GRUPOS = {"1": "ind", "2": "con"}
DO_BALANCO = ("BPA", "BPP")
# a coluna de valor → a ordem dos dados abertos (a terceira, o antepenúltimo, não entra)
COLUNAS_DE_VALOR = {"ValorConta1": "ultimo", "ValorConta2": "penultimo"}
EXERCICIO_ATUAL, EXERCICIO_ANTERIOR = "1", "2"  # NumeroIdentificacaoPeriodo no DFP
DATA_DO_ZIP = (2020, 1, 1, 0, 0, 0)  # fixa: o mesmo conteúdo dá sempre o mesmo zip


class FormatoNaoLido(ValueError):
    """O pacote não está num formato que o TickerLab sabe ler (não é problema de rede)."""


@dataclass(frozen=True)
class _Cabecalho:
    cnpj: str
    empresa: str
    versao: int
    referencia: pd.Timestamp
    escala: float
    motivo: str


def tem_dfp_antigo(pacote: bytes) -> bool:
    """Se o zip do ENET traz um `.dfp` (e não o XML novo)."""
    with zipfile.ZipFile(io.BytesIO(pacote)) as arquivo:
        return any(NOME_DO_DFP.match(n.rsplit("/", 1)[-1]) for n in arquivo.namelist())


def tem_itr_antigo(pacote: bytes) -> bool:
    """Se o zip do ENET traz um `.itr` (formato antigo do ITR, ainda não lido)."""
    with zipfile.ZipFile(io.BytesIO(pacote)) as arquivo:
        return any(NOME_DO_ITR.match(n.rsplit("/", 1)[-1]) for n in arquivo.namelist())


def eh_pacote_enxuto(conteudo: bytes) -> bool:
    """Se o que está guardado é o zip enxuto do formato antigo (e não um XML)."""
    if not zipfile.is_zipfile(io.BytesIO(conteudo)):
        return False
    with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo:
        return set(ARQUIVOS_GUARDADOS) <= set(arquivo.namelist())


def enxugar(pacote: bytes) -> bytes:
    """Um zip só com os três XMLs que importam, sem PDF e sem os dados de quem entregou."""
    with zipfile.ZipFile(io.BytesIO(pacote)) as externo:
        nomes = [
            n for n in externo.namelist() if NOME_DO_DFP.match(n.rsplit("/", 1)[-1])
        ]
        if not nomes:
            raise FormatoNaoLido("o pacote do ENET não tem o .dfp do formato antigo")
        interno = zipfile.ZipFile(io.BytesIO(externo.read(nomes[0])))
    faltam = [n for n in ARQUIVOS_GUARDADOS if n not in interno.namelist()]
    if faltam:
        raise FormatoNaoLido(f"o .dfp do ENET não tem {', '.join(faltam)}")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as enxuto:
        for nome in ARQUIVOS_GUARDADOS:
            info = zipfile.ZipInfo(nome, date_time=DATA_DO_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            enxuto.writestr(info, interno.read(nome))
    return saida.getvalue()


def _data(texto: str | None) -> pd.Timestamp:
    """ "2015-03-31T00:00:00" → 2015-03-31; vazio ou ano 1 (data em branco) → NaT."""
    data = pd.to_datetime((texto or "")[:10], format="%Y-%m-%d", errors="coerce")
    return pd.NaT if data.year == 1 else data


def _folhas(conteudo: bytes, tags: set[str]) -> dict[str, str]:
    """O texto de cada tag pedida (a primeira com texto) em todo o XML."""
    achados: dict[str, str] = {}
    for _, elemento in iterparse(io.BytesIO(conteudo)):
        texto = (elemento.text or "").strip()
        if elemento.tag in tags and texto:
            achados.setdefault(elemento.tag, texto)
    return achados


def _motivo(conteudo: bytes, versao: int) -> str:
    """O motivo da reapresentação da versão lida ("" na versão 1)."""
    motivos: dict[str, str] = {}
    atual: dict[str, str] = {}
    for _, elemento in iterparse(io.BytesIO(conteudo), events=("end",)):
        if elemento.tag in ("VersaoDocumento", "Descricao"):
            atual[elemento.tag] = (elemento.text or "").strip()
        elif elemento.tag == "MotivoReapresentacaoDocumento":
            motivos[atual.get("VersaoDocumento", "")] = atual.get("Descricao", "")
            atual = {}
    return motivos.get(str(versao), "")


def _cabecalho(documento: bytes) -> _Cabecalho:
    campos = _folhas(
        documento,
        {
            "NumeroCnpjCompanhiaAberta",
            "NomeRazaoSocialCompanhiaAberta",
            "NumeroVersaoDocumento",
            "DataReferenciaDocumento",
            "CodigoEscalaMoeda",
        },
    )
    escala = ESCALAS.get(campos.get("CodigoEscalaMoeda", ""))
    if escala is None:
        raise FormatoNaoLido(
            f"escala desconhecida no .dfp do ENET: {campos.get('CodigoEscalaMoeda')!r}"
        )
    versao = int(campos.get("NumeroVersaoDocumento") or 0)
    completo = normalizar_cnpj(campos.get("NumeroCnpjCompanhiaAberta", ""))
    return _Cabecalho(
        cnpj=formatar(completo) if completo else "",
        empresa=campos.get("NomeRazaoSocialCompanhiaAberta", ""),
        versao=versao,
        referencia=_data(campos.get("DataReferenciaDocumento")),
        escala=escala,
        motivo=_motivo(documento, versao),
    )


def _fins_dos_exercicios(
    periodos: bytes, referencia: pd.Timestamp
) -> dict[str, pd.Timestamp]:
    """O fim do último e do penúltimo exercício, lidos do arquivo de períodos."""
    fins: dict[str, pd.Timestamp] = {}
    atual: dict[str, str] = {}
    for _, elemento in iterparse(io.BytesIO(periodos), events=("end",)):
        if elemento.tag in ("NumeroIdentificacaoPeriodo", "DataFimPeriodo"):
            atual[elemento.tag] = (elemento.text or "").strip()
        elif elemento.tag == "PeriodoDemonstracaoFinanceira":
            fins[atual.get("NumeroIdentificacaoPeriodo", "")] = _data(
                atual.get("DataFimPeriodo")
            )
            atual = {}
    if fins.get(EXERCICIO_ATUAL) != referencia or pd.isna(fins.get(EXERCICIO_ANTERIOR)):
        raise FormatoNaoLido(
            "os períodos do .dfp do ENET não batem com a data do documento"
        )
    return {"ultimo": fins[EXERCICIO_ATUAL], "penultimo": fins[EXERCICIO_ANTERIOR]}


def _contas_cruas(contas: bytes) -> Iterator[dict[str, str]]:
    """Cada bloco `InfoFinaDFin` como um dicionário de tag → texto (só as tags que importam)."""
    quer = {
        "CodigoTipoDemonstracaoFinanceira",
        "CodigoTipoInformacaoFinanceira",
        "NumeroConta",
        "IndicadorContaFixa",
        "DescricaoConta1",
        *COLUNAS_DE_VALOR,
    }
    bloco: dict[str, str] = {}
    for _, elemento in iterparse(io.BytesIO(contas)):
        if elemento.tag == "InfoFinaDFin":
            yield bloco
            bloco = {}
            elemento.clear()
        elif elemento.tag in quer:
            bloco[elemento.tag] = (elemento.text or "").strip()


def _numero(texto: str) -> float:
    return float(texto) if texto else float("nan")


def _linhas_da_conta(
    bloco: dict[str, str], fins: dict[str, pd.Timestamp], escala: float
) -> list[dict[str, object]]:
    demonstracao = DEMONSTRACOES.get(bloco.get("CodigoTipoDemonstracaoFinanceira", ""))
    grupo = GRUPOS.get(bloco.get("CodigoTipoInformacaoFinanceira", ""))
    if not demonstracao or not grupo or not bloco.get("NumeroConta"):
        return []  # a DMPL e o que não é conta do plano ficam de fora
    linhas = []
    for coluna, ordem in COLUNAS_DE_VALOR.items():
        fim = fins[ordem]
        inicio = pd.NaT if demonstracao in DO_BALANCO else fim - UM_ANO + UM_DIA
        linhas.append(
            {
                "demonstracao": demonstracao,
                "grupo": grupo,
                "ordem": ordem,
                "inicio": inicio,
                "fim": fim,
                "conta": bloco["NumeroConta"],
                "descricao": bloco.get("DescricaoConta1", ""),
                "conta_fixa": bloco.get("IndicadorContaFixa", "").lower() == "true",
                "valor": _numero(bloco.get(coluna, "")) * escala,
            }
        )
    return linhas


def ler_dfp_antigo(enxuto: bytes) -> DocumentoEnet:
    """O documento (contas individuais e consolidadas) de um zip enxuto do `.dfp` antigo."""
    with zipfile.ZipFile(io.BytesIO(enxuto)) as arquivo:
        documento, periodos, contas = (arquivo.read(n) for n in ARQUIVOS_GUARDADOS)
    cabecalho = _cabecalho(documento)
    fins = _fins_dos_exercicios(periodos, cabecalho.referencia)
    linhas = [
        linha
        for bloco in _contas_cruas(contas)
        for linha in _linhas_da_conta(bloco, fins, cabecalho.escala)
    ]
    identidade: dict[str, object] = {
        "cnpj": cabecalho.cnpj,
        "empresa": cabecalho.empresa,
        "documento": "DFP",
        "referencia": cabecalho.referencia,
    }
    return DocumentoEnet(
        cnpj=cabecalho.cnpj,
        empresa=cabecalho.empresa,
        documento="DFP",
        referencia=cabecalho.referencia,
        versao=cabecalho.versao,
        motivo=cabecalho.motivo,
        contas=montar_tabela(linhas, COLUNAS, identidade, cabecalho.versao),
        dmpl=pd.DataFrame(columns=list(COLUNAS_DA_DMPL)),
    )
