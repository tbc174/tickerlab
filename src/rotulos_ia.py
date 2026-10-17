"""Rótulos da fila das 21h feitos por IA e auditados às cegas pelo Tiago (ADR 0072).

A IA recebe o mesmo guia da página de rotulagem (versão `v2`) e devolve nota (1 a 5), tema e, nos
fatos relevantes, assunto. As proteções da ADR ficam aqui, sem rede:

- **sem o nome da empresa:** razão social, códigos de negociação e CNPJ viram `[EMPRESA]`, `[CODIGO]`
  e `[CNPJ]` antes de ir para o modelo, para ele não dar a nota pelo que sabe que aconteceu depois;
  desde o prompt v3 (Emenda 2, 17/10/2026) o conteúdo que ainda entregava a empresa também sai:
  outras empresas, lugares, pessoas, endereços eletrônicos e números de registro (`anonimizar`);
- **lista fechada** (saída estruturada) e um **trecho que tem de existir** no que o modelo leu;
  resposta fora disso vira erro, nunca um chute;
- cada rótulo guarda `por: "ia"`, o modelo e a versão do prompt, e nunca se mistura com os humanos.

O modelo foi escolhido pelo Tiago antes da auditoria (14/10/2026: Sonnet 5.5, teto de US$ 60); trocar
de modelo ou de prompt depois de ver a auditoria conta como uma tentativa nova (ADR 0006). Desde a
Emenda 1 (17/10/2026), o **Opus 5.5** rotula às cegas o conjunto de prova com o mesmo pedido, para
conferir o Sonnet no lugar do Tiago; os papéis ficam fixos (`MODELO` e `MODELO_CONFERENTE`).
"""

import functools
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

import anthropic

from base.cnpj import dv_confere, normalizar_cnpj, tem_letra
from src import topicos
from src.auditoria_rotulos import GENERICAS

MODELO = "claude-sonnet-5-5"  # o rotulador da fila inteira (14/10)
MODELO_CONFERENTE = "claude-opus-5-5"  # o segundo modelo às cegas (Emenda 1, 17/10)
# chave criada fora de um workspace: a API pede o id do workspace em cada pedido (não é segredo)
VARIAVEL_DO_WORKSPACE = "ANTHROPIC_WORKSPACE_ID"
VERSAO_DO_PROMPT = (
    "3"  # v3 (17/10/2026, Emenda 2): o conteúdo também é anonimizado; v2: sem o setor
)
GUIA = "v2"
MAX_CARACTERES_DO_TEXTO = 6_000  # o começo do documento, como no leitor (ADR 0069)
MAX_TOKENS_DA_RESPOSTA = 2_000  # a resposta é curta; a folga é para o raciocínio
FATO_RELEVANTE = "Fato Relevante"

DESCONTO_DO_LOTE = 0.5  # a Batch API cobra a metade


@dataclass(frozen=True)
class Modelo:
    """Preços em US$ por milhão de tokens. Ler do cache custa uma fração da entrada, que muda por
    modelo; escrever custa 1,25x em todos. A saída por evento é só para a estimativa (o real vem de
    `usage`)."""

    entrada: float
    saida: float
    leitura_do_cache: float
    saida_estimada_por_evento: int


MODELOS = {
    # Sonnet 5.5 (14/10/2026); saída medida no 1º lote (15/10): 59 por evento (167.640 em 2.849)
    MODELO: Modelo(2.00, 10.00, 0.1, 80),
    # Opus 5.5 (skill claude-api, 17/10/2026): cache lido a 0,05x. O raciocínio do Opus não desliga e
    # entra na saída: a estimativa usa o triplo do que o Sonnet gastou, até o piloto medir
    MODELO_CONFERENTE: Modelo(4.00, 20.00, 0.05, 180),
}


def modelo_conhecido(nome: str) -> Modelo:
    """O preço do modelo; um nome fora da lista é erro (nunca o preço de outro)."""
    if nome not in MODELOS:
        raise ValueError(
            f"Modelo sem preço cadastrado: {nome} (conhecidos: {', '.join(MODELOS)})"
        )
    return MODELOS[nome]


EMPRESA, CODIGO, CNPJ = "[EMPRESA]", "[CODIGO]", "[CNPJ]"
# v3 (Emenda 2): o conteúdo que ainda entregava a empresa na v2
OUTRA_EMPRESA, LOCAL, PESSOA = "[OUTRA EMPRESA]", "[LOCAL]", "[pessoa]"
ENDERECO, NUMERO = "[ENDEREÇO]", "[NUMERO]"
MARCADORES = (EMPRESA, CODIGO, CNPJ, OUTRA_EMPRESA, LOCAL, PESSOA, ENDERECO, NUMERO)
_MARCADOR = re.compile("|".join(re.escape(m) for m in MARCADORES))
SEM_TEXTO = "(sem texto: o documento não pôde ser lido; julgue pelo assunto)"

NOTAS = {
    1: "Rotina",
    2: "Pouco relevante",
    3: "Relevante",
    4: "Muito relevante",
    5: "Muda a tese",
}
TEMAS = (
    "resultado",
    "dividendos",
    "divida",
    "governanca",
    "fusao",
    "operacao",
    "regulatorio",
)
CONFIANCAS = ("alta", "media", "baixa")

