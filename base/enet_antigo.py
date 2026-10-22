"""Leitor dos pacotes antigos do ENET: o `.dfp` e o `.itr` com o `InfoFinaDFin.xml` (série 1 da base de ML).

Os pacotes de ~2020 para trás não trazem o XML novo (`base/enet.py`). Trazem um arquivo
`<número>.dfp` (ou `.itr`), que é um zip dentro do zip, com uns doze XMLs. Formato conferido em 20/10/2026 com a
Cia Mineira de Açúcar e Álcool (DFP de 03/2015, versão 2) e a CEB (DFP de 12/2016), comparando com os
dados abertos da CVM:

- **Só três arquivos importam** (iguais no `.dfp` e no `.itr`): `Documento.xml` (CNPJ, versão, data, escala, motivo),
  `PeriodoDemonstracaoFinanceira.xml` (o fim de cada exercício) e `InfoFinaDFin.xml` (as contas). O
  resto é o PDF, anexos e `ResponsavelEsclarecimentoDuvidas.xml` (nome e e-mail de quem entregou):
  `enxugar` guarda só os três, num zip sempre igual para o mesmo conteúdo.
- **Uma conta por bloco `InfoFinaDFin`:** `CodigoTipoDemonstracaoFinanceira` (2 = BPA, 3 = BPP,
  4 = DRE, 5 = DRA, 6 = DFC direto, 7 = DFC indireto, 8 = DMPL, 9 = DVA), `CodigoTipoInformacaoFinanceira`
  (1 = individual, 2 = consolidado), o código em `NumeroConta` e a descrição em `DescricaoConta1`.
- **Valores:** ponto é decimal ("85832.0000000000"), diferente do formato novo. A escala é
  `CodigoEscalaMoeda`: 1 = unidade, 2 = mil. `CodigoTipoDocumento`: 3 = ITR, 4 = DFP (outro valor é recusado).
- **A coluna `ValorContaN` é o período de número N** (`NumeroIdentificacaoPeriodo` do arquivo de períodos),
  nos dois documentos. No `.dfp`: 1 = último exercício, 2 = penúltimo, 3 = antepenúltimo (fica de fora, os
  dados abertos também não trazem).
  No `.itr` (conferido em 21/10/2026 com a Cia Mineira e a CEB, ITR de 2012 a 2016): 2 = trimestre atual,
  3 = fim do exercício anterior (balanço), 4 = acumulado do ano, 5 = mesmo trimestre do ano anterior,
  6 = acumulado do ano anterior; a 1 é o exercício corrente inteiro (sem valor). O balanço usa só a 2 e a 3; o
  resultado, o abrangente, o fluxo de caixa e o valor adicionado usam a 2, 4, 5 e 6 (o fluxo e o valor adicionado
  só a 4 e a 6). As colunas que o quadro não usa vêm com zero, então só se leem as colunas com algum valor no
  quadro. No 1º trimestre a 2 e a 4 (e a 5 e a 6) são o mesmo período e a empresa preenche só uma delas: vale a que
  tem valor; duas com valores diferentes são recusadas.
- **A DMPL tem posições fixas** (conferido contra os dados abertos nos quatro pacotes): `ValorConta1` a `8` são
  capital social, reservas de capital, reservas de lucro, lucros ou prejuízos acumulados, outros resultados
  abrangentes, patrimônio líquido, não controladores e patrimônio líquido consolidado (o individual só tem as seis
  primeiras). Cada bloco da DMPL traz o número do período dele; o bloco **sem período** (número 0, que aparece no
  `.dfp` com saldos de anos mais velhos que o documento) fica de fora, porque não há data para ele.
- **Conferido contra os dados abertos da CVM** (todas as demonstrações, DMPL inclusa; valor, datas e escala, uma
  linha a uma): DFP da Cia Mineira (03/2015) e da CEB (12/2016); ITR da Cia Mineira (06/2015) e da CEB (03/2012,
  09/2012, 03/2016 e 06/2016). Zero divergência nos sete pacotes (1.850 a 2.206 linhas cada).
- **Anos sem leitura:** nenhum dos pacotes conferidos ficou de fora. O que o leitor não entende (tipo de documento
  novo, períodos que não batem com a data, dois valores para o mesmo período) levanta `FormatoNaoLido`, sem
  inventar coluna.
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
NOME_DO_PACOTE = re.compile(r"^\d+\.(dfp|itr)$", re.IGNORECASE)
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
TIPOS_DE_DOCUMENTO = {"3": "ITR", "4": "DFP"}  # CodigoTipoDocumento
# a coluna `ValorContaN` é o período N: o número do período → a ordem dos dados abertos
PERIODOS_DO_DFP = {"1": "ultimo", "2": "penultimo"}  # o 3 (antepenúltimo) não entra
PERIODOS_DO_BALANCO_ITR = {"2": "ultimo", "3": "penultimo"}
PERIODOS_DO_ITR = {"2": "ultimo", "4": "ultimo", "5": "penultimo", "6": "penultimo"}
# a posição da coluna na DMPL → a coluna canônica de `base/dmpl.py`
COLUNAS_DA_DMPL_ANTIGA = {
    "ValorConta1": "capital_social",
    "ValorConta2": "reservas_de_capital",
    "ValorConta3": "reservas_de_lucro",
    "ValorConta4": "lucros_acumulados",
    "ValorConta5": "outros_resultados_abrangentes",
    "ValorConta6": "patrimonio_liquido",
    "ValorConta7": "nao_controladores",
    "ValorConta8": "patrimonio_liquido_consolidado",
}
COLUNAS_DE_VALOR = tuple(COLUNAS_DA_DMPL_ANTIGA)
DATA_DO_ZIP = (2020, 1, 1, 0, 0, 0)  # fixa: o mesmo conteúdo dá sempre o mesmo zip


class FormatoNaoLido(ValueError):
    """O pacote não está num formato que o TickerLab sabe ler (não é problema de rede)."""


@dataclass(frozen=True)
class _Cabecalho:
    tipo: str
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
    """Se o zip do ENET traz um `.itr` (formato antigo do ITR)."""
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
            n for n in externo.namelist() if NOME_DO_PACOTE.match(n.rsplit("/", 1)[-1])
        ]
        if not nomes:
            raise FormatoNaoLido("o pacote do ENET não tem o .dfp nem o .itr antigo")
        interno = zipfile.ZipFile(io.BytesIO(externo.read(nomes[0])))
    faltam = [n for n in ARQUIVOS_GUARDADOS if n not in interno.namelist()]
    if faltam:
        raise FormatoNaoLido(f"o pacote antigo do ENET não tem {', '.join(faltam)}")
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
            "CodigoTipoDocumento",
            "NumeroCnpjCompanhiaAberta",
            "NomeRazaoSocialCompanhiaAberta",
            "NumeroVersaoDocumento",
            "DataReferenciaDocumento",
            "CodigoEscalaMoeda",
        },
    )
    tipo = TIPOS_DE_DOCUMENTO.get(campos.get("CodigoTipoDocumento", ""))
    if tipo is None:
        raise FormatoNaoLido(
            "tipo de documento desconhecido no pacote antigo do ENET: "
            f"{campos.get('CodigoTipoDocumento')!r}"
        )
    escala = ESCALAS.get(campos.get("CodigoEscalaMoeda", ""))
    if escala is None:
        raise FormatoNaoLido(
            "escala desconhecida no pacote antigo do ENET: "
            f"{campos.get('CodigoEscalaMoeda')!r}"
        )
    versao = int(campos.get("NumeroVersaoDocumento") or 0)
    completo = normalizar_cnpj(campos.get("NumeroCnpjCompanhiaAberta", ""))
    return _Cabecalho(
        tipo=tipo,
        cnpj=formatar(completo) if completo else "",
        empresa=campos.get("NomeRazaoSocialCompanhiaAberta", ""),
        versao=versao,
        referencia=_data(campos.get("DataReferenciaDocumento")),
        escala=escala,
        motivo=_motivo(documento, versao),
    )


def _periodos(periodos: bytes) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """O (início, fim) de cada período do arquivo de períodos, pelo número dele."""
    achados: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    atual: dict[str, str] = {}
    campos = ("NumeroIdentificacaoPeriodo", "DataInicioPeriodo", "DataFimPeriodo")
    for _, elemento in iterparse(io.BytesIO(periodos), events=("end",)):
        if elemento.tag in campos:
            atual[elemento.tag] = (elemento.text or "").strip()
        elif elemento.tag == "PeriodoDemonstracaoFinanceira":
            achados[atual.get("NumeroIdentificacaoPeriodo", "")] = (
                _data(atual.get("DataInicioPeriodo")),
                _data(atual.get("DataFimPeriodo")),
            )
            atual = {}
    return achados


def _conferir_periodos(
    cabecalho: _Cabecalho, periodos: dict[str, tuple[pd.Timestamp, pd.Timestamp]]
) -> None:
    """Os períodos do arquivo têm de bater com a data do documento (senão, não se lê)."""
    atual, anterior = ("1", "2") if cabecalho.tipo == "DFP" else ("2", "3")
    fim_atual = periodos.get(atual, (pd.NaT, pd.NaT))[1]
    fim_anterior = periodos.get(anterior, (pd.NaT, pd.NaT))[1]
    if fim_atual != cabecalho.referencia or pd.isna(fim_anterior):
        raise FormatoNaoLido(
            f"os períodos do {cabecalho.tipo.lower()} do ENET não batem com a data do documento"
        )


def _contas_cruas(contas: bytes) -> Iterator[dict[str, str]]:
    """Cada bloco `InfoFinaDFin` como um dicionário de tag → texto (só as tags que importam)."""
    quer = {
        "CodigoTipoDemonstracaoFinanceira",
        "CodigoTipoInformacaoFinanceira",
        "NumeroIdentificacaoPeriodo",
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


def _tem_valor(bloco: dict[str, str], coluna: str) -> bool:
    return bool(bloco.get(coluna)) and _numero(bloco[coluna]) != 0


def _colunas_em_uso(blocos: list[dict[str, str]]) -> set[tuple[str, str, str]]:
    """(demonstração, grupo, coluna) com algum valor: as outras vêm com zero por não existirem."""
    return {
        (
            b.get("CodigoTipoDemonstracaoFinanceira", ""),
            b.get("CodigoTipoInformacaoFinanceira", ""),
            c,
        )
        for b in blocos
        for c in COLUNAS_DE_VALOR
        if _tem_valor(b, c)
    }


def _periodos_da_demonstracao(tipo: str, demonstracao: str) -> dict[str, str]:
    if tipo == "DFP":
        return PERIODOS_DO_DFP
    return PERIODOS_DO_BALANCO_ITR if demonstracao in DO_BALANCO else PERIODOS_DO_ITR


def _inicio(
    tipo: str,
    demonstracao: str,
    periodo: tuple[pd.Timestamp, pd.Timestamp],
) -> pd.Timestamp:
    """Balanço não tem início; o do DFP é o fim menos um ano (o do arquivo vem em branco)."""
    if demonstracao in DO_BALANCO:
        return pd.NaT
    if tipo == "DFP":
        return periodo[1] - UM_ANO + UM_DIA
    return periodo[0]


def _linhas_da_conta(
    bloco: dict[str, str],
    cabecalho: _Cabecalho,
    periodos: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
    em_uso: set[tuple[str, str, str]],
) -> list[dict[str, object]]:
    codigo = bloco.get("CodigoTipoDemonstracaoFinanceira", "")
    demonstracao = DEMONSTRACOES.get(codigo)
    grupo = GRUPOS.get(bloco.get("CodigoTipoInformacaoFinanceira", ""))
    if not demonstracao or not grupo or not bloco.get("NumeroConta"):
        return []  # a DMPL e o que não é conta do plano ficam de fora
    linhas = []
    for numero, ordem in _periodos_da_demonstracao(
        cabecalho.tipo, demonstracao
    ).items():
        coluna = f"ValorConta{numero}"
        grupo_do_bloco = bloco.get("CodigoTipoInformacaoFinanceira", "")
        if cabecalho.tipo == "ITR" and (codigo, grupo_do_bloco, coluna) not in em_uso:
            continue
        inicio_e_fim = periodos[numero]
        linhas.append(
            {
                "demonstracao": demonstracao,
                "grupo": grupo,
                "ordem": ordem,
                "inicio": _inicio(cabecalho.tipo, demonstracao, inicio_e_fim),
                "fim": inicio_e_fim[1],
                "conta": bloco["NumeroConta"],
                "descricao": bloco.get("DescricaoConta1", ""),
                "conta_fixa": bloco.get("IndicadorContaFixa", "").lower() == "true",
                "valor": _numero(bloco.get(coluna, "")) * cabecalho.escala,
            }
        )
    return linhas


def _colunas_da_dmpl(grupo: str, com_nao_controladores: bool) -> dict[str, str]:
    """As colunas da DMPL a ler: o consolidado tem as oito, o individual as seis primeiras."""
    if grupo == "con":
        return COLUNAS_DA_DMPL_ANTIGA
    ate = 7 if com_nao_controladores else 6
    return dict(list(COLUNAS_DA_DMPL_ANTIGA.items())[:ate])


def _linhas_da_dmpl(
    bloco: dict[str, str],
    cabecalho: _Cabecalho,
    periodos: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
    com_nao_controladores: bool,
) -> list[dict[str, object]]:
    grupo = GRUPOS.get(bloco.get("CodigoTipoInformacaoFinanceira", ""))
    numero = bloco.get("NumeroIdentificacaoPeriodo", "")
    validos = PERIODOS_DO_DFP if cabecalho.tipo == "DFP" else PERIODOS_DO_ITR
    # sem número de período (0) não há data: o saldo fica de fora, sem inventar
    if not grupo or not bloco.get("NumeroConta") or numero not in validos:
        return []
    periodo = periodos[numero]
    return [
        {
            "demonstracao": "DMPL",
            "grupo": grupo,
            "ordem": validos[numero],
            "inicio": _inicio(cabecalho.tipo, "DMPL", periodo),
            "fim": periodo[1],
            "conta": bloco["NumeroConta"],
            "descricao": bloco.get("DescricaoConta1", ""),
            "conta_fixa": bloco.get("IndicadorContaFixa", "").lower() == "true",
            "valor": _numero(bloco.get(posicao, "")) * cabecalho.escala,
            "coluna": coluna,
        }
        for posicao, coluna in _colunas_da_dmpl(grupo, com_nao_controladores).items()
    ]


def _unir_periodos_iguais(linhas: list[dict[str, object]]) -> list[dict[str, object]]:
    """Uma linha por conta e período. No ITR, o trimestre e o acumulado do 1º trimestre são o mesmo
    período e a empresa preenche só um: vale o que tem valor; dois valores diferentes não se leem."""
    unidas: dict[tuple, dict[str, object]] = {}
    for linha in linhas:
        chave = tuple(
            linha.get(c)
            for c in (
                "demonstracao",
                "grupo",
                "ordem",
                "inicio",
                "fim",
                "conta",
                "coluna",
            )
        )
        antiga = unidas.setdefault(chave, linha)
        if antiga["valor"] == linha["valor"] or linha["valor"] == 0:
            continue
        if antiga["valor"] != 0:
            raise FormatoNaoLido(
                f"duas colunas do ENET dão valores diferentes à conta {linha['conta']} "
                f"({linha['demonstracao']}) no mesmo período"
            )
        unidas[chave] = linha
    return list(unidas.values())


def ler_documento_antigo(enxuto: bytes) -> DocumentoEnet:
    """O documento (DFP ou ITR; contas individuais e consolidadas e a DMPL) de um zip enxuto."""
    with zipfile.ZipFile(io.BytesIO(enxuto)) as arquivo:
        documento, periodos, contas = (arquivo.read(n) for n in ARQUIVOS_GUARDADOS)
    cabecalho = _cabecalho(documento)
    datas = _periodos(periodos)
    _conferir_periodos(cabecalho, datas)
    blocos = list(_contas_cruas(contas))
    em_uso = _colunas_em_uso(blocos)
    com_nao_controladores = any(
        b.get("CodigoTipoDemonstracaoFinanceira") == DMPL
        and b.get("CodigoTipoInformacaoFinanceira") == "1"
        and _tem_valor(b, "ValorConta7")
        for b in blocos
    )
    linhas = _unir_periodos_iguais(
        [l for b in blocos for l in _linhas_da_conta(b, cabecalho, datas, em_uso)]
    )
    linhas_da_dmpl = _unir_periodos_iguais(
        [
            l
            for b in blocos
            if b.get("CodigoTipoDemonstracaoFinanceira") == DMPL
            for l in _linhas_da_dmpl(b, cabecalho, datas, com_nao_controladores)
        ]
    )
    identidade: dict[str, object] = {
        "cnpj": cabecalho.cnpj,
        "empresa": cabecalho.empresa,
        "documento": cabecalho.tipo,
        "referencia": cabecalho.referencia,
    }
    return DocumentoEnet(
        cnpj=cabecalho.cnpj,
        empresa=cabecalho.empresa,
        documento=cabecalho.tipo,
        referencia=cabecalho.referencia,
        versao=cabecalho.versao,
        motivo=cabecalho.motivo,
        contas=montar_tabela(linhas, COLUNAS, identidade, cabecalho.versao),
        dmpl=montar_tabela(
            linhas_da_dmpl, COLUNAS_DA_DMPL, identidade, cabecalho.versao
        ),
    )
