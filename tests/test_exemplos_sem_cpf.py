"""Os arquivos de exemplo e de teste não guardam CPF válido (LGPD; repositório público; linha 885 da fila).

Os dublês podem ter cara de CPF de propósito: é assim que os leitores provam que descartam a pessoa física
(mascarado, formatado ou inteiro). Mas o número não pode ter o dígito verificador certo, porque aí ele pode ser
o CPF de alguém de verdade. O teste varre `dados_de_exemplo/` e `tests/arquivos/` (também dentro de `.zip` e
`.gz`, e as colunas de `.parquet` e `.xlsx`) com duas regras escolhidas para não dar alarme falso:

1. **CPF formatado** (`999.999.999-99`) em qualquer lugar, com o dígito certo. Nenhum outro dado usa essa forma.
2. **11 dígitos seguidos** (com ou sem pontuação) com o dígito certo, **só em coluna ou chave de documento**
   (o nome tem "cpf", "cnpj", "identificacao", "documento" ou é o "niFornecedor" do PNCP). Um número solto de
   11 dígitos (código, telefone, processo) acerta o dígito por acaso uma vez em cerca de cem, e daria alarme
   falso; numa coluna de documento ele é um CPF (o CNPJ tem 14 dígitos; os dados abertos da CVM e do PNCP
   põem o CPF do devedor ou do fornecedor pessoa física na coluna do CNPJ).

3. **No código dos testes** (`tests/**/*.py`, linha 886 da fila): 11 dígitos em grupos de 3, 3, 3 e 2, com
   ou sem separador entre eles (até 3 caracteres como ponto, hífen, barra, espaço, travessão ou sublinhado, ou
   o `\\n` escrito no código), com o dígito certo, em qualquer lugar. O teste que precisa de um CPF que confere (máscara, detector de CPF no texto, trava de
   pessoa física) monta-o na hora com `tests/ajudantes_de_cpf.py`, a partir de nove dígitos inventados.
4. **CPF completado com zeros** no código dos testes: 14 dígitos seguidos que começam com "000" e cujos 11
   últimos conferem como CPF (é assim que o PIT do TCE e o SUS mandam o CPF). Se os 14 também conferem como
   CNPJ (o do Banco do Brasil começa com zeros), o número é tratado como CNPJ e não conta.

A mensagem de erro diz só o arquivo, a linha e a coluna, nunca o valor. Para consertar, troque os 11 dígitos
por uma sequência claramente inventada com o dígito que não confere (trocar só o último dígito não basta: os
dois dígitos verificadores saem dos nove primeiros, e quem lê refaz o CPF numa conta). O leitor continua
descartando a linha, porque a forma é a mesma.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from base.cnpj import cpf_confere, dv_confere

RAIZ = Path(__file__).resolve().parents[1]
PASTAS = (RAIZ / "dados_de_exemplo", RAIZ / "tests" / "arquivos")
TAMANHO_DO_CPF = 11
CPF_FORMATADO = re.compile(r"(?<![\d.])(\d{3}\.\d{3}\.\d{3}-\d{2})(?!\d)")
SEPARADORES = (";", ",", "\t", "|")
TEXTO = {
    ".csv",
    ".txt",
    ".tsv",
    ".json",
    ".geojson",
    ".html",
    ".xml",
    ".md",
    ".sgml",
    ".index",
}
TABELA_DE_TEXTO = {".csv", ".txt", ".tsv"}


def _so_digitos(valor: object) -> str:
    return re.sub(r"\D", "", str(valor))


def e_cpf_valido(valor: object) -> bool:
    """11 dígitos (a pontuação não conta) com o dígito verificador do CPF certo."""
    digitos = _so_digitos(valor)
    return len(digitos) == TAMANHO_DO_CPF and cpf_confere(digitos)


def _decodificar(conteudo: bytes) -> str:
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("latin-1")


COLUNA_DE_DOCUMENTO = ("cpf", "cnpj", "identificacao", "documento", "nifornecedor")


def _coluna_de_cpf(nome: object) -> bool:
    """Coluna ou chave onde um número de 11 dígitos é um CPF (ver a regra 2 acima)."""
    nome_minusculo = str(nome).lower()
    return any(pedaco in nome_minusculo for pedaco in COLUNA_DE_DOCUMENTO)


def _valor_de_cpf(valor: object) -> bool:
    texto = str(valor).strip()
    return bool(re.fullmatch(r"[\d.\-/ ]+", texto)) and e_cpf_valido(texto)


def achados_no_texto(nome: str, texto: str, sufixo: str) -> Iterator[str]:
    """Onde há CPF válido num arquivo de texto: 'arquivo:linha' ou 'arquivo:linha:coluna'."""
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if any(e_cpf_valido(m.group(1)) for m in CPF_FORMATADO.finditer(linha)):
            yield f"{nome}:{numero} (CPF formatado)"
    if sufixo in TABELA_DE_TEXTO:
        yield from _achados_na_tabela(nome, texto)
    elif sufixo in {".json", ".geojson"}:
        yield from _achados_no_json(nome, texto)


def _achados_na_tabela(nome: str, texto: str) -> Iterator[str]:
    linhas = texto.splitlines()
    if not linhas:
        return
    separador = max(SEPARADORES, key=linhas[0].count)
    leitor = csv.reader(linhas, delimiter=separador)
    cabecalho = next(leitor, [])
    colunas = [i for i, coluna in enumerate(cabecalho) if _coluna_de_cpf(coluna)]
    for numero, campos in enumerate(leitor, start=2):
        for i in colunas:
            if i < len(campos) and _valor_de_cpf(campos[i]):
                yield f"{nome}:{numero}:{cabecalho[i]}"


def _achados_no_json(nome: str, texto: str) -> Iterator[str]:
    try:
        dado = json.loads(texto)
    except ValueError:
        return
    pilha: list[tuple[str, object]] = [("", dado)]
    while pilha:
        caminho, valor = pilha.pop()
        if isinstance(valor, dict):
            pilha.extend(
                (f"{caminho}/{chave}", filho) for chave, filho in valor.items()
            )
        elif isinstance(valor, list):
            pilha.extend((f"{caminho}[{i}]", filho) for i, filho in enumerate(valor))
        elif _coluna_de_cpf(caminho.rsplit("/", 1)[-1]) and _valor_de_cpf(valor):
            yield f"{nome}:{caminho}"


def achados_na_planilha(nome: str, tabela: pd.DataFrame) -> Iterator[str]:
    """CPF formatado em qualquer célula, ou 11 dígitos com o dígito certo em coluna de CPF."""
    nomes = [str(c) for c in tabela.columns]
    for numero, linha in enumerate(tabela.itertuples(index=False), start=1):
        for i, valor in enumerate(linha):
            formatado = any(
                e_cpf_valido(m.group(1)) for m in CPF_FORMATADO.finditer(str(valor))
            )
            if formatado or (_coluna_de_cpf(nomes[i]) and _valor_de_cpf(valor)):
                yield f"{nome}:linha {numero}:{nomes[i]}"


def _achados_no_arquivo(nome: str, sufixo: str, conteudo: bytes) -> Iterator[str]:
    if sufixo == ".zip":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            for membro in pacote.namelist():
                interno = Path(membro).suffix.lower()
                yield from _achados_no_arquivo(
                    f"{nome}!{membro}", interno, pacote.read(membro)
                )
    elif sufixo == ".gz":
        interno = Path(nome.removesuffix(".gz")).suffix.lower()
        yield from _achados_no_arquivo(
            nome, interno or ".txt", gzip.decompress(conteudo)
        )
    elif sufixo == ".parquet":
        yield from achados_na_planilha(nome, pd.read_parquet(io.BytesIO(conteudo)))
    elif sufixo == ".xlsx":
        folhas = pd.read_excel(io.BytesIO(conteudo), sheet_name=None, dtype=str)
        for folha, tabela in folhas.items():
            yield from achados_na_planilha(f"{nome}[{folha}]", tabela)
    elif sufixo in TEXTO:
        yield from achados_no_texto(nome, _decodificar(conteudo), sufixo)


def achados() -> list[str]:
    encontrados: list[str] = []
    for pasta in PASTAS:
        for arquivo in sorted(pasta.rglob("*")):
            if arquivo.is_file():
                nome = arquivo.relative_to(RAIZ).as_posix()
                encontrados.extend(
                    _achados_no_arquivo(
                        nome, arquivo.suffix.lower(), arquivo.read_bytes()
                    )
                )
    return encontrados


PASTA_DOS_TESTES = RAIZ / "tests"
# entre os grupos: nada, "\n" escrito no código, ou até 3 caracteres que não são letra, dígito, vírgula, aspas
# nem parênteses ou colchetes (ponto, hífen, barra, espaço, espaço não separável, travessão, sublinhado,
# " . "...); a vírgula e as aspas ficam de fora para uma lista de números ([100, 101, 102, 99]) não contar
_SEPARADOR = r"(?:\\n|(?:[^\w,'\"()\[\]]|_){0,3})"
CPF_NO_CODIGO = re.compile(
    rf"(?<!\d)(?<!\d[.,])(\d{{3}}{_SEPARADOR}\d{{3}}{_SEPARADOR}\d{{3}}{_SEPARADOR}\d{{2}})(?!\d)"
)
CPF_COMPLETADO_COM_ZEROS = re.compile(r"(?<!\d)000(\d{11})(?!\d)")


def achados_no_codigo(nome: str, texto: str) -> Iterator[str]:
    """Onde há CPF que confere no código de um teste (regras 3 e 4): 'arquivo:linha:coluna', sem o valor."""
    for numero, linha in enumerate(texto.splitlines(), start=1):
        for achado in CPF_NO_CODIGO.finditer(linha):
            if e_cpf_valido(achado.group(1).replace("\\n", "")):
                yield f"{nome}:{numero}:{achado.start() + 1}"
        for achado in CPF_COMPLETADO_COM_ZEROS.finditer(linha):
            # os 14 dígitos que também conferem como CNPJ (o do Banco do Brasil começa com zeros) são CNPJ
            if e_cpf_valido(achado.group(1)) and not dv_confere(achado.group(0)):
                yield f"{nome}:{numero}:{achado.start() + 1}"


def achados_nos_testes() -> list[str]:
    encontrados: list[str] = []
    for arquivo in sorted(PASTA_DOS_TESTES.rglob("*.py")):
        nome = arquivo.relative_to(RAIZ).as_posix()
        encontrados.extend(achados_no_codigo(nome, arquivo.read_text(encoding="utf-8")))
    return encontrados


def test_nenhum_teste_guarda_cpf_valido():
    encontrados = achados_nos_testes()
    assert not encontrados, (
        "CPF com dígito verificador certo no código dos testes (monte-o na hora com tests/ajudantes_de_cpf.py, "
        "ou troque os 11 dígitos por uma sequência inventada com o dígito que não confere; o valor não é "
        "mostrado de propósito):\n" + "\n".join(encontrados)
    )


def test_a_varredura_do_codigo_acha_o_cpf_em_qualquer_forma_e_nao_mostra_o_valor():
    cpf = _cpf_inventado()
    formas = [
        cpf,
        _formatado(cpf),
        f"{cpf[:3]} {cpf[3:6]} {cpf[6:9]} {cpf[9:]}",
        f"{cpf[:3]}/{cpf[3:6]}/{cpf[6:9]}/{cpf[9:]}",
        f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}–{cpf[9:]}",
        f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}\\n{cpf[9:]}",
        f"{cpf[:3]} {cpf[3:6]} {cpf[6:9]} {cpf[9:]}",
        f"{cpf[:3]} . {cpf[3:6]} . {cpf[6:9]} - {cpf[9:]}",
        f"{cpf[:3]}_{cpf[3:6]}_{cpf[6:9]}_{cpf[9:]}",
    ]
    for forma in formas:
        achado = list(achados_no_codigo("t.py", f'x = "a {forma} b"'))
        assert achado == ["t.py:1:8"], forma
        assert cpf[3:9] not in achado[0]
    assert list(achados_no_codigo("t.py", f'x = "N.{cpf}"')) == ["t.py:1:8"]
    assert not list(achados_no_codigo("t.py", f'x = "{_formatado(_estragado(cpf))}"'))
    assert not list(achados_no_codigo("t.py", f'x = "1{cpf}"'))
    assert not list(achados_no_codigo("t.py", f'x = "1.{cpf[:9]},{cpf[9:]}"'))


def test_a_varredura_do_codigo_acha_o_cpf_completado_com_zeros_que_nao_passa_como_cnpj():
    cpf = _cpf_inventado()
    assert not dv_confere("000" + cpf)  # o inventado, com os zeros, não passa como CNPJ
    assert list(achados_no_codigo("t.py", f'x = "000{cpf}"')) == ["t.py:1:6"]
    assert not list(achados_no_codigo("t.py", f'x = "000{_estragado(cpf)}"'))
    assert not list(achados_no_codigo("t.py", f'x = "000{_cpf_que_passa_como_cnpj()}"'))


def _cpf_que_passa_como_cnpj() -> str:
    """Um CPF que confere e que, com "000" na frente, também confere como CNPJ (aí ele conta como CNPJ)."""
    for numero in range(
        1_112_222, 1_212_222
    ):  # começa com 00: os pesos do CNPJ dão os mesmos dígitos
        nove = f"{numero:09d}"
        cpf = next(
            f"{nove}{f:02d}" for f in range(100) if cpf_confere(f"{nove}{f:02d}")
        )
        if dv_confere("000" + cpf):
            return cpf
    raise AssertionError("nenhum passa como CNPJ")  # pragma: no cover


def test_a_varredura_do_codigo_nao_conta_lista_de_numeros():
    cpf = _cpf_inventado()
    lista = f"[{cpf[:3]}, {cpf[3:6]}, {cpf[6:9]}, {cpf[9:]}]"
    chamada = f'linha({cpf[:3]}, "{cpf[3:9]}", {cpf[9:]})'
    assert not list(achados_no_codigo("t.py", lista))
    assert not list(achados_no_codigo("t.py", chamada))


def test_nenhum_exemplo_guarda_cpf_valido():
    encontrados = achados()
    assert not encontrados, (
        "CPF com dígito verificador certo nos arquivos de exemplo (troque os 11 dígitos por uma sequência "
        "inventada com o dígito que não confere; o valor não é mostrado de propósito):\n"
        + "\n".join(encontrados)
    )


def _cpf_inventado() -> str:
    """Um CPF que confere, montado na hora a partir de nove dígitos (o teste não guarda nenhum)."""
    base = "1" * 4 + "2" * 5
    for final in range(100):
        candidato = f"{base}{final:02d}"
        if cpf_confere(candidato):
            return candidato
    raise AssertionError("nenhum dígito confere")  # pragma: no cover


def _estragado(cpf: str) -> str:
    return cpf[:-1] + str((int(cpf[-1]) + 1) % 10)


def _formatado(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def test_a_varredura_acha_o_cpf_formatado_em_qualquer_lugar_e_nao_mostra_o_valor():
    cpf = _cpf_inventado()
    achado = list(
        achados_no_texto("x.html", f"<p>Registro {_formatado(cpf)}</p>", ".html")
    )
    assert achado == ["x.html:1 (CPF formatado)"]
    assert cpf[3:9] not in achado[0]
    assert not list(
        achados_no_texto("x.html", f"<p>{_formatado(_estragado(cpf))}</p>", ".html")
    )


def test_onze_digitos_so_contam_em_coluna_de_cpf():
    cpf = _cpf_inventado()
    tabela = f"processo;CPF_CNPJ\n{cpf};1\n1;{cpf}\n1;{_estragado(cpf)}\n"
    assert list(achados_no_texto("t.csv", tabela, ".csv")) == ["t.csv:3:CPF_CNPJ"]


def test_onze_digitos_na_coluna_do_cnpj_tambem_contam():
    """A CVM e o PNCP põem o CPF do devedor ou do fornecedor pessoa física na coluna do CNPJ."""
    cpf = _cpf_inventado()
    tabela = f"Tipo;CNPJ\nDevedor;{cpf}\nDevedor;{_estragado(cpf)}\n"
    assert list(achados_no_texto("s.csv", tabela, ".csv")) == ["s.csv:2:CNPJ"]


def test_chave_de_json_com_cpf_conta_e_as_outras_nao():
    cpf = _cpf_inventado()
    texto = json.dumps({"dados": [{"cpf": cpf, "niFornecedor": cpf, "codigo": cpf}]})
    assert sorted(achados_no_texto("p.json", texto, ".json")) == [
        "p.json:/dados[0]/cpf",
        "p.json:/dados[0]/niFornecedor",
    ]


def test_dentro_do_zip_e_da_planilha_tambem():
    cpf = _cpf_inventado()
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("dentro.csv", f"cgccpf;nome\n{_formatado(cpf)};EXEMPLO\n")
    assert len(list(_achados_no_arquivo("a.zip", ".zip", pacote.getvalue()))) == 2
    planilha = pd.DataFrame({"CPF": [cpf, _estragado(cpf)], "outro": [cpf, "x"]})
    assert list(achados_na_planilha("b.parquet", planilha)) == ["b.parquet:linha 1:CPF"]
