"""A resposta da API numa planilha (CSV ou XLSX), para a equipe levar ao Excel sem perder a fonte e a data.

Cada lista da resposta vira uma tabela (uma aba no XLSX, um arquivo no CSV), com os valores crus (número como
número, não como texto formatado) e, em cada linha, a fonte e o dia em que o dado ficou público. Os campos soltos
com fonte (o cadastro da empresa, por exemplo) vão para a tabela `campos`. No XLSX, a aba `fontes` traz a licença,
a frase de atribuição de cada fonte e o aviso de que nada é recomendação de investimento.

O XLSX é escrito à mão (o formato é um zip de XML) para o pacote seguir só com `click` e `httpx`. Um texto que
começa com `=`, `+`, `-` ou `@` ganha um apóstrofo na frente no CSV (no XLSX ele já vai como texto, nunca como
fórmula): o nome de uma empresa não pode virar fórmula no Excel de quem abre o arquivo.
"""

import csv
import io
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from tickerlab.formato import (
    AVISO,
    avisos_de_piloto,
    colunas_da_linha,
    e_de_piloto,
    e_envelope,
    frase_de_piloto_da_linha,
    frase_do_envelope,
    rotulo_do_item,
    tem_listas,
)

EXTENSOES = (".csv", ".xlsx")
COLUNA_DA_FONTE = "fonte"
COLUNA_DA_DATA = "publicado_em"
COLUNA_DO_PILOTO = "piloto"
INICIO_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")
LIMITE_DO_NOME_DA_ABA = 31  # o Excel não abre aba com nome maior
PROIBIDO_NO_NOME_DA_ABA = re.compile(r"[\[\]:*?/\\]")
CONTROLE_INVALIDO_NO_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
DATA_FIXA_DO_ZIP = (2026, 1, 1, 0, 0, 0)  # a mesma resposta dá o mesmo arquivo

Valor = str | int | float | bool | None


@dataclass
class Tabela:
    """Uma tabela da planilha: o nome (o caminho na resposta), o cabeçalho e as linhas com valores crus."""

    nome: str
    cabecalho: list[str]
    linhas: list[list[Valor]] = field(default_factory=list)
    # linha de `linhas` -> a frase de piloto do campo que ela traz (só a tabela `campos` usa)
    pilotos: dict[int, str] = field(default_factory=dict)


def _cru(valor: object) -> Valor:
    """O valor como a planilha o guarda: o `value` do envelope; lista ou objeto vira texto."""
    if e_envelope(valor):
        valor = valor["value"]  # type: ignore[index]
    if valor is None or isinstance(valor, str | int | float | bool):
        return valor
    return str(valor)


def _fonte_e_data(envelopes: Sequence[Mapping]) -> list[Valor]:
    """As fontes e as datas de publicação distintas da linha, juntas (quase sempre uma de cada)."""
    fontes = dict.fromkeys(str(env.get("source")) for env in envelopes)
    datas = dict.fromkeys(str(env.get("published_at") or "") for env in envelopes)
    return [", ".join(fontes), ", ".join(d for d in datas if d) or None]


def _tabela_de_linhas(nome: str, linhas: Sequence[Mapping]) -> Tabela:
    colunas = colunas_da_linha(linhas)
    com_fonte = any(e_envelope(v) for linha in linhas for v in linha.values())
    frases = [frase_de_piloto_da_linha(linha) for linha in linhas]
    com_piloto = any(frases)
    extra = [COLUNA_DA_FONTE, COLUNA_DA_DATA] if com_fonte else []
    extra += [COLUNA_DO_PILOTO] if com_piloto else []
    tabela = Tabela(nome, [*colunas, *extra])
    for linha, frase in zip(linhas, frases, strict=True):
        valores = [_cru(linha.get(coluna)) for coluna in colunas]
        if com_fonte:
            valores += _fonte_e_data([v for v in linha.values() if e_envelope(v)])
        if (
            com_piloto
        ):  # a coluna leva a própria frase: o arquivo da lista a carrega sozinho
            valores.append(frase)
        tabela.linhas.append(valores)
    return tabela


def _juntar(caminho: str, nome: str) -> str:
    return f"{caminho} › {nome}" if caminho else nome


def _percorrer(
    caminho: str, dado: Mapping, campos: Tabela, tabelas: list[Tabela]
) -> None:
    """Os campos com fonte vão para `campos`; cada lista de objetos vira uma tabela; o resto desce."""
    for nome, valor in dado.items():
        if nome == "sources":
            continue
        if e_envelope(valor):
            campos.linhas.append(
                [_juntar(caminho, nome), _cru(valor), *_fonte_e_data([valor])]
            )
            if e_de_piloto(valor):
                campos.pilotos[len(campos.linhas) - 1] = frase_do_envelope(valor)
        elif valor is None or isinstance(valor, str | int | float | bool):
            # o que identifica o pedido (CNPJ, dia, hipótese, corte): sem fonte, não é dado de fonte
            campos.linhas.append([_juntar(caminho, nome), valor, None, None])
        elif isinstance(valor, Mapping):
            _percorrer(_juntar(caminho, nome), valor, campos, tabelas)
        elif isinstance(valor, list):
            _lista(_juntar(caminho, nome), valor, campos, tabelas)


