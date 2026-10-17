"""Rótulos de insolvência (série B2): recuperação judicial ou extrajudicial, falência e liquidação.

Fonte: o IPE da CVM desde 2003 (guardado pelo arquivista como `cvm-hist-ipe`). Dois tipos de
evidência, cada uma com a data em que ficou pública (`conhecido_em` = data de entrega à CVM):
- `categoria_ipe`: documentos das categorias próprias da CVM ("Informações de Companhias em
  Recuperação Judicial ou Extrajudicial", "em Falência", "em Liquidação", "Pedidos de falência");
- `fato_relevante`: fato relevante ou comunicado cujo assunto anuncia o pedido. Costuma ser o primeiro
  sinal público, mas pode ser um esclarecimento de notícia: quem montar o modelo decide se usa.

`primeira_ocorrencia` dá a primeira data de cada rótulo por empresa: é o rótulo "entrou em
recuperação judicial em tal data" do catálogo de modelos (ADR 0030).

**De quem é o evento** (relatório 4 dos cruzamentos v2, 16/10/2026): a companhia que entrega o
documento nem sempre é a que entrou em recuperação (Vale sobre a Samarco, Cemig sobre a Renova,
securitizadora sobre a devedora do CRI). Cada linha tem o `evento` (o que aconteceu, com quem for) e
o `rotulo` da companhia que entregou: o próprio evento ou `exposicao_a_terceiro`; a `regra` diz o
que decidiu. A categoria da CVM junta judicial e extrajudicial: o tipo sai do assunto, do tipo do
documento ou do processo que a companhia já tinha aberto; sem nenhum dos três, fica
`recuperacao_judicial_ou_extrajudicial`. Cada documento só usa o que era público até a data dele.
"""

import csv
import io
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import LINHAGEM, gravar_se_mudou
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.versao_do_codigo import versao_do_codigo

COLUNAS = (
    "cnpj",
    "empresa",
    "rotulo",
    "evento",
    "regra",
    "evidencia",
    "categoria",
    "tipo",
    "assunto",
    "conhecido_em",
    "referencia",
    "protocolo",
    "versao",
    "link",
)
# categoria (sem acento, minúsculas) da CVM → evento; a de recuperação junta judicial e extrajudicial
CATEGORIAS = (
    ("recuperacao judicial ou extrajudicial", "recuperacao"),
    ("pedidos de falencia", "pedido_de_falencia"),
    ("em falencia", "falencia"),
    ("sentenca de falencia", "falencia"),
    ("em liquidacao", "liquidacao"),
)
CATEGORIAS_DE_ANUNCIO = ("fato relevante", "comunicado ao mercado")
# assunto do fato relevante → evento (a primeira que casar vale)
ASSUNTOS = (
    (re.compile(r"recuperacao extrajudicial"), "recuperacao_extrajudicial"),
    (re.compile(r"recuperacao judicial"), "recuperacao_judicial"),
    (re.compile(r"(pedido|requerimento)s? de (auto)?falencia"), "pedido_de_falencia"),
    (
        re.compile(
            r"(decreta\w*|sentenca|convola\w*|decreto)( \w+){0,3} (de )?falencia"
            r"|autofalencia|falencia (da|de) (companhia|empresa|sociedade)"
        ),
        "falencia",
    ),
    (
        re.compile(r"liquidacao extrajudicial|em liquidacao|liquidacao da companhia"),
        "liquidacao",
    ),
)
# nomes de órgãos e de leis que só mencionam a palavra (Oi, 2016: "Tribunal de Falências")
MENCOES_SEM_EVENTO = re.compile(
    r"(tribunal|vara|lei|juizo) (empresarial )?de falencias?"
)

