"""Scripts do backup do acervo no Drive (ADR 0123, linha 251).

Rodam com um `rclone` de mentira que só anota os argumentos: nada sobe, nada é lido da conta de ninguém.
O que se prova aqui são as regras que não podem quebrar: só `copy` com `--backup-dir` (nunca `sync`, nunca
apagar do destino), `restrito/` e a sala de dados nunca sobem, uma parte que falha não derruba as outras e o
envio que já está rodando não é atropelado por outro.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PASTA_DOS_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
BACKUP = PASTA_DOS_SCRIPTS / "backup-acervo-drive.sh"
CONFERENCIA = PASTA_DOS_SCRIPTS / "conferir-backup-acervo-drive.sh"
RESTAURACAO = PASTA_DOS_SCRIPTS / "testar-restauracao-drive.sh"
TODOS = (BACKUP, CONFERENCIA, RESTAURACAO)

BASH = shutil.which("bash")
precisa_de_bash = pytest.mark.skipif(
    BASH is None or shutil.which("flock") is None,
    reason="precisa de bash e flock (servidor Linux)",
)

RCLONE_DE_MENTIRA = """#!/usr/bin/env bash
echo "$*" >> "$ANOTACOES"
if [ -n "${FALHAR_EM:-}" ] && [[ "$*" == *"$FALHAR_EM"* ]]; then exit 7; fi
exit 0
"""


@pytest.fixture
def ambiente(tmp_path: Path) -> dict[str, str]:
    """Acervo e backups de mentira, com `restrito/` e a sala de dados no meio, e o rclone que só anota."""
    acervo = tmp_path / "acervo"
    for pasta in ("bruto", "manifesto", "ancoras", "restrito"):
        (acervo / pasta).mkdir(parents=True)
        (acervo / pasta / "a.txt").write_text(pasta)
    backups = tmp_path / "backups"
    for pasta in (
        "tickerlab",
        "tickerlab-pc",
        "tickerlab-acervo",
        "tickerlab-acessos",
        "casa",
        "base-antes-manifestos",
        "tickerlab-sala",
    ):
        (backups / pasta).mkdir(parents=True)
    rclone = tmp_path / "rclone"
    rclone.write_text(RCLONE_DE_MENTIRA)
    rclone.chmod(0o755)
    return {
        **os.environ,
        "ACERVO": str(acervo),
        "PARTES_DO_ACERVO": "manifesto ancoras bruto",
        "EMPACOTADOR": "",  # os pacotes têm teste próprio (test_empacotar_acervo_drive.py)
        "PASTA_DE_BACKUPS": str(backups),
        "RCLONE": str(rclone),
        "RCLONE_CONFIG": str(tmp_path / "rclone.conf"),
        "ANOTACOES": str(tmp_path / "anotacoes.txt"),
        "LOG": str(tmp_path / "backup.log"),
        "TMPDIR": str(tmp_path),
        "DATA_DAS_VERSOES": "2026-11-05",
    }


def rodar(script: Path, ambiente: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(script)],
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def chamadas(ambiente: dict[str, str]) -> list[str]:
    anotacoes = Path(ambiente["ANOTACOES"])
    return anotacoes.read_text().splitlines() if anotacoes.exists() else []


@pytest.mark.parametrize("script", TODOS, ids=lambda s: s.name)
def test_sintaxe_do_bash_esta_certa(script: Path) -> None:
    if BASH is None:
        pytest.skip("sem bash")
    resultado = subprocess.run(
        [BASH, "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.parametrize("script", TODOS, ids=lambda s: s.name)
def test_script_nao_sabe_apagar_nem_espelhar_e_nao_carrega_segredo(
    script: Path,
) -> None:
    codigo = "\n".join(
        linha
        for linha in script.read_text().splitlines()
        if not linha.lstrip().startswith("#")
    ).lower()
    for proibido in (
        " sync ",
        "purge",
        "delete",
        "deletefile",
        "rmdirs",
        " move ",
        "moveto",
        "dedupe",
        "cleanup",
        "--password",
        "pass=",
        "token",
    ):
        assert proibido not in codigo, proibido


@precisa_de_bash
def test_so_copia_com_pasta_de_versoes_datada(ambiente: dict[str, str]) -> None:
    resultado = rodar(BACKUP, ambiente)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    feitas = chamadas(ambiente)
    assert (
        len(feitas) == 3 + 4
    )  # bruto, manifesto, ancoras e as quatro pastas pequenas de backups
    for chamada in feitas:
        assert chamada.startswith("copy ")
        assert "--backup-dir cripto:_versoes/2026-11-05/" in chamada
        assert "--bwlimit" in chamada


@precisa_de_bash
def test_restrito_e_sala_de_dados_nunca_sobem(
    ambiente: dict[str, str], tmp_path: Path
) -> None:
    rodar(BACKUP, ambiente)
    for chamada in chamadas(ambiente):
        origem = Path(chamada.split()[1]).relative_to(tmp_path)
        assert "restrito" not in origem.parts
        assert "tickerlab-sala" not in origem.parts
        assert "--exclude restrito/**" in chamada
        assert "--exclude tickerlab-sala/**" in chamada


def _fontes_do_script(script: Path) -> set[str]:
    for linha in script.read_text().splitlines():
        if linha.startswith("FONTES_SO_NO_RESTRITO="):
            return set(linha.split("=", 1)[1].strip('"').split())
    raise AssertionError(f"{script.name} não define FONTES_SO_NO_RESTRITO")


@pytest.mark.parametrize("script", TODOS, ids=lambda s: s.name)
def test_fontes_com_pessoa_nao_sobem_e_a_lista_acompanha_o_codigo(script: Path) -> None:
    """O que traz nome de pessoa nunca sobe ao Drive (o que sobe nunca mais sai), mesmo se ainda estiver em
    `bruto/`; se o código ganhar uma fonte restrita nova, esta lista tem de acompanhar."""
    from src import acervo
    from src.banco import coletas

    esperadas = set(acervo.FONTES_COM_PESSOA) | set(coletas.FONTES_SO_INTERNAS)
    assert _fontes_do_script(script) == esperadas


@precisa_de_bash
def test_fontes_com_pessoa_entram_como_filtro_em_toda_subida(
    ambiente: dict[str, str],
) -> None:
    rodar(BACKUP, ambiente)
    feitas = chamadas(ambiente)
    assert feitas
    for chamada in feitas:
        for fonte in _fontes_do_script(BACKUP):
            assert f"--exclude {fonte}/**" in chamada


@precisa_de_bash
@pytest.mark.parametrize("proibida", ["restrito", "bruto/restrito", ".", ".."])
def test_recusa_origem_com_nome_proibido(
    ambiente: dict[str, str], proibida: str
) -> None:
    (Path(ambiente["ACERVO"]) / "bruto" / "restrito").mkdir(exist_ok=True)
    resultado = rodar(
        BACKUP,
        {
            **ambiente,
            "PARTES_DO_ACERVO": proibida,
            "BACKUPS_QUE_SOBEM": "tickerlab-sala",
        },
    )
    assert resultado.returncode == 1
    assert "FALHAS:" in resultado.stdout
    assert chamadas(ambiente) == []


@precisa_de_bash
def test_lista_vazia_nao_vira_tudo_certo(ambiente: dict[str, str]) -> None:
    resultado = rodar(
        BACKUP, {**ambiente, "PARTES_DO_ACERVO": "", "BACKUPS_QUE_SOBEM": ""}
    )
    assert resultado.returncode == 1
    assert "FALHAS:" in resultado.stdout
    assert chamadas(ambiente) == []


@precisa_de_bash
def test_parte_que_falha_nao_derruba_as_outras(ambiente: dict[str, str]) -> None:
    resultado = rodar(BACKUP, {**ambiente, "FALHAR_EM": "acervo/bruto"})
    assert resultado.returncode == 1
    assert "FALHAS: acervo-bruto" in resultado.stdout
    assert len(chamadas(ambiente)) == 7  # todas as partes foram tentadas


EMPACOTADOR_DE_MENTIRA = """#!/usr/bin/env bash
echo "empacotador $*" >> "$ANOTACOES"
if [ -n "${PACOTES_FALHAM:-}" ]; then echo "FALHAS: $PACOTES_FALHAM"; exit 1; fi
echo "pacotes ok"
"""


def _com_empacotador(ambiente: dict[str, str], tmp_path: Path) -> dict[str, str]:
    assert BASH is not None
    falso = tmp_path / "empacotador.sh"
    falso.write_text(EMPACOTADOR_DE_MENTIRA)
    return {**ambiente, "EMPACOTADOR": f"{BASH} {falso}"}


@precisa_de_bash
def test_padrao_manda_o_acervo_para_o_empacotador_e_so_os_backups_pequenos_por_arquivo(
    ambiente: dict[str, str], tmp_path: Path
) -> None:
    """Sem as variáveis, o acervo e os backups grandes vão em pacotes; só as quatro pastas pequenas em `copy`."""
    padrao = {
        k: v
        for k, v in _com_empacotador(ambiente, tmp_path).items()
        if k not in ("PARTES_DO_ACERVO", "BACKUPS_QUE_SOBEM")
    }
    resultado = rodar(BACKUP, padrao)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    feitas = chamadas(ambiente)
    copias = [c for c in feitas if c.startswith("copy ")]
    assert len(copias) == 4
    for grande in (
        "tickerlab-pc",
        "tickerlab-acervo",
        "/bruto",
        "/manifesto",
        "/ancoras",
    ):
        assert not any(grande in c.split()[1] for c in copias), grande
    assert [c for c in feitas if c.startswith("empacotador")] == ["empacotador subir"]


@precisa_de_bash
def test_pacote_que_falha_marca_a_falha_e_as_outras_partes_ainda_sobem(
    ambiente: dict[str, str], tmp_path: Path
) -> None:
    resultado = rodar(
        BACKUP,
        {**_com_empacotador(ambiente, tmp_path), "PACOTES_FALHAM": "pacotes-bruto"},
    )
    assert resultado.returncode == 1
    assert resultado.stdout.count("FALHAS:") == 1
    assert "FALHAS: pacotes-bruto" in resultado.stdout
    assert len([c for c in chamadas(ambiente) if c.startswith("copy ")]) == 7


@precisa_de_bash
def test_so_o_empacotador_ligado_ja_e_um_backup(
    ambiente: dict[str, str], tmp_path: Path
) -> None:
    resultado = rodar(
        BACKUP,
        {
            **_com_empacotador(ambiente, tmp_path),
            "PARTES_DO_ACERVO": "",
            "BACKUPS_QUE_SOBEM": "",
        },
    )
    assert resultado.returncode == 0, resultado.stdout
    assert chamadas(ambiente) == ["empacotador subir"]


@precisa_de_bash
def test_conferencia_e_restauracao_chamam_o_empacotador(
    ambiente: dict[str, str], tmp_path: Path
) -> None:
    com = _com_empacotador(ambiente, tmp_path)
    sem_listas = {**com, "PARTES_DO_ACERVO": "", "BACKUPS_QUE_SOBEM": ""}
    assert rodar(CONFERENCIA, sem_listas).returncode == 0
    assert rodar(RESTAURACAO, sem_listas).returncode == 0
    assert chamadas(ambiente) == ["empacotador conferir", "empacotador amostra"]
    ruim = rodar(CONFERENCIA, {**sem_listas, "PACOTES_FALHAM": "pacotes-bruto"})
    assert ruim.returncode == 1
    assert "FALHAS: pacotes-bruto" in ruim.stdout
    ruim = rodar(RESTAURACAO, {**sem_listas, "PACOTES_FALHAM": "x"})
    assert ruim.returncode == 1
    assert "FALHAS: restauracao-drive" in ruim.stdout


@precisa_de_bash
def test_origem_que_sumiu_e_falha_e_nao_chama_o_rclone(
    ambiente: dict[str, str],
) -> None:
    shutil.rmtree(Path(ambiente["ACERVO"]) / "manifesto")
    resultado = rodar(BACKUP, ambiente)
    assert resultado.returncode == 1
    assert "FALHAS: acervo-manifesto" in resultado.stdout
    assert not any(
        chamada.split()[1].endswith("/acervo/manifesto")
        for chamada in chamadas(ambiente)
    )


@precisa_de_bash
def test_envio_em_andamento_nao_e_atropelado(ambiente: dict[str, str]) -> None:
    segurando = subprocess.Popen(
        [
            BASH or "bash",
            "-c",
            f'exec 9>"{ambiente["TMPDIR"]}/tickerlab-backup-acervo-drive.lock"; flock -n 9 && sleep 20',
        ],
    )
    try:
        for _ in range(50):  # espera o outro pegar a trava
            if Path(ambiente["TMPDIR"], "tickerlab-backup-acervo-drive.lock").exists():
                break
        resultado = rodar(BACKUP, ambiente)
    finally:
        segurando.kill()
    assert resultado.returncode == 0
    assert "ainda está subindo" in resultado.stdout
    assert chamadas(ambiente) == []


@precisa_de_bash
def test_conferencia_acusa_diferenca_do_cryptcheck(ambiente: dict[str, str]) -> None:
    rclone = Path(ambiente["RCLONE"])
    rclone.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = size ]; then echo \'{"count":2,"bytes":10}\'; exit 0; fi\n'
        'if [ "$1" = cryptcheck ]; then echo "* arquivo.csv"; exit 1; fi\n'
    )
    resultado = rodar(
        CONFERENCIA, {**ambiente, "PARTES_DO_ACERVO": "bruto", "BACKUPS_QUE_SOBEM": ""}
    )
    assert resultado.returncode == 1
    assert "FALHAS: acervo-bruto" in resultado.stdout
    assert (
        "origem 2 arquivos / 10 bytes; Drive 2 arquivos / 10 bytes" in resultado.stdout
    )


@precisa_de_bash
def test_conferencia_passa_quando_tudo_bate(ambiente: dict[str, str]) -> None:
    rclone = Path(ambiente["RCLONE"])
    rclone.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = size ]; then echo \'{"count":2,"bytes":10}\'; exit 0; fi\n'
        'if [ "$1" = cryptcheck ]; then echo "= arquivo.csv"; exit 0; fi\n'
    )
    resultado = rodar(
        CONFERENCIA, {**ambiente, "PARTES_DO_ACERVO": "bruto", "BACKUPS_QUE_SOBEM": ""}
    )
    assert resultado.returncode == 0, resultado.stdout
    assert (
        "TOTAL origem 2 arquivos / 10 bytes; Drive 2 arquivos / 10 bytes"
        in resultado.stdout
    )


@precisa_de_bash
def test_conferencia_com_origem_vazia_nao_passa(ambiente: dict[str, str]) -> None:
    rclone = Path(ambiente["RCLONE"])
    rclone.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = size ]; then echo \'{"count":0,"bytes":0}\'; exit 0; fi\n'
        "exit 0\n"
    )
    resultado = rodar(
        CONFERENCIA, {**ambiente, "PARTES_DO_ACERVO": "bruto", "BACKUPS_QUE_SOBEM": ""}
    )
    assert resultado.returncode == 1
    assert "origem-vazia" in resultado.stdout


@precisa_de_bash
def test_restauracao_confere_sha256_do_que_baixou(ambiente: dict[str, str]) -> None:
    acervo = Path(ambiente["ACERVO"])
    (acervo / "bruto" / "dados.csv").write_text("conteudo")
    rclone = Path(ambiente["RCLONE"])
    # lsf lista os arquivos da origem; copyto "baixa" copiando da origem (ou de um arquivo adulterado)
    rclone.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = lsf ]; then (cd "${@: -1}" && find . -type f | sed "s|^./||"); exit 0; fi\n'
        'if [ "$1" = copyto ]; then\n'
        '  origem="${2#cripto:acervo/}"\n'
        '  if [ -n "${ADULTERAR:-}" ]; then echo adulterado > "$3"; else cp "$ACERVO/$origem" "$3"; fi\n'
        "  exit 0\nfi\n"
    )
    ambiente = {**ambiente, "PARTES_DO_ACERVO": "bruto", "TAMANHO_DA_AMOSTRA": "5"}
    ok = rodar(RESTAURACAO, ambiente)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert (
        "2 arquivos baixados, decifrados e conferidos por sha256; 0 com problema"
        in ok.stdout
    )
    ruim = rodar(RESTAURACAO, {**ambiente, "ADULTERAR": "1"})
    assert ruim.returncode == 1
    assert "FALHAS: restauracao-drive" in ruim.stdout


MONTAR = PASTA_DOS_SCRIPTS / "montar-config-backup-drive.sh"
BLOCO_DO_TOKEN = (
    "Paste the following into your remote machine --->\n"
    "eyJ0b2tlbiI6IntcImFjY2Vzc190b2tlblwiOlwiQUFBXCJ9In0\n"
    "<---End paste\n"
)  # base64 de {"token":"{\"access_token\":\"AAA\"}"}


def montar(
    tmp_path: Path, entrada: str, **extra: str
) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    rclone = tmp_path / "rclone-obscure"
    rclone.write_text('#!/usr/bin/env bash\nprintf "ofuscada:%s" "$(cat)"\n')
    rclone.chmod(0o755)
    token = tmp_path / "token.saida"
    token.write_text(BLOCO_DO_TOKEN)
    ambiente = {
        **os.environ,
        "RCLONE": str(rclone),
        "PASTA": str(tmp_path / "config"),
        **extra,
    }
    return subprocess.run(
        [BASH, str(MONTAR), str(token)],
        env=ambiente,
        input=entrada,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_montar_config_cifra_nomes_e_nao_imprime_a_senha(tmp_path: Path) -> None:
    resultado = montar(tmp_path, "senha-secreta\nsal-secreto\n")
    assert resultado.returncode == 0, resultado.stderr
    assert "senha-secreta" not in resultado.stdout + resultado.stderr
    assert "sal-secreto" not in resultado.stdout + resultado.stderr
    config = (tmp_path / "config" / "rclone.conf").read_text()
    assert "type = crypt" in config
    assert "filename_encryption = standard" in config
    assert "directory_name_encryption = true" in config
    assert "scope = drive.file" in config
    assert (
        "password = ofuscada:senha-secreta" in config
    )  # só a versão que o rclone ofuscou
    assert "password2 = ofuscada:sal-secreto" in config
    if os.name == "posix":
        assert (tmp_path / "config" / "rclone.conf").stat().st_mode & 0o077 == 0


def test_montar_config_exige_senha_e_sal_e_nao_sobrescreve(tmp_path: Path) -> None:
    sem_sal = montar(tmp_path, "so-a-senha\n")
    assert sem_sal.returncode == 1
    assert not (tmp_path / "config" / "rclone.conf").exists()
    assert montar(tmp_path, "a\nb\n").returncode == 0
    segunda = montar(tmp_path, "c\nd\n")
    assert segunda.returncode == 1
    assert "password = ofuscada:a" in (tmp_path / "config" / "rclone.conf").read_text()
