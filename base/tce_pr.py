"""PIT do TCE-PR (Portal de Informações para Todos): licitações, contratos e ligações dos 399 municípios
do Paraná, de 2013 em diante (frente de sinais de risco em compras públicas, ADR 0085).

**O que vai para o acervo** (regra do acervo do plano de 17/10/2026): cada ZIP interno do PIT
(`<ano>_<IBGE>_<Tema>.zip`) é regravado **só com os atributos da lista** (`PERMITIDOS`). O que a lista
não diz não entra: atributo novo da fonte, ou XML novo dentro do ZIP, fica de fora até alguém pôr na
lista. Nunca entram nomes (`nm*`: participante, vencedor, contratado, executor da cessão, município e
órgão), nem texto livre (`dsObjeto`, `dsItem`, motivos de aditivo e multa), que pode trazer o nome de
uma pessoa ("show do cantor Fulano"). O município e o órgão ficam pelos códigos (`cdIBGE`,
`idPessoa`/`idEntidade`).

**Documento do licitante, vencedor, contratado e executor** (ADR 0075, só pessoa jurídica): entra só
se for CNPJ de DV certo; senão a linha fica (conta como concorrente) sem o número e com a classe em
`tipoDocumento` (`cpf`, `cnpj_ou_cpf`, `cnpj_dv_errado`, `outro`, `vazio`). O PIT manda o CPF com 14
posições e zeros à esquerda; quando não há sigla (vencedor, contratado), o número que pode ser um CPF é
tratado como CPF. O que passa como CNPJ e como CPF (5 zeros ou mais à esquerda) sai sem o número, com
uma exceção medida no ensaio de 17/10/2026: a raiz do Banco do Brasil (39 de 40 casos em 2013 e 2025).

**Formato medido em 17/10/2026**: 2013 em UTF-16 (BOM `FF FE`), anos recentes em UTF-8 com BOM; os
atributos são os mesmos de 2013 a 2025. Cada linha traz `dtEnvio` (licitação, contrato), que a D1 da
ADR 0085 usa para estimar quando ficou público, e `DataReferencia` (mês em que o PIT foi gerado).

O regravado é igual byte a byte para o mesmo conteúdo (data fixa, ordem fixa): o PIT regrava o ano
corrente toda semana, e o acervo guarda uma vez só o que não mudou.
"""

import io
import logging
import re
import zipfile
from collections.abc import Mapping
from xml.etree.ElementTree import Element, SubElement, tostring

from defusedxml.ElementTree import fromstring, iterparse

from base import cnpj
from base.arquivo.obter import decodificar_xml

log = logging.getLogger(__name__)

TIPO_DO_DOCUMENTO = "tipoDocumento"
DATA_FIXA_NO_ZIP = (
    1980,
    1,
    1,
    0,
    0,
    0,
)  # a menor que o ZIP aceita: o regravado não muda com o dia
SISTEMA_UNIX = 3  # o mesmo "criado em" no PC e no servidor (senão o SHA-256 muda)
PERMISSOES_NO_ZIP = 0o644 << 16
# o XML é lido linha a linha, mas o texto decodificado fica inteiro na memória (~2,5× o XML, com a
# entrada): o maior da Despesa de 2025 tem 228 MB (Londrina); a carga roda com memória para isso
LIMITE_DO_XML = 1024**3
# município grande parte o XML em pedaços (`Empenho_1.xml`, `Empenho_2.xml`, medido na Despesa de 2025):
# o tipo é o mesmo, e o pedaço não pode ficar de fora
NOME_DO_XML = re.compile(r"^\d{4}_\d+_([A-Za-z]+)(?:_\d+)?\.xml$")
ATRIBUTOS_DE_PESSOA = ("nm",)
TEXTO_LIVRE = ("dsObjeto", "dsHistorico", "dsItem")
# atributos com números que não são documentos (códigos, valores, datas): fora da varredura de CPF
NAO_SAO_DOCUMENTO = ("id", "vl", "dt", "cd")
# com 5 zeros ou mais à esquerda, os DVs do CNPJ e do CPF são a mesma conta (os pesos só diferem nas
# 2 primeiras posições do CPF): o número passa nos dois. Isso só acontece nas raízes mais antigas,
# de bancos. A do Banco do Brasil (00.000.000, uma por agência) aparece aos milhares e fica como CNPJ;
# como CPF seria 000.00x.xxx-xx, dos primeiros emitidos. As outras saem sem o número (`cnpj_ou_cpf`)
RAIZ_DO_BANCO_DO_BRASIL = "00000000"
CLASSES_DE_POSSIVEL_PESSOA = ("cpf", "cnpj_ou_cpf")