_ASSUNTOS = "\n".join(f"- {codigo}: {nome}" for codigo, nome in topicos.TOPICOS.items())
SISTEMA = f"""Você rotula documentos públicos de companhias abertas brasileiras (CVM), como uma pessoa \
faria na página de rotulagem do TickerLab. O nome, os códigos de negociação e o CNPJ da empresa foram \
trocados por {EMPRESA}, {CODIGO} e {CNPJ}; outras empresas, lugares, pessoas, endereços eletrônicos e \
números de registro viram {OUTRA_EMPRESA}, {LOCAL}, {PESSOA}, {ENDERECO} e {NUMERO}: não tente \
descobrir qual é a empresa nem quem são os outros. Julgue só pelo que está no documento, como se \
fosse a data de entrega dele; não use o que aconteceu depois.

Importância (nota de 1 a 5). Pergunte: para quem tem esta ação, este documento muda alguma coisa?
1 Rotina. Obrigação de calendário, formulário padrão, posição mensal de ações de administradores sem \
nada fora do comum.
2 Pouco relevante. Informação útil, mas esperada: convocação de assembleia comum, ata sem surpresas, \
ajuste de estatuto.
3 Relevante. Vale ler: resultado do trimestre, proventos anunciados, emissão de dívida, troca de diretor.
4 Muito relevante. Mexe com o valor da empresa: aquisição, venda de ativo grande, revisão forte de \
metas, renegociação de dívida.
5 Muda a tese. Recuperação judicial, fusão ou OPA, troca de controle, fraude ou reapresentação grave \
de balanço.
Na dúvida entre duas notas, fique com a menor.

Tema: o assunto principal. resultado, dividendos, divida, governanca, fusao (inclui aquisição e OPA), \
operacao (o negócio em si) ou regulatorio.

Assunto (só quando for pedido, nos fatos relevantes): o que a empresa está comunicando, em detalhe. \
Use só os códigos:
{_ASSUNTOS}
Fusão, incorporação de empresa e de ações são FUSAO_INCORPORACAO; OPA para cancelamento de registro é \
FECHAMENTO_CAPITAL; recompra não é aquisição. Sem assunto claro, OUTROS.

Trecho: copie exatamente do documento (ou do assunto) a frase ou parte de frase que mais justifica a \
nota. Não resuma nem traduza.
Confiança: alta, media ou baixa."""


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )


_VARIANTES = {
    "a": "aáàâãä",
    "e": "eéèêë",
    "i": "iíìîï",
    "o": "oóòôõö",
    "u": "uúùûü",
    "c": "cç",
    "n": "nñ",
}
_SUFIXO = re.compile(r"(?i)[\s,.-]*\b(s\.?\s*/?\s*a\.?|ltda\.?)\s*$")
# com letras desde a IN RFB 2.229/2024 (só nos 12 primeiros; os 2 DVs continuam números)
_CNPJ = re.compile(r"\b[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2}\b")
_CODIGO = re.compile(r"\b[A-Z]{4}\d{1,2}\b")
_MIN_LETRAS_DO_NOME = 4

# --- v2 (17/10/2026): o teste de identificação da v1 achou a palavra do nome no texto em 118 de 176 ---
# o cadastro junta partes com " - ": "PETRÓLEO BRASILEIRO S.A. - PETROBRAS", "LIGHT S.A. - EM RECUPERAÇÃO
# JUDICIAL"; a situação é de hoje e, no texto, é conteúdo (nunca é trocada)
_PARTES = re.compile(r"\s+-\s+")
_SITUACAO = re.compile(
    r"(?i)^(massa\s+)?(falida|em\s+recupera[cç][aã]o(\s+extra)?\s*judicial"
    r"|em\s+liquida[cç][aã]o(\s+extrajudicial)?)$"
)
_CONECTORES = frozenset(["de", "do", "da", "dos", "das", "e", "em"])
# começos de nome de 2 ou 3 letras que são palavras (em maiúsculas, aparecem em qualquer título:
# "PODERÁ SER", "VIA E-MAIL") ou termos de qualquer empresa ("SPE"): não são trocados
_SIGLAS_COMUNS = frozenset(
    ["DE", "DO", "DA", "DOS", "DAS", "E", "EM", "NO", "NA", "AO", "SA", "CIA", "LTD", "INC", "CO",
     "RIO", "SUL", "AÇO", "BOA", "SER", "SOC", "SPE", "VIA", "SAO", "SÃO", "PAR", "SOL", "LUZ"]
)  # fmt: skip
_ANTES_DA_SIGLA = frozenset(["BANCO", "GRUPO"])  # "BANCO ABC BRASIL", "GRUPO SBF"
# palavras dos 816 nomes da fila (lidas em 17/10/2026) que são português ou termo do negócio: apagar
# "pagamento", "distribuidora" ou "recuperação" tiraria o sentido do texto. As que a auditoria já
# trata como genéricas (`GENERICAS`) também ficam. Nomes de lugar no nome da empresa ("Sergipe",
# "Bahia") e marcas ("Vale", "Rumo", "Claro") saem, só nos documentos dela.
_TEXTO_DAS_COMUNS = """
    recuperacao judicial extrajudicial liquidacao falida massa
    empresa grupo holdings part particip participacao participations sociedade company corp limited
    capital investimento investments partners consorcio
    securitizadora securitizacao concessionaria concessao concessoes concess conc rodovias rodovia
    rodoviarios estradas ferrovia distribuidora distrib educacao educacional educacionais escola
    engenharia imobiliarios imobiliario imoveis imob mercantil creditos credito cred credit financeiros
    financiamento financial finance telecomunicacoes telecomunicacao telecom aguas agua esgoto esgotos
    tecidos produtos energias energetica energeticos energ eletricas eletricidade eletronica centrais
    empreend empreends infraestrutura infra industrial industriais industrializados locacao
    renovaveis lojas shopping saude health consultoria desenvolvimento arrendamento leasing solucoes
    solutions transmissora veiculos digital agropecuaria agro agricola agricolas agroindustrial
    agronegocios farmaceutica farmaceuticos farma pharma farmacia drogaria mineracao minerals miner
    cartoes metropolitana metropolitano metrop redes rede papel celulose hospital hospitalar hotel
    hoteis global quimica petroquimica center centers centro textil porto portuaria operacoes operacao
    operadora internet corretora corretagem varejo varejista tech technology seguridade seguro servico
    advisory malls properties propriedades prop ambiental environmental diagnosticos sistema ligas
    ferro forca consignados pagamento instituicao instituto fiacao tecelagem linha linhas integradas
    medicamentos incorporacoes fabrica fertilizantes esportivos transportes transportadora medicos
    medicina residencial turismo usinas maquinas equipamentos equip alimentacao cereais cabos metais
    metal metalicos componentes editora bolsa balcao mobile mobilidade mobility bicicletas assessoria
    restaurantes sementes borrachas real estate securities regiao modas moda store carvao imagem trans
    basico basicos melhoramentos aluminio aeroporto aeroportos internacional international terapeuticos
    agencia viagens parts laboratorios laboratorio frigorifico outlets general meios fibra aereas casas
    talheres care florestal florestas embalagem irrigacao refratarios brinquedos manufatura foods
    estruturas consumidor consumo cosmeticos trade navegacao maritimos trust valorizacao residuos plano
    publicos produtores software implementos recebiveis negocios roupas plasticos fidelidade
    abastecimento abastec solar bebidas entretenimento armas terminal conteineres pigmentos moveis
    caminhoes urbano biologicos cimentos siderurgicas mecanicas academias ginastica petroleos petroleum
    oleo confeccoes interestaduais intermodal commercial relacionamentos adquirencia compartilhamento
    automob auto hidro gerais estadual securitzadora const empr emp arrend telec resseguros norte nordeste sudeste noroeste leste oeste brazil brazilian america
    americas bank para mais menos tres nova novo alto forte terra verde quero fica pague uniao dias
    pratica impacto origem estilo quality
"""
PALAVRAS_COMUNS = frozenset(_TEXTO_DAS_COMUNS.split())