# --- de quem é o evento --------------------------------------------------------------------------
JUDICIAL = "recuperacao_judicial"
EXTRAJUDICIAL = "recuperacao_extrajudicial"
SEM_TIPO = "recuperacao_judicial_ou_extrajudicial"
TERCEIRO = "exposicao_a_terceiro"
RECUPERACOES = (JUDICIAL, EXTRAJUDICIAL)
# como as companhias escrevem cada recuperação no assunto (Casas Bahia: "Plano de RE";
# Rio Alto: "R.Extra"; Oi: "RJ"); judicial ganha quando o assunto fala das duas
TEXTO_JUDICIAL = re.compile(r"recupera\w*\s+judicia|\b(rj|prj)\b")
TEXTO_EXTRAJUDICIAL = re.compile(
    r"extrajudicial|\b(re|pre|prej|rej)\b(?!-)|\br\.? ?extra\b"
)
# o assunto diz que é da própria companhia ("da Companhia e de certas Subsidiárias"), ou que um
# credor pede a falência dela
TEXTO_PROPRIO = re.compile(
    r"\b(da|pela|na|contra a) (companhia|cia)\b"
    r"|\bcompanhia e (de )?(suas|certas|determinadas)\b"
    r"|\be (de )?(parte de )?(suas |certas |determinadas )?(controladas|subsidiarias)\b"
    r"|\be de determinadas\b|\bsua recuperacao\b|\bcredora\b"
)
# o assunto fala de outra companhia ligada a quem entrega ("da controlada CELPA", "da Devedora")
TEXTO_DE_TERCEIRO = re.compile(
    r"\b(controladas?|investidas?|coligadas?|subsidiarias?|participadas?|controladora"
    r"|acionistas? controlador\w*|devedoras?|cedentes?)\b"
)
# o assunto anuncia um pedido: é da própria companhia mesmo depois de falar de um terceiro
TEXTO_DE_PEDIDO = re.compile(r"\b(ajuiza\w*|pedido|requer\w*|impetra\w*|protocol\w*)\b")
# palavras do processo, de datas e de ligação: o que sobra no assunto, fora o nome de quem entrega,
# é nome de outra empresa (Samarco, Renova, Republic Airways)
_PALAVRAS_DO_PROCESSO = """
    a o as os e de da do das dos em no na nos nas ao aos para por pelo pela com sem sobre que se
    sua seu suas seus ii iii iv vi vii viii ix sa ltda
    pedido pedidos recuperacao recuperacoes recup judicial extrajudicial plano planos deferimento
    deferido deferida deferiu homologacao homologado homologada homologou homologatoria peticao
    credor credores credora credoras aprovacao aprovado aprova aprovou decisao decisoes assembleia
    assembleias inicial geral gerais companhia companhias cia sentenca apresentacao apresenta
    apresentado edital financeiras financeiro financeira financeiros encerramento relatorio ata
    atas convocacao rj re pre prej rej prj falencia falencias autofalencia agc age processo
    processamento procedimento grupo protocolo protocola protocolado oficio ajuizamento ajuiza
    ajuizou relacao esclarecimento esclarecimentos esclarece anexo anexos administracao
    administrador administradores administradora fato relevante contabeis novo nova resposta
    acordo comunicado comunica comunicacao solicitacao solicita solicitacoes aditamento suspensao
    proposta informacoes informacao informa requerimento requerimentos requer balanco balancos
    lista aditivo cvm gae sae sre bm bovespa atualizacao atualizacoes parte resultado resultados
    pagamento pagamentos prorrogacao atividades laudo conselho vara estado fluxo caixa concessao
    concessiva patrimonial mensal mensais reestruturacao economico economica consolidado
    consolidacao juizo empresarial comite acao acoes decretacao agravo agravos instrumento versao
    publicacao publico publica despacho capital viabilidade alienacao deliberacao termo alteracao
    alteracoes nao liquidante liquidacao apoio manifestacao juntada stay period upi aviso leilao
    debentures debenturistas bondholders demonstracao demonstracoes demonstrativas nomeacao
    exercicio parecer creditos ratificacao constituicao reconhecimento integra ministerio venda
    certidao certidoes contas renegociacao dividas empresa notificacao renuncia votacao
    continuidade andamento desistencia auditores adiamento juiz notas reapresentacao corte
    julgamento cessao minuta adesao aumento mercado divulgacao divulga carta contratacao tribunal
    justica ativos embargos aj diretor diretoria revogacao auditadas exposicao recibo documentos
    nota cancelamento eua comarca retomada contrato modificacao modificativo instalacao convolacao
    quadro recuperandas recuperanda financiamento acordao classe liberacao antecipacao comprovante
    aquisicao dip oferta celebracao df extincao reuniao sumario especial concursais tjrj
    complemento finalizacao realizada cronograma liminar audiencia civel distribuicao itr causas
    lei final inclusao disponibilizacao consultoria tutela urgencia efeitos avaliacao razoes
    favoravel ajustes autos registro previa sociedades ressalva anuncia conclui confirma
    obrigacoes junto dados bancarios quirografarios intimacao fornecimento importante ciencia
    respeito negociacoes remocao ambito juridico processual tempestiva interposicao recurso
    referente declaracao conclusao material ocorrencia segunda autorizar confessar titulares
    consultas impetracao ajuizaento holding holdco
    janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro
    jan fev mar abr mai jun jul ago set out nov dez
"""
PALAVRAS_DO_PROCESSO = frozenset(_PALAVRAS_DO_PROCESSO.split())


