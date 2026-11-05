"""Leitores dos contratos e das despesas por CNPJ de quatro tribunais de contas (API dados C1 a C4):
TCE-PE, TCE-SP, TCE-CE (SIM) e TCE-RS (LicitaCon). Uso interno; licença a confirmar (ADR 0102, Emenda 2).

Só leitura de bytes já baixados: o download, o ritmo e o registro da fonte ficam fora daqui. Cada
leitor devolve linhas simples (dicionários com texto, número e data ISO) e **só de pessoa jurídica**
(ADR 0075): o documento precisa ser um CNPJ de 14 dígitos com o DV certo. Linha de pessoa física, de
CPF parcial ou de CNPJ com DV errado é descartada e contada em `Leitura.descartadas`.

**Nunca entram** nomes (de fornecedor, contratado ou gestor), endereço, telefone, CPF nem texto livre
(objeto, justificativa): o nome de um MEI é o da pessoa, e o TCE-SP traz CPF dentro do nome do
fornecedor ("FULANO 11813999805"). Cada leitor copia só os campos da lista do seu tribunal.

**Sem olhar o futuro**: nenhuma das quatro fontes traz a data em que a linha ficou pública. Toda linha
leva `disponivel_em`, a data da coleta que o chamador informa: o dado só vale a partir dela.

Formatos conferidos em 03/11/2026 (rodada de aprofundamento de fontes, `evidencias/regionais`):
- **PE** (Dados Abertos, JSON em ISO-8859-1, `{"resposta": {"conteudo": [...]}}`): o filtro é
  `NumeroDocumentoAjustado`, nunca `TipoCredor=2` (em despesas há CPF mascarado com esse tipo).
  `LicitacoesDetalhes` só foi visto vazio: o mapa de campos dela é o mais provável, a conferir na 1ª carga.
- **SP** (Portal da Transparência Municipal, JSON): `id_fornecedor` é texto ("CNPJ - PESSOA JURÍDICA -
  <14 dígitos>"); valor com vírgula decimal; os eventos (empenhado, liquidado, pago) não se somam.
- **CE** (SIM, `elements`): `contratados` liga ao `contratos` por município, número e data do contrato.
- **RS** (LicitaCon, ZIP por órgão): só o `contrato.csv`; o `pessoas.csv` (com CPF) nem é aberto.
"""

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from base import cnpj

Linha = dict[str, str | float | None]

CODIFICACAO_PE = "iso-8859-1"
ESPACOS = re.compile(r"\s+")
DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
SO_DIGITOS = re.compile(r"\D")
CONTRATO_DO_RS = "contrato.csv"
TIPO_PESSOA_JURIDICA_RS = "J"
MARCA_CNPJ_SP = "CNPJ"
SEPARADORES_DO_CSV = (";", ",")

