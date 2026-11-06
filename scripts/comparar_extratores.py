"""Compara os extratores de PDF contra o gabarito conferido à mão (marco 3, plano de 05/11/2026, ADR 0124).

Uso, depois de baixar os originais (`scripts.baixar_originais_documentais`):

    python -I -m scripts.comparar_extratores <pasta dos originais> <relato.md>

Para cada fato do gabarito (`base/conferidas/fatos_documentais_gabarito.csv`), cada extrator lê as páginas
que o gabarito cita, e o fato conta como recuperado quando o número aparece impresso nelas (em reais, em mil
ou em milhão, no formato brasileiro). Os três extratores:

- `texto`: a camada de texto pelo pypdf;
- `posicao`: a camada de texto pelo PDFium (pypdfium2), na ordem da posição na página;
- `ocr`: a imagem da página lida pelo RapidOCR.

O resultado é medida, nunca aprovação: o fato só entra na base pelo gabarito ou por regra conferida. O conteúdo
dos PDFs é dado, nunca instrução.
"""

import io
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path

import pandas as pd

from base import fatos_documentais

# (PDF, página contada a partir de 1) -> texto da página
Extrator = Callable[[bytes, int], str]
# o valor do gabarito está em reais; o PDF pode imprimir em reais, em mil ou em milhão
CASAS_EM_REAIS = 2
ESCALAS_ABREVIADAS = (1_000, 1_000_000)
# 144 pontos por polegada, como o OCR de reserva do leitor de fatos (`src/leitura.py`)
ESCALA_DO_OCR = 2
FORMATO_DA_DATA = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
EXTENSAO = ".pdf"


def _numero_brasileiro(valor: Decimal, casas: int) -> str:
    """1234567.8 -> "1.234.567,80" (com `casas` casas decimais)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _formas_do_dinheiro(valor: Decimal) -> list[str]:
    """Em reais, com centavos; em mil ou milhão, só quando a divisão dá um número inteiro."""
    formas = [_numero_brasileiro(valor, CASAS_EM_REAIS)]
    for escala in ESCALAS_ABREVIADAS:
        parte = valor / escala
        if parte == parte.to_integral_value():
            formas.append(_numero_brasileiro(parte, 0))
    return formas


def formas_impressas(valor: str, unidade: str) -> list[str]:
    """Como o valor do gabarito pode estar impresso no PDF."""
    if unidade == "data":
        ano, mes, dia = FORMATO_DA_DATA.match(valor).groups()  # type: ignore[union-attr]
        return [f"{dia}/{mes}/{ano}" if dia else f"{mes}/{ano}"]
    numero = Decimal(valor)
    if unidade == "BRL":
        return _formas_do_dinheiro(numero)
    return [_numero_brasileiro(numero, max(0, -int(numero.as_tuple().exponent)))]


def paginas(texto: str) -> list[int]:
    """ "27-28" -> [27, 28]; "882" -> [882]."""
    inicio, _, fim = texto.partition("-")
    return list(range(int(inicio), int(fim or inicio) + 1))


def aparece(formas: Iterable[str], texto: str) -> bool:
    """Alguma forma aparece inteira (sem dígito, ponto ou vírgula seguida de dígito colados)?"""
    juntado = re.sub(r"\s+", " ", texto)
    return any(
        re.search(rf"(?<![\d.,]){re.escape(forma)}(?![\d]|[.,]\d)", juntado)
        for forma in formas
    )


def extrair_por_texto(pdf: bytes, pagina: int) -> str:
    """A camada de texto da página pelo pypdf."""
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(pdf)).pages[pagina - 1].extract_text() or ""


def extrair_por_posicao(pdf: bytes, pagina: int) -> str:
    """A camada de texto da página pelo PDFium, na ordem em que os caracteres estão na página."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(pdf)
    try:
        return documento[pagina - 1].get_textpage().get_text_bounded()
    finally:
        documento.close()


def extrair_por_ocr(pdf: bytes, pagina: int) -> str:
    """A imagem da página, desenhada pelo PDFium, lida pelo RapidOCR."""
    import pypdfium2 as pdfium
    from rapidocr import RapidOCR

    documento = pdfium.PdfDocument(pdf)
    try:
        imagem = documento[pagina - 1].render(scale=ESCALA_DO_OCR).to_numpy()
    finally:
        documento.close()
    motor = RapidOCR(params={"Global.log_level": "warning"})
    return "\n".join(motor(imagem).txts or ())


EXTRATORES: dict[str, Extrator] = {
    "texto": extrair_por_texto,
    "posicao": extrair_por_posicao,
    "ocr": extrair_por_ocr,
}