def _simples(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore"
    )
    return sem_acento.decode().lower().strip()


def _ler_ipe_bruto(conteudo_do_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        nome = next(n for n in arquivo.namelist() if "ipe_cia_aberta" in n)
        with arquivo.open(nome) as csv:
            return pd.read_csv(csv, sep=";", encoding="latin-1", dtype=str).fillna("")


def _texto(linha: pd.Series, coluna: str) -> str:
    return str(linha[coluna]).strip()


def _evento_da_categoria(categoria: str) -> str | None:
    return next((evento for trecho, evento in CATEGORIAS if trecho in categoria), None)


def _evento_do_assunto(assunto: str) -> str | None:
    assunto = MENCOES_SEM_EVENTO.sub(" ", assunto)
    return next((evento for padrao, evento in ASSUNTOS if padrao.search(assunto)), None)


def _classificar(categoria: str, assunto: str) -> tuple[str, str] | None:
    """(evento, evidência) do documento sozinho, ou None se não fala de insolvência.

    O evento `recuperacao` (categoria da CVM) ainda não sabe se é judicial ou extrajudicial.
    """
    categoria = _simples(categoria)
    evento = _evento_da_categoria(categoria)
    if evento:
        return evento, "categoria_ipe"
    if categoria in CATEGORIAS_DE_ANUNCIO:
        evento = _evento_do_assunto(_simples(assunto))
        if evento:
            return evento, "fato_relevante"
    return None


def _tipo_de_recuperacao_no_texto(assunto: str, tipo: str) -> str | None:
    """Judicial ou extrajudicial pelo assunto e, se ele não diz, pelo tipo do documento."""
    if TEXTO_JUDICIAL.search(assunto):
        return JUDICIAL
    if TEXTO_EXTRAJUDICIAL.search(assunto) or "extrajudicial" in tipo:
        return EXTRAJUDICIAL
    return None


def nomes_de_outra_empresa(assunto: str, empresa: str) -> list[str]:
    """As palavras do assunto que parecem nome de empresa e não são do nome de quem entrega.

    Num assunto com maiúsculas e minúsculas, só as palavras com inicial maiúscula contam; num todo
    em maiúsculas, todas. Saem as palavras do processo (`PALAVRAS_DO_PROCESSO`).
    """
    do_nome = set(re.findall(r"[a-z0-9]+", _simples(empresa)))
    caixa_alta = assunto.upper() == assunto
    achadas = []
    for palavra in re.findall(r"[^\W\d_]+", assunto):
        if not caixa_alta and not palavra[0].isupper():
            continue
        simples = _simples(palavra)
        if len(simples) < 2 or simples in do_nome or simples in PALAVRAS_DO_PROCESSO:
            continue
        achadas.append(simples)
    return achadas


def _rotular_companhia(documentos: pd.DataFrame) -> pd.DataFrame:
    """Evento, rótulo e regra dos documentos de uma companhia, em ordem de entrega.

    Cada documento só olha os da mesma companhia entregues até o mesmo dia.
    """
    tipos = [
        _tipo_de_recuperacao_no_texto(_simples(a), _simples(t))
        for a, t in zip(documentos["assunto"], documentos["tipo"], strict=True)
    ]
    # o tipo do processo aberto só sai dos documentos que não falam de um terceiro
    explicitos: dict[object, set[str]] = {}
    for (_, doc), tipo in zip(documentos.iterrows(), tipos, strict=True):
        recuperacao = doc["_base"] == "recuperacao" or doc["_base"] in RECUPERACOES
        if tipo and recuperacao and not _fala_de_terceiro(doc):
            explicitos.setdefault(doc["conhecido_em"], set()).add(tipo)
    propria_desde: dict[str, object] = {}
    anterior: tuple[str, str] | None = None
    eventos, rotulos_, regras = [], [], []
    for (_, doc), tipo in zip(documentos.iterrows(), tipos, strict=True):
        evento = str(doc["_base"])
        if evento == "recuperacao" or evento in RECUPERACOES:
            evento = tipo or _tipo_do_processo_aberto(explicitos, doc["conhecido_em"])
        de_terceiro, regra = _de_quem(
            doc,
            sem_processo_proprio=evento not in propria_desde,
            anterior_de_terceiro=anterior == (TERCEIRO, evento),
        )
        if not de_terceiro:
            propria_desde.setdefault(evento, doc["conhecido_em"])
        rotulo = TERCEIRO if de_terceiro else evento
        anterior = (rotulo, evento)
        eventos.append(evento)
        rotulos_.append(rotulo)
        regras.append(regra)
    return documentos.assign(evento=eventos, rotulo=rotulos_, regra=regras)


def _de_quem(
    doc: pd.Series, sem_processo_proprio: bool, anterior_de_terceiro: bool
) -> tuple[bool, str]:
    """(fala de terceiro?, regra que decidiu), na ordem de força dos sinais.

    `sem_processo_proprio`: a companhia ainda não tinha documento próprio deste evento;
    `anterior_de_terceiro`: o documento anterior dela era do mesmo evento, de terceiro.
    """
    assunto = _simples(doc["assunto"])
    empresa = str(doc["empresa"])
    fato = doc["evidencia"] == "fato_relevante"
    outras = nomes_de_outra_empresa(str(doc["assunto"]), empresa) if fato else []
    if TEXTO_PROPRIO.search(assunto):
        return False, "texto_proprio"
    if TEXTO_DE_TERCEIRO.search(assunto):
        return True, "texto_de_terceiro"
    if fato and sem_processo_proprio and "securitiz" in _simples(empresa):
        return True, "securitizadora"
    if outras and sem_processo_proprio:
        return True, f"outra_empresa ({', '.join(outras[:3])})"
    pedido = TEXTO_DE_PEDIDO.search(assunto)
    if fato and sem_processo_proprio and anterior_de_terceiro and not pedido:
        return True, "contexto_de_terceiro"
    return False, str(doc["evidencia"])


def _fala_de_terceiro(doc: pd.Series) -> bool:
    """O assunto fala de outra companhia (sem olhar os documentos anteriores)."""
    assunto = _simples(doc["assunto"])
    if TEXTO_PROPRIO.search(assunto):
        return False
    if TEXTO_DE_TERCEIRO.search(assunto):
        return True
    fato = doc["evidencia"] == "fato_relevante"
    outras = nomes_de_outra_empresa(str(doc["assunto"]), str(doc["empresa"]))
    return fato and bool(outras)


def _tipo_do_processo_aberto(explicitos: dict[object, set[str]], dia: object) -> str:
    """O tipo da recuperação mais recente que a companhia já tinha dito até `dia` (inclusive)."""
    dias = [d for d in explicitos if d <= dia]
    if not dias:
        return SEM_TIPO
    return JUDICIAL if JUDICIAL in explicitos[max(dias)] else EXTRAJUDICIAL


def rotular_com_contexto(tabela: pd.DataFrame) -> pd.DataFrame:
    """Refaz `evento`, `rotulo` e `regra` de cada documento olhando os anteriores da companhia.

    Serve para um arquivo anual e para todos juntos (`base/historico.py`), porque o processo de uma
    companhia atravessa anos. Recalcula tudo das colunas da CVM: rodar de novo não muda nada.
    """
    if tabela.empty:
        return tabela
    base = [
        _classificar(c, a)
        for c, a in zip(tabela["categoria"], tabela["assunto"], strict=True)
    ]
    ordenada = tabela.assign(
        _base=[b[0] if b else None for b in base], _ordem=range(len(tabela))
    ).sort_values(["cnpj", "conhecido_em", "protocolo"], kind="stable")
    partes = [
        _rotular_companhia(documentos)
        for _, documentos in ordenada.groupby("cnpj", sort=False)
    ]
    rotulada = pd.concat(partes).sort_values("_ordem")
    return rotulada.drop(columns=["_base", "_ordem"]).reset_index(drop=True)


def ler_insolvencia_do_ipe(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os documentos de um arquivo anual do IPE que indicam insolvência, um por entrega."""
    bruto = _ler_ipe_bruto(conteudo_do_zip)
    linhas = []
    for _, linha in bruto.iterrows():
        classe = _classificar(linha["Categoria"], linha["Assunto"])
        if classe is None:
            continue
        linhas.append(
            {
                "cnpj": _texto(linha, "CNPJ_Companhia"),
                "empresa": _texto(linha, "Nome_Companhia"),
                "evidencia": classe[1],
                "categoria": _texto(linha, "Categoria"),
                "tipo": _texto(linha, "Tipo"),
                "assunto": _texto(linha, "Assunto"),
                "conhecido_em": linha["Data_Entrega"],
                "referencia": linha["Data_Referencia"],
                # de 2003 a 2014 o protocolo vem vazio: o link identifica o documento
                "protocolo": _texto(linha, "Protocolo_Entrega")
                or _texto(linha, "Link_Download"),
                "versao": pd.to_numeric(linha["Versao"], errors="coerce"),
                "link": _texto(linha, "Link_Download"),
            }
        )
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS))
    if tabela.empty:
        return tabela
    for coluna in ("conhecido_em", "referencia"):
        tabela[coluna] = pd.to_datetime(tabela[coluna], errors="coerce").dt.date
    tabela = tabela.dropna(subset=["conhecido_em"])
    # reapresentações da mesma entrega: fica a versão mais nova
    tabela = tabela.sort_values(["protocolo", "versao"]).drop_duplicates(
        "protocolo", keep="last"
    )
    tabela = tabela.sort_values(["conhecido_em", "cnpj"]).reset_index(drop=True)
    return rotular_com_contexto(tabela)


def primeira_ocorrencia(tabela: pd.DataFrame) -> pd.DataFrame:
    """A primeira data pública de cada rótulo por empresa (com a evidência daquele dia)."""
    if tabela.empty:
        return tabela
    ordenada = tabela.sort_values(["conhecido_em", "protocolo"])
    return ordenada.drop_duplicates(["cnpj", "rotulo"], keep="first").reset_index(
        drop=True
    )


# --- parte 2: "situação especial" do CNPJ (Receita, arquivos de estabelecimentos) ----------------
# o arquivo não tem cabeçalho: 30 colunas; 0-2 CNPJ (básico, ordem, dígito), 3 matriz (1) ou filial
# (2), 28 situação especial, 29 data da situação especial (layout da Receita, conferido em 14/10/2026)
POSICAO_DA_SITUACAO = 28
POSICAO_DA_DATA = 29
SITUACOES = {
    "FALIDO": "falencia",
    "RECUPERACAO JUDICIAL": "recuperacao_judicial",
    "RECUPERACAO EXTRAJUDICIAL": "recuperacao_extrajudicial",
    "LIQUIDACAO EXTRA-JUDICIAL": "liquidacao_extrajudicial",
    "EM LIQUID.EXTRA-JUDICIAL": "liquidacao_extrajudicial",
    "LIQUIDACAO JUDICIAL": "liquidacao_judicial",
    "EM LIQUIDACAO": "liquidacao",
    "INTERVENCAO": "intervencao",
}
MES_NA_PASTA = re.compile(r"/(\d{4}-\d{2})/Estabelecimentos\d*\.zip$", re.IGNORECASE)


def ler_situacao_especial_do_cnpj(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os estabelecimentos com "situação especial" num arquivo de estabelecimentos do CNPJ.

    Lê em fluxo (o arquivo tem milhões de linhas) e guarda só CNPJ, matriz ou filial, situação e data:
    nome fantasia, endereço, telefone e e-mail nunca saem (LGPD).
    """
    linhas = []
    with (
        zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo,
        arquivo.open(arquivo.namelist()[0]) as bruto,
    ):
        leitor = csv.reader(io.TextIOWrapper(bruto, encoding="latin-1"), delimiter=";")
        for campos in leitor:
            if len(campos) <= POSICAO_DA_DATA:
                continue
            situacao = campos[POSICAO_DA_SITUACAO].strip()
            if not situacao:
                continue
            basico, ordem, digito = (campos[i].strip() for i in range(3))
            linhas.append(
                {
                    "cnpj": f"{basico[:2]}.{basico[2:5]}.{basico[5:8]}/{ordem}-{digito}",
                    "cnpj_basico": basico,
                    "matriz": campos[3].strip() == "1",
                    "situacao_especial": situacao,
                    "rotulo": SITUACOES.get(situacao),
                    "data_situacao_especial": campos[POSICAO_DA_DATA].strip(),
                }
            )
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "cnpj",
            "cnpj_basico",
            "matriz",
            "situacao_especial",
            "rotulo",
            "data_situacao_especial",
        ],
    )
    tabela["data_situacao_especial"] = pd.to_datetime(
        tabela["data_situacao_especial"], format="%Y%m%d", errors="coerce"
    ).dt.date
    tabela["rotulo"] = (
        tabela["rotulo"].astype(object).where(tabela["rotulo"].notna(), None)
    )
    return tabela


