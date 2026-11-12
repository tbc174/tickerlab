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

from base.cnpj import cpf_confere

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