def _palavras(texto: str) -> set[str]:
    """As palavras do texto sem acento e em minúsculas ("PETRÓLEO" vira "petroleo")."""
    return set(re.findall(r"[a-z0-9]+", _sem_acento(texto).lower()))


def _distintas(nome: str) -> set[str]:
    """As palavras do nome que distinguem a empresa: 4 letras ou mais (como a auditoria conta o
    acerto), fora das genéricas da auditoria e das palavras comuns."""
    return {
        p for p in _palavras(nome)
        if len(p) >= _MIN_LETRAS_DO_NOME and p not in GENERICAS and p not in PALAVRAS_COMUNS
    }  # fmt: skip


def _partes_do_nome(nome: str) -> list[str]:
    """O nome do cadastro em partes, sem as de situação ("- EM RECUPERAÇÃO JUDICIAL")."""
    partes = _PARTES.split(" ".join(nome.split()))
    return [p for p in partes if p and not _SITUACAO.match(_SUFIXO.sub("", p))]


def _parte_e_nome(parte: str, principal: bool) -> bool:
    """A primeira parte é sempre o nome. As outras só quando têm palavra que distingue ("PETROBRAS")
    ou são um nome sem conector ("BRASIL, BOLSA, BALCÃO"); com conector ("INSTITUIÇÃO DE PAGAMENTO")
    são descrição e ficam no texto."""
    if principal or _distintas(parte):
        return True
    palavras = _palavras(parte)
    return len(palavras) >= 2 and not _CONECTORES.intersection(palavras)


def _siglas(nome: str) -> set[str]:
    """As siglas curtas do nome (OI, BRF, B3), como estão no cadastro: a primeira palavra de uma
    parte, ou a que vem depois de "BANCO" ou "GRUPO". As do meio ("IND. E COM.") são abreviações."""
    siglas = set()
    for parte in _partes_do_nome(nome):
        palavras = re.findall(r"[^\W_]+", parte)
        if not palavras:
            continue
        candidatas = palavras[:2] if palavras[0] in _ANTES_DA_SIGLA else palavras[:1]
        siglas.update(
            s for s in candidatas
            if 2 <= len(s) <= 3 and any(c.isalpha() for c in s) and s not in _SIGLAS_COMUNS
        )  # fmt: skip
    return siglas


# --- v3 (17/10/2026, Emenda 2): o cadastro abrevia ("CIA", "IND E COM", "ENERG") e tira os conectivos;
# o texto escreve por extenso ("Companhia de Saneamento Básico do Estado de São Paulo"). Na v2 isso
# escapou em parte dos 110 reconhecidos. Cada grupo é uma palavra do cadastro e suas formas no texto.
_FORMAS_DA_ABREVIACAO = (
    ("cia", "companhia"), ("cias", "companhias"),
    ("ind", "industria", "industrias", "industrial"),
    ("com", "comercio", "comercial"),
    ("part", "particip", "participacoes"),
    ("empreend", "empreends", "empreendimentos"),
    ("adm", "administracao", "administradora"),
    ("distrib", "distribuidora", "distribuicao"),
    ("telec", "telecomunicacoes"),
    ("energ", "energia", "energetica"),
    ("metrop", "metropolitana", "metropolitano"),
    ("emp", "empr", "empresa", "empresas"),
    ("const", "constr", "construcoes", "construtora"),
    ("sid", "siderurgica"), ("nac", "nacional"),
    ("bras", "brasil", "brasileira", "brasileiro"),
    ("agric", "agricola"), ("imob", "imobiliaria", "imobiliarios"),
    ("transp", "transportes"), ("arrend", "arrendamento"),
    ("abastec", "abastecimento"), ("equip", "equipamentos"),
    ("concess", "conc", "concessoes", "concessionaria"),
    ("infra", "infraestrutura"), ("mat", "materiais"), ("petr", "petroleo"),
)  # fmt: skip
_ABREVIACOES = {forma: formas for formas in _FORMAS_DA_ABREVIACAO for forma in formas}
_SOCIEDADE_ANONIMA = re.compile(r"^s\.?\s*/?\s*a\.?$")
# entre as palavras do nome cabem conectivos que o cadastro não tem ("de", "do", "e")
_ENTRE_PALAVRAS = r"(?:\s+(?i:d[aeo]s?|e|em))*\s+"