_ENVIO = ("ultimoEnvioSIMAMNesteExercicio", "DataReferencia")
_ADITIVO = (
    "nrAditivoContrato",
    "nrAnoAditivoContrato",
    "idTipoAditivoContrato",
    "dsTipoAditivoContrato",
    "idTipoOperacaoAditivoContrato",
    "dsTipoOperacaoAditivoContrato",
    "dtAditivoContrato",
    *_ENVIO,
)
_LIGACAO = ("DataReferencia",)

# o que entra de cada XML (o nome é o do arquivo sem `<ano>_<IBGE>_` nem `.xml`). O documento de
# pessoa jurídica não está aqui: sai por `DOCUMENTOS`, só quando é CNPJ de DV certo
PERMITIDOS: Mapping[str, frozenset[str]] = {
    nome: frozenset(atributos)
    for nome, atributos in {
        "Licitacao": (
            "cdIBGE", "idPessoa", "idLicitacao", "dsModalidadeLicitacao", "nrLicitacao",
            "nrAnoLicitacao", "nrEditalOrigem", "nranoEditalOrigem", "dtEdital", "dtAbertura",
            "vlLicitacao", "dtEnvio", "dsNaturezaLicitacao", "dsAvaliacaoLicitacao",
            "dsClassificacaoObjetoLicitacao", "dsRegimeExecucaoLicitacao",
            "dsTipoSituacaoLicitacao", "dtOcorrencia", "dsClausulaProrrogacao", *_ENVIO,
        ),
        "LicitacaoParticipante": (
            "cdIBGE", "idEntidade", "idLicitacao", "nrLicitacao", "nrAnoLicitacao",
            "dsTipoSituacaoParticipante", "dtOcorrencia", *_ENVIO,
        ),
        "LicitacaoVencedor": (
            "cdIBGE", "idPessoa", "idlicitacao", "nrAnoLicitacao", "nrLicitacao",
            "dsModalidadeLicitacao", "nrLote", "nrItem", "nrQuantidade", "idUnidadeMedida",
            "dsUnidadeMedida", "vlMinimoUnitarioItem", "vlMinimoTotal", "vlMaximoUnitarioitem",
            "vlMaximoTotal", "dsFormaPagamento", "nrPrazoLimiteEntrega", "idTipoEntregaProduto",
            "dsTipoEntregaProduto", "nrQuantidadePropostaLicitacao", "vlPropostaItem",
            "dtValidadeProposta", "dtPrazoEntregaPropostaLicitacao",
            "nrQuantidadeVencedorLicitacao", "vlLicitacaoVencedorLicitacao", "nrClassificacao",
            "dtHomologacao", *_ENVIO,
        ),
        "Contrato": (
            "cdIBGE", "idPessoa", "idContrato", "nrContrato", "nrAnoContrato", "vlContrato",
            "vlDesteContratado", "dsTipoFormaPagamentoContrato", "dtAssinatura", "dtInicio",
            "dtFim", "dtProrrogacao", "dsTipoRegimeExecucaoContrato", "dsTipoGarantiaContrato",
            "dsTipoAtoContrato", "flSubContratacao", "dsTipoOrigemContrato", "dtEnvio",
            "nrMesProcessamento", "nrAnoProcessamento", "dsTipoMultaContrato", *_ENVIO,
        ),
        "ContratoAditivo": ("idcontrato", "vlAditivo", "vlAtualizadoContrato", *_ADITIVO),
        "ContratoAditivoPrazo": ("idcontrato", "dtFim", *_ADITIVO),
        "ContratoAditivoRescisao": (
            "idContrato", "idTipoMotivoRescisaoContrato", "dsTipoMotivoRescisaoContrato",
            *_ADITIVO,
        ),
        "ContratoAditivoCessao": ("idcontrato", *_ADITIVO),
        "ContratoAditivoRedimensionamento": (
            "idcontrato", "idTipoRedimensionamentoObjetoContrato",
            "dsTipoRedimensionamentoObjetoContrato", "nrQuantidade", "vlAditivoItem", *_ADITIVO,
        ),
        # vazio em todos os municípios olhados (2013 e 2025): só os campos comuns dos aditivos; o
        # documento do subcontratado fica de fora até alguém ver o formato e pôr em `DOCUMENTOS`
        "ContratoAditivoSubContratacao": ("idcontrato", "idContrato", *_ADITIVO),
        "LicitacaoXContrato": ("idLicitacao", "idContrato", *_LIGACAO),
        "EmpenhoXContrato": ("idEmpenho", "idContrato", *_LIGACAO),
        "LicitacaoXEmpenho": ("idLicitacao", "idEmpenho", *_LIGACAO),
        "ContratoXConvenio": ("idContrato", "idConvenio", *_LIGACAO),
        "LicitacaoXConvenio": ("idLicitacao", "idConvenio", *_LIGACAO),
        # `Despesa` (PR 2): códigos da classificação (cd*), valores, datas e ids. As descrições (ds*) saem
        # (vêm dos códigos); o texto livre e todo nome também
        "Empenho": (
            "cdIBGE", "idPessoa", "idEmpenho", "nrEmpenho", "nrAnoEmpenho", "dtEmpenho",
            "idTipoEmpenho", "dsTipoEmpenho", "idOrigemEmpenho", "cdOrgao", "cdUnidade",
            "cdFuncao", "cdSubFuncao", "cdPrograma", "cdProjetoAtividade", "cdCategoriaEconomica",
            "cdGrupoNatureza", "cdModalidade", "cdElemento", "cdDesdobramento", "cdFontePadrao",
            "cdGrupoFonte", "cdOrigemFonte", "cdDesdobramentoFonte", "cdDetalhamentoFonte",
            "nrAnoCompetencia", "nrMesCompetencia", "vlEmpenho", "vlEstornoEmpenho",
            "vlLiquidacao", "vlEstornoLiquidacao", "vlPagamento", "vlEstornoPagamento",
            "vlSaldoAntDotacao", *_ENVIO,
        ),
        "EmpenhoLiquidacao": (
            "cdIBGE", "idPessoa", "idEmpenho", "idLiquidacao", "idOrigemLiquidacao",
            "nrLiquidacao", "nrAnoLiquidacao", "dtLiquidacao", "vlLiquidacaoBruto",
            "vlLiquidacaoEstornado", "vlLiquidacaoLiquido", "DataEnvioParaTCE", *_ENVIO,
        ),
        "EmpenhoLiquidacaoEstorno": (
            "cdIBGE", "idPessoa", "idEmpenho", "idLiquidacao", "idEstornoLiquidacao",
            "nrEstorno", "nrAnoEstorno", "nrAnoLiquidacao", "dtEstorno", "vlEstorno",
            "DataEnvioParaTCE", *_ENVIO,
        ),
        "EmpenhoPagamento": (
            "cdIBGE", "idPessoa", "idEmpenho", "idLiquidacao", "idPagamento", "nrPagamento",
            "nrAnoPagamento", "nrAnoLiquidacao", "dtOperacao", "vlOperacao", "vlPagamentoBruto",
            "DataEnvioParaTCE", *_ENVIO,
        ),
        "EmpenhoPagamentoEstorno": (
            "cdIBGE", "idPessoa", "idEmpenho", "idLiquidacao", "idPagamento",
            "idEstornoPagamento", "nrEstorno", "nrAnoEstorno", "nrAnoLiquidacao", "dtEstorno",
            "vlEstorno", "DataEnvioParaTCE", *_ENVIO,
        ),
    }.items()
}  # fmt: skip

