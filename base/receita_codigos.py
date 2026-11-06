"""As tabelas de códigos dos dados abertos do CNPJ: o código vira o texto que a Receita publica.

Os arquivos em `base/conferidas/rfb_*.csv` são cópias das tabelas auxiliares da publicação de 10/2026
(`Qualificacoes`, `Cnaes`, `Municipios` e `Paises`, lidas do acervo e gravadas em UTF-8 sem mudar o texto;
o município vem em maiúsculas e sem acento, como a Receita escreve). A situação cadastral não tem tabela: os
cinco códigos estão no dicionário de dados do CNPJ. Código que a tabela não tem volta como "código X", para a
tela nunca esconder um valor nem inventar um nome.
"""

import csv
from functools import cache
from pathlib import Path

PASTA = Path(__file__).resolve().parent / "conferidas"
SITUACOES_CADASTRAIS = {
    "01": "Nula",
    "02": "Ativa",
    "03": "Suspensa",
    "04": "Inapta",
    "08": "Baixada",
}
TIPOS_DE_SOCIO = {"1": "pessoa jurídica", "2": "pessoa física", "3": "estrangeiro"}
# o tamanho do código em cada tabela (a base guarda sem os zeros à esquerda em alguns meses)
TAMANHOS = {"qualificacoes": 2, "cnaes": 7, "municipios": 4, "paises": 3}


@cache
def _tabela(nome: str) -> dict[str, str]:
    with open(PASTA / f"rfb_{nome}.csv", encoding="utf-8", newline="") as arquivo:
        return {
            linha["codigo"]: linha["descricao"]
            for linha in csv.DictReader(arquivo, delimiter=";")
        }


def _procurar(tabela: dict[str, str], codigo: str | None, tamanho: int) -> str | None:
    """O texto do código; None sem código; "código X" quando a tabela não tem."""
    if codigo is None or not str(codigo).strip():
        return None
    chave = str(codigo).strip().zfill(tamanho)
    return tabela.get(chave, f"código {chave}")


def _traduzir(nome: str, codigo: str | None) -> str | None:
    return _procurar(_tabela(nome), codigo, TAMANHOS[nome])


def qualificacao(codigo: str | None) -> str | None:
    """A qualificação do sócio (`05` → "Administrador")."""
    return _traduzir("qualificacoes", codigo)


def cnae(codigo: str | None) -> str | None:
    """A atividade econômica (`0111301` → "Cultivo de arroz")."""
    return _traduzir("cnaes", codigo)


def municipio(codigo: str | None) -> str | None:
    """O município pelo código da Receita (não é o do IBGE: `0003` → "PORTO VELHO")."""
    return _traduzir("municipios", codigo)


def pais(codigo: str | None) -> str | None:
    """O país pelo código da Receita (`013` → "AFEGANISTAO")."""
    return _traduzir("paises", codigo)


def situacao_cadastral(codigo: str | None) -> str | None:
    """A situação cadastral (`02` → "Ativa")."""
    return _procurar(SITUACOES_CADASTRAIS, codigo, 2)


def tipo_de_socio(codigo: str | None) -> str | None:
    """O tipo do sócio (`2` → "pessoa física")."""
    return _procurar(TIPOS_DE_SOCIO, codigo, 1)
