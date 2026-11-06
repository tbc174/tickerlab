"""A entrega preserva aprovação, proveniência e a fotografia anterior se houver falha."""

import hashlib
import io
import json
import tarfile

import pytest

from scripts import transferir_analises as entrega

CNPJ = "12345678000190"


def gravar(pasta, nome, valor):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")


def preparar(tmp_path):
    entrada = {"cnpj": "12.345.678/0001-90", "corte": "2026-10-18", "linhas": []}
    texto = json.dumps(
        entrada, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    analise = {
        "cnpj": entrada["cnpj"],
        "publicavel": True,
        "hash_da_entrada_atual": hashlib.sha256(texto.encode()).hexdigest(),
        "analise": {"partes": []},
        "linhagem": {"porta3": {"veredito": "aprovado"}},
        "graficos": {"escolha": {"graficos": []}},
    }
    origem, entradas = tmp_path / "origem", tmp_path / "entradas"
    gravar(origem, f"{CNPJ}.json", analise)
    gravar(entradas / "leva-1", f"{CNPJ}.json", entrada)
    return origem, entradas, analise


def arquivos(pacote):
    with tarfile.open(fileobj=io.BytesIO(pacote)) as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers()}


def tar_de(conteudos):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for nome, texto in conteudos.items():
            info = tarfile.TarInfo(nome)
            info.size = len(texto)
            tar.addfile(info, io.BytesIO(texto))
    return buffer.getvalue()


def test_entrega_so_aprovada_recupera_corte_pelo_hash_e_preserva_original(tmp_path):
    origem, entradas, analise = preparar(tmp_path)
    gravar(origem, "99887766000110.json", {"publicavel": False})
    conteudos = arquivos(entrega.empacotar(origem, entradas))
    assert set(conteudos) == {f"{CNPJ}.json", "manifesto.json"}
    publicada = json.loads(conteudos[f"{CNPJ}.json"])
    entrada = json.loads((entradas / "leva-1" / f"{CNPJ}.json").read_text())
    assert publicada == {**analise, "corte": "2026-10-18", "entrada_aprovada": entrada}
    assert "corte" not in json.loads((origem / f"{CNPJ}.json").read_text())


def test_nao_adivinha_corte_quando_hash_nao_bate(tmp_path):
    origem, entradas, _ = preparar(tmp_path)
    gravar(entradas / "leva-1", f"{CNPJ}.json", {"corte": "2026-10-19"})
    with pytest.raises(ValueError, match="entrada original"):
        entrega.empacotar(origem, entradas)


def test_mesmo_com_corte_exige_a_entrada_original(tmp_path):
    origem, entradas, analise = preparar(tmp_path)
    analise["corte"] = "2026-10-18"
    gravar(origem, f"{CNPJ}.json", analise)
    gravar(entradas / "leva-1", f"{CNPJ}.json", {"corte": "2026-10-19"})
    with pytest.raises(ValueError, match="entrada original"):
        entrega.empacotar(origem, entradas)


@pytest.mark.parametrize("defeito", ["hash", "cnpj", "corte"])
def test_recebedor_recusa_fotografia_incompativel_mesmo_com_manifesto_valido(
    tmp_path, defeito
):
    origem, entradas, _ = preparar(tmp_path)
    conteudos = arquivos(entrega.empacotar(origem, entradas))
    nome = f"{CNPJ}.json"
    analise = json.loads(conteudos[nome])
    entrada = analise["entrada_aprovada"]
    if defeito == "corte":
        analise["corte"] = "2026-10-19"
    else:
        entrada["cnpj"] = "99.887.766/0001-10"
        if defeito == "cnpj":
            bruto = json.dumps(
                entrada, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
            analise["hash_da_entrada_atual"] = hashlib.sha256(bruto).hexdigest()
    conteudos[nome] = json.dumps(analise).encode()
    manifesto = json.loads(conteudos["manifesto.json"])
    manifesto["arquivos"][nome] = hashlib.sha256(conteudos[nome]).hexdigest()
    conteudos["manifesto.json"] = json.dumps(manifesto).encode()
    dados = tmp_path / "dados"
    with pytest.raises(ValueError, match="entrada original"):
        entrega.instalar(tar_de(conteudos), dados)
    assert not dados.exists()


def test_nao_aceita_marca_publicavel_sem_aprovacao(tmp_path):
    origem, entradas, analise = preparar(tmp_path)
    analise["linhagem"]["porta3"]["veredito"] = "numero_errado"
    gravar(origem, f"{CNPJ}.json", analise)
    with pytest.raises(ValueError, match="aprovação"):
        entrega.empacotar(origem, entradas)


@pytest.mark.skipif(__import__("os").name == "nt", reason="o recebedor roda no Linux")
def test_instala_atomica_idempotente_e_retira_aprovacao_revogada(tmp_path):
    origem, entradas, analise = preparar(tmp_path)
    pacote = entrega.empacotar(origem, entradas)
    dados = tmp_path / "dados"
    entrega.instalar(pacote, dados)
    atual = dados / "analises"
    anterior = atual.resolve()
    assert json.loads((atual / f"{CNPJ}.json").read_text())["publicavel"] is True
    entrega.instalar(pacote, dados)
    assert atual.resolve() == anterior
    analise["publicavel"] = False
    gravar(origem, f"{CNPJ}.json", analise)
    entrega.instalar(entrega.empacotar(origem, entradas), dados)
    assert not (atual / f"{CNPJ}.json").exists()
    assert (anterior / f"{CNPJ}.json").exists()


@pytest.mark.parametrize(
    "defeito", ["caminho", "hash", "reprovada", "duplicado", "link"]
)
def test_recusa_pacote_ruim_sem_tocar_no_destino(tmp_path, defeito):
    origem, entradas, _ = preparar(tmp_path)
    conteudos = arquivos(entrega.empacotar(origem, entradas))
    if defeito == "caminho":
        conteudos["../escape.json"] = b"{}"
    elif defeito == "hash":
        conteudos[f"{CNPJ}.json"] += b" "
    elif defeito == "reprovada":
        analise = json.loads(conteudos[f"{CNPJ}.json"])
        analise["publicavel"] = False
        conteudos[f"{CNPJ}.json"] = json.dumps(analise).encode()
        manifesto = json.loads(conteudos["manifesto.json"])
        manifesto["arquivos"][f"{CNPJ}.json"] = hashlib.sha256(
            conteudos[f"{CNPJ}.json"]
        ).hexdigest()
        conteudos["manifesto.json"] = json.dumps(manifesto).encode()
    pacote = tar_de(conteudos)
    if defeito in ("duplicado", "link"):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            for _ in range(2 if defeito == "duplicado" else 1):
                info = tarfile.TarInfo(f"{CNPJ}.json")
                if defeito == "link":
                    info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                tar.addfile(info)
        pacote = buffer.getvalue()
    dados = tmp_path / "dados"
    dados.mkdir()
    sentinel = dados / "preservar"
    sentinel.write_text("anterior")
    with pytest.raises(ValueError):
        entrega.instalar(pacote, dados)
    assert list(dados.iterdir()) == [sentinel]


def test_origem_inexistente_nao_revoga_tudo(tmp_path):
    with pytest.raises(ValueError, match="origem"):
        entrega.empacotar(tmp_path / "ausente", tmp_path)