def _letras(palavra: str) -> str:
    """Cada letra com e sem acento, nas duas caixas ("a" casa "A", "á", "Ã"...)."""
    pedacos = []
    for letra in palavra:
        if letra in _VARIANTES:
            pedacos.append(f"[{_VARIANTES[letra]}{_VARIANTES[letra].upper()}]")
        elif letra.isalpha():
            pedacos.append(f"[{letra}{letra.upper()}]")
        else:
            pedacos.append(re.escape(letra))
    return "".join(pedacos)


def _palavra_do_nome(palavra: str) -> str:
    """O padrão de uma palavra do cadastro: "S.A." em qualquer grafia, abreviação ou forma por
    extenso (com ponto opcional: "Cia."), ou as letras; a pontuação do meio aceita espaços."""
    if _SOCIEDADE_ANONIMA.match(palavra):
        return r"[sS]\.?\s?/?\s?[aA]\.?"
    pedacos = []
    for pedaco in re.findall(r"[a-z0-9]+|[^a-z0-9]", palavra):
        if pedaco in _ABREVIACOES:
            formas = "|".join(_letras(f) + r"\.?" for f in _ABREVIACOES[pedaco])
            pedacos.append(f"(?:{formas})")
        elif pedaco.isalnum():
            pedacos.append(_letras(pedaco))
        else:
            pedacos.append(r"\s*" + re.escape(pedaco) + r"\s*")
    return "".join(pedacos)


def _corpo_do_nome(nome: str) -> str:
    """O padrão de uma variante do nome, palavra a palavra, sem os conectivos do cadastro (eles e
    os do texto cabem entre as palavras)."""
    palavras = [
        p for p in _sem_acento(nome).lower().split() if p not in _CONECTORES
    ] or _sem_acento(nome).lower().split()
    return _ENTRE_PALAVRAS.join(_palavra_do_nome(p) for p in palavras)


def _padrao_do_nome(nome: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + _corpo_do_nome(nome) + r"(?!\w)")


def _comecos(nome: str) -> list[str]:
    """Os começos do nome com pelo menos duas palavras de 4 letras ("Viver Incorporadora"), sem
    terminar num conector ("e", "de"). Palavra sozinha só entra pelas distintas (`_distintas`, v2):
    "Banco" ou "Petróleo" apagariam o sentido do texto."""
    palavras = nome.split()
    comecos = []
    for k in range(2, len(palavras)):
        parte = palavras[:k]
        if len(parte[-1]) >= 3 and sum(len(p) >= 4 for p in parte) >= 2:
            comecos.append(" ".join(parte))
    return comecos


def _variantes_do_nome(nomes: list[str]) -> list[str]:
    """Cada parte do nome que é nome (v2), sem o sufixo da sociedade (S.A., S/A, Ltda.), os começos
    dela e as palavras que distinguem a empresa, do maior para o menor (o maior troca primeiro)."""
    variantes = set()
    for nome in nomes:
        partes = _partes_do_nome(nome)
        variantes.add(" - ".join(partes))  # o nome inteiro, sem a situação
        for i, parte in enumerate(partes):
            if _parte_e_nome(parte, principal=i == 0):
                sem_sufixo = _SUFIXO.sub("", parte)
                variantes.update((parte, sem_sufixo, *_comecos(sem_sufixo)))
        variantes.update(_distintas(nome))
    return sorted(
        (v for v in variantes if sum(c.isalpha() for c in v) >= _MIN_LETRAS_DO_NOME),
        key=len,
        reverse=True,
    )


def _mascara_do_cnpj(achado: re.Match[str]) -> str:
    """Só números: máscara sempre, como antes; com letras, só se o DV confere (não é uma palavra)."""
    texto = achado.group()
    completo = normalizar_cnpj(texto)
    if not tem_letra(texto) or (completo is not None and dv_confere(completo)):
        return CNPJ
    return texto


def _sem_o_nome(texto: str, nomes: list[str]) -> str:
    """A empresa do documento vira [EMPRESA]: nomes do cadastro em qualquer grafia (v2 e v3), o
    sufixo que sobrou ("[EMPRESA] S/A") e as siglas."""
    for variante in _variantes_do_nome(nomes):
        texto = _padrao_do_nome(variante).sub(EMPRESA, texto)
    texto = _SUFIXO_SOLTO.sub(EMPRESA, texto)
    for sigla in set().union(*(_siglas(nome) for nome in nomes)):
        formas = "|".join(re.escape(f) for f in {sigla, sigla.capitalize()})
        texto = re.sub(rf"(?<![\w/])(?:{formas})(?![\w/])", EMPRESA, texto)
    return texto


