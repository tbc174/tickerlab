"""O perfil "TickerLab" do Windows Terminal (scripts/terminal/perfil_windows_terminal.py): as cores vêm da
marca, o fragment tem só perfil e esquema, e instalar/desfazer mexem só nas pastas que recebem."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.terminal import perfil_windows_terminal as perfil_wt
from src import marca

COR = re.compile(r"^#[0-9a-f]{6}$")
CHAVES_DO_ESQUEMA = {
    "name",
    "background",
    "foreground",
    "cursorColor",
    "selectionBackground",
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "purple",
    "cyan",
    "white",
    "brightBlack",
    "brightRed",
    "brightGreen",
    "brightYellow",
    "brightBlue",
    "brightPurple",
    "brightCyan",
    "brightWhite",
}


def ambiente_de_teste(tmp_path: Path) -> dict[str, str]:
    return {
        "LOCALAPPDATA": str(tmp_path / "local"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "claude"),
    }


def test_clarear_mistura_com_branco():
    assert perfil_wt.clarear("#000000", 0.5) == "#808080"
    assert perfil_wt.clarear("#ffffff", 0.3) == "#ffffff"
    assert perfil_wt.clarear(marca.QUEDA, 0) == marca.QUEDA
    assert perfil_wt.clarear(marca.QUEDA, 1) == "#ffffff"


def test_esquema_tem_todas_as_cores_do_terminal_e_vem_da_marca():
    esquema = perfil_wt.esquema_de_cores()
    assert set(esquema) == CHAVES_DO_ESQUEMA
    assert esquema["name"] == "TickerLab"
    assert all(COR.match(valor) for chave, valor in esquema.items() if chave != "name")
    assert esquema["background"] == marca.FUNDO
    assert esquema["foreground"] == marca.TEXTO
    assert esquema["green"] == marca.ALTA
    assert esquema["red"] == marca.QUEDA
    assert esquema["yellow"] == marca.ATENCAO
    assert esquema["blue"] == marca.AZUL_TEXTO
    assert esquema["brightBlack"] == marca.TEXTO_SUTIL
    assert esquema["cursorColor"] == marca.AZUL


def test_perfil_abre_o_lancador_na_raiz_do_repositorio():
    raiz = Path("C:/projetos/analise-acoes")
    dados = perfil_wt.perfil(raiz, "C:/pwsh/pwsh.exe", "Cascadia Mono")
    assert dados["name"] == "TickerLab"
    assert dados["colorScheme"] == "TickerLab"
    assert dados["startingDirectory"] == str(raiz)
    assert dados["font"] == {"face": "Cascadia Mono"}
    linha_de_comando = str(dados["commandline"])
    assert linha_de_comando.startswith('"C:/pwsh/pwsh.exe" -NoLogo -NoExit -File "')
    assert linha_de_comando.endswith('claude-tickerlab.ps1"')
    assert str(dados["icon"]).endswith("icone.png")


def test_fragmento_tem_so_perfil_e_esquema_e_vira_json():
    fragmento = perfil_wt.fragmento(Path("/repo"), "pwsh", "Cascadia Mono")
    assert set(fragmento) == {"profiles", "schemes"}
    recarregado = json.loads(json.dumps(fragmento))
    assert recarregado["profiles"][0]["name"] == "TickerLab"
    assert (
        recarregado["schemes"][0]["name"] == recarregado["profiles"][0]["colorScheme"]
    )


def test_fonte_do_perfil_e_a_da_marca_ou_a_reserva():
    assert perfil_wt.fonte_do_perfil() in {marca.FONTE_MONO, perfil_wt.FONTE_RESERVA}
    assert perfil_wt.fonte_instalada("Fonte Que Não Existe Em Lugar Nenhum") is False


def test_instalar_grava_fragmento_estilo_e_atalhos(tmp_path):
    ambiente = ambiente_de_teste(tmp_path)
    feitos = perfil_wt.instalar(ambiente, com_fonte=False, raiz=Path("/repo"))
    assert len(feitos) == 3
    fragmento = json.loads(
        perfil_wt.arquivo_do_fragmento(ambiente).read_text(encoding="utf-8")
    )
    assert fragmento["profiles"][0]["name"] == "TickerLab"
    assert "Windows Terminal" in str(perfil_wt.arquivo_do_fragmento(ambiente))
    estilo = perfil_wt.arquivo_do_estilo(ambiente)
    assert estilo.name == "TickerLab.md"
    assert estilo.read_bytes() == perfil_wt.ESTILO_DE_SAIDA.read_bytes()
    assert (
        perfil_wt.arquivo_dos_atalhos(ambiente).read_bytes()
        == perfil_wt.ATALHOS.read_bytes()
    )


def test_instalar_nao_sobrescreve_os_atalhos_da_pessoa(tmp_path):
    ambiente = ambiente_de_teste(tmp_path)
    atalhos = perfil_wt.arquivo_dos_atalhos(ambiente)
    atalhos.parent.mkdir(parents=True)
    atalhos.write_text('{"bindings": []}', encoding="utf-8")
    feitos = perfil_wt.instalar(ambiente, com_fonte=False, raiz=Path("/repo"))
    assert atalhos.read_text(encoding="utf-8") == '{"bindings": []}'
    assert any("junte à mão" in linha for linha in feitos)


def test_desfazer_apaga_so_o_que_instalou(tmp_path):
    ambiente = ambiente_de_teste(tmp_path)
    perfil_wt.instalar(ambiente, com_fonte=False, raiz=Path("/repo"))
    feitos = perfil_wt.desfazer(ambiente, com_fonte=False)
    assert len(feitos) == 3
    assert not perfil_wt.arquivo_do_fragmento(ambiente).exists()
    assert not perfil_wt.arquivo_do_fragmento(ambiente).parent.exists()
    assert not perfil_wt.arquivo_do_estilo(ambiente).exists()
    assert not perfil_wt.arquivo_dos_atalhos(ambiente).exists()


def test_desfazer_mantem_os_atalhos_da_pessoa(tmp_path):
    ambiente = ambiente_de_teste(tmp_path)
    atalhos = perfil_wt.arquivo_dos_atalhos(ambiente)
    atalhos.parent.mkdir(parents=True)
    atalhos.write_text('{"bindings": []}', encoding="utf-8")
    feitos = perfil_wt.desfazer(ambiente, com_fonte=False)
    assert atalhos.exists()
    assert feitos == [f"mantido (tem atalhos da pessoa): {atalhos}"]


def test_so_mostrar_imprime_o_fragment_e_nao_grava_nada(tmp_path, capsys):
    ambiente = ambiente_de_teste(tmp_path)
    assert perfil_wt.principal(["--so-mostrar"], ambiente) == 0
    impresso = json.loads(capsys.readouterr().out)
    assert impresso["profiles"][0]["name"] == "TickerLab"
    assert not (tmp_path / "local").exists()
    assert not (tmp_path / "claude").exists()


def test_principal_instala_e_desfaz(tmp_path, capsys):
    ambiente = ambiente_de_teste(tmp_path)
    assert perfil_wt.principal([], ambiente) == 0
    saida = capsys.readouterr().out
    assert "Pronto" in saida
    assert (
        '"statusLine"' in saida
    )  # a única parte que a pessoa liga à mão: o programa diz a linha
    assert "scripts/terminal/statusline.js" in saida
    assert str(tmp_path / "claude" / "settings.json") in saida
    assert perfil_wt.arquivo_do_fragmento(ambiente).exists()
    assert perfil_wt.principal(["--desfazer"], ambiente) == 0
    assert not perfil_wt.arquivo_do_fragmento(ambiente).exists()
