"""Backup do acervo em pacotes .tar no Drive (ADR 0123, Emenda 1; linha 251).

O Drive aqui é uma pasta e o `rclone` é um programa de mentira em Python que só sabe `rcat`, `lsjson` e `cat`:
nada sai do computador. O que se prova são as regras que não podem quebrar: pessoa e `restrito/` nunca entram
(em qualquer profundidade), pacote é imutável, nada é apagado nem movido no Drive, o que muda sobe em pacote
novo, um pacote que falha não vira objeto pela metade e a conferência acusa falta, adulteração e diferença.
"""

import json
import os
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from scripts import empacotar_acervo_drive as emp

RCLONE_DE_MENTIRA = """
import json, os, sys
from pathlib import Path

drive = Path(os.environ["FAKE_DRIVE"])
args = [a for a in sys.argv[1:]]
# uma escrita só, em modo append: dois processos ao mesmo tempo não misturam as linhas (no Windows `open` mistura)
fd = os.open(os.environ["FAKE_ANOTACOES"], os.O_WRONLY | os.O_APPEND | os.O_CREAT)
os.write(fd, (" ".join(args) + "\\n").encode())
os.close(fd)
sub = args[0]
caminho = next(a for a in args[1:] if ":" in a and not a.startswith("-")).split(":", 1)[1]
alvo = drive / caminho
falhar = os.environ.get("FALHAR_EM")
if sub == "rcat":
    dados = sys.stdin.buffer.read()
    if falhar and falhar in caminho:
        sys.exit(7)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_bytes(dados)
elif sub == "mkdir":
    alvo.mkdir(parents=True, exist_ok=True)
elif sub == "lsjson":
    if not alvo.is_dir():
        sys.exit(3)
    itens = [{"Path": p.relative_to(alvo).as_posix(), "Name": p.name, "Size": p.stat().st_size}
             for p in sorted(alvo.rglob("*")) if p.is_file()]
    print(json.dumps(itens))
elif sub == "cat":
    dados = alvo.read_bytes()
    if "--offset" in args:
        inicio = int(args[args.index("--offset") + 1])
        total = int(args[args.index("--count") + 1])
        dados = dados[inicio:inicio + total]
    sys.stdout.buffer.write(dados)
else:
    sys.exit(9)
"""


@pytest.fixture
def mundo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> emp.Configuracao:
    """Acervo e backups de mentira, com pessoa, `restrito/` e sala de dados no meio, e o Drive de pasta."""
    monkeypatch.setattr(emp, "ESPERA_DA_CONFERENCIA", 0.0)
    monkeypatch.setattr(emp, "ESPERA_ENTRE_TENTATIVAS", 0.0)
    acervo = tmp_path / "acervo"
    velho = time.time() - 24 * 3600
    ano = datetime.now(tz=emp.UTC).year

    def criar(base: Path, rel: str, conteudo: bytes) -> None:
        arquivo = base / rel
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(conteudo)
        os.utime(arquivo, (velho, velho))

    criar(acervo, "bruto/cvm-dfp/2024/a.bin.gz", b"A" * 1000)
    criar(acervo, "bruto/cvm-dfp/2024/b.bin.gz", b"B" * 2000)
    criar(acervo, f"bruto/cvm-dfp/{ano}/c.bin.gz", b"C" * 3000)
    criar(acervo, "bruto/bcb-sgs/2025/d.bin.gz", b"D" * 500)
    # o que NUNCA pode subir, em qualquer profundidade:
    criar(acervo, "bruto/rfb-cnpj/2025/pessoas.bin.gz", b"PESSOA")
    criar(acervo, "bruto/datajud/2025/processo.bin.gz", b"PROCESSO")
    criar(acervo, "bruto/cvm-dfp/2024/ibama-autos/escondido.bin.gz", b"PESSOA")
    criar(acervo, "bruto/cvm-dfp/restrito/x.bin.gz", b"LICENCA")
    criar(acervo, "manifesto/2026-10-15.jsonl", b'{"a":1}\n')
    criar(acervo, "ancoras/2026-10-15.json", b"{}")
    backups = tmp_path / "backups"
    criar(backups, "tickerlab-pc/TickerLab-Backup-2026-10-13/doc/leia.md", b"oi")
    criar(backups, "tickerlab-pc/TickerLab-Backup-2026-10-13/seg/chave.age", b"X" * 50)
    criar(backups, "tickerlab-acervo/2026-10-15/base.age", b"Y" * 80)
    criar(backups, "tickerlab-sala/cliente.pdf", b"CLIENTE")
    drive = tmp_path / "drive"
    drive.mkdir()
    rclone = tmp_path / "rclone_falso.py"
    rclone.write_text(RCLONE_DE_MENTIRA, encoding="utf-8")
    monkeypatch.setenv("FAKE_DRIVE", str(drive))
    monkeypatch.setenv("FAKE_ANOTACOES", str(tmp_path / "anotacoes.txt"))
    monkeypatch.delenv("FALHAR_EM", raising=False)
    return emp.Configuracao(
        acervo=acervo,
        pasta_de_backups=backups,
        rclone=[sys.executable, str(rclone)],
        estado=tmp_path / "estado.jsonl",
        log=None,
        bwlimit="off",
        paralelo=2,
        min_idade=300,
    )


