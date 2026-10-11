"""Muda o plano de um usuário pela linha de comando (até o painel de administração existir).

Uso, dentro do contêiner do servidor:
    docker exec tickerlab python -m src.banco.mudar_plano pessoa@exemplo.com pro
"""

import sys

from src.banco.conexao import obter_engine
from src.banco.modelo import PLANOS
from src.banco.usuarios import buscar_por_email, mudar_plano


def main(argumentos: list[str]) -> int:
    if len(argumentos) != 2 or argumentos[1] not in PLANOS:
        print(f"Uso: python -m src.banco.mudar_plano EMAIL {{{'|'.join(PLANOS)}}}")
        return 2
    email, plano = argumentos
    with obter_engine().begin() as conexao:
        usuario = buscar_por_email(conexao, email)
        if usuario is None:
            print("Nenhum usuário com esse e-mail (a pessoa precisa entrar uma vez).")
            return 1
        mudar_plano(conexao, usuario.id, plano)
    print(f"Plano de {usuario.email} agora é {plano}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
