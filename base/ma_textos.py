"""Os textos dos candidatos de M&A (série 1 do plano da base de M&A): a ordem da fila e o texto de cada
documento.

Os ~23 mil documentos de `ma_candidatos` (`base/ma_ipe.py`) vêm do sistema de documentos da CVM (RAD),
que limita os downloads por endereço: a coleta (`scripts/coletar_ma_textos.py`) leva semanas, então a
fila põe primeiro o que mais rende. Cada documento vai bruto para o acervo, com registro (fonte
`cvm-ipe-ma`, com SHA-256), e o texto vai para `<acervo>/ma/textos/`, que é o que a extração lê.

O texto sai do mesmo jeito que o da amostra de ouro (baixada pela rotulagem por IA): a medida da
extração (Sonnet 91,5% nos campos-chave) só vale para a base se o texto for igual.
"""

from collections.abc import Collection
from pathlib import Path

import pandas as pd

from base import ma_ipe
from src import leitura

FONTE_DOS_DOCUMENTOS = "cvm-ipe-ma"
PASTA_DOS_TEXTOS = Path("ma") / "textos"
MAX_CARACTERES_GUARDADOS = (
    20_000  # igual à rotulagem por IA, de onde vieram os textos da amostra
)
FATO_RELEVANTE = "Fato Relevante"

# a fila: o que mais rende primeiro
LISTA_PEDIDA = 0  # protocolos pedidos à mão (a conferência dos ~40 documentos novos)
COM_TIPO = 1  # fatos relevantes com tipo pelo assunto e editais de OPA
GENERICO = 2  # fatos relevantes de assunto genérico: o texto decide
DEMAIS = 3  # comunicados ao mercado
TENTATIVAS_ANTES_DO_FIM = (
    3  # um documento que voltou página tantas vezes vai para o fim da fila
)


def grupo(candidatos: pd.DataFrame) -> pd.Series:
    """O grupo de cada candidato na fila (`COM_TIPO`, `GENERICO` ou `DEMAIS`)."""
    fato = candidatos["categoria"].eq(FATO_RELEVANTE)
    com_tipo = (fato & candidatos["evidencia"].eq(ma_ipe.POR_ASSUNTO)) | candidatos[
        "evidencia"
    ].eq(ma_ipe.POR_CATEGORIA)
    generico = candidatos["evidencia"].eq(ma_ipe.POR_ASSUNTO_GENERICO)
    return (
        pd.Series(DEMAIS, index=candidatos.index)
        .mask(generico, GENERICO)
        .mask(com_tipo, COM_TIPO)
    )


def fila(
    candidatos: pd.DataFrame,
    resolvidos: Collection[str],
    tentativas: dict[str, int],
    pedidos: Collection[str] = (),
) -> pd.DataFrame:
    """Os candidatos ainda por baixar, na ordem da coleta.

    Primeiro os `pedidos` (protocolos), depois os grupos, do mais novo ao mais velho em cada um. O que
    já veio (ou que a CVM disse não existir) sai. O que voltou página da CVM `TENTATIVAS_ANTES_DO_FIM`
    vezes vai para o fim: um documento quebrado na fonte não pode travar a fila inteira (foi o que
    aconteceu com a rotulagem por IA desde 17/10).
    """
    faltam = candidatos[~candidatos["link"].isin(resolvidos)].copy()
    faltam["_grupo"] = grupo(faltam).mask(
        faltam["protocolo"].isin(pedidos), LISTA_PEDIDA
    )
    faltam["_insiste"] = (
        faltam["link"].map(tentativas).fillna(0).ge(TENTATIVAS_ANTES_DO_FIM)
    )
    faltam = faltam.sort_values(
        ["_insiste", "_grupo", "publico_em", "protocolo", "versao"],
        ascending=[True, True, False, False, False],
        kind="stable",
    )
    return faltam.drop(columns=["_grupo", "_insiste"]).reset_index(drop=True)


def texto_do_documento(conteudo: bytes, categoria: str) -> str:
    """O texto como na amostra de ouro: "" se não é PDF ou está ilegível; nos fatos relevantes, sem o
    cabeçalho e a assinatura; espaços juntados; até `MAX_CARACTERES_GUARDADOS`."""
    lido = leitura.ler_documento(conteudo)
    if not lido.legivel:
        return ""
    texto = lido.texto
    if categoria == FATO_RELEVANTE:
        texto = leitura.sem_cabecalho_e_assinatura(texto)
    return " ".join(texto.split())[:MAX_CARACTERES_GUARDADOS]


def gravar_texto(pasta_dos_textos: Path, nome: str, texto: str) -> Path:
    """`<nome>.txt` com o texto, ou `<nome>.sem_texto` vazio (não é PDF, é só imagem ilegível...)."""
    pasta_dos_textos.mkdir(parents=True, exist_ok=True)
    arquivo = pasta_dos_textos / f"{nome}.{'txt' if texto else 'sem_texto'}"
    arquivo.write_text(texto, encoding="utf-8")
    return arquivo