# campos copiados de cada tabela do TCE-PE: a chave é o nome na fonte, o valor é o nome na linha
CAMPOS_PE_CONTRATO = {
    "CodigoContrato": "codigo_contrato",
    "NumeroContrato": "numero_contrato",
    "AnoContrato": "ano_contrato",
    "CodigoUG": "codigo_ug",
    "CodigoEfiscoUG": "codigo_efisco_ug",
    "Municipio": "municipio",
    "Esfera": "esfera",
    "Situacao": "situacao",
    "Estagio": "estagio",
    "TipoProcesso": "tipo_processo",
    "NumeroProcesso": "numero_processo",
    "LinkArquivo": "link",
}
CAMPOS_PE_ADITIVO = {
    "CodigoContrato": "codigo_contrato",
    "NumeroContrato": "numero_contrato",
    "AnoContrato": "ano_contrato",
    "NumeroTermoAditivo": "numero_aditivo",
    "AnoTermoAditivo": "ano_aditivo",
    "CodigoUG": "codigo_ug",
    "CodigoEfiscoUG": "codigo_efisco_ug",
    "Municipio": "municipio",
    "Situacao": "situacao",
    "Estagio": "estagio",
    "LinkArquivo": "link",
}
CAMPOS_PE_LICITACAO = {
    "CodigoLicitacao": "codigo_licitacao",
    "NumeroLicitacao": "numero_licitacao",
    "AnoLicitacao": "ano_licitacao",
    "Modalidade": "modalidade",
    "CodigoUG": "codigo_ug",
    "CodigoEfiscoUG": "codigo_efisco_ug",
    "Municipio": "municipio",
    "Situacao": "situacao",
    "LinkArquivo": "link",
}
CAMPOS_PE = {
    "contratos": CAMPOS_PE_CONTRATO,
    "aditivos": CAMPOS_PE_ADITIVO,
    "licitacoes": CAMPOS_PE_LICITACAO,
}
CAMPOS_SP = {
    "mes": "mes",
    "evento": "evento",
    "nr_empenho": "numero_empenho",
}
CAMPOS_CE_CONTRATADO = {
    "codigo_municipio": "codigo_municipio",
    "numero_contrato": "numero_contrato",
    "codigo_tipo_negociante": "codigo_tipo_negociante",
    "data_referencia_doc": "data_referencia",
}
CAMPOS_CE_CONTRATO = {
    "tipo_contrato": "tipo_contrato",
    "modalide_contrato": "modalidade",  # a fonte grafa assim
    "numero_processo_adm": "numero_processo",
}
CAMPOS_RS = {
    "CD_ORGAO": "codigo_orgao",
    "NR_LICITACAO": "numero_licitacao",
    "ANO_LICITACAO": "ano_licitacao",
    "CD_TIPO_MODALIDADE": "codigo_modalidade",
    "NR_CONTRATO": "numero_contrato",
    "ANO_CONTRATO": "ano_contrato",
    "TP_INSTRUMENTO": "tipo_instrumento",
    "NR_PROCESSO": "numero_processo",
    "ANO_PROCESSO": "ano_processo",
    "LINK_LICITACON_CIDADAO": "link",
}


@dataclass
class Leitura:
    """O que um leitor achou: as linhas de pessoa jurídica e quantas linhas ficaram de fora."""

    linhas: list[Linha] = field(default_factory=list)
    descartadas: int = 0


def _texto(valor: object) -> str | None:
    """Texto sem espaços das pontas e com os do meio colapsados; None se vazio."""
    if valor is None:
        return None
    limpo = ESPACOS.sub(" ", str(valor)).strip()
    return limpo or None


def _cnpj_de_pj(valor: object) -> str | None:
    """O CNPJ de 14 caracteres com DV certo, ou None (CPF, parcial e DV errado ficam de fora)."""
    texto = _texto(valor)
    if texto is None:
        return None
    completo = cnpj.completo(texto)
    return completo if completo and cnpj.dv_confere(completo) else None


def _numero(valor: object) -> float | None:
    """Valor em reais; aceita "10000.00", "2959,50" e "1.234,56"."""
    texto = _texto(valor)
    if texto is None:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _data_iso(valor: object) -> str | None:
    """Data em AAAA-MM-DD a partir de "dd/mm/aaaa" ou de "aaaa-mm-ddT..."; None se não for data."""
    texto = _texto(valor)
    if texto is None:
        return None
    br = DATA_BR.fullmatch(texto)
    try:
        if br:
            return date(int(br[3]), int(br[2]), int(br[1])).isoformat()
        return datetime.fromisoformat(texto[:10]).date().isoformat()
    except ValueError:
        return None


def _copiar(origem: Mapping[str, object], campos: Mapping[str, str]) -> Linha:
    return {destino: _texto(origem.get(nome)) for nome, destino in campos.items()}


def _carimbar(linha: Linha, tribunal: str, tabela: str, coletado_em: date) -> Linha:
    return {
        "tribunal": tribunal,
        "tabela": tabela,
        "disponivel_em": coletado_em.isoformat(),
        **linha,
    }


# ---------------------------------------------------------------------------------------------- PE


