"""Leitores dos contratos e das despesas por CNPJ de GO, MS e da capital de SP (API dados C5).

Uso interno; licença a confirmar (ADR 0102, Emenda 2), exceto a de SP (CC0). Mesmo molde de
`base/contratos_tces.py`: só leitura de bytes já baixados, linhas simples e **só de pessoa jurídica**
(ADR 0075, CNPJ de 14 caracteres com DV certo). Linha de pessoa física, de CPF mascarado ou de CNPJ com DV
errado é descartada e contada em `Leitura.descartadas`.

**Nunca entram** nomes (credor, contratado, empreendimento), endereço nem texto livre (objeto, atividade).
Cada leitor copia só os campos da lista da sua fonte.

**Sem olhar o futuro**: nenhuma das fontes traz a data em que a linha ficou pública; toda linha leva
`disponivel_em`, a data da coleta que o chamador informa.

Formatos conferidos em 03/11/2026 (rodada de aprofundamento de fontes, `evidencias/territorio_n_co`):
- **GO, licenças do Ipê** (CKAN dadosabertos.go.gov.br, CSV mensal, vírgula, UTF-8, CC BY): `cpf_cnpj` vem
  com CPF mascarado nas pessoas físicas. As datas não foram vistas (evidência reduzida ao cabeçalho).
- **MS, despesas por credor** (CKAN www.dados.ms.gov.br, dump CSV mensal desde 2012): coluna `Cpf/Cnpj`; o
  `Credor` (nome) nunca é lido. O mês vem do nome do recurso, por isso é argumento.
- **SP capital, extrato de contrato** (CKAN dados.prefeitura.sp.gov.br, CSV anual, CC0): o CSV não foi
  amostrado; os cabeçalhos são procurados por apelidos e a primeira carga confere o mapa.
"""

import csv
import io
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date

from base.contratos_tces import (
    Leitura,
    Linha,
    _carimbar,
    _cnpj_de_pj,
    _copiar,
    _data_iso,
    _numero,
    _texto,
)

SEPARADORES_DO_CSV = (",", ";", "\t")
LINHAS_DE_TITULO_MAX = 10  # até onde procurar o cabeçalho
CELULAS_MINIMAS_DO_CABECALHO = 2  # título tem 0 ou 1 célula cheia; cabeçalho tem várias
NAO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")

# GO: a chave é o nome na fonte; o valor é o nome na linha
CAMPOS_GO = {
    "numero_licenca": "numero_licenca",
    "versao": "versao",
    "municipio_empreendimento": "municipio",
    "tipo_licenca": "tipo_licenca",
    "status": "situacao",
    "orgao": "orgao",
}
# MS: a coluna "Documento" é o número do documento da despesa (empenho), não o do credor
CAMPOS_MS = {
    "Orgão": "orgao",
    "Função": "funcao",
    "Sub-Função": "subfuncao",
    "Elemento de Despesa": "elemento_despesa",
    "Modalidade": "modalidade",
    "Tipo de Licitação": "tipo_licitacao",
    "Documento": "numero_documento",
}
DOCUMENTO_MS = "Cpf/Cnpj"
VALORES_MS = {"Empenhado": "empenhado", "Liquidado": "liquidado", "Pago": "pago"}

# SP capital: cada campo da linha tem os apelidos do cabeçalho (normalizados), em ordem de preferência
DOCUMENTO_SP = (
    "cnpj",
    "cnpj_cpf",
    "cpf_cnpj",
    "cnpj_contratada",
    "cnpj_fornecedor",
    "documento",
)
APELIDOS_SP = {
    "numero_contrato": (
        "numero_contrato",
        "numero_do_contrato",
        "n_contrato",
        "contrato",
        "num_contrato",
    ),
    "numero_processo": (
        "numero_processo",
        "numero_do_processo",
        "processo",
        "n_processo",
        "num_processo",
        "processo_administrativo",
    ),
    "modalidade": ("modalidade", "modalidade_licitacao"),
    "orgao": ("orgao", "nome_do_orgao", "secretaria", "unidade", "orgao_contratante"),
}
DATAS_SP = {
    "data_assinatura": (
        "data_assinatura",
        "data_de_assinatura",
        "data_da_assinatura",
        "dt_assinatura",
        "data_contrato",
    ),
    "vigencia_inicio": ("inicio_vigencia", "data_inicio_vigencia", "vigencia_inicio"),
    "vigencia_fim": ("fim_vigencia", "data_fim_vigencia", "vigencia_fim"),
}
VALORES_SP = ("valor_total", "valor_contrato", "valor", "valor_global", "valor_r")