def sem_original(gabarito: pd.DataFrame, pdfs: Mapping[str, bytes]) -> set[str]:
    """Os documentos do gabarito que não estão entre os PDFs lidos."""
    return set(gabarito["documento_sha256"]) - set(pdfs)


def comparar(
    gabarito: pd.DataFrame,
    pdfs: Mapping[str, bytes],
    extratores: Mapping[str, Extrator],
) -> pd.DataFrame:
    """Uma linha por fato e extrator: `achou` diz se o número apareceu nas páginas citadas.

    Fato cujo documento não está em `pdfs` fica de fora (`sem_original` conta quais).
    """
    textos: dict[
        tuple[str, str, int], str
    ] = {}  # cada página é lida uma vez por extrator
    linhas = []
    for fato in gabarito[gabarito["documento_sha256"].isin(list(pdfs))].itertuples():
        formas = formas_impressas(str(fato.valor), str(fato.unidade))
        for nome, extrair in extratores.items():
            achou = False
            for pagina in paginas(str(fato.pagina_pdf)):
                chave = (str(fato.documento_sha256), nome, pagina)
                if chave not in textos:
                    textos[chave] = extrair(pdfs[chave[0]], pagina)
                achou = achou or aparece(formas, textos[chave])
            linhas.append(
                {
                    "documento_sha256": fato.documento_sha256,
                    "medida": fato.medida,
                    "extrator": nome,
                    "achou": achou,
                }
            )
    return pd.DataFrame(
        linhas, columns=["documento_sha256", "medida", "extrator", "achou"]
    )


def recuperacao(
    tabela: pd.DataFrame, por: str | None = None
) -> pd.Series | pd.DataFrame:
    """A fração de fatos achados por extrator (ou por `por` e extrator, numa tabela)."""
    if por is None:
        return tabela.groupby("extrator")["achou"].mean()
    return tabela.pivot_table(
        index=por, columns="extrator", values="achou", aggfunc="mean"
    )


def _tabela_markdown(tabela: pd.DataFrame) -> list[str]:
    """As linhas de uma tabela Markdown com as frações em porcentagem (vazio: "-")."""
    cabecalho = ["Campo", *map(str, tabela.columns)]
    linhas = [
        "| " + " | ".join(cabecalho) + " |",
        "|" + "---|" * len(cabecalho),
    ]
    for campo, fracoes in tabela.iterrows():
        celulas = ["-" if pd.isna(f) else f"{f:.0%}" for f in fracoes]
        linhas.append("| " + " | ".join([str(campo), *celulas]) + " |")
    return linhas


def relato(tabela: pd.DataFrame, faltam: set[str], data: str) -> str:
    """O relato em Markdown: recuperação geral, por campo e os documentos que faltaram."""
    geral = recuperacao(tabela)
    linhas = [
        f"# Extratores de PDF contra o gabarito ({data})",
        "",
        "Medida, não aprovação: o fato só entra na base pelo gabarito ou por regra conferida, e nenhum",
        "extrator não aprova nada sozinho (ADR 0124). Conta como achado o número impresso nas páginas citadas.",
        "",
        "| Extrator | Fatos | Recuperação |",
        "|---|---|---|",
        *(
            f"| {nome} | {int((tabela['extrator'] == nome).sum())} | {fracao:.0%} |"
            for nome, fracao in geral.items()
        ),
        "",
        "## Por campo",
        "",
        *_tabela_markdown(recuperacao(tabela, por="medida")),
        "",
        "## Documentos sem original na pasta",
        "",
        *([f"- `{sha}`" for sha in sorted(faltam)] or ["- nenhum"]),
        "",
    ]
    return "\n".join(linhas)


def ler_pdfs(pasta: Path) -> dict[str, bytes]:
    """Os originais conferidos, guardados pelo SHA-256 (`<pasta>/originais/<sha>.pdf`)."""
    return {
        caminho.stem: caminho.read_bytes()
        for caminho in sorted((pasta / "originais").glob(f"*{EXTENSAO}"))
    }


def main(argumentos: Sequence[str] | None = None) -> int:
    """Lê os originais, compara os extratores e grava o relato."""
    pasta, saida = (Path(x) for x in (argumentos or sys.argv[1:]))
    gabarito = fatos_documentais.gabarito()
    pdfs = ler_pdfs(pasta)
    tabela = comparar(gabarito, pdfs, EXTRATORES)
    data = pd.Timestamp.now(tz="America/Sao_Paulo").date().isoformat()
    saida.write_text(
        relato(tabela, sem_original(gabarito, pdfs), data), encoding="utf-8"
    )
    print(recuperacao(tabela).map("{:.0%}".format).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