def drive_de(_mundo: emp.Configuracao) -> Path:
    return Path(os.environ["FAKE_DRIVE"])


def objetos(mundo: emp.Configuracao, pasta: str) -> list[Path]:
    return sorted(p for p in (drive_de(mundo) / pasta).rglob("*") if p.is_file())


def membros_do_drive(mundo: emp.Configuracao) -> set[str]:
    nomes: set[str] = set()
    for tar_path in objetos(mundo, "pacotes"):
        with tarfile.open(tar_path) as tar:
            nomes.update(tar.getnames())
    return nomes


def anotacoes() -> list[str]:
    return Path(os.environ["FAKE_ANOTACOES"]).read_text(encoding="utf-8").splitlines()


def test_lista_de_fontes_proibidas_acompanha_o_codigo() -> None:
    """Se o código ganhar uma fonte restrita nova, a lista que impede o envio ao Drive tem de acompanhar."""
    from src import acervo
    from src.banco import coletas

    esperadas = set(acervo.FONTES_COM_PESSOA) | set(coletas.FONTES_SO_INTERNAS)
    assert set(emp.FONTES_SO_NO_RESTRITO) == esperadas
    assert set(emp.NOMES_PROIBIDOS) == {"restrito", "tickerlab-sala"}


def test_pessoa_restrito_e_sala_nunca_entram_em_nenhuma_profundidade(
    mundo: emp.Configuracao,
) -> None:
    assert emp.subir(mundo) == 0
    membros = membros_do_drive(mundo)
    assert membros
    for proibido in (
        "rfb-cnpj",
        "datajud",
        "ibama-autos",
        "restrito",
        "tickerlab-sala",
        "pessoas",
        "cliente",
    ):
        assert not any(proibido in m for m in membros), proibido
    assert "bruto/cvm-dfp/2024/a.bin.gz" in membros
    assert "tickerlab-pc/TickerLab-Backup-2026-10-13/doc/leia.md" in membros
    # o índice também não cita o que ficou de fora
    texto_dos_indices = "".join(
        p.read_text(encoding="utf-8") for p in objetos(mundo, "indices")
    )
    for proibido in ("rfb-cnpj", "datajud", "ibama-autos", "restrito", "cliente"):
        assert proibido not in texto_dos_indices


@pytest.mark.parametrize(
    "origem",
    ["/x/restrito", "/x/tickerlab-sala/y", "/x/bruto/rfb-cnpj", "/x/.", "/x/.."],
)
def test_origem_com_nome_proibido_e_recusada(origem: str) -> None:
    assert not emp.origem_permitida(origem)
    assert emp.origem_permitida("/mnt/dados/tickerlab-acervo/bruto")


def test_pacote_por_fonte_e_ano_e_o_ano_corrente_por_mes(
    mundo: emp.Configuracao,
) -> None:
    emp.subir(mundo)
    pacotes = [
        p.relative_to(drive_de(mundo)).as_posix() for p in objetos(mundo, "pacotes")
    ]
    ano = datetime.now(tz=emp.UTC).year
    mes = f"{datetime.fromtimestamp(time.time() - 24 * 3600, tz=emp.UTC):%m}"
    assert any(p.startswith("pacotes/acervo/bruto/cvm-dfp/2024/") for p in pacotes)
    assert any(p.startswith("pacotes/acervo/bruto/bcb-sgs/2025/") for p in pacotes)
    assert any(
        p.startswith(f"pacotes/acervo/bruto/cvm-dfp/{ano}-{mes}/") for p in pacotes
    )
    assert any(
        "backups/tickerlab-pc/TickerLab-Backup-2026-10-13/" in p for p in pacotes
    )
    assert any(p.startswith("pacotes/acervo/manifesto/") for p in pacotes)
    # cada pacote tem o índice dele, também no Drive
    assert len(objetos(mundo, "indices")) == len(pacotes)