# XML -> (atributo da sigla "CNPJ"/"CPF", ou None quando a fonte não diz; atributo do número)
DOCUMENTOS: Mapping[str, tuple[str | None, str]] = {
    "LicitacaoParticipante": (
        "sgDocParticipanteLicitacao",
        "nrDocParticipanteLicitacao",
    ),
    "LicitacaoVencedor": (None, "nrDocumento"),
    "Contrato": (None, "nrDocContratado"),
    "ContratoAditivoCessao": ("sgDocExecutor", "nrDocumento"),
    "Empenho": ("sgDocCredor", "nrDocCredor"),
}

# Despesa: o empenho de credor que pode ser pessoa sai inteiro; estes XMLs saem junto, pelo `idEmpenho`
DEPENDENTES_DO_EMPENHO = frozenset(
    {
        "EmpenhoLiquidacao",
        "EmpenhoLiquidacaoEstorno",
        "EmpenhoPagamento",
        "EmpenhoPagamentoEstorno",
    }
)
DESCARTADAS = "descartadasPorCredorPf"


def _pode_ser_cpf(digitos: str) -> bool:
    sem_zeros = digitos.lstrip("0")
    return len(sem_zeros) <= cnpj.TAMANHO_DO_CPF and cnpj.cpf_confere(
        sem_zeros.zfill(cnpj.TAMANHO_DO_CPF)
    )