def anonimizar(
    texto: str, nomes: list[str], outras: Sequence[str] | None = None
) -> str:
    """O que o modelo não pode ver (ADR 0072, Emenda 2): CNPJ, códigos de negociação (aqui e em
    outras bolsas), endereços eletrônicos, a empresa do documento (`nomes`), as outras empresas
    (`outras`, o cadastro da fila; por padrão `OUTRAS_EMPRESAS`) e qualquer sociedade com sufixo,
    lugares, números de registro e pessoas. Datas, valores, leis e o vocabulário do negócio ficam."""
    texto = _CNPJ.sub(_mascara_do_cnpj, texto)
    texto = _CODIGO.sub(CODIGO, texto)
    texto = _BOLSA_ESTRANGEIRA.sub(CODIGO, texto)
    texto = _CODIGO_DE_ADR.sub(CODIGO, texto)
    texto = _ENDERECO_ELETRONICO.sub(ENDERECO, texto)
    texto = _sem_o_nome(texto, nomes)
    texto = mascarar_pessoas(
        texto
    )  # antes das outras empresas: um sobrenome pode ser marca
    padrao_das_outras = _padrao_das_outras(
        OUTRAS_EMPRESAS if outras is None else tuple(outras)
    )
    if padrao_das_outras is not None:
        texto = padrao_das_outras.sub(OUTRA_EMPRESA, texto)
    texto = _OUTRA_SOCIEDADE.sub(OUTRA_EMPRESA, texto)
    texto = _GRUPO.sub(OUTRA_EMPRESA, texto)
    # o apelido que o documento define ("Sabesp", "GOL") vale para quem foi definido
    for marcador in (EMPRESA, OUTRA_EMPRESA):
        for apelido in _apelidos(texto, marcador):
            texto = _padrao_do_apelido(apelido).sub(marcador, texto)
    texto = _DATACAO.sub(f"{LOCAL}, ", texto)
    texto = _CIDADE_UF.sub(LOCAL, texto)
    texto = _LUGARES_CONHECIDOS.sub(LOCAL, texto)
    texto = _ENDERECO_POSTAL.sub(LOCAL, texto)
    texto = _CEP.sub(LOCAL, texto)
    for padrao in (_NIRE, _PROCESSO):
        texto = padrao.sub(NUMERO, texto)
    for padrao in (_NIRE_SEM_PONTO, _REGISTRO_CVM):
        texto = padrao.sub(lambda m: m.group(1) + NUMERO, texto)
    return texto


# --- v3: o conteúdo que entregava a empresa na v2 (ADR 0072, Emenda 2) --------------------------

OUTRAS_EMPRESAS: tuple[str, ...] = ()
_MIN_LETRAS_DE_OUTRA = (
    5  # palavra sozinha de outra empresa: "Cosan" sim, "Vale" não (é verbo)
)


def definir_outras_empresas(nomes: Iterable[str]) -> None:
    """O cadastro da fila inteira (todas as empresas dos eventos), lido uma vez em `main`, antes
    de qualquer filtro: `documento()` o usa em todos os passos, então o pedido guardado e o
    recalculado em `buscar` têm o mesmo hash."""
    global OUTRAS_EMPRESAS
    OUTRAS_EMPRESAS = tuple(dict.fromkeys(n for n in nomes if n))


def _padrao_das_outras(outras: tuple[str, ...]) -> re.Pattern[str] | None:
    return _padrao_das_outras_guardado(outras)


@functools.lru_cache(maxsize=4)
def _padrao_das_outras_guardado(outras: tuple[str, ...]) -> re.Pattern[str] | None:
    """Um só padrão com as variantes de todos os nomes do cadastro, do maior para o menor: nome com
    e sem sufixo, começos e palavras distintas de 5 letras ou mais (fora as de lugar), só quando
    começam em maiúscula no texto ("Light" sim, "light" não)."""
    variantes = [
        v for v in _variantes_do_nome(list(outras))
        if len(v.split()) >= 2
        or (sum(c.isalpha() for c in v) >= _MIN_LETRAS_DE_OUTRA
            and _sem_acento(v).lower() not in _PALAVRAS_DE_LUGAR)
    ]  # fmt: skip
    if not variantes:
        return None
    corpos = (
        _corpo_do_nome(v) + (r"(?!\w)\.?" if _SUFIXO.search(v) else r"(?!\w)")
        for v in variantes
    )
    return re.compile(r"(?<!\w)(?![a-zà-ÿ])(?:" + "|".join(corpos) + ")")


_SUFIXO_SOLTO = re.compile(r"\[EMPRESA\]\s*,?\s*(?:S\.?\s?/?\s?A\.?|Ltda\.?)(?!\w)")
# o documento define o apelido logo depois do nome: ("Sabesp" ou "Companhia"), (“FNS”); entre o
# marcador e a definição podem estar os códigos e o CNPJ, já trocados
_JANELA_DO_APELIDO = {
    marcador: re.compile(
        re.escape(marcador) + r"((?:[^\n\[]|\[(?:CODIGO|CNPJ|NUMERO)\]){0,120})"
    )
    for marcador in (EMPRESA, OUTRA_EMPRESA)
}
_DEFINICAO = re.compile(r"\(\s*((?:[\"“][^\"“”\n]{2,40}[\"”]\s*(?:ou|,|e)?\s*)+)\)")
_ENTRE_ASPAS = re.compile(r"[\"“]\s*([^\"“”\n]{2,40}?)\s*[\"”]")
# um apelido com uma destas palavras não é o nome da empresa ("Grupo Ad Hoc", "Companhias")
_APELIDOS_GENERICOS = frozenset(
    [
        "companhia",
        "companhias",
        "sociedade",
        "sociedades",
        "empresa",
        "empresas",
        "emissora",
        "emitente",
        "ofertante",
        "devedora",
        "cedente",
        "banco",
        "grupo",
        "group",
        "fundo",
        "controladora",
        "controladas",
        "incorporadora",
        "administradora",
        "compradora",
        "vendedora",
        "garantidora",
        "acordo",
        "contrato",
        "oferta",
        "operacao",
    ]
)


def _apelidos(texto: str, marcador: str) -> set[str]:
    """Os termos definidos entre aspas e parênteses logo depois do marcador, fora os genéricos
    ("Companhia", "Sociedade"): o nome pelo qual o documento chama a empresa dali em diante."""
    apelidos = set()
    for janela in _JANELA_DO_APELIDO[marcador].finditer(texto):
        for definicao in _DEFINICAO.findall(janela.group(1)):
            for apelido in _ENTRE_ASPAS.findall(definicao):
                palavras = _palavras(apelido)
                if (
                    palavras
                    and len(apelido.split()) <= 3
                    and not palavras & (_APELIDOS_GENERICOS | GENERICAS)
                    and not palavras <= PALAVRAS_COMUNS
                ):
                    apelidos.add(apelido)
    return apelidos