def test_indice_tem_bytes_sha256_e_posicao_que_restauram_o_arquivo_avulso(
    mundo: emp.Configuracao,
) -> None:
    import hashlib

    emp.subir(mundo)
    achados = 0
    for caminho in objetos(mundo, "indices"):
        linhas = [
            json.loads(x) for x in caminho.read_text(encoding="utf-8").splitlines()
        ]
        cabecalho, entradas = linhas[0], linhas[1:]
        assert cabecalho["arquivos"] == len(entradas)
        tar_path = drive_de(mundo) / cabecalho["pacote"]
        assert tar_path.stat().st_size == cabecalho["tar_bytes"]
        dados_do_tar = tar_path.read_bytes()
        for e in entradas:
            original = (
                mundo.acervo
                if e["p"].startswith(("bruto", "manifesto", "ancoras"))
                else mundo.pasta_de_backups
            ) / e["p"]
            assert e["b"] == original.stat().st_size
            assert e["sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
            trecho = dados_do_tar[e["o"] : e["o"] + e["b"]]
            assert trecho == original.read_bytes(), e["p"]
            achados += 1
    assert achados == 9


def test_segunda_subida_nao_manda_nada_e_nao_apaga_nem_move(
    mundo: emp.Configuracao,
) -> None:
    emp.subir(mundo)
    antes = {p: p.stat().st_mtime_ns for p in objetos(mundo, "pacotes")}
    chamadas_antes = len(anotacoes())
    assert emp.subir(mundo) == 0
    assert {p: p.stat().st_mtime_ns for p in objetos(mundo, "pacotes")} == antes
    novas = anotacoes()[chamadas_antes:]
    assert not any(c.startswith("rcat") for c in novas)
    for chamada in anotacoes():
        assert chamada.split()[0] in {"rcat", "lsjson", "cat", "mkdir"}


def test_pastas_sao_criadas_uma_a_uma_antes_de_qualquer_envio(
    mundo: emp.Configuracao,
) -> None:
    """O Drive aceita pasta repetida: criar `pacotes/` em paralelo duplicaria e o rclone perderia pacote."""
    assert emp.subir(mundo) == 0
    comandos = [c.split()[0] for c in anotacoes()]
    assert "mkdir" in comandos
    assert comandos.index("rcat") > max(
        i for i, c in enumerate(comandos) if c == "mkdir"
    )


def test_arquivo_novo_e_arquivo_mudado_sobem_em_pacote_novo_e_o_antigo_fica(
    mundo: emp.Configuracao,
) -> None:
    emp.subir(mundo)
    antigos = {p: p.read_bytes() for p in objetos(mundo, "pacotes")}
    velho = time.time() - 3600
    novo = mundo.acervo / "bruto/cvm-dfp/2024/novo.bin.gz"
    novo.write_bytes(b"N" * 100)
    mudado = mundo.acervo / "bruto/cvm-dfp/2024/a.bin.gz"
    mudado.write_bytes(b"A2" * 700)
    for arquivo in (novo, mudado):
        os.utime(arquivo, (velho, velho))
    time.sleep(1.1)  # carimbo de hora diferente
    assert emp.subir(mundo) == 0
    depois = objetos(mundo, "pacotes")
    assert len(depois) == len(antigos) + 1
    delta = [p for p in depois if p not in antigos]
    assert all(
        p.read_bytes() == dados for p, dados in antigos.items()
    )  # pacote antigo intacto
    assert len(delta) == 1
    with tarfile.open(delta[0]) as tar:
        assert sorted(tar.getnames()) == [
            "bruto/cvm-dfp/2024/a.bin.gz",
            "bruto/cvm-dfp/2024/novo.bin.gz",
        ]
    assert emp.conferir(mundo) == 0  # a versão mais nova de cada arquivo é a do delta


def test_arquivo_recente_demais_fica_para_a_proxima(mundo: emp.Configuracao) -> None:
    (mundo.acervo / "bruto/cvm-dfp/2024/gravando.bin.gz").write_bytes(
        b"x"
    )  # acabou de ser escrito
    emp.subir(mundo)
    assert "bruto/cvm-dfp/2024/gravando.bin.gz" not in membros_do_drive(mundo)


def test_pacote_grande_e_dividido_pelo_limite(mundo: emp.Configuracao) -> None:
    mundo.limite_pacote = 2500
    emp.subir(mundo)
    nomes = [p.name for p in objetos(mundo, "pacotes/acervo/bruto/cvm-dfp/2024")]
    assert len(nomes) == 2 and all("-p" in n for n in nomes)


def test_pacote_que_falha_nao_vira_objeto_e_os_outros_sobem(
    mundo: emp.Configuracao,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FALHAR_EM", "bcb-sgs")
    assert emp.subir(mundo) == 1
    assert "FALHAS: pacotes-acervo-bruto" in capsys.readouterr().out
    assert not any("bcb-sgs" in str(p) for p in objetos(mundo, "pacotes"))
    assert "bruto/cvm-dfp/2024/a.bin.gz" in membros_do_drive(mundo)
    estado = emp.carregar_estado(mundo.estado)
    assert ("acervo-bruto", "bcb-sgs/2025/d.bin.gz") not in estado
    assert ("acervo-bruto", "cvm-dfp/2024/a.bin.gz") in estado
    monkeypatch.delenv("FALHAR_EM")
    assert emp.subir(mundo) == 0  # a próxima rodada completa o que faltou
    assert any("bcb-sgs" in str(p) for p in objetos(mundo, "pacotes"))


def test_cota_do_google_passageira_refaz_o_pacote_sem_contar_falha(
    mundo: emp.Configuracao, monkeypatch: pytest.MonkeyPatch
) -> None:
    """403 de cota por minuto some em instantes: o envio é refeito e a rodada termina sem falha."""
    original = emp.enviar_tar
    tentativas: dict[str, int] = {}

    def instavel(cfg: emp.Configuracao, pacote: emp.Pacote, alvo_tar: str):
        tentativas[alvo_tar] = tentativas.get(alvo_tar, 0) + 1
        if tentativas[alvo_tar] < 3:
            raise RuntimeError("rclone rcat falhou (rateLimitExceeded)")
        return original(cfg, pacote, alvo_tar)

    monkeypatch.setattr(emp, "enviar_tar", instavel)
    assert emp.subir(mundo) == 0
    assert tentativas and all(n == 3 for n in tentativas.values())
    assert "bruto/cvm-dfp/2024/a.bin.gz" in membros_do_drive(mundo)


def test_cota_que_nao_passa_acaba_em_falha_depois_das_tentativas(
    mundo: emp.Configuracao,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chamadas: list[str] = []

    def sempre_falha(cfg: emp.Configuracao, pacote: emp.Pacote, alvo_tar: str):
        chamadas.append(alvo_tar)
        raise RuntimeError("rateLimitExceeded")

    monkeypatch.setattr(emp, "enviar_tar", sempre_falha)
    assert emp.subir(mundo) == 1
    assert "FALHAS:" in capsys.readouterr().out
    assert len(chamadas) % emp.TENTATIVAS_DO_PACOTE == 0 and chamadas
    assert not objetos(mundo, "pacotes")


def test_tar_completo_nunca_e_reenviado_quando_so_o_indice_falha(
    mundo: emp.Configuracao, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revisão cruzada P1-A: pacote já completo no Drive não é reescrito na nova tentativa do índice."""
    original_tar = emp.enviar_tar
    original_indice = emp.enviar_indice
    envios_do_tar: dict[str, int] = {}
    falhas_do_indice: dict[str, int] = {}

    def conta_tar(cfg: emp.Configuracao, pacote: emp.Pacote, alvo_tar: str):
        envios_do_tar[alvo_tar] = envios_do_tar.get(alvo_tar, 0) + 1
        return original_tar(cfg, pacote, alvo_tar)

    def indice_instavel(cfg: emp.Configuracao, alvo_indice: str, indice: bytes) -> None:
        falhas_do_indice[alvo_indice] = falhas_do_indice.get(alvo_indice, 0) + 1
        if falhas_do_indice[alvo_indice] < 3:
            raise RuntimeError("rclone rcat falhou no índice (rateLimitExceeded)")
        original_indice(cfg, alvo_indice, indice)

    monkeypatch.setattr(emp, "enviar_tar", conta_tar)
    monkeypatch.setattr(emp, "enviar_indice", indice_instavel)
    assert emp.subir(mundo) == 0
    assert envios_do_tar and all(n == 1 for n in envios_do_tar.values())
    assert all(n == 3 for n in falhas_do_indice.values())


def test_conferencia_ignora_indice_cortado_e_avisa(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    """Revisão cruzada P1-B: um índice cortado (envio interrompido) não derruba a conferência inteira."""
    assert emp.subir(mundo) == 0
    indices = [p for p in objetos(mundo, "indices") if p.suffix == ".jsonl"]
    assert indices
    alvo = indices[0]
    linhas = alvo.read_text(encoding="utf-8").splitlines()
    cortado = chr(10).join([*linhas[:-1], linhas[-1][:10]])
    alvo.write_text(cortado, encoding="utf-8")
    emp.conferir(mundo)
    saida = capsys.readouterr().out
    assert "índice inválido" in saida


def test_erro_ao_montar_o_pacote_corta_o_envio_sem_deixar_objeto(
    mundo: emp.Configuracao,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def quebra(*_args: object, **_kwargs: object) -> None:
        raise OSError("arquivo sumiu")

    monkeypatch.setattr(emp, "montar_pacote", quebra)
    assert emp.subir(mundo) == 1
    assert "FALHAS:" in capsys.readouterr().out
    assert not objetos(mundo, "pacotes")
    assert not objetos(mundo, "indices")


def test_parte_vazia_nao_vira_tudo_certo(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    for arquivo in (mundo.acervo / "ancoras").iterdir():
        arquivo.unlink()
    assert emp.subir(mundo) == 1
    assert "pacotes-acervo-ancoras-vazia" in capsys.readouterr().out


def test_origem_que_falta_falha(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    mundo.partes = [emp.Parte("x", mundo.acervo, "nao-existe", "unico", "acervo/x")]
    assert emp.subir(mundo) == 1
    assert "FALHAS: pacotes-x" in capsys.readouterr().out


def test_simular_nao_sobe_nada(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    assert emp.subir(mundo, simular=True) == 0
    assert "cvm-dfp" in capsys.readouterr().out
    assert not objetos(mundo, "pacotes")


def test_conferencia_passa_e_acusa_falta_de_arquivo_e_de_pacote(
    mundo: emp.Configuracao,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    emp.subir(mundo)
    mundo.min_idade = 300
    assert emp.conferir(mundo) == 0
    assert "tudo certo" in capsys.readouterr().out
    velho = time.time() - 3600
    extra = mundo.acervo / "bruto/bcb-sgs/2025/e.bin.gz"
    extra.write_bytes(b"E")
    os.utime(extra, (velho, velho))
    assert emp.conferir(mundo) == 1
    assert "ausentes no Drive: 1" in capsys.readouterr().out
    extra.unlink()
    objetos(mundo, "pacotes")[0].unlink()
    assert emp.conferir(mundo) == 1
    assert "pacotes com tamanho errado ou ausentes: 1" in capsys.readouterr().out


def test_indice_aceita_nome_de_arquivo_que_nao_e_utf8() -> None:
    """Nome em latin-1 (zip antigo) chega como texto com `surrogateescape`: o índice não pode estourar."""
    nome = b"bruto/fonte/2019/caf\xe9.csv".decode("utf-8", "surrogateescape")
    linha = emp.json_linha({"p": nome, "b": 1})
    linha.encode("utf-8")
    assert json.loads(linha)["p"] == nome
    assert (
        emp.json_linha({"p": "café.csv"}) == '{"p": "café.csv"}'
    )  # nome normal segue legível


@pytest.mark.skipif(sys.platform == "win32", reason="nome em bytes só existe no Linux")
def test_pacote_com_nome_nao_utf8_sobe_uma_vez_so(mundo: emp.Configuracao) -> None:
    estranho = os.fsencode(mundo.acervo) + b"/bruto/bcb-sgs/2025/caf\xe9.bin.gz"
    with open(estranho, "wb") as f:
        f.write(b"Z" * 10)
    os.utime(estranho, (time.time() - 86400,) * 2)
    assert emp.subir(mundo) == 0
    assert emp.subir(mundo) == 0
    assert len(objetos(mundo, "pacotes")) == len(objetos(mundo, "indices"))
    antes = len(objetos(mundo, "pacotes"))
    assert emp.subir(mundo) == 0
    assert len(objetos(mundo, "pacotes")) == antes  # não sobe de novo todo dia


def test_conferencia_avisa_pacote_sem_indice_sem_apagar_nada(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    emp.subir(mundo)
    orfao = objetos(mundo, "pacotes")[0].parent / "2000-01-01_000000.tar"
    orfao.write_bytes(b"cortado")
    emp.conferir(mundo)
    assert "sem índice no Drive" in capsys.readouterr().out
    assert orfao.exists()


def test_sigterm_derruba_o_envio_em_andamento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O handler mata os `rclone rcat` ativos antes de sair, para um `.tar` cortado não virar objeto completo."""
    mortos: list[str] = []

    class Envio:
        def kill(self) -> None:
            mortos.append("rcat")

    saidas: list[int] = []
    monkeypatch.setattr(emp.os, "_exit", saidas.append)
    monkeypatch.setattr(emp, "ENVIOS_ATIVOS", {Envio()})
    emp._encerrar_com_sigterm(15, None)
    assert mortos == ["rcat"] and saidas == [143]


def test_conferencia_com_origem_vazia_nao_passa(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    mundo.partes = [
        emp.Parte("vazia", mundo.acervo, "ancoras", "unico", "acervo/ancoras")
    ]
    for arquivo in (mundo.acervo / "ancoras").iterdir():
        arquivo.unlink()
    assert emp.conferir(mundo) == 1
    assert "origem-vazia" in capsys.readouterr().out


def test_leitura_completa_acha_adulteracao_no_drive(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    emp.subir(mundo)
    assert emp.conferir(mundo, completo=True) == 0
    assert "0 com problema" in capsys.readouterr().out
    alvo = next(p for p in objetos(mundo, "pacotes/acervo/bruto/cvm-dfp/2024"))
    dados = bytearray(alvo.read_bytes())
    dados[600] ^= 0xFF  # um bit virado dentro do conteúdo de um arquivo
    alvo.write_bytes(bytes(dados))
    assert emp.conferir(mundo, completo=True) == 1
    saida = capsys.readouterr().out
    assert "não bate" in saida and "FALHAS" in saida


def test_leitura_completa_acha_mudanca_na_origem(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib

    emp.subir(mundo)
    capsys.readouterr()
    arquivo = mundo.acervo / "bruto/bcb-sgs/2025/d.bin.gz"
    estado = arquivo.stat()
    arquivo.write_bytes(
        b"Z" * estado.st_size
    )  # mesmo tamanho e mesma data, conteúdo outro
    os.utime(arquivo, ns=(estado.st_atime_ns, estado.st_mtime_ns))
    assert (
        hashlib.sha256(arquivo.read_bytes()).hexdigest()
        != hashlib.sha256(b"D" * 500).hexdigest()
    )
    assert emp.conferir(mundo, completo=True) == 1
    assert "a origem não bate" in capsys.readouterr().out


def test_amostra_restaura_pacotes_e_arquivos_avulsos(
    mundo: emp.Configuracao, capsys: pytest.CaptureFixture[str]
) -> None:
    emp.subir(mundo)
    assert emp.amostra(mundo, pacotes_na_amostra=3) == 0
    saida = capsys.readouterr().out
    assert "conferidos por sha256; 0 com problema" in saida
    alvo = next(p for p in objetos(mundo, "pacotes/acervo/bruto/bcb-sgs/2025"))
    dados = bytearray(alvo.read_bytes())
    dados[600] ^= 0xFF
    alvo.write_bytes(bytes(dados))
    assert emp.amostra(mundo, pacotes_na_amostra=20) == 1


def test_estado_se_refaz_dos_indices_do_drive(mundo: emp.Configuracao) -> None:
    emp.subir(mundo)
    original = emp.carregar_estado(mundo.estado)
    assert emp.reconstruir_estado(mundo) == 0
    refeito = emp.carregar_estado(mundo.estado.with_suffix(".reconstruido"))
    assert refeito == original
    assert len(original) == 9


def test_nenhum_comando_destrutivo_no_codigo() -> None:
    codigo = (Path(emp.__file__)).read_text(encoding="utf-8")
    for proibido in (
        '"sync"',
        '"delete"',
        '"deletefile"',
        '"purge"',
        '"move"',
        '"moveto"',
        '"dedupe"',
        '"cleanup"',
    ):
        assert proibido not in codigo, proibido
