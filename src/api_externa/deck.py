"""O deck (`.pptx`) da API externa (linha 782): o setor e o perfil da empresa como arquivo de slides.

O deck não lê nada sozinho: recebe o corpo que a rota JSON já serviu (`conjuntos/setores.py` e
`conjuntos/ficha.py`, depois do portão do contrato e da redistribuição) e só o escreve em slides, com o
mesmo desenho do deck do app (`src/apresentacao_pptx.py`). Assim o arquivo nunca tem um campo que o JSON
da mesma chave não teria. Cada tabela leva embaixo a fonte e o dia em que o dado ficou público; o fim do
deck tem as fontes (licença e atribuição) e os limites.

Cuidados do arquivo: o texto vem de dado público (nome de companhia, avisos da ficha da noite) e passa
por `_limpo` (caractere de controle quebraria o XML do `.pptx`) e por `tirar_cpf`; cada tabela mostra no
máximo `LINHAS_POR_TABELA` linhas e o deck no máximo `SLIDES_NO_MAXIMO` slides (o resto sai no JSON).
"""

import re
from collections.abc import Callable, Iterable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from base import cnpj as cnpj_da_base
from base import receita_codigos
from base.pessoas.sem_cpf import tirar_cpf
from src import dossie
from src.api_externa.conjuntos import ficha
from src.apresentacao import (
    AVISO_DO_DECK,
    CAPA,
    FONTES,
    LIMITES,
    TABELA,
    TEXTO,
    TITULO_DAS_FONTES,
    TITULO_DOS_LIMITES,
    Apresentacao,
    Linha,
    Slide,
)
from src.apresentacao_pptx import apresentacao_em_pptx

FUSO = ZoneInfo("America/Sao_Paulo")  # o "Gerado em" do deck é a hora de Brasília
TIPO_DO_ARQUIVO = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
LINHAS_POR_SLIDE = (
    8  # o mesmo das tabelas do deck do app (`apresentacao._slides_de_tabela`)
)
LINHAS_POR_TABELA = 40  # cinco slides por tabela; a tabela inteira sai no JSON
SLIDES_NO_MAXIMO = (
    60  # o arquivo fica pequeno (bem abaixo de 1 MB) mesmo com o plano maior
)
SEM_VALOR = "—"
AVISO_DO_CORTE = "O plano da chave limita as linhas por resposta: este deck tem só as primeiras, como o JSON."
LIMITES_DO_SETOR = (
    "Os números são os da ficha da noite do dia na capa: nada publicado depois dela entra.",
    (
        "A concentração (CR4 e HHI) e a parte de cada companhia são contas do TickerLab sobre a série "
        "pública da agência; não são opinião sobre as empresas."
    ),
    "Só companhias (CNPJ de 14 dígitos) aparecem; pessoa natural não é servida.",
)
# colunas da concentração que cabem num slide (as outras saem no JSON)
COLUNAS_DA_CONCENTRACAO_NO_DECK = (
    "ano",
    "participantes",
    "total",
    "cr4",
    "hhi",
    "faixa",
)
SITUACOES_DA_ENTREGA = {
    ficha.NO_PRAZO: "No prazo",
    ficha.ATRASOU: "Atrasou",
    ficha.ZONA_CINZENTA: "Zona cinzenta",
    ficha.ATRASO_GRAVE: "Atraso grave",
    ficha.NAO_ENTREGUE: "Não entregue",
}
# caractere de controle, os dois que não são caractere e as metades soltas: nada disso cabe no XML
_FORA_DO_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f￾￿\ud800-\udfff]")

Escritor = Callable[[object], str]
Coluna = tuple[str, str, Escritor]


# --- texto e valores -----------------------------------------------------------------------------


def _limpo(texto: str) -> str:
    """O texto sem o que quebraria o arquivo e sem número que pareça CPF."""
    return tirar_cpf(_FORA_DO_XML.sub("", texto))


def _dia(valor: object) -> str:
    """`2026-10-17` → `17/10/2026`; `2026-10` → `10/2026`."""
    texto = str(valor)
    if len(texto) >= len("2026-10-17"):
        return date.fromisoformat(texto[:10]).strftime("%d/%m/%Y")
    ano, _, mes = texto.partition("-")
    return f"{mes}/{ano}" if mes else texto