def _padrao_do_apelido(apelido: str) -> re.Pattern[str]:
    """Como o nome, mas só começando em maiúscula: "Grupo Ad Hoc" não casa "um grupo ad hoc"."""
    return re.compile(r"(?<!\w)(?![a-zà-ÿ])" + _corpo_do_nome(apelido) + r"(?!\w)")


_BOLSA_ESTRANGEIRA = re.compile(
    r"\b(?:NYSE|NASDAQ|OTCQX|OTCQB|OTC|LSE|LATIBEX|EURONEXT|TSX"
    r"|ADR(?:\s+(?:N[ií]vel\s+)?(?:I{1,3}|[1-3]))?)\s*:\s*[A-Z]{2,6}\b"
)
_CODIGO_DE_ADR = re.compile(
    r"\b[A-Z]{4}Y\b"
)  # LZRFY, PBRAY: o código do ADR termina em Y
_ENDERECO_ELETRONICO = re.compile(
    r"(?i)\b(?:https?://|www\.)[^\s)>\]]+"
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|(?<![\w@])(?:[\w-]+\.)+(?:com\.br|gov\.br|org\.br|net\.br|com|net|org|io)(?![\w.])(?:/[^\s)]*)?"
)
_MAIUSCULA = "A-ZÁÉÍÓÚÂÊÔÃÕÇ"
_MINUSCULA = "a-záéíóúâêôãõç"
_SUFIXOS_DE_SOCIEDADE = (
    r"(?:S\.?\s?/?\s?A\.?|Ltda\.?|S\.?R\.?L\.?|Inc\.?|LLC|L\.?P\.?|N\.?V\.?|Ltd\.?|Corp\.?|GmbH"
    r"|Holding|Participa[çc][õo]es)(?!\w)"
)
_PALAVRA_DE_EMPRESA = rf"[{_MAIUSCULA}\d][\w&'’.-]*"
_OUTRA_SOCIEDADE = re.compile(
    rf"(?<![\w\[])[{_MAIUSCULA}\d][\w&'’.-]+"  # a 1ª palavra tem 2 letras ou mais ("A Alfa" não)
    rf"(?:\s+(?:(?i:d[aeo]s?|e|&)\s+)?{_PALAVRA_DE_EMPRESA}){{0,6}}\s*,?\s+{_SUFIXOS_DE_SOCIEDADE}"
)
_GRUPO = re.compile(
    rf"(?<!\w)Grupo\s+[{_MAIUSCULA}][\w&-]*(?:\s+[{_MAIUSCULA}][\w&-]*){{0,2}}"
)
_UF = r"(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)"
_PALAVRA_DE_LUGAR = rf"[{_MAIUSCULA}][\w'’]*"
_LUGAR = rf"{_PALAVRA_DE_LUGAR}(?:\s+(?:(?i:d[aeo]s?)\s+)?{_PALAVRA_DE_LUGAR}){{0,3}}"
_COM_UF = rf"(?:\(\s*{_UF}\s*\)|/\s?{_UF}(?!\w)|\s+-\s+{_UF}(?!\w))"
_DATACAO = (
    re.compile(  # "Caxias do Sul, 31 de julho de 2024" (ou em caixa alta): a data fica
        rf"(?<!\w){_LUGAR}\s*{_COM_UF}?,\s*"
        rf"(?=\d{{1,2}}º?\s+(?i:de)\s+[^\W\d_]+\s+(?i:de)\s+\d{{4}})"
    )
)
_CIDADE_UF = re.compile(rf"(?<!\w){_LUGAR}\s*{_COM_UF}")
_ESTADOS_E_CAPITAIS = (
    "Acre", "Alagoas", "Amapá", "Amazonas", "Bahia", "Ceará", "Distrito Federal", "Espírito Santo",
    "Goiás", "Maranhão", "Mato Grosso", "Mato Grosso do Sul", "Minas Gerais", "Pará", "Paraíba",
    "Paraná", "Pernambuco", "Piauí", "Rio de Janeiro", "Rio Grande do Norte", "Rio Grande do Sul",
    "Rondônia", "Roraima", "Santa Catarina", "São Paulo", "Sergipe", "Tocantins",
    "Rio Branco", "Maceió", "Macapá", "Manaus", "Salvador", "Fortaleza", "Brasília", "Vitória",
    "Goiânia", "São Luís", "Cuiabá", "Campo Grande", "Belo Horizonte", "Belém", "João Pessoa",
    "Curitiba", "Recife", "Teresina", "Natal", "Porto Alegre", "Porto Velho", "Boa Vista",
    "Florianópolis", "Aracaju", "Palmas",
)  # fmt: skip
_PALAVRAS_DE_LUGAR = frozenset(
    p for lugar in _ESTADOS_E_CAPITAIS for p in _palavras(lugar)
)
_LUGARES_CONHECIDOS = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(forma)
        for lugar in sorted(_ESTADOS_E_CAPITAIS, key=len, reverse=True)
        for forma in (lugar, lugar.upper())
    )
    + r")(?!\w)"
)
_ENDERECO_POSTAL = re.compile(  # só a via e o número; andar, bairro e cidade seguem suas regras
    r"(?i)(?<!\w)(?:rua|avenida|av\.|alameda|pra[çc]a|rodovia|rod\.|estrada|travessa|largo)\s+"
    r"[^,;.\n]{2,60}(?:,\s*(?:n[º°.o]*\s*)?\d+(?:\s*[-–/]\s*\w+)?)?"
)
_CEP = re.compile(r"\b\d{5}-\d{3}\b")
_NIRE = re.compile(  # 33.300.294.597; um valor "R$ 12.345.678.901" não
    r"(?<!\$ )(?<![\d.$])\d{2}\.\d{3}\.\d{3}\.\d{3}(?![\d.])"
)
_NIRE_SEM_PONTO = re.compile(r"(?i)(NIRE\s*(?:n[º°.o]*\s*)?)\d{11}")
_PROCESSO = re.compile(r"\b\d{7}-?\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")  # numeração do CNJ
_REGISTRO_CVM = re.compile(
    r"(?i)(c[oó]digo\s+(?:de\s+registro\s+)?(?:na\s+)?cvm\s*(?:n[º°.o]*\s*)?)\d{3,6}"
)