def _marcar_campos_de_piloto(campos: Tabela) -> None:
    """Acrescenta a coluna `piloto` (com a frase) nos campos soltos quando a API marcou algum como piloto."""
    if not campos.pilotos:
        return
    campos.cabecalho.append(COLUNA_DO_PILOTO)
    for posicao, linha in enumerate(campos.linhas):
        linha.append(campos.pilotos.get(posicao))


def _lista(caminho: str, itens: list, campos: Tabela, tabelas: list[Tabela]) -> None:
    objetos = [item for item in itens if isinstance(item, Mapping)]
    if objetos and all(tem_listas(item) for item in objetos):
        for posicao, item in enumerate(objetos, start=1):
            _percorrer(
                _juntar(caminho, rotulo_do_item(item, posicao)), item, campos, tabelas
            )
    elif objetos:
        tabelas.append(_tabela_de_linhas(caminho, objetos))
    elif textos := [item for item in itens if isinstance(item, str)]:
        tabelas.append(Tabela(caminho, ["texto"], [[texto] for texto in textos]))


def tabelas_da_resposta(corpo: Mapping) -> list[Tabela]:
    """As tabelas da planilha: `campos` (os campos soltos) e uma por lista da resposta."""
    campos = Tabela("campos", ["campo", "valor", COLUNA_DA_FONTE, COLUNA_DA_DATA])
    tabelas: list[Tabela] = []
    _percorrer("", corpo, campos, tabelas)
    _marcar_campos_de_piloto(campos)
    return [campos, *tabelas] if campos.linhas else tabelas


def tabela_das_fontes(corpo: Mapping) -> Tabela:
    """As fontes da resposta com a atribuição e a licença que pedem, e o aviso no fim."""
    fontes = Tabela("fontes", ["fonte", "atribuicao", "licenca"])
    for item in corpo.get("sources") or []:
        if isinstance(item, Mapping):
            fontes.linhas.append(
                [
                    _cru(item.get("source")),
                    _cru(item.get("attribution")),
                    _cru(item.get("license")),
                ]
            )
    fontes.linhas.append(["aviso", AVISO, None])
    fontes.linhas.extend(
        ["aviso de piloto", frase, None] for frase in avisos_de_piloto(corpo)
    )
    return fontes


# ---------------------------------------------------------------- CSV


def _celula_do_csv(valor: Valor) -> str:
    """O valor no jeito do Excel em português: vírgula decimal, sim e não, texto que não vira fórmula."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, float):
        return repr(valor).replace(".", ",")
    texto = str(valor)
    if isinstance(valor, str) and texto.startswith(INICIO_DE_FORMULA):
        return "'" + texto
    return texto


def texto_do_csv(tabela: Tabela) -> str:
    """Uma tabela em CSV com `;` (o separador que o Excel em português espera)."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(tabela.cabecalho)
    escritor.writerows([_celula_do_csv(v) for v in linha] for linha in tabela.linhas)
    return saida.getvalue()


