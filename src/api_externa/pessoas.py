"""Sócios e donos pela API por chave (ADR 0128, Emenda 4, 18/11/2026): só para a organização com a permissão.

`GET /data/v1/companies/{cnpj}/people` devolve, do cadastro público da Receita, os sócios pessoa física adultos
do CNPJ (nome, qualificação e data de entrada) e, no MEI e no empresário individual, o nome do titular, sem os
dígitos do CPF que a razão social traz. Nada de CPF (inteiro, mascarado ou o da ligação), menor de idade,
endereço ou contato: o acervo já nasce sem eles (`scripts/montar_acervo_pessoa.py`, com as oposições), e esta
resposta passa por uma varredura por máquina antes de sair (`falhas_da_resposta`).

Quem vê: a chave de uma organização cujo contrato tem a linha `pessoa_no_conector`, finalidade `analise`,
vigente no dia. É outra linha que a `pessoa_na_tela` da tela com login, para que ligar a tela não abra a API
sem querer. Nasce desligada; ligar numa organização em produção é só do Tiago (`conceder-direito`). O acervo
de pessoa fica fora da base e é lido só por `src/analista/pessoa.py`: nada daqui passa pela Porta nem pelo
portão, e a rota não entra no contrato público da `/data/v1`.

Sem Streamlit e sem banco: entra a pasta do acervo e o CNPJ, sai o corpo em tipos simples, já com os nomes de
fora (em inglês). Quem confere a permissão, audita e conta o consumo é a rota (`src/api_externa/rotas.py`).
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from src.analista import pessoa
from src.pessoa_no_texto import telefone_no_texto, texto_de_pessoa

CONJUNTO = "pessoa_no_conector"
TIPO_DA_AUDITORIA = "socios_e_donos"
CANAL_DA_AUDITORIA = "api_externa"

PRONTA = "ready"
SEM_PESSOA = "no_people"
SEM_TITULAR = "none"
TITULARES_FORA_DO_AR = "unavailable"

# a lista fechada de chaves que a resposta pode ter, em qualquer profundidade (o "detail" é o dos erros)
CHAVES_DA_RESPOSTA = frozenset(
    {
        "status", "partners", "partners_total", "owners", "owners_status", "name", "role",
        "since", "source", "attribution", "snapshot_month", "limits",
    }
)  # fmt: skip
# CEP com ou sem hífen, nunca colado a outro dígito
_CEP = re.compile(r"(?<!\d)\d{5}-?\d{3}(?!\d)")
_DIGITO = re.compile(r"\d")
_ESPACOS = re.compile(r"\s+")

LIMITES = (
    *pessoa.LIMITES,
    pessoa.LIMITES_DO_TITULAR[0],
    pessoa.LIMITES_DO_TITULAR[1],
    "Sem CPF, sem data de nascimento, sem endereço e sem contato da pessoa. Quem pediu oposição não aparece.",
)


class RespostaComPessoaProibida(Exception):
    """A resposta montada falhou na varredura; `caminhos` diz onde (nunca o valor)."""

    def __init__(self, caminhos: list[str]) -> None:
        super().__init__(f"varredura de pessoa falhou em {len(caminhos)} lugar(es)")
        self.caminhos = caminhos


def _texto_proibido(texto: str) -> bool:
    return (
        texto_de_pessoa(texto) or telefone_no_texto(texto) or bool(_CEP.search(texto))
    )


def _falhas(valor: object, caminho: str) -> Iterator[str]:
    if isinstance(valor, dict):
        for chave, filho in valor.items():
            onde = f"{caminho}.{chave}" if caminho else str(chave)
            if chave not in CHAVES_DA_RESPOSTA:
                yield onde
            yield from _falhas(filho, onde)
    elif isinstance(valor, list):
        for indice, filho in enumerate(valor):
            yield from _falhas(filho, f"{caminho}[{indice}]")
    elif isinstance(valor, str) and _texto_proibido(valor):
        yield caminho or "(raiz)"


def falhas_da_resposta(corpo: object) -> list[str]:
    """Onde a resposta foge da regra: chave fora da lista fechada (CPF, nascimento, idade, endereço, contato
    não estão nela) ou texto com CPF (formatado, mascarado ou onze dígitos que conferem), e-mail, telefone ou
    CEP. Devolve o caminho de cada falha, nunca o valor."""
    return list(_falhas(corpo, ""))


def _sem_digitos(nome: str) -> str:
    """O nome sem nenhum dígito: a razão social do MEI traz o CPF colado ao nome."""
    return _ESPACOS.sub(" ", _DIGITO.sub("", nome)).strip()


def _socio(socio: dict[str, str | None]) -> dict[str, str | None]:
    return {
        "name": _sem_digitos(socio["nome"] or ""),
        "role": socio["qualificacao"],
        "since": socio["entrou_em"],
    }


def _titulares(pasta: Path, cnpj: str) -> tuple[pessoa.Titular | None, str]:
    """O titular do MEI ou do empresário individual; sem a tabela neste servidor, None e o aviso."""
    if not (pasta / pessoa.INDIVIDUAIS).is_dir():
        return None, TITULARES_FORA_DO_AR
    titular = pessoa.titular_da_empresa(pasta, cnpj)
    return titular, (PRONTA if titular.titulares else SEM_TITULAR)


def pessoas_da_empresa(pasta: Path, cnpj: str) -> dict[str, object]:
    """O corpo da resposta, já varrido. `pessoa.CnpjInvalidoError` se o CNPJ é inválido,
    `pessoa.AcervoIndisponivelError` se o acervo não pôde ser lido e `RespostaComPessoaProibida` se a
    varredura achou algo que não pode sair."""
    socios = pessoa.socios_da_empresa(pasta, cnpj)
    titular, estado_dos_titulares = _titulares(pasta, cnpj)
    donos = [] if titular is None else [
        {"name": _sem_digitos(t["nome"])} for t in titular.titulares
    ]  # fmt: skip
    meses = [socios.mes_do_retrato, titular.mes_do_retrato if titular else None]
    corpo: dict[str, object] = {
        "status": PRONTA if socios.socios or donos else SEM_PESSOA,
        "partners": [_socio(s) for s in socios.socios],
        "partners_total": socios.total,
        "owners": donos,
        "owners_status": estado_dos_titulares,
        "source": pessoa.FONTE,
        "attribution": {
            "partners": pessoa.ATRIBUICAO,
            "owners": pessoa.ATRIBUICAO_DO_TITULAR,
        },
        "snapshot_month": next((m for m in meses if m), None),
        "limits": list(LIMITES),
    }
    falhas = falhas_da_resposta(corpo)
    if falhas:
        raise RespostaComPessoaProibida(falhas)
    return corpo


def linhas_servidas(corpo: dict[str, object]) -> int:
    """Quantas pessoas saíram (sócios mais titulares): o número da auditoria e do consumo."""
    return len(cast(list, corpo["partners"])) + len(cast(list, corpo["owners"]))