def ler_pe(corpo: bytes, tabela: str, coletado_em: date) -> Leitura:
    """Lê uma resposta do TCE-PE (`contratos`, `aditivos` ou `licitacoes`).

    O CNPJ vem de `NumeroDocumentoAjustado` (o campo que filtra bem); `TipoCredor` não é consultado.
    A vigência ("12/03/2025 a 12/07/2025") vira início e fim em ISO.
    """
    campos = CAMPOS_PE[tabela]
    resposta = json.loads(corpo.decode(CODIFICACAO_PE))["resposta"]
    leitura = Leitura()
    for item in resposta.get("conteudo") or []:
        documento = _cnpj_de_pj(item.get("NumeroDocumentoAjustado"))
        if documento is None:
            leitura.descartadas += 1
            continue
        inicio, fim = _vigencia_pe(item.get("Vigencia"))
        linha = _copiar(item, campos)
        if tabela != "licitacoes":
            linha.update(vigencia_inicio=inicio, vigencia_fim=fim)
        if tabela == "contratos":
            linha["valor"] = _numero(item.get("Valor"))
        linha["cnpj"] = documento
        leitura.linhas.append(_carimbar(linha, "pe", tabela, coletado_em))
    return leitura


def _vigencia_pe(valor: object) -> tuple[str | None, str | None]:
    datas = DATA_BR.findall(_texto(valor) or "")
    isos = [_data_iso("/".join(d)) for d in datas]
    return (isos[0] if isos else None, isos[1] if len(isos) > 1 else None)


# ---------------------------------------------------------------------------------------------- SP


def ler_sp(corpo: bytes, ano: int, coletado_em: date) -> Leitura:
    """Lê as despesas de um município e mês do TCE-SP; só fornecedor que a própria fonte marca como CNPJ.

    O nome do fornecedor nunca é lido. Cada evento do empenho é uma linha (não se soma empenhado,
    liquidado e pago). `ano` é o da consulta: a fonte só traz o mês por extenso.
    """
    dados = json.loads(corpo.decode("utf-8"))
    registros = dados if isinstance(dados, list) else dados.get("despesas", [])
    leitura = Leitura()
    for item in registros:
        documento = _cnpj_do_fornecedor_sp(item.get("id_fornecedor"))
        if documento is None:
            leitura.descartadas += 1
            continue
        linha = _copiar(item, CAMPOS_SP)
        linha.update(
            cnpj=documento,
            ano=str(ano),
            data_emissao=_data_iso(item.get("dt_emissao_despesa")),
            valor=_numero(item.get("vl_despesa")),
        )
        leitura.linhas.append(_carimbar(linha, "sp", "despesas", coletado_em))
    return leitura


def _cnpj_do_fornecedor_sp(valor: object) -> str | None:
    texto = _texto(valor)
    if texto is None or not texto.upper().startswith(MARCA_CNPJ_SP):
        return None  # "CPF - PESSOA FÍSICA - 123456" e o que não for CNPJ
    return _cnpj_de_pj(SO_DIGITOS.sub("", texto.rsplit("-", 1)[-1]))


def anos_sem_dado(linhas_por_ano: Mapping[int, int]) -> list[int]:
    """Os anos consultados em que não veio nenhuma linha de pessoa jurídica (para listar no relatório)."""
    return sorted(ano for ano, quantas in linhas_por_ano.items() if quantas == 0)


# ---------------------------------------------------------------------------------------------- CE


