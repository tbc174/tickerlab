"""Contratos, sanções e cadastro de fornecedores dos estados, do arquivista (linha 1075, lote 1 dos estados).

Para quem cada empresa vende no governo estadual, por quanto, e se o estado a puniu: o primeiro lote das
tabelas estaduais com CNPJ da meta das 300 (linha 904; decisão do Tiago em 16/11/2026, "estados entram
todos"). As tabelas saem de `base/contratos_estaduais.py`; aqui só se descobre e se guarda.

- **Rio de Janeiro, SIGA (SEPLAG)** (`govrj-*`): três CSVs do Sistema Integrado de Gestão de Aquisições, em
  endereço fixo (`www.compras.rj.gov.br/siga/imagens/`), regravados inteiros todo dia, em Latin-1 com ";":
  os contratos (`CONTRATOS.CSV`, uns 53 MB), as sanções a fornecedores (`FORNECEDOR_SANCOES.CSV`) e o cadastro
  de fornecedores (`FORNECEDORES.CSV`). Licença PDDL (domínio público) nos conjuntos do CKAN do estado, lida em
  25/11/2026; o `robots.txt` do `compras.rj.gov.br` não existe (404) e o do CKAN fecha `/api/`, então a coleta
  não passa pelo CKAN: baixa os três endereços fixos. Depois (PR 2), as compras diretas
  (`COMPRAS_DIRETAS.CSV`, uns 66 MB: dispensa e inexigibilidade, item por item), do mesmo jeito.
- **Espírito Santo, portal da transparência** (`esdados-contratos` e `esdados-empenhos`): os CSVs por ano dos
  contratos e dos empenhos do conjunto `portal-da-transparencia-contratos` (dados.es.gov.br, CC BY, lida em
  25/11/2026; UTF-8 com ";"). O pacote junta contratos, empenhos, aditivos e comissões: o nome do arquivo escolhe.
  A descoberta lê a página do conjunto (o `robots.txt` fecha `/api/` e pede 10 s entre pedidos), só links do
  próprio portal; as alterações contratuais não trazem o CNPJ e ficam fora.

Escolhas (testes em `tests/test_base_arquivo_lote_contratos_estaduais.py`), as mesmas da ordem cronológica
(`base/arquivo/lote_ordem_cronologica.py`, de onde vem o filtro):
- **LGPD (ADR 0075 e 0088): só pessoa jurídica.** Fica a linha cujo documento é um CNPJ inteiro (o SIGA
  mascara o CPF: "***.123.456-**", que sai); **saem de todas** o nome do fornecedor (o de MEI é o da pessoa),
  o objeto e o número do processo (texto livre) e o endereço do PNCP. Linha com CPF em qualquer campo,
  inclusive no texto livre, sai inteira antes de o texto ser descartado;
- **endereço fixo, nunca vindo de dado:** nada de SSRF; o endereço do PNCP que o contrato traz nem é guardado;
- **o formato mudou, a coleta falha:** sem a coluna do documento no cabeçalho, nada é guardado; nunca fica CSV
  pela metade, e o original nunca fica no acervo, só o filtrado.
"""

from dataclasses import dataclass

from base.arquivo.coleta import Fonte
from base.arquivo.lote_ordem_cronologica import (
    PAUSA_DO_ROBOTS_EM_SEGUNDOS,
    Formato,
    alvo_do_csv,
    descobrir_em,
)

MENSAL = "mensal"
SEMANAL = "semanal"
SIGA_DO_RJ = "https://www.compras.rj.gov.br/siga/imagens"
LATIN1 = "latin-1"
DOCUMENTO_DO_SIGA = "cpf/cnpj"


@dataclass(frozen=True)
class ArquivoFixo:
    """Um CSV de endereço fixo: onde está, com que filtro e com que frequência o arquivista o olha."""

    url: str
    formato: Formato
    grupo: str