def documento_ou_classe(
    sigla: str | None, numero: str | None
) -> tuple[str, str | None]:
    """A classe do documento e o CNPJ (só quando é CNPJ de DV certo); o número de pessoa nunca sai.

    `sigla` é o que a fonte diz ("CNPJ", "CPF", com espaços à direita) ou None quando não diz.
    """
    texto = cnpj.SEPARADORES.sub("", (numero or "").strip()).upper()
    tipo = (sigla or "").strip().upper()
    if not texto:
        return "vazio", None
    if tipo == "CPF":
        return "cpf", None
    if tipo not in ("", "CNPJ"):
        return "outro", None
    if texto.isdigit():
        numerico = texto.zfill(cnpj.TAMANHO) if len(texto) <= cnpj.TAMANHO else ""
        e_cnpj = bool(numerico) and cnpj.dv_confere(numerico)
        if e_cnpj and numerico.startswith(RAIZ_DO_BANCO_DO_BRASIL):
            return "cnpj", numerico
        if _pode_ser_cpf(texto):
            if e_cnpj:
                return "cnpj_ou_cpf", None
            return ("cnpj_dv_errado" if tipo else "cpf"), None
        if e_cnpj:
            return "cnpj", numerico
    elif cnpj.FORMA.match(texto) and cnpj.dv_confere(
        texto
    ):  # CNPJ com letras (2026 em diante)
        return "cnpj", texto
    if tipo == "CNPJ" or len(texto) == cnpj.TAMANHO:
        return "cnpj_dv_errado", None
    return "outro", None


def _regravar_linha(tipo: str, original: Mapping[str, str], destino: Element) -> bool:
    """Grava a linha só com a lista; False (nada gravado) no empenho de credor que pode ser pessoa."""
    classe_e_documento = None
    if tipo in DOCUMENTOS:
        sigla, numero = DOCUMENTOS[tipo]
        classe_e_documento = documento_ou_classe(
            original.get(sigla) if sigla else None, original.get(numero)
        )
        if tipo == "Empenho" and classe_e_documento[0] in CLASSES_DE_POSSIVEL_PESSOA:
            return False
    permitidos = PERMITIDOS[tipo]
    linha = SubElement(destino, tipo)
    for atributo, valor in original.items():
        if atributo in permitidos:
            linha.set(atributo, valor)
    if classe_e_documento:
        classe, documento = classe_e_documento
        if documento:
            linha.set(DOCUMENTOS[tipo][1], documento)
        linha.set(TIPO_DO_DOCUMENTO, classe)
    return True