# --- pessoas: nome junto de um cargo (veio de `base/leitor_release.py`, que importa daqui) -------
_PALAVRA_DE_NOME = rf"[{_MAIUSCULA}][{_MINUSCULA}]+"
_NOME = rf"{_PALAVRA_DE_NOME}(?:\s+(?:d[aeo]s?\s+)?{_PALAVRA_DE_NOME})+"
_CARGO = (
    r"(?:Vice-Presidente|Presidente|Diretor(?:a)?(?:-\w+)?|CEO|CFO|COO|CIO|Superintendente|"
    r"Gerente|Head)"
    rf"(?:\s+d[aeo]s?\s+[{_MAIUSCULA}]\w+(?:\s+(?:com|d[aeo]s?)?\s*[{_MAIUSCULA}]?\w+){{0,3}})?"
)
_NOME_DEPOIS_DO_CARGO = re.compile(rf"(?P<cargo>\b{_CARGO})(?P<sep>[\s,:]+){_NOME}")
_NOME_ANTES_DO_CARGO = re.compile(rf"{_NOME}(?=\s*[,(–-]?\s*{_CARGO})")


def mascarar_pessoas(texto: str) -> str:
    """Troca por "[pessoa]" os nomes escritos junto de um cargo ("CFO Maria Souza", "João Silva,
    Diretor-Presidente"). É uma heurística; os guias também mandam não copiar nomes."""
    texto = _NOME_DEPOIS_DO_CARGO.sub(
        lambda m: f"{m['cargo']}{m['sep']}{PESSOA}", texto
    )
    return _NOME_ANTES_DO_CARGO.sub(PESSOA, texto)


def marcadores(texto: str) -> Counter[str]:
    """Quantas vezes cada marcador aparece no documento anonimizado (o passo `vazamento` conta em
    quantos documentos cada um entrou: é o registro, sem API, do que o v3 tirou)."""
    return Counter(_MARCADOR.findall(texto))


def palavras_que_vazam(texto: str, nome: str) -> set[str]:
    """As palavras que distinguem a empresa (as que a auditoria conta como acerto, fora as comuns)
    e que ainda estão no documento: a conferência sem custo antes do teste de identificação."""
    return _distintas(nome) & _palavras(texto)


def palavras_comuns_que_ficam(texto: str, nome: str) -> set[str]:
    """As palavras comuns do nome que ficam no documento de propósito ("pagamento") e que a auditoria
    contaria como acerto se a IA as dissesse: o resto do que a identificação pode pegar."""
    comuns = {
        p for p in _palavras(nome)
        if len(p) >= _MIN_LETRAS_DO_NOME and p not in GENERICAS and p in PALAVRAS_COMUNS
    }  # fmt: skip
    return comuns & _palavras(texto)


def e_fato_relevante(evento: dict) -> bool:
    return evento.get("categoria") == FATO_RELEVANTE


def documento(evento: dict, texto: str) -> str:
    """O que o modelo lê: os dados do IPE e o começo do texto, sem o nome da empresa. Sem o setor
    desde a v2: o guia não usa o setor para a nota, e alguns setores da CVM são quase de uma empresa
    só ("Bolsas de Valores")."""
    nomes = [evento.get("empresa") or ""]
    corpo = anonimizar(texto[: MAX_CARACTERES_DO_TEXTO + 500], nomes)[
        :MAX_CARACTERES_DO_TEXTO
    ]
    return (
        f"Categoria: {evento.get('categoria', '')}\n"
        f"Tipo: {evento.get('tipo', '')}\n"
        f"Espécie: {evento.get('especie', '')}\n"
        f"Assunto: {anonimizar(evento.get('assunto') or '', nomes)}\n"
        f"Data de entrega: {evento.get('entrega', '')}\n\n"  # v2: sem o setor
        f"Texto do documento (começo):\n{corpo.strip() or SEM_TEXTO}"
    )


def esquema(fato_relevante: bool) -> dict:
    propriedades: dict = {
        "nota": {"type": "integer", "enum": list(NOTAS)},
        "tema": {"type": "string", "enum": list(TEMAS)},
        "trecho": {"type": "string"},
        "confianca": {"type": "string", "enum": list(CONFIANCAS)},
    }
    if fato_relevante:
        propriedades["assunto"] = {"type": "string", "enum": list(topicos.TOPICOS)}
    return {
        "type": "object",
        "properties": propriedades,
        "required": list(propriedades),
        "additionalProperties": False,
    }


def pedido(evento: dict, texto: str, modelo: str = MODELO) -> dict:
    """Os parâmetros de `messages.create` para um evento (os mesmos servem para o lote). Só o modelo
    muda entre o rotulador e o conferente: guia, prompt e texto anonimizado são os mesmos."""
    modelo_conhecido(modelo)
    pede_assunto = e_fato_relevante(evento)
    instrucao = "Rotule este documento (nota, tema" + (
        ", assunto" if pede_assunto else ""
    )
    return {
        "model": modelo,
        "max_tokens": MAX_TOKENS_DA_RESPOSTA,
        "system": [
            {"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": esquema(pede_assunto)},
        },
        "messages": [
            {
                "role": "user",
                "content": f"{instrucao}, trecho e confiança).\n\n{documento(evento, texto)}",
            }
        ],
    }


