"""Validação por evidência: um fato só vale se o trecho citado está **literalmente** no original
baixado (conferido pelo SHA-256) e o valor, o CNPJ e o período estão dentro do trecho.

Isto não prova que o fato é verdadeiro no mundo; prova que a fonte diz o que o agente afirma que ela
diz, no lugar que ele aponta. O resto (a fonte é a certa para a pergunta? é a empresa certa?) é da
reconciliação entre as IAs. Sem trecho, sem hash ou com o valor fora do trecho, o fato fica
**pendente**, nunca "provável".
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from pesquisa import leitores

CONFIRMADO = "confirmado"
PENDENTE = "pendente"
MINIMO_DO_TRECHO = 12  # caracteres: "R$ 5" aparece em qualquer lugar e não prova nada
TUDO = (
    10**9
)  # a conferência lê o documento inteiro, sem os limites de leitura do agente
SO_ALFANUMERICOS = re.compile(r"[^0-9a-zà-ÿ]+", re.IGNORECASE)


@dataclass(frozen=True)
class Fato:
    """O que o agente afirma e onde está a prova."""

    afirmacao: str  # a frase: "Parque X: 120 MW, vigência 2035"
    valor: str  # o dado em si, como está na fonte: "120"
    trecho: str  # o texto literal da fonte que sustenta
    sha256: str  # do original baixado (vem do `baixar_documento`)
    posicao: str | None = (
        None  # "pagina 3", "Planilha1 linha 12": ajuda a achar, e se dada, vale
    )
    exigir_no_trecho: tuple[
        str, ...
    ] = ()  # CNPJ, CEG, ano: o que prova de quem e de quando


@dataclass
class Veredito:
    situacao: str
    motivos: list[str] = field(default_factory=list)
    onde: str | None = None

    def para_dict(self) -> dict[str, object]:
        return {"situacao": self.situacao, "motivos": self.motivos, "onde": self.onde}


def normalizar(texto: str) -> str:
    """Espaços e quebras viram um espaço, caixa ignorada: o PDF quebra a linha onde quer. A barra
    que separa as células de uma linha de planilha conta como espaço (o agente reescreve a linha
    com espaço ou com barra, e as duas formas são o mesmo conteúdo)."""
    return leitores.limpar(texto.replace("|", " ")).casefold()


def _so_alfanumericos(texto: str) -> str:
    return SO_ALFANUMERICOS.sub("", texto.casefold())


def validar(fato: Fato, original: Path | None) -> Veredito:
    """Confere o fato contra o original; devolve `confirmado` ou `pendente` com os motivos."""
    motivos = _conferir_campos(fato)
    if original is None:
        motivos.append("o original com este sha256 não está guardado (baixe de novo)")
        return Veredito(PENDENTE, motivos)
    motivos += _conferir_integridade(fato, original)
    if motivos:
        return Veredito(PENDENTE, motivos)
    onde = _onde_esta_o_trecho(fato, original)
    if onde is None:
        local = f" em {fato.posicao}" if fato.posicao else ""
        return Veredito(
            PENDENTE, [f"o trecho não está literalmente no documento{local}"]
        )
    motivos += _conferir_dentro_do_trecho(fato)
    return Veredito(CONFIRMADO if not motivos else PENDENTE, motivos, onde)


def _conferir_campos(fato: Fato) -> list[str]:
    motivos = []
    if len(normalizar(fato.trecho)) < MINIMO_DO_TRECHO:
        motivos.append(f"trecho curto demais (mínimo {MINIMO_DO_TRECHO} caracteres)")
    if not fato.valor.strip():
        motivos.append("sem valor")
    return motivos


def _conferir_integridade(fato: Fato, original: Path) -> list[str]:
    from pesquisa.coletor import (
        _sha256_do_arquivo,
    )

    if _sha256_do_arquivo(original) != fato.sha256:
        return ["o arquivo guardado não tem o sha256 informado (foi alterado?)"]
    return []


def _onde_esta_o_trecho(fato: Fato, original: Path) -> str | None:
    extracao = leitores.extrair(
        original, maximo_de_linhas=TUDO, maximo_de_caracteres=TUDO, pagina_final=None
    )
    procurado = normalizar(fato.trecho)
    for posicao, texto in extracao.trechos():
        if fato.posicao and not _so_alfanumericos(posicao).startswith(
            _so_alfanumericos(fato.posicao)
        ):
            continue
        if procurado in normalizar(texto):
            return posicao
    return None


def _conferir_dentro_do_trecho(fato: Fato) -> list[str]:
    trecho = normalizar(fato.trecho)
    sem_pontuacao = _so_alfanumericos(fato.trecho)
    motivos = []
    if normalizar(fato.valor) not in trecho:
        motivos.append(f"o valor {fato.valor!r} não está dentro do trecho citado")
    motivos.extend(
        f"{exigido!r} não aparece no trecho (de quem ou de quando é?)"
        for exigido in fato.exigir_no_trecho
        if normalizar(exigido) not in trecho
        and _so_alfanumericos(exigido) not in sem_pontuacao
    )
    return motivos