def _decodificar(corpo: bytes) -> str:
    try:
        return corpo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return corpo.decode("cp1252", errors="replace")


def _sem_titulo(texto: str) -> str:
    """Tira as linhas de título que alguns extratos (SP capital) têm antes do cabeçalho."""
    linhas = texto.splitlines(keepends=True)
    for posicao, linha in enumerate(linhas[:LINHAS_DE_TITULO_MAX]):
        celulas = [c for c in re.split(r"[,;\t]", linha) if c.strip(' "\r\n')]
        if len(celulas) >= CELULAS_MINIMAS_DO_CABECALHO:
            return "".join(linhas[posicao:])
    return texto


def _separador(texto: str) -> str:
    cabecalho = texto.split("\n", 1)[0]
    return max(SEPARADORES_DO_CSV, key=cabecalho.count)


def _linhas_do_csv(corpo: bytes) -> list[dict[str, str]]:
    texto = _sem_titulo(_decodificar(corpo))
    leitor = csv.DictReader(io.StringIO(texto), delimiter=_separador(texto))
    return [
        {chave: valor for chave, valor in item.items() if chave and valor is not None}
        for item in leitor
    ]


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return NAO_ALFANUMERICO.sub("_", sem_acento.lower()).strip("_")


def _por_apelido(item: Mapping[str, str], apelidos: Sequence[str]) -> str | None:
    """O primeiro apelido (já normalizado) que existe no cabeçalho da linha e tem valor."""
    normalizado = {_normalizar(chave): valor for chave, valor in item.items()}
    return next((v for a in apelidos if (v := _texto(normalizado.get(a)))), None)


# ---------------------------------------------------------------------------------------------- GO


def ler_go_licencas(corpo: bytes, coletado_em: date) -> Leitura:
    """Lê um CSV mensal de licenças ambientais do Ipê (GO); só `cpf_cnpj` que for CNPJ válido.

    Nome do empreendimento, razão social e atividade não são lidos.
    """
    leitura = Leitura()
    for item in _linhas_do_csv(corpo):
        documento = _cnpj_de_pj(item.get("cpf_cnpj"))
        if documento is None:
            leitura.descartadas += 1
            continue
        linha = _copiar(item, CAMPOS_GO)
        linha.update(
            cnpj=documento,
            data_emissao=_data_iso(item.get("data_emissao")),
            data_validade=_data_iso(item.get("data_validade")),
        )
        leitura.linhas.append(_carimbar(linha, "go", "licencas_ipe", coletado_em))
    return leitura


# ---------------------------------------------------------------------------------------------- MS


def ler_ms_despesas(corpo: bytes, ano: int, mes: int, coletado_em: date) -> Leitura:
    """Lê o dump mensal de despesas por credor do MS; só `Cpf/Cnpj` que for CNPJ válido.

    O nome do credor nunca é lido. `ano` e `mes` são os do recurso (a fonte não traz a data).
    Empenhado, liquidado e pago são colunas da mesma linha e não se somam.
    """
    leitura = Leitura()
    for item in _linhas_do_csv(corpo):
        documento = _cnpj_de_pj(item.get(DOCUMENTO_MS))
        if documento is None:
            leitura.descartadas += 1
            continue
        linha = _copiar(item, CAMPOS_MS)
        linha.update(cnpj=documento, ano=str(ano), mes=f"{mes:02d}")
        linha.update(
            {destino: _numero(item.get(nome)) for nome, destino in VALORES_MS.items()}
        )
        leitura.linhas.append(_carimbar(linha, "ms", "despesas", coletado_em))
    return leitura


# ---------------------------------------------------------------------------------------------- SP


def ler_sp_capital_contratos(corpo: bytes, coletado_em: date) -> Leitura:
    """Lê o extrato anual de contratos da Prefeitura de São Paulo (CC0); só contratada com CNPJ válido.

    Os cabeçalhos são achados por apelidos (o CSV não foi amostrado na rodada de fontes); nome da
    contratada e objeto nunca são lidos.
    """
    leitura = Leitura()
    for item in _linhas_do_csv(corpo):
        documento = _cnpj_de_pj(_por_apelido(item, DOCUMENTO_SP))
        if documento is None:
            leitura.descartadas += 1
            continue
        linha: Linha = {c: _por_apelido(item, a) for c, a in APELIDOS_SP.items()}
        linha.update({c: _data_iso(_por_apelido(item, a)) for c, a in DATAS_SP.items()})
        linha.update(cnpj=documento, valor=_numero(_por_apelido(item, VALORES_SP)))
        leitura.linhas.append(_carimbar(linha, "sp_capital", "contratos", coletado_em))
    return leitura
