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
`tipoDocumento` (`cpf`, `cnpj_dv_errado`, `outro`, `vazio`). O PIT manda o CPF com 14 posições e zeros
à esquerda; quando não há sigla (vencedor, contratado), o número que pode ser um CPF é tratado como
CPF, mesmo que também passe como CNPJ (o do Banco do Brasil, `00000000000191`): perde-se a ligação de
um CNPJ antigo, nunca se guarda um CPF.

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

from defusedxml.ElementTree import fromstring

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
# o maior XML visto (vencedores de um município em 2013) tem ~8 MB; o XML vira árvore na memória
LIMITE_DO_XML = 128 * 1024**2
NOME_DO_XML = re.compile(r"^\d{4}_\d+_([A-Za-z]+)\.xml$")
ATRIBUTOS_DE_PESSOA = ("nm",)
TEXTO_LIVRE = ("dsObjeto", "dsHistorico", "dsItem")
# atributos com números que não são documentos (códigos, valores, datas): fora da varredura de CPF
NAO_SAO_DOCUMENTO = ("id", "vl", "dt", "cd")

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
}


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
        if not tipo and _pode_ser_cpf(texto):
            return "cpf", None
        if len(texto) <= cnpj.TAMANHO and cnpj.dv_confere(texto.zfill(cnpj.TAMANHO)):
            return "cnpj", texto.zfill(cnpj.TAMANHO)
    elif cnpj.FORMA.match(texto) and cnpj.dv_confere(
        texto
    ):  # CNPJ com letras (2026 em diante)
        return "cnpj", texto
    if tipo == "CNPJ" or len(texto) == cnpj.TAMANHO:
        return "cnpj_dv_errado", None
    return "outro", None


def _regravar_linha(tipo: str, original: Mapping[str, str], destino: Element) -> None:
    permitidos = PERMITIDOS[tipo]
    linha = SubElement(destino, tipo)
    for atributo, valor in original.items():
        if atributo in permitidos:
            linha.set(atributo, valor)
    if tipo in DOCUMENTOS:
        sigla, numero = DOCUMENTOS[tipo]
        classe, documento = documento_ou_classe(
            original.get(sigla) if sigla else None, original.get(numero)
        )
        if documento:
            linha.set(numero, documento)
        linha.set(TIPO_DO_DOCUMENTO, classe)


def regravar_xml(tipo: str, conteudo: bytes) -> bytes:
    """O XML em UTF-8 só com as linhas do tipo e os atributos da lista (`defusedxml`: recusa entidades)."""
    raiz = fromstring(decodificar_xml(conteudo))
    saida = Element(raiz.tag)
    for elemento in raiz:
        if elemento.tag == tipo:
            _regravar_linha(tipo, elemento.attrib, saida)
        else:
            log.info(
                "TCE-PR: linha <%s> fora do tipo %s, fica de fora", elemento.tag, tipo
            )
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
            _gravar(regravado, nome, regravar_xml(tipo, entrada.read(info)))
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
            and documento_ou_classe(None, valor)[0] == "cpf"
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