def _sim_ou_nao(valor: object) -> str:
    return "Sim" if valor else "Não"


def _texto(valor: object) -> str:
    return str(valor)


def _situacao_cadastral(valor: object) -> str:
    nome = receita_codigos.situacao_cadastral(str(valor))
    return f"{valor} ({nome})" if nome else str(valor)


def _situacao_da_entrega(valor: object) -> str:
    return SITUACOES_DA_ENTREGA.get(str(valor), str(valor))


def _inteiro(valor: object) -> str:
    return dossie.inteiro(valor)


def _celula(envelope: object, escrever: Escritor) -> str:
    """O valor de um campo servido (`{"valor", "fonte", "publico_em", "visto_em"}`) escrito em texto."""
    valor = envelope.get("valor") if isinstance(envelope, dict) else None
    if valor is None:
        return SEM_VALOR
    return escrever(valor)


def _notas_das_fontes(linhas: Iterable[dict]) -> tuple[str, ...]:
    """Uma nota por fonte, com o dia (ou o intervalo de dias) em que os campos ficaram públicos."""
    dias: dict[str, set[str]] = {}
    for linha in linhas:
        for envelope in linha.values():
            if isinstance(envelope, dict) and envelope.get("fonte"):
                dias.setdefault(str(envelope["fonte"]), set()).add(
                    str(envelope.get("publico_em") or "")
                )
    notas = []
    for fonte, publicos in sorted(dias.items()):
        datas = sorted(d for d in publicos if d)
        quando = _dia(datas[0]) if datas else SEM_VALOR
        if len(datas) > 1:
            quando = f"{_dia(datas[0])} a {_dia(datas[-1])}"
        notas.append(f"Fonte: {fonte} · público em {quando}")
    return tuple(notas)


# --- slides --------------------------------------------------------------------------------------


def _titulo_da_parte(titulo: str, indice: int, total: int) -> str:
    return titulo if total == 1 else f"{titulo} ({indice + 1}/{total})"


def _slides_da_tabela(
    titulo: str, linhas: list[dict], colunas: list[Coluna], onde: str
) -> list[Slide]:
    """A tabela em slides de `LINHAS_POR_SLIDE` linhas, só com as colunas que o portão deixou sair; as
    linhas além de `LINHAS_POR_TABELA` ficam no JSON (a nota diz onde)."""
    presentes = [c for c in colunas if any(c[0] in linha for linha in linhas)]
    if not linhas or not presentes:
        return []
    mostradas = linhas[:LINHAS_POR_TABELA]
    cabecalho: Linha = tuple(rotulo for _, rotulo, _ in presentes)
    corte: tuple[str, ...] = ()
    if len(linhas) > LINHAS_POR_TABELA:
        corte = (
            (
                f"Mostradas {LINHAS_POR_TABELA} de {len(linhas)} linhas; a tabela inteira sai em "
                f"JSON em {onde}."
            ),
        )
    blocos = [
        mostradas[i : i + LINHAS_POR_SLIDE]
        for i in range(0, len(mostradas), LINHAS_POR_SLIDE)
    ]
    return [
        Slide(
            TABELA,
            _titulo_da_parte(titulo, i, len(blocos)),
            cabecalho=cabecalho,
            linhas=tuple(
                tuple(
                    _celula(linha.get(nome), escrever)
                    for nome, _, escrever in presentes
                )
                for linha in bloco
            ),
            # a fonte e o dia das células deste slide (só das colunas mostradas)
            notas=_notas_das_fontes(
                {nome: linha.get(nome) for nome, _, _ in presentes} for linha in bloco
            )
            + corte,
        )
        for i, bloco in enumerate(blocos)
    ]


def _slide_de_texto(titulo: str, topicos: Iterable[str], tipo: str = TEXTO) -> Slide:
    return Slide(tipo, titulo, topicos=tuple(topicos))


