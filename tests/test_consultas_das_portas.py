"""A lista única das portas (frente 2 do foco de 24/11/2026): o conector, a CLI e a API saem do mesmo registro.

`conector_remoto/consultas_das_portas.py` é o lugar de cada consulta. Ferramenta nova no conector, comando novo na CLI ou rota
nova na `/data/v1` fora do registro faz este arquivo falhar; porta que não oferece uma consulta tem o motivo escrito.

A foto (`tests/arquivos/portas_foto.json`) guarda o que a IA do analista lê de cada ferramenta (título, descrição,
parâmetros) e as instruções do servidor. Mudar esse texto é decisão, não efeito colateral: quando a mudança é de
propósito, regrave a foto com `TICKERLAB_GRAVAR_FOTO=1` e diga no PR o que a IA passa a ler de diferente.
"""

import asyncio
import hashlib
import html
import json
import os
import re
from pathlib import Path

import click
import pytest
import tomllib
from mcp.server.mcpserver import MCPServer
from tickerlab import comandos, consultas
from tickerlab.comandos import principal

from conector_remoto import consultas_das_portas as registro
from conector_remoto import ferramentas as do_conector
from conector_remoto import socios_e_donos
from conector_remoto.cliente_api import ClienteDaApi
from conector_remoto.ferramentas import registrar_ferramentas
from conector_remoto.servidor import INSTRUCOES
from scripts.exportar_conteudo import DOCUMENTOS_DAS_PORTAS
from scripts.mudou_so_texto import e_so_texto
from src.api_externa.rotas import router
from src.chat import ferramentas as do_chat

FOTO = Path(__file__).parent / "arquivos" / "portas_foto.json"
RAIZ = Path(__file__).parent.parent
JSON_DA_CLI = RAIZ / "cli" / "tickerlab" / "consultas.json"
GRAVAR_FOTO = "TICKERLAB_GRAVAR_FOTO"
# divergências entre as portas que já se sabem, com o PR que as resolve (plano da frente 2, PR 5)
DIVERGENCIAS_DA_CLI = {
    (
        "buscar_empresas",
        "porte",
    ): "o conector aceita também os nomes da API (small, other, not_informed), que ele recebia antes do PR 5c; a CLI, só os em português",
}


def _ferramentas_do_conector() -> dict[str, dict]:
    servidor = MCPServer("teste")
    registrar_ferramentas(
        servidor, ClienteDaApi("http://api.exemplo.test", tempo_limite_s=1), True
    )
    lista = asyncio.run(servidor.list_tools())
    return {f.name: f.model_dump(mode="json", exclude_none=True) for f in lista}


def _sem_recuo(texto: str) -> str:
    # o docstring de antes levava o recuo do código; o que a IA lê são as palavras
    return " ".join(texto.split())


def _foto_de_agora() -> dict:
    ferramentas = _ferramentas_do_conector()
    for f in ferramentas.values():
        f["description"] = _sem_recuo(f["description"])
    return {"instrucoes": INSTRUCOES, "ferramentas": ferramentas}


def _faixa(esquema: dict) -> tuple[float | None, float | None, bool, tuple[str, ...]]:
    minimo = maximo = None
    aberto = False
    valores: tuple[str, ...] = ()
    for parte in [esquema, *esquema.get("anyOf", [])]:
        if "minimum" in parte:
            minimo = parte["minimum"]
        if "exclusiveMinimum" in parte:
            minimo, aberto = parte["exclusiveMinimum"], True
        maximo = parte.get("maximum", maximo)
        valores = tuple(parte.get("enum", parte.get("items", {}).get("enum", valores)))
    return minimo, maximo, aberto, valores


def _consulta_da_ferramenta(nome: str) -> registro.Consulta:
    return next(
        c for c in registro.CONSULTAS if any(f.nome == nome for f in c.ferramentas)
    )


