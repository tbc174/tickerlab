"""Regras do `AGENTS.md` que eram só texto e passam a ter teste (plano de agentes, Fase C, item C1).

Cada teste cita a regra que guarda. Eles só leem o repositório (código, migrações, documentos e o que o Git
versiona): nenhum muda comportamento do app. O mapa de qual regra tem qual trava está em
`docs/travas-do-livro-de-regras.md`; regra nova com teste entra lá também.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _arquivos_python(*pastas: str) -> list[Path]:
    """Os `.py` das pastas, sem caches."""
    return sorted(
        caminho
        for pasta in pastas
        for caminho in (RAIZ / pasta).rglob("*.py")
        if "__pycache__" not in caminho.parts
    )


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))


def _relativo(caminho: Path) -> str:
    return caminho.relative_to(RAIZ).as_posix()


def _git(*argumentos: str) -> str:
    """Saída de um comando do Git na raiz do repositório (sem Git, o teste é pulado)."""
    comando = ["git", "-C", str(RAIZ), "-c", "core.quotepath=off", *argumentos]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        pytest.skip(f"sem git: {erro}")
    # o git grep sai com 1 quando não acha nada: isso é o resultado esperado, não erro
    if resultado.returncode not in (0, 1):
        pytest.skip(f"git falhou: {resultado.stderr.strip()[:200]}")
    return resultado.stdout


# --- "src/ não importa o Streamlit" (Arquitetura) ----------------------------------------------------


def _modulos_importados(arvore: ast.Module) -> set[str]:
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(apelido.name for apelido in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.add(no.module)
        elif (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "import_module"
            and no.args
            and isinstance(no.args[0], ast.Constant)
            and isinstance(no.args[0].value, str)
        ):
            nomes.add(no.args[0].value)
    return nomes


def test_src_nao_importa_o_streamlit() -> None:
    """As contas, regras e dados ficam em `src/`; a cola com o Streamlit fica em `telas/`."""
    culpados = [
        _relativo(caminho)
        for caminho in _arquivos_python("src")
        if any(
            nome == "streamlit" or nome.startswith("streamlit.")
            for nome in _modulos_importados(_arvore(caminho))
        )
    ]
    assert not culpados, (
        f"src/ importou o Streamlit em {culpados}. Leve a parte da tela para telas/ e deixe a regra em src/."
    )


def test_a_conferencia_do_streamlit_acha_os_jeitos_de_importar() -> None:
    codigo = (
        "import streamlit as st\n"
        "from streamlit.testing.v1 import AppTest\n"
        "import importlib\nimportlib.import_module('streamlit')\n"
    )
    assert _modulos_importados(ast.parse(codigo)) >= {
        "streamlit",
        "streamlit.testing.v1",
    }


# --- "Nenhum estado mutável num módulo de telas/" (Arquitetura) ---------------------------------------

METODOS_QUE_MUDAM = frozenset(
    {
        "append",
        "extend",
        "insert",
        "add",
        "update",
        "setdefault",
        "pop",
        "popitem",
        "remove",
        "discard",
        "clear",
    }
)
CONSTRUTORES_MUTAVEIS = frozenset(
    {"list", "dict", "set", "defaultdict", "deque", "OrderedDict", "Counter"}
)


def _nomes_mutaveis_do_modulo(arvore: ast.Module) -> set[str]:
    """Nomes do topo do módulo ligados a lista, dicionário ou conjunto."""
    nomes: set[str] = set()
    for no in arvore.body:
        if isinstance(no, ast.Assign):
            alvos, valor = no.targets, no.value
        elif isinstance(no, ast.AnnAssign) and no.value is not None:
            alvos, valor = [no.target], no.value
        else:
            continue
        mutavel = isinstance(valor, (ast.List, ast.Dict, ast.Set)) or (
            isinstance(valor, ast.Call)
            and isinstance(valor.func, ast.Name)
            and valor.func.id in CONSTRUTORES_MUTAVEIS
        )
        if mutavel:
            nomes.update(alvo.id for alvo in alvos if isinstance(alvo, ast.Name))
    return nomes


def _mudancas_de_estado_do_modulo(arvore: ast.Module) -> list[str]:
    """Onde uma função do módulo muda estado do próprio módulo (o que valeria para todos os usuários)."""
    mutaveis = _nomes_mutaveis_do_modulo(arvore)
    achados: list[str] = []
    funcoes = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for funcao in funcoes:
        for no in ast.walk(funcao):
            if isinstance(no, ast.Global):
                achados.append(f"linha {no.lineno}: global {', '.join(no.names)}")
            elif (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr in METODOS_QUE_MUDAM
                and isinstance(no.func.value, ast.Name)
                and no.func.value.id in mutaveis
            ):
                achados.append(
                    f"linha {no.lineno}: {no.func.value.id}.{no.func.attr}()"
                )
            elif isinstance(no, (ast.Assign, ast.AugAssign, ast.Delete)):
                alvos = (
                    no.targets
                    if isinstance(no, (ast.Assign, ast.Delete))
                    else [no.target]
                )
                achados.extend(
                    f"linha {no.lineno}: {alvo.value.id}[...]"
                    for alvo in alvos
                    if isinstance(alvo, ast.Subscript)
                    and isinstance(alvo.value, ast.Name)
                    and alvo.value.id in mutaveis
                )
    return achados


def test_telas_nao_guardam_estado_no_modulo() -> None:
    """O módulo importado roda uma vez por processo: a variável dele seria de todos os usuários."""
    achados = {
        _relativo(caminho): mudancas
        for caminho in _arquivos_python("telas")
        if (mudancas := _mudancas_de_estado_do_modulo(_arvore(caminho)))
    }
    assert not achados, (
        f"função de telas/ mudando estado do módulo: {achados}. Estado de usuário vai no "
        "st.session_state; o que importa, no banco."
    )


def test_a_conferencia_do_estado_acha_global_e_mudanca_de_lista() -> None:
    codigo = (
        "VISTOS = []\nCACHE: dict = {}\nCONTADOR = 0\n"
        "def f():\n    global CONTADOR\n    CONTADOR += 1\n    VISTOS.append(1)\n    CACHE['a'] = 1\n"
        "def g():\n    local = []\n    local.append(1)\n"
    )
    achados = _mudancas_de_estado_do_modulo(ast.parse(codigo))
    assert len(achados) == 3
    assert any("global CONTADOR" in achado for achado in achados)


# --- "hide_parameters=True" (Banco: erros do banco não levam e-mails para os logs) --------------------


def _chamadas_de_create_engine(arvore: ast.Module) -> list[ast.Call]:
    return [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and (
            (isinstance(no.func, ast.Attribute) and no.func.attr == "create_engine")
            or (isinstance(no.func, ast.Name) and no.func.id == "create_engine")
        )
    ]


def _esconde_os_valores(chamada: ast.Call) -> bool:
    return any(
        palavra.arg == "hide_parameters"
        and isinstance(palavra.value, ast.Constant)
        and palavra.value.value is True
        for palavra in chamada.keywords
    )


def test_toda_engine_do_codigo_esconde_os_valores_das_consultas() -> None:
    pastas = ("src", "base", "scripts", "telas", "cli", "conector_remoto", "migracoes")
    sem_trava = [
        f"{_relativo(caminho)}:{chamada.lineno}"
        for caminho in _arquivos_python(*pastas)
        for chamada in _chamadas_de_create_engine(_arvore(caminho))
        if not _esconde_os_valores(chamada)
    ]
    assert not sem_trava, (
        f"create_engine sem hide_parameters=True em {sem_trava}: o erro do banco citaria e-mails e nomes. "
        "Use src.banco.conexao.criar_engine."
    )


def test_a_engine_do_app_esconde_os_valores() -> None:
    from src.banco.conexao import criar_engine

    motor = criar_engine("sqlite://")
    try:
        assert motor.hide_parameters is True
    finally:
        motor.dispose()


# --- Migrações: "numeração seguida" e "caminho de volta (downgrade)" ------------------------------------

PASTA_DAS_MIGRACOES = RAIZ / "migracoes" / "versions"
# Números que ficaram sem arquivo antes desta trava (25/11/2026). Buraco novo falha.
NUMEROS_QUE_JA_FALTAVAM = frozenset({33, 38})


def _valor_do_topo(arvore: ast.Module, nome: str) -> object:
    for no in arvore.body:
        alvo = None
        if isinstance(no, ast.Assign) and len(no.targets) == 1:
            alvo, valor = no.targets[0], no.value
        elif isinstance(no, ast.AnnAssign) and no.value is not None:
            alvo, valor = no.target, no.value
        if isinstance(alvo, ast.Name) and alvo.id == nome:
            return ast.literal_eval(valor)
    raise AssertionError(f"sem {nome} no topo")


def _migracoes() -> list[tuple[int, Path, ast.Module]]:
    lista = []
    for caminho in sorted(PASTA_DAS_MIGRACOES.glob("*.py")):
        numero = re.match(r"(\d{4})_", caminho.name)
        assert numero, (
            f"migração sem número de 4 dígitos no começo do nome: {caminho.name}"
        )
        lista.append((int(numero.group(1)), caminho, _arvore(caminho)))
    return lista


def test_migracoes_numeradas_em_fila_sem_buraco_novo() -> None:
    numeros = [numero for numero, _, _ in _migracoes()]
    assert len(numeros) == len(set(numeros)), (
        "dois arquivos de migração com o mesmo número"
    )
    faltam = set(range(1, max(numeros) + 1)) - set(numeros)
    assert faltam == NUMEROS_QUE_JA_FALTAVAM, (
        f"números sem migração: {sorted(faltam)}. Use o próximo número (reservado no quadro de sessões)."
    )


def test_as_migracoes_formam_uma_fila_so_sem_ramo() -> None:
    """Uma raiz, uma cabeça, e cada migração com uma só seguinte (a ordem da fila pode não ser a do número)."""
    para_tras: dict[str, str | None] = {}
    for numero, caminho, arvore in _migracoes():
        revisao = _valor_do_topo(arvore, "revision")
        assert revisao == f"{numero:04d}", f"{caminho.name}: revision {revisao!r}"
        anterior = _valor_do_topo(arvore, "down_revision")
        assert anterior is None or isinstance(anterior, str), (
            f"{caminho.name}: down_revision {anterior!r} (migração que junta ramos)"
        )
        para_tras[revisao] = anterior
    raizes = [revisao for revisao, anterior in para_tras.items() if anterior is None]
    assert len(raizes) == 1, f"mais de uma migração sem anterior: {raizes}"
    seguintes: dict[str, str] = {}
    for revisao, anterior in para_tras.items():
        if anterior is None:
            continue
        assert anterior in para_tras, (
            f"{revisao} aponta para {anterior}, que não existe"
        )
        assert anterior not in seguintes, (
            f"{anterior} tem duas seguintes ({seguintes[anterior]} e {revisao}): duas cabeças"
        )
        seguintes[anterior] = revisao
    fila = [raizes[0]]
    while fila[-1] in seguintes:
        fila.append(seguintes[fila[-1]])
    assert len(fila) == len(para_tras), "há migração fora da fila que sai da primeira"


def test_toda_migracao_tem_caminho_de_volta() -> None:
    sem_volta = []
    for _, caminho, arvore in _migracoes():
        funcoes = [
            no
            for no in arvore.body
            if isinstance(no, ast.FunctionDef) and no.name == "downgrade"
        ]
        corpo = [
            comando
            for funcao in funcoes
            for comando in funcao.body
            if not (
                isinstance(comando, ast.Expr)
                and isinstance(comando.value, ast.Constant)
            )
        ]
        if not corpo or all(isinstance(comando, ast.Pass) for comando in corpo):
            sem_volta.append(caminho.name)
    assert not sem_volta, f"migração sem downgrade de verdade: {sem_volta}"


# --- trader: "as versões anteriores do pré-registro não se editam" -------------------------------------

# SHA-256 com quebras de linha normalizadas para \n (como em trader/holdout.py::hash_do_texto). A v0.4 é
# conferida por trader/holdout.py e a quant por trader/criterio_quant.py; estas três só tinham o começo do
# hash num comentário de trader/holdout.py.
PRE_REGISTROS_CONGELADOS = {
    "pre-registro-m2-v0.1.md": "b8074c37ae92cb4542965d1c2285f3d31f9751f5f3cb6758497d7baa07f32e98",
    "pre-registro-m2-v0.2.md": "8d72f930aa4f405160fcea545aa544550ab971b4e28003fa0bc0e7ccd60ff24c",
    "pre-registro-m2-v0.3.md": "0c10de649d4c17a2bead1583a4b3094093f665b37f7f92f55812d203d251acf1",
}


@pytest.mark.parametrize("arquivo", sorted(PRE_REGISTROS_CONGELADOS))
def test_pre_registro_antigo_da_m2_continua_igual(arquivo: str) -> None:
    texto = (RAIZ / "docs" / arquivo).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(texto).hexdigest() == PRE_REGISTROS_CONGELADOS[arquivo], (
        f"{arquivo} mudou. Versão superada não se edita, nem para avisar (trader/AGENTS.md, regra 2)."
    )


def test_o_comentario_do_holdout_cita_os_mesmos_hashes() -> None:
    comentario = (RAIZ / "trader" / "holdout.py").read_text(encoding="utf-8")
    for arquivo, esperado in PRE_REGISTROS_CONGELADOS.items():
        versao = re.search(r"v0\.\d", arquivo)
        assert versao
        assert f"{versao.group(0)} ({esperado[:8]}" in comentario, arquivo


# --- "não adicionar LICENSE nem dependência GPL/AGPL" (Segurança e privacidade) ----------------------


def _licencas_proibidas(texto: str) -> bool:
    """GPL ou AGPL sem a opção LGPL ao lado (a LGPL e a dupla 'LGPL OR GPL' são permitidas)."""
    if re.search(r"LGPL|Lesser General Public", texto):
        return False
    return bool(re.search(r"(?<![A-Za-z])A?GPL|GNU (Affero )?General Public", texto))


def test_a_regra_da_licenca_separa_gpl_de_lgpl() -> None:
    assert _licencas_proibidas("GPL-3.0-only")
    assert _licencas_proibidas("AGPL-3.0-or-later")
    assert _licencas_proibidas(
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"
    )
    assert not _licencas_proibidas("LGPL-3.0-only")
    assert not _licencas_proibidas("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only")
    assert not _licencas_proibidas("MIT")


def test_nenhuma_biblioteca_instalada_e_gpl() -> None:
    """Vale para o que o CI instala (requirements*.txt e o que eles puxam)."""
    proibidas = []
    for distribuicao in importlib.metadata.distributions():
        dados = distribuicao.metadata
        texto = " ".join(
            [
                dados.get("License-Expression") or "",
                (dados.get("License") or "")[:300],
                *[
                    classificador
                    for classificador in (dados.get_all("Classifier") or [])
                    if classificador.startswith("License")
                ],
            ]
        )
        if _licencas_proibidas(texto):
            proibidas.append(dados.get("Name"))
    assert not proibidas, (
        f"biblioteca GPL/AGPL instalada: {sorted(set(map(str, proibidas)))}. O repositório não tem licença "
        "aberta; troque a biblioteca."
    )


def test_repositorio_sem_arquivo_de_licenca_aberta() -> None:
    arquivos = _git("ls-files").splitlines()
    licencas = [
        caminho
        for caminho in arquivos
        if re.fullmatch(
            r"(LICEN[CS]E|COPYING)(\.[A-Za-z]+)?", Path(caminho).name, re.IGNORECASE
        )
    ]
    assert not licencas, (
        f"arquivo de licença no repositório: {licencas} (todos os direitos reservados)"
    )
    pacote = json.loads((RAIZ / "web" / "package.json").read_text(encoding="utf-8"))
    assert pacote.get("license") == "UNLICENSED"
    assert pacote.get("private") is True


# --- "Segredos só em .env e .streamlit/secrets.toml (fora do Git)" e "nada de e-mail em código, log ou teste"

NOMES_DE_SEGREDO = re.compile(
    r"(^|/)(\.env|secrets\.toml|credentials\.json|oauth_creds\.json|auth\.json|id_(rsa|ed25519|ecdsa))$"
    r"|\.(pfx|p12|age|key|keystore)$",
    re.IGNORECASE,
)
# Certificados públicos de autoridades (a cadeia que algumas fontes do governo não mandam).
PASTA_DOS_CERTIFICADOS_PUBLICOS = "base/arquivo/certificados/"


def test_nenhum_arquivo_de_segredo_no_git() -> None:
    arquivos = _git("ls-files").splitlines()
    suspeitos = [caminho for caminho in arquivos if NOMES_DE_SEGREDO.search(caminho)]
    pem_fora = [
        caminho
        for caminho in arquivos
        if caminho.lower().endswith(".pem")
        and not caminho.startswith(PASTA_DOS_CERTIFICADOS_PUBLICOS)
    ]
    assert not suspeitos and not pem_fora, (
        f"arquivo com cara de segredo versionado: {suspeitos + pem_fora}. Tire do Git (git rm --cached) "
        "e ponha no .gitignore; se for um certificado público, guarde em "
        f"{PASTA_DOS_CERTIFICADOS_PUBLICOS}."
    )


def test_a_lista_de_segredos_pega_os_nomes_comuns() -> None:
    for caminho in (
        ".env",
        "app/.env",
        ".streamlit/secrets.toml",
        "x/chave.pfx",
        "cofre.age",
    ):
        assert NOMES_DE_SEGREDO.search(caminho), caminho
    for caminho in (
        ".env.example",
        ".streamlit/secrets.toml.example",
        "docs/chaves.md",
    ):
        assert not NOMES_DE_SEGREDO.search(caminho), caminho


PROVEDORES_DE_EMAIL_PESSOAL = (
    "gmail",
    "googlemail",
    "hotmail",
    "outlook",
    "live",
    "msn",
    "yahoo",
    "icloud",
    "me",
    "uol",
    "bol",
    "terra",
    "ig",
    "protonmail",
    "proton",
)
# Nomes claramente inventados, que os testes usam para conferir que o e-mail é recusado ou escondido.
NOMES_INVENTADOS = frozenset(
    {"fulano", "ciclano", "beltrano", "exemplo", "teste", "usuario", "alguem", "nome"}
)
_EMAIL_PESSOAL = re.compile(
    r"([A-Za-z0-9._%+-]+)@(?:"
    + "|".join(PROVEDORES_DE_EMAIL_PESSOAL)
    + r")\.com(?:\.br)?\b",
    re.IGNORECASE,
)


def _emails_pessoais(texto: str) -> list[str]:
    return [
        achado.group(1)
        for achado in _EMAIL_PESSOAL.finditer(texto)
        if achado.group(1).lower() not in NOMES_INVENTADOS
    ]


def test_a_varredura_de_email_separa_o_inventado_do_real() -> None:
    # montados na hora: escritos por inteiro, a própria varredura acharia este arquivo
    arroba = "@"
    assert _emails_pessoais(f"contato: maria.silva{arroba}gmail.com") == ["maria.silva"]
    assert _emails_pessoais(f"x{arroba}hotmail.com.br e y{arroba}uol.com.br") == [
        "x",
        "y",
    ]
    assert not _emails_pessoais(
        "Fulano@gmail.com, teste@exemplo.com, ana@empresa.com.br"
    )


def test_nenhum_email_pessoal_versionado() -> None:
    """O repositório é público. A mensagem diz o arquivo e a linha, nunca o endereço."""
    padrao = r"@(" + "|".join(PROVEDORES_DE_EMAIL_PESSOAL) + r")\.com"
    saida = _git("grep", "-I", "-n", "-i", "-E", padrao)
    achados = []
    for linha in saida.splitlines():
        arquivo, numero, texto = linha.split(":", 2)
        if _emails_pessoais(texto):
            achados.append(f"{arquivo}:{numero}")
    assert not achados, (
        f"e-mail pessoal versionado em {achados}. Troque por um nome inventado (fulano@...) ou por "
        "@exemplo.com."
    )
