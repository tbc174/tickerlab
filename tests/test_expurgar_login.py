"""O script do expurgo diário do login: roda no banco da configuração e conta o que apagou."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from scripts import expurgar_login
from src import codigo_de_entrada as cod
from src.banco.modelo import codigos_de_entrada


def test_o_script_apaga_o_codigo_vencido_ha_mais_de_um_dia(banco, caplog):
    agora = datetime.now(UTC)
    with banco.begin() as conexao:
        cod.pedir_codigo(conexao, "ana@exemplo.com", agora=agora - timedelta(days=3))
        cod.pedir_codigo(conexao, "bia@exemplo.com", agora=agora)
    with caplog.at_level("INFO", logger="tickerlab.expurgo"):
        assert expurgar_login.main() == 0
    with banco.connect() as conexao:
        restantes = conexao.execute(sa.select(codigos_de_entrada)).all()
    assert len(restantes) == 1
    assert "exemplo.com" not in caplog.text  # só contagens, nunca e-mail