def regravar_xml(
    tipo: str, conteudo: bytes, empenhos_descartados: set[str] | None = None
) -> bytes:
    """O XML em UTF-8 só com as linhas do tipo e os atributos da lista (`defusedxml`: recusa entidades).

    `empenhos_descartados` (Despesa): no `Empenho`, recebe o `idEmpenho` de cada linha de credor que pode
    ser pessoa, que sai; nos XMLs que dependem do empenho, saem as linhas desses empenhos. Quantas linhas
    saíram vai na raiz (`descartadasPorCredorPf`).
    """
    descartados = empenhos_descartados if empenhos_descartados is not None else set()
    saida: Element | None = None
    raiz: Element | None = None
    fora = 0
    # linha a linha, descartando o que já foi lido: o XML de Londrina em 2025 tem 228 MB, e a árvore
    # inteira de um XML desse tamanho passa de vários GB
    for evento, elemento in iterparse(
        io.StringIO(decodificar_xml(conteudo)), events=("start", "end")
    ):
        if raiz is None:
            raiz = elemento
            saida = Element(elemento.tag)
            continue
        if evento == "start" or elemento is raiz:
            continue
        if elemento.tag != tipo:
            log.info(
                "TCE-PR: linha <%s> fora do tipo %s, fica de fora", elemento.tag, tipo
            )
        elif (
            tipo in DEPENDENTES_DO_EMPENHO and elemento.get("idEmpenho") in descartados
        ):
            fora += 1
        elif not _regravar_linha(tipo, elemento.attrib, saida):
            descartados.add(elemento.get("idEmpenho", ""))
            fora += 1
        raiz.clear()
    if saida is None:
        raise ValueError("TCE-PR: XML vazio")
    if fora:
        saida.set(DESCARTADAS, str(fora))
    return tostring(saida, encoding="utf-8", xml_declaration=True)


def _gravar(arquivo_zip: zipfile.ZipFile, nome: str, conteudo: bytes) -> None:
    info = zipfile.ZipInfo(nome, DATA_FIXA_NO_ZIP)
    info.create_system = SISTEMA_UNIX
    info.external_attr = PERMISSOES_NO_ZIP
    arquivo_zip.writestr(info, conteudo, compress_type=zipfile.ZIP_DEFLATED)


def regravar(zip_interno: bytes) -> bytes:
    """O ZIP interno do PIT (`<ano>_<IBGE>_<Tema>.zip`) só com os XMLs e os atributos da lista."""
    saida = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(zip_interno)) as entrada,
        zipfile.ZipFile(saida, "w") as regravado,
    ):
        membros = []
        for info in sorted(entrada.infolist(), key=lambda i: i.filename):
            # só o nome do arquivo, nunca a pasta que a fonte puser nele ("../x.xml")
            nome = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
            achado = NOME_DO_XML.match(nome)
            tipo = achado.group(1) if achado else ""
            if tipo not in PERMITIDOS:
                log.warning("TCE-PR: %s fora da lista de XMLs, fica de fora", nome)
                continue
            if info.file_size > LIMITE_DO_XML:
                raise ValueError(
                    f"TCE-PR: {nome} com {info.file_size} bytes, acima do limite"
                )
            membros.append((tipo, nome, info))
        # o `Empenho` é lido primeiro: ele diz quais empenhos (de credor que pode ser pessoa) levam
        # junto a liquidação, o pagamento e os estornos; a gravação segue em ordem de nome
        descartados: set[str] = set()
        xmls = {
            nome: regravar_xml(tipo, entrada.read(info), descartados)
            for tipo, nome, info in sorted(membros, key=lambda m: m[0] != "Empenho")
        }
        for nome in sorted(xmls):
            _gravar(regravado, nome, xmls[nome])
    return saida.getvalue()


def _vestigios_da_linha(xml: str, atributos: Mapping[str, str]) -> list[str]:
    achados = []
    for atributo, valor in atributos.items():
        if atributo.startswith(ATRIBUTOS_DE_PESSOA) or atributo in TEXTO_LIVRE:
            achados.append(f"{xml}: atributo {atributo}")
        elif (
            not atributo.startswith(NAO_SAO_DOCUMENTO)
            and valor.strip().isdigit()
            and len(valor.strip()) in (cnpj.TAMANHO_DO_CPF, cnpj.TAMANHO)
            and documento_ou_classe(None, valor)[0] in CLASSES_DE_POSSIVEL_PESSOA
        ):
            achados.append(f"{xml}: possível CPF em {atributo}")
    return achados


def vestigios_de_pessoa(regravado: bytes) -> list[str]:
    """O que parece pessoa num ZIP regravado (atributo de nome ou texto livre, número que pode ser
    CPF), sem o valor: para os testes e para conferir o ensaio e a carga. Vazio = nada achado."""
    achados: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(regravado)) as arquivo_zip:
        for nome in arquivo_zip.namelist():
            raiz = fromstring(decodificar_xml(arquivo_zip.read(nome)))
            for elemento in raiz:
                achados.update(_vestigios_da_linha(nome, elemento.attrib))
    return sorted(achados)
