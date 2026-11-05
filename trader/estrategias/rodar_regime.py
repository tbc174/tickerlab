"""Rodada da ficha P0-8: trava enquanto nenhuma estratégia foi aprovada, sem gastar tentativa.

A ficha testa "cada estratégia aprovada com e sem o filtro". Aplicar o filtro a uma estratégia reprovada
seria resgatá-la depois de ver o resultado, o que a seção 10 proíbe. Então esta rodada só lê o registro:
- nenhuma aprovada → diz que a ficha não tem objeto e sai, sem registrar nada;
- alguma aprovada → lista quais e sai do mesmo jeito: a comparação dela, com o retorno diário da
  estratégia, é escrita num PR antes de rodar (o filtro está em `regime.py`).

Uso: `python -I -m trader.estrategias.rodar_regime`. Nada aqui é recomendação de investimento.
"""

from __future__ import annotations

import sys

from trader import criterio_quant
from trader.registro import Registro

FICHA = "P0-8"
SAIDA_SEM_OBJETO = 3
SAIDA_FALTA_A_COMPARACAO = 4
MENSAGEM_SEM_OBJETO = (
    "SEM OBJETO: nenhuma estratégia do registro foi aprovada no critério da seção 5; a ficha P0-8 testa "
    "só as aprovadas. Nenhuma tentativa foi registrada."
)
MENSAGEM_FALTA_A_COMPARACAO = (
    "APROVADAS: {nomes}. Escreva a comparação com e sem o filtro num PR antes de rodar; nenhuma "
    "tentativa foi registrada."
)

abrir_registro = criterio_quant.abrir_registro


def _foi_aprovada(resultado: dict | None) -> bool:
    """Só conta o veredito gravado pelo código; linha reconstruída sem veredito não é aprovação."""
    veredito = (resultado or {}).get("veredito")
    return isinstance(veredito, dict) and veredito.get("aprovado") is True


def aprovadas(registro: Registro) -> list[str]:
    """Nomes das tentativas do desenvolvimento aprovadas, fora estudo, monitor e a própria P0-8."""
    fora = (*criterio_quant.FICHAS_SEM_CRITERIO, FICHA)
    nomes = []
    for linha in registro.listar("desenvolvimento"):
        if linha["familia"] in fora:
            continue
        if _foi_aprovada(registro.obter(linha["id"])["resultado"]):
            nomes.append(f"{linha['familia']} {linha['nome']}")
    return nomes


def main(registro: Registro | None = None) -> int:
    criterio_quant.conferir()
    lista = aprovadas(registro if registro is not None else abrir_registro())
    if not lista:
        print(MENSAGEM_SEM_OBJETO)
        return SAIDA_SEM_OBJETO
    print(MENSAGEM_FALTA_A_COMPARACAO.format(nomes=", ".join(lista)))
    return SAIDA_FALTA_A_COMPARACAO


if __name__ == "__main__":
    sys.exit(main())
