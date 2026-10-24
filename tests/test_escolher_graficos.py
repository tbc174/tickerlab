"""O script que escolhe os gráficos (plano de 23/10/2026) com um cliente de mentira: nada vai à rede.

O que importa: estimar não gasta; nada é enviado acima do teto (contando o que já foi gasto); a
resposta guardada não é paga de novo; o texto de outra ficha fica de fora; sem a porta 2 só a reserva
vai ao ar; o item que a porta 2 reprova sai e a reserva completa o mínimo.
"""

import copy
import json
import re
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from scripts import escolher_graficos as eg
from scripts import escrever_analises as ea
from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import pedido, saida
from src.analise_escrita import porta2_dos_graficos as p2g
from src.analise_escrita import reserva_dos_graficos as rg
from tests.ajudantes_da_analise import PAR_DA_CPFL

ARQUIVO_DA_ENTRADA = PAR_DA_CPFL / "entrada.json"
ENTRADA = json.loads(ARQUIVO_DA_ENTRADA.read_text(encoding="utf-8"))
TEXTO = json.loads((PAR_DA_CPFL / "gabarito.json").read_text(encoding="utf-8"))[
    "analise"
]
_ROTULO = re.compile(r"^\[((?:grafico|destaque)\.\d+)\] ", re.MULTILINE)


# o achado do modelo tem número da primeira linha da tabela (a porta 1 confere)
ACHADOS = {
    "ofertas_e_fundos.fundos_por_mes": "No primeiro mês, 436 fundos tinham a ação.",
    "setor_regulado.aneel_consumidores": "No primeiro ano, a empresa tinha 11,1% dos consumidores.",
}


def _do_modelo(tabela: str, tipo: str, eixo: str, coluna: str, parte: str) -> dict:
    return {
        "tipo": tipo, "tabela": tabela, "eixo": eixo, "colunas": [coluna],
        "titulo": "Um gráfico", "parte": parte, "paragrafo": 0,
        "por_que": {"texto": ACHADOS[tabela], "notas": [f"{tabela}.0"]},
    }  # fmt: skip


ESCOLHA = {
    "graficos": [
        _do_modelo("ofertas_e_fundos.fundos_por_mes", "linha_no_tempo", "Mês",
                   "Fundos", "quem_manda"),
        _do_modelo("setor_regulado.aneel_consumidores", "linha_no_tempo", "Ano",
                   "Consumidores", "o_que_e"),
    ],
    "destaques": [
        {"secao": "resultado", "parte": "o_que_os_numeros_mostram",
         "por_que": {"texto": "A cascata mostra os passos.",
                     "notas": ["resultado.cascata.0"]}},
    ],
}  # fmt: skip