def _fechamento(fontes: list[dict], limites: Iterable[str], onde: str) -> list[Slide]:
    """As fontes (atribuição e licença de cada uma, como no JSON) e os limites, com o aviso do deck."""
    linhas = [
        f"{f['atribuicao']} ({f['fonte']}; licença: {f['licenca']})" for f in fontes
    ]
    return [
        Slide(
            FONTES,
            TITULO_DAS_FONTES,
            topicos=tuple(linhas) or ("Nenhuma fonte serviu dado nesta resposta.",),
            notas=(f"Os mesmos dados, campo a campo, saem em JSON em {onde}.",),
        ),
        _slide_de_texto(TITULO_DOS_LIMITES, [*limites, AVISO_DO_DECK], LIMITES),
    ]


def _no_maximo(slides: list[Slide], fechamento: list[Slide], onde: str) -> list[Slide]:
    """O deck com no máximo `SLIDES_NO_MAXIMO` slides: o fechamento fica sempre; o meio para antes."""
    cabem = SLIDES_NO_MAXIMO - len(fechamento)
    if len(slides) > cabem:
        aviso = _slide_de_texto(
            "O deck parou aqui",
            [f"O resto desta resposta sai em JSON em {onde}."],
        )
        slides = [*slides[: cabem - 1], aviso]
    return [*slides, *fechamento]


def _capa(titulo: str, subtitulo: str, como_era_em: str, gerado_em: datetime) -> Slide:
    return Slide(
        CAPA,
        titulo,
        subtitulo=subtitulo,
        notas=(
            f"Como era em {_dia(como_era_em)}",
            f"Gerado em {gerado_em:%d/%m/%Y às %H:%M}",
        ),
    )


# --- o setor -------------------------------------------------------------------------------------


def _colunas_da_concentracao(serie: str) -> list[Coluna]:
    todas = dossie.colunas_da_tabela(f"{dossie.PREFIXO_DA_CONCENTRACAO}{serie}") or []
    return [c for c in todas if c[0] in COLUNAS_DA_CONCENTRACAO_NO_DECK]


def _slides_da_serie(entrada: dict, onde: str) -> list[Slide]:
    serie = str(entrada.get("serie"))
    if serie not in dossie.SERIES_DO_SETOR:
        return []
    medida = dossie.SERIES_DO_SETOR[serie].medida
    concentracao = dossie.titulo_da_tabela(f"{dossie.PREFIXO_DA_CONCENTRACAO}{serie}")
    participacao = f"{dossie.titulo_da_tabela('participacao_dos_membros')}: {medida}"
    return [
        *_slides_da_tabela(
            concentracao,
            entrada.get("concentracao", []),
            _colunas_da_concentracao(serie),
            onde,
        ),
        *_slides_da_tabela(
            participacao,
            entrada.get("participacao_dos_membros", []),
            dossie.colunas_da_participacao(serie),
            onde,
        ),
    ]


def do_setor(corpo: dict, fontes: list[dict], gerado_em: datetime) -> Apresentacao:
    """O deck do setor a partir do corpo de `/data/v1/sectors/{key}` (chaves em português)."""
    onde = f"/data/v1/sectors/{corpo['setor']}"
    slides = [
        _capa(corpo["nome"], "Relatório do setor", corpo["como_era_em"], gerado_em)
    ]
    avisos = list(corpo.get("avisos", []))
    if corpo.get("cortada"):
        avisos.insert(0, AVISO_DO_CORTE)
    if avisos:
        slides.append(_slide_de_texto("Antes de ler", avisos))
    for entrada in corpo.get("por_serie", []):
        slides += _slides_da_serie(entrada, onde)
    slides += _slides_da_tabela(
        dossie.titulo_da_tabela("membros"),
        corpo.get("membros", []),
        dossie.COLUNAS["membros"],
        onde,
    )
    limites = [*LIMITES_DO_SETOR, *([AVISO_DO_CORTE] if corpo.get("cortada") else [])]
    fechamento = _fechamento(fontes, limites, onde)
    return Apresentacao(
        f"Relatório do setor: {corpo['nome']}",
        corpo["nome"],
        AVISO_DO_DECK,
        tuple(_no_maximo(slides, fechamento, onde)),
    )


# --- a empresa -----------------------------------------------------------------------------------