def _nome_de_arquivo(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_") or "tabela"


def gravar_csv(destino: Path, tabelas: Sequence[Tabela]) -> list[Path]:
    """Uma tabela vai no próprio `destino`; várias, cada uma num arquivo com o nome dela no fim."""
    if len(tabelas) == 1:
        arquivos = [(destino, tabelas[0])]
    else:
        arquivos = [
            (
                destino.with_name(
                    f"{destino.stem}-{_nome_de_arquivo(t.nome)}{destino.suffix}"
                ),
                t,
            )
            for t in tabelas
        ]
    for arquivo, tabela in arquivos:
        arquivo.write_text(texto_do_csv(tabela), encoding="utf-8-sig", newline="")
    return [arquivo for arquivo, _tabela in arquivos]


# ---------------------------------------------------------------- XLSX

_CABECA_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
_TIPO = "application/vnd.openxmlformats-officedocument.spreadsheetml"
_RELACAO = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_TIPOS = (
    _CABECA_XML
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    f'<Override PartName="/xl/workbook.xml" ContentType="{_TIPO}.sheet.main+xml"/>'
    "{abas}</Types>"
)
_ABA_NOS_TIPOS = (
    '<Override PartName="/xl/worksheets/sheet{n}.xml" ContentType="'
    + _TIPO
    + '.worksheet+xml"/>'
)
_RELACOES = (
    _CABECA_XML
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    "{itens}</Relationships>"
)
_RELACAO_DO_PACOTE = f'<Relationship Id="rId1" Type="{_RELACAO}/officeDocument" Target="xl/workbook.xml"/>'
_ABA_NAS_RELACOES = (
    '<Relationship Id="rId{n}" Type="'
    + _RELACAO
    + '/worksheet" Target="worksheets/sheet{n}.xml"/>'
)
_PASTA = (
    _CABECA_XML
    + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    f'xmlns:r="{_RELACAO}"><sheets>{{abas}}</sheets></workbook>'
)
_FOLHA = (
    _CABECA_XML
    + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    "<sheetData>{linhas}</sheetData></worksheet>"
)


def _coluna(indice: int) -> str:
    """A letra da coluna do Excel: 0 vira A, 25 vira Z, 26 vira AA."""
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(ord("A") + resto) + letras
    return letras


def _texto_do_xml(texto: str) -> str:
    return escape(CONTROLE_INVALIDO_NO_XML.sub("", texto), {'"': "&quot;"})


def _celula_do_xlsx(referencia: str, valor: Valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return f'<c r="{referencia}" t="b"><v>{int(valor)}</v></c>'
    if isinstance(valor, int | float):
        return f'<c r="{referencia}"><v>{valor!r}</v></c>'
    texto = _texto_do_xml(str(valor))
    return f'<c r="{referencia}" t="inlineStr"><is><t xml:space="preserve">{texto}</t></is></c>'


def _folha(tabela: Tabela) -> str:
    linhas = []
    for numero, valores in enumerate([tabela.cabecalho, *tabela.linhas], start=1):
        celulas = "".join(
            _celula_do_xlsx(f"{_coluna(i)}{numero}", valor)
            for i, valor in enumerate(valores)
        )
        linhas.append(f'<row r="{numero}">{celulas}</row>')
    return _FOLHA.format(linhas="".join(linhas))


def _nome_curto(partes: list[str]) -> str:
    """O fim do caminho que cabe na aba: os últimos pedaços inteiros; se nem dois cabem, o penúltimo
    encurtado (`aneel_consumidore.concentration`), que é o que distingue uma série da outra."""
    nome = partes[-1][:LIMITE_DO_NOME_DA_ABA] or "tabela"
    for parte in reversed(partes[:-1]):
        if len(parte) + 1 + len(nome) <= LIMITE_DO_NOME_DA_ABA:
            nome = f"{parte}.{nome}"
            continue
        if "." not in nome and (sobra := LIMITE_DO_NOME_DA_ABA - len(nome) - 1) > 0:
            nome = f"{parte[:sobra]}.{nome}"
        break
    return nome


def nomes_das_abas(tabelas: Sequence[Tabela]) -> list[str]:
    """Nomes que o Excel aceita: sem `[]:*?/\\`, até 31 caracteres e sem repetir (sem olhar maiúscula)."""
    nomes: list[str] = []
    for tabela in tabelas:
        base = _nome_curto(PROIBIDO_NO_NOME_DA_ABA.sub("_", tabela.nome).split(" › "))
        nome, extra = base, 2
        while nome.lower() in {n.lower() for n in nomes}:
            sufixo = f"~{extra}"
            nome, extra = (
                base[: LIMITE_DO_NOME_DA_ABA - len(sufixo)] + sufixo,
                extra + 1,
            )
        nomes.append(nome)
    return nomes


def conteudo_do_xlsx(tabelas: Sequence[Tabela]) -> bytes:
    """O arquivo XLSX com uma aba por tabela."""
    numeros = range(1, len(tabelas) + 1)
    abas = "".join(
        f'<sheet name="{_texto_do_xml(nome)}" sheetId="{n}" r:id="rId{n}"/>'
        for n, nome in zip(numeros, nomes_das_abas(tabelas), strict=True)
    )
    partes = {
        "[Content_Types].xml": _TIPOS.format(
            abas="".join(_ABA_NOS_TIPOS.format(n=n) for n in numeros)
        ),
        "_rels/.rels": _RELACOES.format(itens=_RELACAO_DO_PACOTE),
        "xl/workbook.xml": _PASTA.format(abas=abas),
        "xl/_rels/workbook.xml.rels": _RELACOES.format(
            itens="".join(_ABA_NAS_RELACOES.format(n=n) for n in numeros)
        ),
    }
    for n, tabela in zip(numeros, tabelas, strict=True):
        partes[f"xl/worksheets/sheet{n}.xml"] = _folha(tabela)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as arquivo:
        for nome, texto in partes.items():
            info = zipfile.ZipInfo(nome, DATA_FIXA_DO_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            arquivo.writestr(info, texto.encode("utf-8"))
    return saida.getvalue()


def gravar(destino: Path, corpo: Mapping) -> list[Path]:
    """Grava a resposta em `destino` (.csv ou .xlsx) e devolve os arquivos gravados."""
    tabelas = tabelas_da_resposta(corpo)
    if destino.suffix.lower() == ".xlsx":
        destino.write_bytes(conteudo_do_xlsx([*tabelas, tabela_das_fontes(corpo)]))
        return [destino]
    return gravar_csv(destino, tabelas or [Tabela("vazia", ["campo"])])