def _mensagem(texto: str, stop="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=texto)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=30_000, output_tokens=2_000,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )  # fmt: skip


class ClienteDeMentira:
    """Escolhe `ESCOLHA` e, na porta 2, dá `mostra` a tudo (menos aos rótulos de `ruins`)."""

    def __init__(
        self, ruins: frozenset[str] = frozenset(), resposta: str | None = None
    ):
        self.ruins = ruins
        self.resposta = (
            json.dumps(ESCOLHA, ensure_ascii=False) if resposta is None else resposta
        )
        self.criados: list[dict] = []
        self.messages = SimpleNamespace(
            stream=self._fluxo,
            count_tokens=lambda **_: SimpleNamespace(input_tokens=30_000),
        )

    def _texto(self, params: dict) -> str:
        if params["output_config"]["format"]["schema"] == p2g.ESQUEMA:
            rotulos = _ROTULO.findall(params["messages"][0]["content"])
            itens = [
                {"item": r, "motivo": "",
                 "veredito": p2g.NAO_MOSTRA if r in self.ruins else p2g.MOSTRA}
                for r in rotulos
            ]  # fmt: skip
            return json.dumps({"itens": itens})
        return self.resposta

    @contextmanager
    def _fluxo(self, **params):
        self.criados.append(params)
        yield SimpleNamespace(get_final_message=lambda: _mensagem(self._texto(params)))


@pytest.fixture
def analises(tmp_path):
    """A pasta do `escrever_analises` com o texto da CPFL já montado."""
    pasta = tmp_path / "texto"
    ea._gravar(
        ea.arquivo_da_analise(pasta, ENTRADA),
        {"hash_da_entrada_atual": en.hash_da_entrada(ENTRADA), "analise": TEXTO},
    )
    return pasta


def _montado(cliente, analises, pasta, modelo=pedido.SONNET, cegas=True) -> dict:
    eg.piloto(cliente, [ENTRADA], analises, pasta, [modelo], teto=2)
    if cegas:
        eg.cegas(cliente, [ENTRADA], analises, pasta, [modelo], teto=2)
    eg.conferir([ENTRADA], analises, pasta, [modelo])
    arquivo = eg.arquivo_dos_graficos(pasta, ENTRADA, modelo)
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _origens(montado: dict) -> list[str]:
    return [g["origem"] for g in montado["escolha"]["graficos"]]


def test_estimar_nao_gasta(analises, tmp_path):
    cliente = ClienteDeMentira()
    modelos = [pedido.HAIKU, pedido.SONNET, pedido.OPUS]
    custos = eg.estimar(cliente, [ENTRADA], analises, tmp_path / "g", modelos)
    assert cliente.criados == []
    # a escolha e a porta 2: o Sonnet julgado pelo Opus custa o que o Opus julgado pelo Sonnet
    assert 0 < custos[pedido.HAIKU] < custos[pedido.SONNET] == custos[pedido.OPUS]


def test_teto_trava_antes_de_gastar(analises, tmp_path):
    cliente = ClienteDeMentira()
    with pytest.raises(eg.TetoPassado):
        eg.piloto(
            cliente, [ENTRADA], analises, tmp_path / "g", [pedido.SONNET], teto=0.01
        )
    assert cliente.criados == []
    assert not (tmp_path / "g").exists()


def test_teto_conta_o_que_ja_foi_gasto(analises, tmp_path):
    pasta = tmp_path / "g"
    pasta.mkdir()
    (pasta / "manifesto.json").write_text(json.dumps({"gasto_em_dolares": 1.99}))
    with pytest.raises(eg.TetoPassado):
        eg.piloto(
            ClienteDeMentira(), [ENTRADA], analises, pasta, [pedido.SONNET], teto=2
        )


def test_resposta_guardada_nao_paga_de_novo(analises, tmp_path):
    cliente, pasta = ClienteDeMentira(), tmp_path / "g"
    assert eg.piloto(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 1
    gasto = eg.ler_manifesto(pasta)["gasto_em_dolares"]
    assert gasto > 0
    assert eg.piloto(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 0
    assert eg.cegas(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 1
    assert eg.cegas(cliente, [ENTRADA], analises, pasta, [pedido.SONNET], teto=2) == 0
    assert len(cliente.criados) == 2


def test_texto_de_outra_ficha_fica_de_fora(analises, tmp_path):
    outra = copy.deepcopy(ENTRADA)
    outra["linhas"][0]["texto"] = "CPFL ENERGIA S/A"  # mesma chave, outra ficha
    cliente = ClienteDeMentira()
    assert (
        eg.piloto(cliente, [outra], analises, tmp_path / "g", [pedido.SONNET], teto=2)
        == 0
    )
    assert cliente.criados == []


def test_sem_a_porta_2_so_a_reserva(analises, tmp_path):
    montado = _montado(ClienteDeMentira(), analises, tmp_path / "g", cegas=False)
    assert set(_origens(montado)) == {rg.ORIGEM_REGRAS}
    assert montado["escolha"]["destaques"] == []
    assert montado["linhagem"]["porta2"] is None
    assert montado["linhagem"]["escolha_do_modelo"] is not None


def test_com_a_porta_2_a_escolha_do_modelo_vai_ao_ar(analises, tmp_path):
    montado = _montado(ClienteDeMentira(), analises, tmp_path / "g")
    assert _origens(montado) == [saida.ORIGEM_MODELO] * 2
    assert len(montado["escolha"]["destaques"]) == 1
    linhagem = montado["linhagem"]
    assert linhagem["porta1"] == []
    assert linhagem["porta2"]["conferente"] == pedido.OPUS  # o Sonnet não julga a si
    assert linhagem["porta2"]["reprovados"] == []
    assert linhagem["custo_em_dolares"] > 0


def test_reprovado_na_porta_2_da_lugar_a_reserva(analises, tmp_path):
    cliente = ClienteDeMentira(ruins=frozenset({"grafico.1", "destaque.0"}))
    montado = _montado(cliente, analises, tmp_path / "g")
    assert _origens(montado) == [saida.ORIGEM_MODELO, rg.ORIGEM_REGRAS]
    assert montado["escolha"]["destaques"] == []
    assert montado["linhagem"]["porta2"]["reprovados"] == ["destaque.0", "grafico.1"]


def test_resposta_fora_do_formato_nao_vai_a_porta_2(analises, tmp_path):
    cliente = ClienteDeMentira(resposta='{"graficos": "nenhum"}')
    montado = _montado(cliente, analises, tmp_path / "g")
    assert len(cliente.criados) == 1  # só a escolha; a porta 2 não gasta com ela
    assert set(_origens(montado)) == {rg.ORIGEM_REGRAS}
    assert "gráficos" in montado["linhagem"]["motivo"]
    assert len(montado["escolha"]["graficos"]) == gr.MINIMO_DE_GRAFICOS


def test_passos_que_gastam_exigem_o_teto(analises, tmp_path):
    for passo in eg.GASTAM:
        with pytest.raises(SystemExit):
            eg.main([passo, "--entradas", str(ARQUIVO_DA_ENTRADA),
                     "--analises", str(analises), "--pasta", str(tmp_path / "g")])  # fmt: skip


def test_main_estimar_mostra_o_custo_sem_gastar(
    analises, tmp_path, monkeypatch, capsys
):
    cliente = ClienteDeMentira()
    monkeypatch.setattr(eg.ri, "cliente", lambda: cliente)
    argumentos = [
        "estimar",
        "--entradas",
        str(ARQUIVO_DA_ENTRADA),
        "--analises",
        str(analises),
    ]
    assert (
        eg.main([*argumentos, "--pasta", str(tmp_path / "g"), "--teto-dolares", "2"])
        == 0
    )
    assert "cabe no teto" in capsys.readouterr().out
    assert cliente.criados == []


def test_main_conferir_nao_usa_a_api(analises, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        eg.ri, "cliente", lambda: pytest.fail("conferir não chama a API")
    )
    argumentos = [
        "conferir",
        "--entradas",
        str(ARQUIVO_DA_ENTRADA),
        "--analises",
        str(analises),
    ]
    assert eg.main([*argumentos, "--pasta", str(tmp_path / "g")]) == 0
    assert "1 escolhas montadas" in capsys.readouterr().out


def test_o_modelo_ve_e_usa_as_series_calculadas(analises, tmp_path):
    """O pedido leva as séries; o texto continua conferido contra a entrada original."""
    escolha = copy.deepcopy(ESCOLHA)
    escolha["graficos"][1] = {
        "tipo": "barras_no_tempo", "tabela": "series.margens", "eixo": "Ano",
        "colunas": ["Margem líquida"], "titulo": "Margem líquida ano a ano",
        "parte": "o_que_os_numeros_mostram", "paragrafo": 0,
        "por_que": {"texto": "A margem líquida foi de 12,9% em 2025.",
                    "notas": ["series.margens.1"]},
    }  # fmt: skip
    cliente = ClienteDeMentira(resposta=json.dumps(escolha, ensure_ascii=False))
    montado = _montado(cliente, analises, tmp_path / "g")
    pedido_da_escolha = cliente.criados[0]["messages"][0]["content"]
    assert "series.margens (2 linhas)" in pedido_da_escolha
    assert montado["linhagem"]["porta1"] == []
    assert montado["escolha"]["graficos"][1]["tabela"] == "series.margens"
    assert _origens(montado) == [saida.ORIGEM_MODELO] * 2


def _publicado(analises, pasta) -> dict:
    _montado(ClienteDeMentira(), analises, pasta, modelo=eg.MODELO_DOS_RELATORIOS)
    assert eg.publicar([ENTRADA], analises, pasta) == 1
    arquivo = ea.arquivo_da_analise(analises, ENTRADA)
    return json.loads(arquivo.read_text(encoding="utf-8"))


def test_publicar_grava_a_escolha_do_opus_junto_do_texto(analises, tmp_path):
    """A porta 3 do Tiago (23/10): o Opus escolhe os gráficos dos relatórios."""
    pasta = tmp_path / "g"
    guardada = _publicado(analises, pasta)
    assert guardada["analise"] == TEXTO  # o texto fica como estava
    graficos = guardada[eg.CAMPO_DOS_GRAFICOS]
    montado = json.loads(
        eg.arquivo_dos_graficos(pasta, ENTRADA, pedido.OPUS).read_text(encoding="utf-8")
    )
    assert graficos["modelo"] == pedido.OPUS
    assert graficos["escolha"] == montado["escolha"]
    assert graficos["hash_da_entrada"] == montado["hash_da_entrada"]
    assert graficos["hash_do_texto"] == gr.hash_do_texto(saida.ler_analise(TEXTO))


def test_publicar_sem_a_montagem_nao_mexe_no_texto(analises, tmp_path):
    arquivo = ea.arquivo_da_analise(analises, ENTRADA)
    antes = arquivo.read_text(encoding="utf-8")
    assert eg.publicar([ENTRADA], analises, tmp_path / "g") == 0
    assert arquivo.read_text(encoding="utf-8") == antes


def test_publicada_a_escolha_vai_para_o_relatorio(tmp_path):
    """Do passo `publicar` à tela, com a ficha como o lote a exporta (sem o preço da ação)."""
    from src import relatorio_empresa as re_
    from src.analise_escrita.exibicao import com_analise
    from tests.ajudantes_da_analise import CORTE, entradas_da_cpfl
    from tests.test_analise_na_tela import entrada_do_lote

    lote, analises, pasta = entrada_do_lote(), tmp_path / "texto", tmp_path / "g"
    arquivo = ea.arquivo_da_analise(analises, lote)
    ea._gravar(
        arquivo, {"hash_da_entrada_atual": en.hash_da_entrada(lote), "analise": TEXTO}
    )
    cliente = ClienteDeMentira()
    eg.piloto(cliente, [lote], analises, pasta, [pedido.OPUS], teto=2)
    eg.cegas(cliente, [lote], analises, pasta, [pedido.OPUS], teto=2)
    eg.conferir([lote], analises, pasta, [pedido.OPUS])
    assert eg.publicar([lote], analises, pasta) == 1
    guardada = json.loads(arquivo.read_text(encoding="utf-8"))
    guardada |= {"cnpj": lote["cnpj"], "corte": CORTE.isoformat(), "publicavel": True}
    app = tmp_path / "app"
    ea._gravar(app / f"{ea.chave(lote)}.json", guardada)
    entradas = entradas_da_cpfl()
    analise = com_analise(re_.montar(entradas, "pro"), entradas, "pro", app).analise
    assert analise is not None
    assert [g.origem for g in analise.graficos] == [saida.ORIGEM_MODELO] * 2


def test_main_publicar_usa_o_opus_sem_a_api(analises, tmp_path, monkeypatch, capsys):
    pasta = tmp_path / "g"
    _montado(ClienteDeMentira(), analises, pasta, modelo=pedido.OPUS)
    monkeypatch.setattr(
        eg.ri, "cliente", lambda: pytest.fail("publicar não chama a API")
    )
    argumentos = ["publicar", "--entradas", str(ARQUIVO_DA_ENTRADA)]
    assert (
        eg.main([*argumentos, "--analises", str(analises), "--pasta", str(pasta)]) == 0
    )
    assert "1 escolhas publicadas" in capsys.readouterr().out


# o caminho sem a API (Tiago, 23/10/2026: "Roda nesta conversa"): a sessão do Claude Code lê o
# mesmo pedido, escreve a resposta num arquivo e o passo `importar` a guarda como a da API


def _responder(arquivo_do_pedido, arquivo_da_resposta, resposta: str) -> None:
    assert arquivo_do_pedido.exists()
    arquivo_da_resposta.parent.mkdir(parents=True, exist_ok=True)
    arquivo_da_resposta.write_text(resposta, encoding="utf-8")


def _veredito_de_tudo(pedido_cego: str, ruins: frozenset[str] = frozenset()) -> str:
    itens = [
        {"item": r, "motivo": "",
         "veredito": p2g.NAO_MOSTRA if r in ruins else p2g.MOSTRA}
        for r in _ROTULO.findall(pedido_cego)
    ]  # fmt: skip
    return json.dumps({"itens": itens})


def _pela_sessao(analises, pasta, ruins: frozenset[str] = frozenset()) -> None:
    """Pedido, escolha escrita na sessão, porta 2 escrita às cegas por outro modelo."""
    modelo = pedido.OPUS
    assert eg.pedidos([ENTRADA], analises, pasta, [modelo]) == 1
    _responder(
        eg.arquivo_do_pedido(pasta, ENTRADA, modelo),
        eg.arquivo_da_resposta(pasta, ENTRADA, modelo),
        json.dumps(ESCOLHA, ensure_ascii=False),
    )
    assert eg.importar([ENTRADA], analises, pasta, [modelo]) == 1
    assert eg.pedidos([ENTRADA], analises, pasta, [modelo]) == 1  # agora o cego
    cego = eg.arquivo_do_pedido_cego(pasta, ENTRADA, modelo)
    _responder(
        cego,
        eg.arquivo_da_resposta_cega(pasta, ENTRADA, modelo),
        _veredito_de_tudo(cego.read_text(encoding="utf-8"), ruins),
    )
    assert eg.importar([ENTRADA], analises, pasta, [modelo]) == 1


def test_pedidos_escreve_o_pedido_da_api_sem_chamar_a_api(analises, tmp_path):
    pasta = tmp_path / "g"
    assert eg.pedidos([ENTRADA], analises, pasta, [pedido.OPUS]) == 1
    texto = eg.arquivo_do_pedido(pasta, ENTRADA, pedido.OPUS).read_text(
        encoding="utf-8"
    )
    parametros = eg.pg.pedido(
        eg.series.ampliar(ENTRADA), saida.ler_analise(TEXTO), pedido.OPUS
    )
    assert parametros["system"][0]["text"] in texto  # o mesmo guia
    assert (
        parametros["messages"][0]["content"] in texto
    )  # a mesma ficha e o mesmo texto
    esquema = parametros["output_config"]["format"]["schema"]
    assert json.dumps(esquema, ensure_ascii=False, indent=2) in texto
    assert not eg.arquivo_do_pedido_cego(pasta, ENTRADA, pedido.OPUS).exists()


def test_o_pedido_cego_nao_diz_quem_escolheu(analises, tmp_path):
    pasta = tmp_path / "g"
    _pela_sessao(analises, pasta)
    cego = eg.arquivo_do_pedido_cego(pasta, ENTRADA, pedido.OPUS).read_text(
        encoding="utf-8"
    )
    assert "opus" not in cego.lower() and "claude" not in cego.lower()
    assert p2g.SISTEMA in cego


def test_pela_sessao_a_escolha_vai_ao_ar_com_a_linhagem(analises, tmp_path):
    pasta = tmp_path / "g"
    _pela_sessao(analises, pasta)
    escolha = json.loads(
        eg.arquivo_da_escolha(pasta, ENTRADA, pedido.OPUS).read_text(encoding="utf-8")
    )
    assert escolha["via"] == eg.PELA_SESSAO
    assert escolha["custo_em_dolares"] == 0.0
    assert eg.conferir([ENTRADA], analises, pasta, [pedido.OPUS]) == 1
    montado = json.loads(
        eg.arquivo_dos_graficos(pasta, ENTRADA, pedido.OPUS).read_text(encoding="utf-8")
    )
    assert _origens(montado) == [saida.ORIGEM_MODELO] * 2
    linhagem = montado["linhagem"]
    assert linhagem["via"] == eg.PELA_SESSAO
    assert linhagem["porta2"]["conferente"] == pedido.SONNET
    assert linhagem["porta2"]["via"] == eg.PELA_SESSAO
    assert eg.publicar([ENTRADA], analises, pasta) == 1


def test_pela_sessao_reprovado_na_porta_2_da_lugar_a_reserva(analises, tmp_path):
    pasta = tmp_path / "g"
    _pela_sessao(analises, pasta, ruins=frozenset({"grafico.1"}))
    eg.conferir([ENTRADA], analises, pasta, [pedido.OPUS])
    montado = json.loads(
        eg.arquivo_dos_graficos(pasta, ENTRADA, pedido.OPUS).read_text(encoding="utf-8")
    )
    assert _origens(montado)[0] == saida.ORIGEM_MODELO
    assert saida.ORIGEM_MODELO not in _origens(montado)[1:]


def test_resposta_de_um_pedido_que_mudou_nao_entra(analises, tmp_path):
    """A resposta só vale para o pedido que está no arquivo: mudou o pedido, responde de novo."""
    pasta = tmp_path / "g"
    eg.pedidos([ENTRADA], analises, pasta, [pedido.OPUS])
    arquivo = eg.arquivo_do_pedido(pasta, ENTRADA, pedido.OPUS)
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8") + "\noutro", encoding="utf-8"
    )
    _responder(
        arquivo,
        eg.arquivo_da_resposta(pasta, ENTRADA, pedido.OPUS),
        json.dumps(ESCOLHA, ensure_ascii=False),
    )
    assert eg.importar([ENTRADA], analises, pasta, [pedido.OPUS]) == 0
    assert not eg.arquivo_da_escolha(pasta, ENTRADA, pedido.OPUS).exists()


def test_escolha_pela_api_tem_a_via_da_api(analises, tmp_path):
    montado = _montado(ClienteDeMentira(), analises, tmp_path / "g")
    assert montado["linhagem"]["via"] == "api"


def test_main_pedidos_e_importar_nao_usam_a_api(
    analises, tmp_path, monkeypatch, capsys
):
    pasta = tmp_path / "g"
    monkeypatch.setattr(eg.ri, "cliente", lambda: pytest.fail("sem a API"))
    comum = ["--entradas", str(ARQUIVO_DA_ENTRADA), "--analises", str(analises)]
    assert eg.main(["pedidos", *comum, "--pasta", str(pasta)]) == 0
    assert "1 pedidos escritos" in capsys.readouterr().out
    assert eg.arquivo_do_pedido(
        pasta, ENTRADA, pedido.OPUS
    ).exists()  # o Opus, por padrão
    assert eg.main(["importar", *comum, "--pasta", str(pasta)]) == 0
    assert "0 respostas importadas" in capsys.readouterr().out
