"""A lista única das portas (frente 2 do foco de 24/11/2026): o conector, a CLI e a API saem do mesmo registro.

`conector_remoto/consultas_das_portas.py` é o lugar de cada consulta. Ferramenta nova no conector, comando novo na CLI ou rota
nova na `/data/v1` fora do registro faz este arquivo falhar; porta que não oferece uma consulta tem o motivo escrito.

A foto (`tests/arquivos/portas_foto.json`) guarda o que a IA do analista lê de cada ferramenta (título, descrição,
parâmetros) e as instruções do servidor. Mudar esse texto é decisão, não efeito colateral: quando a mudança é de
propósito, regrave a foto com `TICKERLAB_GRAVAR_FOTO=1` e diga no PR o que a IA passa a ler de diferente.
"""

import asyncio
import json
import os
from pathlib import Path

import click
import pytest
from mcp.server.mcpserver import MCPServer
from tickerlab.comandos import principal

from conector_remoto import consultas_das_portas as registro
from conector_remoto import socios_e_donos
from conector_remoto.cliente_api import ClienteDaApi
from conector_remoto.ferramentas import registrar_ferramentas
from conector_remoto.servidor import INSTRUCOES
from src.api_externa.rotas import router
from src.chat import ferramentas as do_chat

FOTO = Path(__file__).parent / "arquivos" / "portas_foto.json"
GRAVAR_FOTO = "TICKERLAB_GRAVAR_FOTO"
# divergências entre as portas que já se sabem, com o PR que as resolve (plano da frente 2, PR 5)
DIVERGENCIAS_DA_CLI = {
    (
        "buscar_empresas",
        "porte",
    ): "a CLI usa os nomes em português (micro, pequena, demais, nao_informado); PR 5c",
    ("fundo", "retorno_suposto"): "a CLI ainda não confere a faixa; PR 5b",
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