CAMPOS_DO_CADASTRO: list[Coluna] = [
    ("razao_social", "Razão social", _texto),
    ("situacao_cadastral", "Situação cadastral", _situacao_cadastral),
    ("data_situacao_cadastral", "Desde", _dia),
    ("motivo_situacao", "Motivo da situação (código da Receita)", _texto),
    ("natureza_juridica", "Natureza jurídica (código da Receita)", _texto),
    ("matriz", "Matriz", _sim_ou_nao),
    ("optante_simples", "Optante do Simples", _sim_ou_nao),
    ("data_opcao_simples", "Entrou no Simples em", _dia),
    ("data_exclusao_simples", "Saiu do Simples em", _dia),
    ("mes_do_retrato", "Arquivo da Receita do mês", _dia),
]
COLUNAS_DAS_ENTREGAS: list[Coluna] = [
    ("documento", "Documento", _texto),
    ("referencia", "Referência", _dia),
    ("prazo", "Prazo", _dia),
    ("primeira_entrega", "Entregue em", _dia),
    ("dias_uteis_de_atraso", "Dias úteis de atraso", _inteiro),
    ("situacao_da_entrega", "Situação", _situacao_da_entrega),
]


def _slides_do_cadastro(cadastro: dict) -> list[Slide]:
    """O cadastro (um campo por chave) como tabela de duas colunas: o campo e o valor."""
    presentes = [c for c in CAMPOS_DO_CADASTRO if isinstance(cadastro.get(c[0]), dict)]
    corpo = [
        (rotulo, _celula(cadastro[nome], escrever))
        for nome, rotulo, escrever in presentes
    ]
    blocos = [
        corpo[i : i + LINHAS_POR_SLIDE] for i in range(0, len(corpo), LINHAS_POR_SLIDE)
    ]
    notas = _notas_das_fontes([{nome: cadastro[nome] for nome, _, _ in presentes}])
    return [
        Slide(
            TABELA,
            _titulo_da_parte("Cadastro na Receita", i, len(blocos)),
            cabecalho=("Campo", "Valor"),
            linhas=tuple(bloco),
            notas=notas,
        )
        for i, bloco in enumerate(blocos)
    ]


def da_empresa(corpo: dict, fontes: list[dict], gerado_em: datetime) -> Apresentacao:
    """O deck do perfil a partir do corpo de `/data/v1/companies/{cnpj}/profile` (chaves em português)."""
    onde = f"/data/v1/companies/{corpo['cnpj']}/profile"
    cnpj = cnpj_da_base.formatar(corpo["cnpj"])
    cadastro = corpo.get("cadastro_na_receita", {})
    razao = cadastro.get("razao_social", {}).get("valor") if cadastro else None
    titulo = str(razao) if razao else f"CNPJ {cnpj}"
    subtitulo = f"CNPJ {cnpj}" if razao else "Perfil da empresa"
    slides = [_capa(titulo, subtitulo, corpo["como_era_em"], gerado_em)]
    slides += _slides_do_cadastro(cadastro)
    slides += _slides_da_tabela(
        "Entregas à CVM (DFP e ITR)",
        corpo.get("entregas", []),
        COLUNAS_DAS_ENTREGAS,
        onde,
    )
    fechamento = _fechamento(fontes, corpo.get("limites", []), onde)
    return Apresentacao(
        f"Perfil da empresa: {titulo}",
        f"CNPJ {cnpj}",
        AVISO_DO_DECK,
        tuple(_no_maximo(slides, fechamento, onde)),
    )


# --- o arquivo -----------------------------------------------------------------------------------


def _slide_limpo(slide: Slide) -> Slide:
    def limpar(textos: Linha) -> Linha:
        return tuple(_limpo(t) for t in textos)

    return Slide(
        slide.tipo,
        _limpo(slide.titulo),
        _limpo(slide.subtitulo),
        limpar(slide.cabecalho),
        tuple(limpar(linha) for linha in slide.linhas),
        limpar(slide.topicos),
        limpar(slide.notas),
    )


def em_arquivo(deck: Apresentacao, gerado_em: datetime) -> bytes:
    """Os bytes do `.pptx`, com todo texto limpo antes de entrar no XML."""
    limpo = Apresentacao(
        _limpo(deck.titulo),
        _limpo(deck.subtitulo),
        _limpo(deck.aviso),
        tuple(_slide_limpo(s) for s in deck.slides),
    )
    return apresentacao_em_pptx(limpo, gerado_em)