def montar_situacao_especial(
    conexao: sa.Connection, pasta: Path, agora: datetime
) -> dict[str, int]:
    """`<pasta>/cnpj_situacao_especial/<AAAA-MM>.parquet` para cada mês do CNPJ guardado.

    O CNPJ só mostra o retrato do mês: cada mês guardado vira um retrato, e o histórico "como era na
    data" nasce da sequência deles (`mes_do_retrato`, mais `data_situacao_especial` da Receita).
    """
    por_mes: dict[str, list[pd.DataFrame]] = {}
    origens: dict[str, list[dict[str, str]]] = {}
    for original in originais_mais_recentes(conexao, "rfb-cnpj"):
        achado = MES_NA_PASTA.search(original.url)
        conteudo = acervo.ler_original(original.caminho_do_original)
        if achado is None or conteudo is None:
            continue
        tabela = ler_situacao_especial_do_cnpj(conteudo).assign(
            mes_do_retrato=achado.group(1),
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
            versao_do_codigo=versao_do_codigo(),
        )
        por_mes.setdefault(achado.group(1), []).append(tabela)
        origens.setdefault(achado.group(1), []).append(
            {"url": original.url, "sha256": original.sha256}
        )
    linhas: dict[str, int] = {}
    for mes, partes in por_mes.items():
        tabela = pd.concat(partes, ignore_index=True)
        gravar_se_mudou(
            tabela,
            pasta / "cnpj_situacao_especial" / f"{mes}.parquet",
            origens[mes],
            ["cnpj"],
            carimbos=LINHAGEM,
        )
        linhas[mes] = len(tabela)
    return linhas