def ler_ce(contratados: bytes, contratos: bytes, coletado_em: date) -> Leitura:
    """Junta `contratados` e `contratos` do SIM do TCE-CE pela chave (município, número, data do contrato).

    Só contratado com CNPJ válido. Guarda o id do PNCP (`id_pncp`, vazio vira None) para casar com a
    carga do PNCP sem duplicar. Nome, endereço, telefone, CEP, objeto e CPF do gestor não são lidos.
    """
    por_chave = {_chave_ce(c): c for c in _elementos(contratos)}
    leitura = Leitura()
    for contratado in _elementos(contratados):
        documento = _cnpj_de_pj(contratado.get("numero_documento_negociante"))
        if documento is None:
            leitura.descartadas += 1
            continue
        contrato = por_chave.get(_chave_ce(contratado), {})
        linha = _copiar(contratado, CAMPOS_CE_CONTRATADO) | _copiar(
            contrato, CAMPOS_CE_CONTRATO
        )
        linha.update(
            cnpj=documento,
            data_contrato=_data_iso(contratado.get("data_contrato")),
            vigencia_inicio=_data_iso(contrato.get("data_inicio_vigencia_contrato")),
            vigencia_fim=_data_iso(contrato.get("data_fim_vigencia_contrato")),
            valor=_numero(contrato.get("valor_total_contrato")),
            id_pncp=_texto(contrato.get("numero_id_contrato_pncp")),
            com_contrato=str(bool(contrato)),
        )
        leitura.linhas.append(_carimbar(linha, "ce", "contratos", coletado_em))
    return leitura


def _elementos(corpo: bytes) -> list[dict[str, object]]:
    return json.loads(corpo.decode("utf-8")).get("elements", [])


def _chave_ce(item: Mapping[str, object]) -> tuple[str | None, str | None, str | None]:
    return (
        _texto(item.get("codigo_municipio")),
        _texto(item.get("numero_contrato")),
        _data_iso(item.get("data_contrato")),
    )


# ---------------------------------------------------------------------------------------------- RS


def ler_rs(zip_do_orgao: bytes, coletado_em: date) -> Leitura:
    """Lê o `contrato.csv` do pacote de um órgão do LicitaCon; só `TP_DOCUMENTO=J` com CNPJ válido.

    Os outros arquivos do ZIP (em especial o `pessoas.csv`, com CPF) nunca são abertos.
    """
    with zipfile.ZipFile(io.BytesIO(zip_do_orgao)) as pacote:
        nome = next(
            (n for n in pacote.namelist() if n.lower().endswith(CONTRATO_DO_RS)), None
        )
        if nome is None:
            return Leitura()
        texto = pacote.read(nome).decode("utf-8-sig")
    leitura = Leitura()
    for item in csv.DictReader(io.StringIO(texto), delimiter=_separador(texto)):
        documento = _cnpj_de_pj(item.get("NR_DOCUMENTO"))
        if item.get("TP_DOCUMENTO") != TIPO_PESSOA_JURIDICA_RS or documento is None:
            leitura.descartadas += 1
            continue
        linha = _copiar(item, CAMPOS_RS)
        linha.update(
            cnpj=documento,
            vigencia_inicio=_data_iso(item.get("DT_INICIO_VIGENCIA")),
            vigencia_fim=_data_iso(item.get("DT_FINAL_VIGENCIA")),
            data_assinatura=_data_iso(item.get("DT_ASSINATURA")),
            valor=_numero(item.get("VL_CONTRATO")),
        )
        leitura.linhas.append(_carimbar(linha, "rs", "contratos", coletado_em))
    return leitura


def _separador(texto: str) -> str:
    cabecalho = texto.split("\n", 1)[0]
    return max(SEPARADORES_DO_CSV, key=cabecalho.count)


def pacotes_de_contratos(busca_ckan: bytes) -> list[tuple[str, str]]:
    """(nome do pacote, endereço do ZIP) dos pacotes de contratos de uma resposta `package_search` do CKAN."""
    achados = []
    for pacote in json.loads(busca_ckan.decode("utf-8"))["result"]["results"]:
        if not str(pacote.get("name", "")).startswith("contratos-"):
            continue
        achados.extend(
            (pacote["name"], recurso["url"])
            for recurso in pacote.get("resources", [])
            if str(recurso.get("url", "")).lower().endswith(".zip")
        )
    return achados


def pendentes(todos: Iterable[str], concluidos: Iterable[str]) -> Sequence[str]:
    """Os pacotes que faltam, na ordem do índice: a coleta retoma de onde parou, sem baixar de novo."""
    feitos = set(concluidos)
    return [nome for nome in todos if nome not in feitos]