def hash_da_entrada(parametros: dict) -> str:
    """SHA-256 do pedido inteiro: prova de que o rótulo saiu daquela entrada (ADR 0055, exigência 13)."""
    return hashlib.sha256(
        json.dumps(parametros, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RotuloDaIA:
    evento_id: str
    nota: int
    tema: str
    assunto: str | None
    trecho: str
    confianca: str

    def para_guardar(self, modelo: str = MODELO) -> dict:
        return {
            **asdict(self),
            "por": "ia",
            "modelo": modelo,
            "versao_do_prompt": VERSAO_DO_PROMPT,
            "guia": GUIA,
        }


@dataclass(frozen=True)
class ErroDeRotulo:
    evento_id: str
    motivo: str


def _junto(texto: str) -> str:
    return " ".join(texto.split())


def interpretar(
    resposta: str, evento: dict, texto: str, conferir_trecho: bool = True
) -> RotuloDaIA | ErroDeRotulo:
    """A resposta do modelo vira rótulo só se respeitar a lista fechada e o trecho literal.
    `conferir_trecho=False` só serve ao desvio registrado da comparação (Emenda 1 da ADR 0072):
    a lista fechada continua valendo."""
    evento_id = str(evento.get("id", ""))

    def erro(motivo: str) -> ErroDeRotulo:
        return ErroDeRotulo(evento_id, motivo)

    try:
        dados = json.loads(resposta)
    except json.JSONDecodeError:
        return erro("resposta não é JSON")
    if not isinstance(dados, dict):
        return erro("resposta não é um objeto")
    nota, tema, confianca = dados.get("nota"), dados.get("tema"), dados.get("confianca")
    if not isinstance(nota, int) or isinstance(nota, bool) or nota not in NOTAS:
        return erro(f"nota fora da escala: {nota!r}")
    if tema not in TEMAS:
        return erro(f"tema fora da lista: {tema!r}")
    if confianca not in CONFIANCAS:
        return erro(f"confiança fora da lista: {confianca!r}")
    assunto = None
    if e_fato_relevante(evento):
        assunto = dados.get("assunto")
        if assunto not in topicos.TOPICOS:
            return erro(f"assunto fora da lista: {assunto!r}")
    trecho = _junto(str(dados.get("trecho") or ""))
    if conferir_trecho and (
        not trecho or trecho not in _junto(documento(evento, texto))
    ):
        return erro("trecho não está no documento")
    return RotuloDaIA(evento_id, nota, tema, assunto, trecho, confianca)


def de_mensagem(
    stop_reason: str | None, texto: str, evento: dict, texto_do_documento: str
) -> RotuloDaIA | ErroDeRotulo:
    """O rótulo de uma resposta da API: recusa ou resposta cortada vira erro."""
    if stop_reason != "end_turn":
        return ErroDeRotulo(str(evento.get("id", "")), f"parada: {stop_reason}")
    return interpretar(texto, evento, texto_do_documento)


def custo_em_dolares(
    tokens_entrada: int, tokens_saida: int, lote: bool = True, modelo: str = MODELO
) -> float:
    """O custo pelos preços do modelo; pela Batch API, a metade."""
    preco = modelo_conhecido(modelo)
    custo = (tokens_entrada * preco.entrada + tokens_saida * preco.saida) / 1_000_000
    return custo * (DESCONTO_DO_LOTE if lote else 1.0)


# --- teste de identificação (auditoria, ADR 0072): a IA reconhece a empresa pelo texto? ----------

SISTEMA_DA_IDENTIFICACAO = f"""O documento abaixo é de uma companhia aberta brasileira e foi \
anonimizado: {EMPRESA}, {CODIGO} e {CNPJ} são a empresa; {OUTRA_EMPRESA}, {LOCAL}, {PESSOA}, \
{ENDERECO} e {NUMERO} são outras empresas, lugares, pessoas, endereços eletrônicos e números de \
registro. Diga qual companhia você acha que é, pelo nome. Se não tiver um bom palpite, responda \
NAO_SEI. Responda só o nome."""
NAO_SEI = "NAO_SEI"


def pedido_de_identificacao(evento: dict, texto: str) -> dict:
    """O mesmo documento que o rotulador lê, perguntando qual é a empresa."""
    return {
        "model": MODELO,
        "max_tokens": 1_000,
        "system": [
            {
                "type": "text",
                "text": SISTEMA_DA_IDENTIFICACAO,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "output_config": {
            "effort": "low",
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"empresa": {"type": "string"}},
                    "required": ["empresa"],
                    "additionalProperties": False,
                },
            },
        },
        "messages": [{"role": "user", "content": documento(evento, texto)}],
    }


def palpite_da_identificacao(stop_reason: str | None, resposta: str) -> str:
    """O nome que a IA chutou (NAO_SEI se recusou, cortou ou respondeu fora do formato)."""
    if stop_reason != "end_turn":
        return NAO_SEI
    try:
        dados = json.loads(resposta)
    except json.JSONDecodeError:
        return NAO_SEI
    palpite = str(dados.get("empresa") or "").strip() if isinstance(dados, dict) else ""
    return palpite or NAO_SEI


def cliente() -> anthropic.Anthropic:
    """O cliente da API (a chave vem de ANTHROPIC_API_KEY), com o cabeçalho do workspace quando a
    chave não é de um workspace (ANTHROPIC_WORKSPACE_ID no `.env`)."""
    workspace = os.environ.get(VARIAVEL_DO_WORKSPACE, "").strip()
    if workspace:
        return anthropic.Anthropic(
            default_headers={"anthropic-workspace-id": workspace}
        )
    return anthropic.Anthropic()