def test_o_que_a_ia_le_de_cada_ferramenta_e_igual_a_foto():
    agora = _foto_de_agora()
    if os.environ.get(GRAVAR_FOTO):
        FOTO.write_text(
            json.dumps(agora, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    foto = json.loads(FOTO.read_text(encoding="utf-8"))
    assert agora["instrucoes"] == foto["instrucoes"]
    assert sorted(agora["ferramentas"]) == sorted(foto["ferramentas"])
    for nome, ferramenta in foto["ferramentas"].items():
        assert agora["ferramentas"][nome] == ferramenta, (
            f"{nome}: o que a IA lê mudou. Se foi de propósito, regrave a foto ({GRAVAR_FOTO}=1)."
        )


def test_toda_ferramenta_do_conector_esta_no_registro_e_vice_versa():
    do_conector = set(_ferramentas_do_conector())
    do_registro = {f.nome for f in registro.FERRAMENTAS}
    assert do_conector - do_registro == set(), (
        "ferramenta nova no conector: ponha-a em conector_remoto/consultas_das_portas.py"
    )
    assert do_registro - do_conector == set()
    assert len(do_registro) == len(registro.FERRAMENTAS)  # nome repetido


def test_titulo_descricao_e_parametros_saem_do_registro():
    do_conector = _ferramentas_do_conector()
    for f in registro.FERRAMENTAS:
        anunciada = do_conector[f.nome]
        assert anunciada["title"] == f.titulo
        assert anunciada["description"] == f.descricao
        propriedades = anunciada["input_schema"].get("properties", {})
        assert list(propriedades) == [p.nome for p in f.parametros], f.nome
        for p in f.parametros:
            assert _faixa(propriedades[p.nome]) == (
                p.minimo,
                p.maximo,
                p.minimo_aberto,
                p.valores,
            ), f"{f.nome}.{p.nome}"


def test_toda_ferramenta_esta_numa_consulta_so():
    usadas = [f.nome for c in registro.CONSULTAS for f in c.ferramentas]
    assert sorted(usadas) == sorted(f.nome for f in registro.FERRAMENTAS)


def test_todo_comando_da_cli_esta_no_registro_e_vice_versa():
    do_registro = [c for consulta in registro.CONSULTAS for c in consulta.comandos]
    assert len(do_registro) == len(set(do_registro))
    assert set(principal.commands) - set(do_registro) == set(), (
        "comando novo na CLI: ponha-o em conector_remoto/consultas_das_portas.py"
    )
    assert set(do_registro) - set(principal.commands) == set()


def _parametro_da_cli(comando: click.Command, grafia: str) -> click.Parameter | None:
    for p in comando.params:
        if grafia in getattr(p, "opts", []) or (
            isinstance(p, click.Argument) and p.name == grafia.lower()
        ):
            return p
    return None


def test_a_opcao_da_cli_de_cada_parametro_existe_e_tem_a_mesma_faixa():
    for f in registro.FERRAMENTAS:
        comandos = _consulta_da_ferramenta(f.nome).comandos
        for p in f.parametros:
            if p.cli is None:
                continue
            achados = [
                _parametro_da_cli(principal.commands[c], p.cli) for c in comandos
            ]
            achados = [a for a in achados if a is not None]
            assert achados, f"{f.nome}.{p.nome}: a CLI não tem {p.cli}"
            if (f.nome, p.nome) in DIVERGENCIAS_DA_CLI:
                continue
            for achado in achados:
                tipo = achado.type
                if isinstance(tipo, click.IntRange | click.FloatRange):
                    assert (tipo.min, tipo.max) == (p.minimo, p.maximo), (
                        f"{f.nome}.{p.nome}"
                    )
                if isinstance(tipo, click.Choice) and p.valores:
                    assert sorted(tipo.choices) == sorted(p.valores), (
                        f"{f.nome}.{p.nome}"
                    )


def test_as_divergencias_conhecidas_ainda_existem():
    """Resolvida a divergência, tire-a da lista (para a lista não esconder uma nova)."""
    for nome, parametro in DIVERGENCIAS_DA_CLI:
        p = next(x for x in registro.ferramenta(nome).parametros if x.nome == parametro)
        comando = principal.commands[_consulta_da_ferramenta(nome).comandos[0]]
        achado = _parametro_da_cli(comando, p.cli or "")
        assert achado is not None
        tipo = achado.type
        if isinstance(tipo, click.Choice):
            assert sorted(tipo.choices) != sorted(p.valores)
        else:
            assert not isinstance(tipo, click.IntRange | click.FloatRange)


def _rotas_do_roteador() -> set[str]:
    rotas = set()
    for rota in router.routes:
        caminho = rota.path.removeprefix(router.prefix)  # type: ignore[attr-defined]
        for metodo in rota.methods:  # type: ignore[attr-defined]
            rotas.add(f"{metodo} {caminho}")
    return rotas


def test_toda_rota_da_api_esta_no_registro_e_vice_versa():
    do_registro = [r for c in registro.CONSULTAS for r in c.rotas]
    assert len(do_registro) == len(set(do_registro))
    assert _rotas_do_roteador() - set(do_registro) == set(), (
        "rota nova na /data/v1: ponha-a no registro"
    )
    assert set(do_registro) - _rotas_do_roteador() == set()


@pytest.mark.parametrize("consulta", registro.CONSULTAS, ids=lambda c: c.chave)
def test_cada_porta_oferece_a_consulta_ou_diz_por_que_nao(consulta):
    oferece = {
        "conector": consulta.ferramentas,
        "cli": consulta.comandos,
        "api": consulta.rotas,
    }
    assert set(consulta.fora_de_uma_porta) <= set(registro.PORTAS)
    for porta in registro.PORTAS:
        motivo = consulta.fora_de_uma_porta.get(porta, "").strip()
        assert bool(oferece[porta]) != bool(motivo), (
            f"{consulta.chave}: {porta} oferece ou tem motivo, um dos dois"
        )


def test_chaves_das_consultas_sao_unicas():
    chaves = [c.chave for c in registro.CONSULTAS]
    assert len(chaves) == len(set(chaves))


def test_o_conjunto_das_pessoas_e_o_do_conector():
    assert registro.CONJUNTO_DAS_PESSOAS == socios_e_donos.CONJUNTO
    assert registro.ferramenta("socios_e_donos").conjuntos == frozenset(
        {socios_e_donos.CONJUNTO}
    )


def test_o_chat_do_app_le_a_lista_do_registro():
    assert {
        f.nome for f in registro.FERRAMENTAS if f.no_chat_do_app
    } == do_chat.NOMES_DAS_FERRAMENTAS


def test_ferramenta_fora_do_registro_da_erro_claro():
    with pytest.raises(KeyError):
        registro.ferramenta("nao_existe")


# ---------------------------------------------------------------- a CLI lê a cópia em JSON (PR 2)


def test_o_json_da_cli_esta_em_dia():
    assert JSON_DA_CLI.read_text(encoding="utf-8") == registro.json_da_cli(), (
        "a lista das portas mudou: rode python -m scripts.exportar_conteudo e faça o commit do consultas.json"
    )


def test_o_pacote_da_cli_leva_o_json():
    pacote = tomllib.loads(
        (RAIZ / "cli" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert JSON_DA_CLI.name in pacote["tool"]["setuptools"]["package-data"]["tickerlab"]


@pytest.mark.parametrize("nome", sorted(registro.TRADUCOES))
def test_a_cli_traduz_pelo_mapa_do_registro(nome):
    assert consultas.traducao(nome) == registro.TRADUCOES[nome]
    # a ordem também: a ajuda da CLI mostra as escolhas nela
    assert list(consultas.traducao(nome)) == list(registro.TRADUCOES[nome])


def _parametro(nome_da_ferramenta: str, nome: str) -> registro.Parametro:
    return next(
        p for p in registro.ferramenta(nome_da_ferramenta).parametros if p.nome == nome
    )


def test_conector_e_cli_usam_os_mesmos_mapas():
    for nome in (
        "TIPOS_DE_EVENTO",
        "TIPOS_DA_ANVISA",
        "ORDENS_DA_BUSCA",
        "TIPOS_DE_VINCULO",
    ):
        assert (
            getattr(comandos, nome)
            == getattr(do_conector, nome)
            == getattr(registro, nome)
        ), nome
    assert comandos.PORTES == registro.PORTES
    assert (
        _parametro("buscar_empresas", "situacao_cadastral").valores
        == comandos.SITUACOES
    )


def test_as_escolhas_de_cada_parametro_saem_do_mapa_da_traducao():
    """O parâmetro com escolhas em português aceita exatamente as chaves do mapa que o traduz para a API."""
    assert _parametro("eventos", "tipos").valores == tuple(registro.TIPOS_DE_EVENTO)
    assert _parametro("vinculos", "tipos").valores == tuple(registro.TIPOS_DE_VINCULO)
    assert _parametro("buscar_empresas", "anvisa_tipo").valores == tuple(
        registro.TIPOS_DA_ANVISA
    )


def test_opcao_fora_da_lista_da_erro_claro():
    with pytest.raises(KeyError):
        consultas.faixa_inteira("prospectar", "--nao-existe")


# os documentos com a tabela gerada do registro (PR 3b): entre as marcas, o texto é o de `registro.tabela(...)`
DOCUMENTOS_GERADOS = DOCUMENTOS_DAS_PORTAS
# o que nenhuma tabela pública leva (travas do texto público e de pessoa física)
PALAVRAS_FORA = ("recomend", "oportunidade", "mais dados que", "R$", "garant", "CPF")


@pytest.mark.parametrize("caminho", DOCUMENTOS_GERADOS, ids=lambda c: c.name)
def test_a_tabela_dos_documentos_esta_em_dia(caminho):
    texto = caminho.read_text(encoding="utf-8")
    assert texto.count(registro.MARCA_DO_COMECO) == 1, caminho
    assert texto.count(registro.MARCA_DO_FIM) == 1, caminho
    assert registro.trocar_a_tabela(texto, DOCUMENTOS_GERADOS[caminho]) == texto, (
        "a lista das portas mudou: rode python -m scripts.exportar_conteudo e faça o commit dos documentos"
    )


@pytest.mark.parametrize("consulta", registro.CONSULTAS, ids=lambda c: c.chave)
def test_cada_consulta_tem_nome_e_resumo(consulta):
    assert consulta.nome.strip() and consulta.resumo.strip()
    assert "\n" not in consulta.nome + consulta.resumo
    assert "|" not in consulta.nome + consulta.resumo  # quebraria a tabela


@pytest.mark.parametrize("qual", ["guia", "portas"])
def test_a_tabela_publica_nao_leva_pessoa_nem_frase_travada(qual):
    tabela = registro.tabela(qual)
    privadas = [c for c in registro.CONSULTAS if not c.publica]
    assert [c.chave for c in privadas] == ["socios_e_donos"]
    for consulta in privadas:
        assert consulta.nome not in tabela
        for item in consulta.ferramentas:
            assert item.nome not in tabela
        for rota in consulta.rotas:
            assert rota.split(" ", 1)[1] not in tabela
    minusculas = tabela.lower()
    for palavra in PALAVRAS_FORA:
        assert palavra.lower() not in minusculas, (qual, palavra)


def test_a_tabela_das_portas_traz_cada_porta_ou_o_motivo():
    linhas = registro.tabela("portas").splitlines()
    assert linhas[0] == "| Consulta | Conector | CLI | API (`/data/v1`) |"
    publicas = [c for c in registro.CONSULTAS if c.publica]
    assert len(linhas) == 2 + len(publicas)
    for consulta, linha in zip(publicas, linhas[2:], strict=True):
        colunas = linha.strip("|").split(" | ")
        assert colunas[0].strip() == f"**{consulta.nome}**: {consulta.resumo}"
        for porta, celula in zip(registro.PORTAS, colunas[1:], strict=True):
            if porta in consulta.fora_de_uma_porta:
                assert celula.strip().startswith("não tem"), (consulta.chave, porta)
        for item in consulta.ferramentas:
            assert f"`{item.nome}`" in colunas[1]
        for comando in consulta.comandos:
            assert f"`tickerlab {comando}`" in colunas[2]
        for rota in consulta.rotas:
            assert f"`{rota}`" in colunas[3]


def test_o_guia_traz_cada_consulta_do_conector():
    """O guia do analista lista toda ferramenta pública (antes faltavam a análise, os ativos, os compradores e as
    novidades)."""
    tabela = registro.tabela("guia")
    com_ferramenta = [c for c in registro.CONSULTAS if c.publica and c.ferramentas]
    assert len(tabela.splitlines()) == 2 + len(com_ferramenta)
    for consulta in com_ferramenta:
        assert f"| {consulta.nome} | {consulta.resumo} |" in tabela
    for nome in ("Análise completa", "Ativos físicos", "Quem já se mexeu no setor"):
        assert nome in tabela


def test_os_documentos_gerados_rodam_a_suite_inteira():
    """Mudança só nesses documentos não pode pular este arquivo no CI (`scripts/mudou_so_texto.py`)."""
    for caminho in DOCUMENTOS_DAS_PORTAS:
        assert not e_so_texto(caminho.relative_to(RAIZ).as_posix()), caminho


def test_trocar_a_tabela_pede_as_marcas():
    with pytest.raises(ValueError):
        registro.trocar_a_tabela("sem marca", "guia")


# ---------------------------------------------------------------- a página inicial do site (PR 4 da frente 2)
# o texto aprovado pelo Tiago em 24/11/2026 ("Aprovo o texto"): só as consultas que leem a base, nesta ordem;
# a de pessoa física, a chave e as instruções do agente ficam fora
CONSULTAS_DA_PAGINA = (
    "busca", "ficha", "analise", "comparaveis", "demonstracoes", "eventos", "vinculos", "ativos", "compradores",
    "fundo", "setores", "novidades", "catalogo", "de_onde_vem", "credito", "o_que_mudou", "comparar", "acompanhar", "dossie",
    "deck", "lotes",
)  # fmt: skip
# nomes de concorrente que o texto público não cita
CONCORRENTES = (
    "brapi",
    "economatica",
    "bloomberg",
    "capital iq",
    "refinitiv",
    "pitchbook",
    "speedio",
    "econodata",
)
# o motivo interno das tabelas do repositório cita fila e decisões; a página leva só a frase curta
INTERNO = ("linha ", "diretoria", "fila", "#", "pr ", "adr")
INDEX = RAIZ / "site" / "index.html"


def test_a_pagina_leva_so_as_consultas_que_leem_a_base():
    assert [c["chave"] for c in registro.para_o_site()] == list(CONSULTAS_DA_PAGINA)


def test_a_lista_da_pagina_e_a_do_conteudo_do_site():
    gravada = json.loads(
        (RAIZ / "web" / "conteudo" / "consultas.json").read_text(encoding="utf-8")
    )
    assert gravada == registro.para_o_site(), (
        "rode python -m scripts.exportar_conteudo e os geradores do site"
    )


@pytest.mark.parametrize(
    "consulta",
    [c for c in registro.CONSULTAS if c.chave in CONSULTAS_DA_PAGINA],
    ids=lambda c: c.chave,
)
def test_a_porta_sem_a_consulta_tem_a_frase_curta_da_pagina(consulta):
    assert set(consulta.na_pagina) == set(consulta.fora_de_uma_porta)
    for frase in consulta.na_pagina.values():
        assert 0 < len(frase) <= 40, frase
        assert not any(palavra in frase.lower() for palavra in INTERNO), frase


def test_a_lista_da_pagina_nao_leva_pessoa_nem_frase_travada():
    texto = json.dumps(registro.para_o_site(), ensure_ascii=False).lower()
    assert (
        "socios_e_donos" not in texto
        and "sócios e donos" not in texto
        and "/people" not in texto
    )
    for palavra in PALAVRAS_FORA + CONCORRENTES:
        assert palavra.lower() not in texto, palavra


def _secao_das_portas() -> str:
    """O texto da seção "Três portas, uma base" do site gerado, sem as marcas do HTML."""
    pagina = INDEX.read_text(encoding="utf-8")
    comeco = pagina.index('id="portas"')
    secao = pagina[comeco : pagina.index("</section>", comeco)]
    # a marca sai sem espaço: `lote (<code>POST …</code>)` fica como a frase; o teste só procura trechos
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", secao)).split())


def test_a_pagina_inicial_gerada_mostra_a_lista_das_portas():
    secao = _secao_das_portas()
    for consulta in registro.para_o_site():
        assert (
            f"{consulta['nome']}" in secao
            and " ".join(str(consulta["resumo"]).split()) in secao
        ), consulta
        for porta in registro.PORTAS:
            celula = consulta[porta]
            textos = celula.get("nomes") or [str(celula["frase"]).replace("`", "")]
            for texto in textos:
                assert " ".join(texto.split()) in secao, (
                    consulta["chave"],
                    porta,
                    texto,
                )


def test_a_secao_das_portas_nao_leva_pessoa_nem_frase_travada():
    secao = _secao_das_portas().lower()
    assert (
        "socios_e_donos" not in secao
        and "sócios e donos" not in secao
        and "/people" not in secao
    )
    for palavra in PALAVRAS_FORA + CONCORRENTES:
        assert palavra.lower() not in secao, palavra


def test_a_pagina_inicial_tem_uma_secao_so_das_portas():
    pagina = INDEX.read_text(encoding="utf-8")
    for antiga in ("Porta 1 · Conector MCP", "Porta 2 · CLI", "Porta 3 · API"):
        assert antiga not in pagina
    # as âncoras antigas seguem valendo: agora levam ao cartão de cada porta
    for ancora in ('id="conector"', 'id="comandos"', 'id="api"'):
        assert pagina.count(ancora) == 1, ancora


# a impressão digital do texto da lista da página inicial (texto público, nível 1): o aprovado em 24/11/2026, com as
# quatro versões longas que a Diretoria decidiu manter em 25/11 (as mesmas do guia do analista desde o #1281) e, da
# onda 2 do conector (linha 980), a consulta "Acompanhar uma lista de empresas"
IMPRESSAO_DA_LISTA_DA_PAGINA = (
    "fe91892428c5075a951cca7d841173fff144b094dd4644ba8f0517b21e1762f6"
)


def test_o_texto_da_lista_da_pagina_e_o_aprovado():
    texto = json.dumps(registro.para_o_site(), ensure_ascii=False, sort_keys=True)
    assert hashlib.sha256(texto.encode()).hexdigest() == IMPRESSAO_DA_LISTA_DA_PAGINA, (
        "o texto da lista da página inicial mudou (um nome, resumo ou frase do registro): é texto público, passa "
        "pela revisão de segurança e pela cruzada; depois regrave IMPRESSAO_DA_LISTA_DA_PAGINA"
    )


# PR 5a: a chave do setor no formato da API, a mesma nas duas portas; o que cada porta aceitava antes continua
CHAVES_DE_SETOR = [
    ("eletricas", "eletricas"),
    ("saude_suplementar", "saude_suplementar"),
    ("saude-suplementar", "saude_suplementar"),  # o conector aceitava o hífen
    ("_x", "_x"),  # a CLI aceitava começar com `_`
    ("a" * 80, "a" * 80),  # o conector aceitava até 80
    ("a" * 81, None),
    ("Bancos", None),
    ("..", None),
    ("../catalog", None),
    ("bancos/..", None),
    ("a.b", None),
    ("", None),
]


@pytest.mark.parametrize(("digitada", "enviada"), CHAVES_DE_SETOR)
def test_a_chave_do_setor_e_a_mesma_nas_duas_portas(digitada, enviada):
    assert registro.chave_do_setor(digitada) == enviada
    try:
        da_cli = comandos._setor(None, None, digitada)  # type: ignore[arg-type]
    except click.BadParameter:
        da_cli = None
    assert da_cli == enviada


def test_a_cli_le_o_formato_da_chave_do_registro():
    assert consultas.formato("chave_do_setor") == registro.FORMATO_DA_CHAVE_DO_SETOR


# PR 5c: o conector aceita o porte em português, como a CLI, sem deixar de aceitar os nomes da API
def test_o_conector_aceita_o_porte_nas_duas_grafias():
    valores = _parametro("buscar_empresas", "porte").valores
    assert set(registro.PORTES) <= set(valores)
    assert set(registro.PORTES.values()) <= set(valores)
    assert valores[: len(registro.PORTES)] == tuple(registro.PORTES)