RJ_CONTRATOS = ArquivoFixo(
    url=f"{SIGA_DO_RJ}/CONTRATOS.CSV",
    formato=Formato(
        id="govrj-contratos",
        portal="https://www.compras.rj.gov.br",
        pacote="contratos_siga",
        documento=DOCUMENTO_DO_SIGA,
        guardadas=(
            "código do contrato",
            "id processo",
            "contratação",
            "status contratação",
            "data contratação",
            "unidade",
            "codug",
            "tipo de aquisição",
            "critério de julgamento",
            "data início vigência",
            "data fim vigência",
            DOCUMENTO_DO_SIGA,
            "valor total contrato/valor estimado para contratação (r$)",
            "valor total empenhado (r$)",
            "valor total liquidado (r$)",
            "valor total pago (r$)",
            "data public deorj",
            "regimejuridico",
            "data_assinatura",
            "emergencial",
        ),
        codificacao=LATIN1,
    ),
    grupo=MENSAL,
)
RJ_SANCOES = ArquivoFixo(
    url=f"{SIGA_DO_RJ}/FORNECEDOR_SANCOES.CSV",
    formato=Formato(
        id="govrj-sancoes",
        portal="https://www.compras.rj.gov.br",
        pacote="sancoes-fornecedor",
        documento=DOCUMENTO_DO_SIGA,
        guardadas=(
            DOCUMENTO_DO_SIGA,
            "órgão/entidade apenadora",
            "enquadramento legal",
            "motivo",
            "contrato",
            "data de efetivação",
            "status da penalidade",
        ),
        codificacao=LATIN1,
    ),
    grupo=SEMANAL,  # risco de contraparte: a sanção nova não espera um mês
)
RJ_FORNECEDORES = ArquivoFixo(
    url=f"{SIGA_DO_RJ}/FORNECEDORES.CSV",
    formato=Formato(
        id="govrj-fornecedores",
        portal="https://www.compras.rj.gov.br",
        pacote="fornecedores2",
        documento=DOCUMENTO_DO_SIGA,
        guardadas=(
            DOCUMENTO_DO_SIGA,
            "crc",
            "tipo empresarial",
            "me/epp",
            "situação da empresa",
            "data de cadastro",
            "cidade",
            "uf",
        ),
        codificacao=LATIN1,
    ),
    grupo=MENSAL,
)
RJ_COMPRAS_DIRETAS = ArquivoFixo(
    url=f"{SIGA_DO_RJ}/COMPRAS_DIRETAS.CSV",
    formato=Formato(
        id="govrj-compras-diretas",
        portal="https://www.compras.rj.gov.br",
        pacote="compras-diretas",
        documento="cnpj_cpf",
        # sem o processo, o objeto, o enquadramento legal e o item: texto livre (15 mil e 41 mil valores no
        # arquivo de 25/11/2026), onde pode aparecer nome; fica o código do item
        guardadas=(
            "unidade",
            "id processo",
            "afastamento",
            "data de aprovação",
            "valor do processo (r$)",
            "cnpj_cpf",
            "id item",
            "qtd.",
            "unidade de medida",
            "vl. unitário (r$)",
            "ped",
            "regime",
            "temporalidade",
        ),
        codificacao=LATIN1,
    ),
    grupo=MENSAL,
)
ARQUIVOS_FIXOS = (RJ_CONTRATOS, RJ_SANCOES, RJ_FORNECEDORES, RJ_COMPRAS_DIRETAS)

PORTAL_DO_ES = "https://dados.es.gov.br"
PACOTE_DO_ES = "portal-da-transparencia-contratos"
# o fornecedor e o objeto são texto livre (o de MEI é o nome da pessoa) e não ficam; o CNPJ formatado repete o outro
ES_CONTRATOS = Formato(
    id="esdados-contratos",
    portal=PORTAL_DO_ES,
    pacote=PACOTE_DO_ES,
    documento="cnpjfornecedor",
    guardadas=(
        "id",
        "idorgao",
        "nomeorgao",
        "numeroprocesso",
        "modalidadeprocesso",
        "numeroedital",
        "numerodocumento",
        "tipodocumento",
        "cnpjfornecedor",
        "tipoaquisicao",
        "situacao",
        "datacelebracao",
        "datainiciovigencia",
        "datafimvigencia",
        "valorinicial",
        "valorfinal",
        "eregistropreco",
    ),
    arquivos=r"contratos-\d{4}\.csv",
)
ES_EMPENHOS = Formato(
    id="esdados-empenhos",
    portal=PORTAL_DO_ES,
    pacote=PACOTE_DO_ES,
    documento="cnpjfornecedor",
    guardadas=(
        "id",
        "numeroprocesso",
        "numerodocumento",
        "tipodocumento",
        "numeroempenho",
        "valorglobal",
        "cnpjfornecedor",
    ),
    arquivos=r"empenhos-\d{4}\.csv",
)
CONJUNTOS_DO_ES = (ES_CONTRATOS, ES_EMPENHOS)


def _fonte_fixa(arquivo: ArquivoFixo) -> Fonte:
    alvo = alvo_do_csv(arquivo.url, arquivo.formato)
    return Fonte(arquivo.formato.id, arquivo.grupo, lambda _cliente, _agora: [alvo])


def _fonte_do_portal(formato: Formato) -> Fonte:
    return Fonte(
        formato.id,
        MENSAL,
        lambda cliente, _agora: descobrir_em(cliente, formato),
        pausa_minima=PAUSA_DO_ROBOTS_EM_SEGUNDOS,
    )


def fontes() -> list[Fonte]:
    """As fontes do lote para a lista `FONTES` (o id segue a família: `govrj-...`, `esdados-...`)."""
    return [
        *(_fonte_fixa(arquivo) for arquivo in ARQUIVOS_FIXOS),
        *(_fonte_do_portal(formato) for formato in CONJUNTOS_DO_ES),
    ]
