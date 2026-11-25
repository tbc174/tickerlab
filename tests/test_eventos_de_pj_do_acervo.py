"""A cola dos eventos de PJ com o acervo e o registro de coletas (`src/eventos_de_pj/acervo.py`, linha 414).

Tudo sintético, com o banco e o acervo da pasta do teste (sem internet e sem servidor): o que os
adaptadores de `fidc.py` e `cadastro_cvm.py` recebem pronto aqui é lido das versões guardadas.
Pessoa e linha de dado real não entram: só CNPJs de mentira e contagens.
"""

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime

import pytest

from base import cnpj as cnpj_base
from base.arquivo.fontes import FIDC_DO_MES
from base.cadastro import FONTE_DO_CADASTRO
from src import acervo
from src.banco.coletas import registrar_arquivo
from src.demonstracoes import URL_DO_CADASTRO
from src.eventos_de_pj import acervo as cola
from src.eventos_de_pj.evento import (
    FONTE_FALHOU,
    MUDOU,
    NAO_OBSERVADO,
    Tentativa,
    como_era_em,
)

FONTE_DO_FIDC = "cvm-fidc-recente"


def _cnpj(k: int) -> str:
    base12 = f"{k:08d}0001"
    return base12 + cnpj_base.digitos_verificadores(base12)


A, B, C, D = (_cnpj(k) for k in (1, 2, 3, 4))
JULHO, AGOSTO = date(2026, 7, 31), date(2026, 8, 31)
PRAZO_DE_AGOSTO = date(2026, 10, 15)  # 31/08 + 45 dias


def _quando(dia: date, hora: int = 12) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, tzinfo=UTC)


def _guardar(banco, fonte: str, url: str, conteudo: bytes, quando: datetime) -> None:
    """Uma coleta boa: o original no acervo e a linha no registro."""
    caminho = acervo.guardar_original(fonte, url, conteudo, quando)
    with banco.begin() as conexao:
        registrar_arquivo(
            conexao,
            fonte,
            url,
            hashlib.sha256(conteudo).hexdigest(),
            len(conteudo),
            "ok",
            None,
            quando,
            caminho,
        )


def _falhar(banco, fonte: str, url: str, quando: datetime) -> None:
    with banco.begin() as conexao:
        registrar_arquivo(conexao, fonte, url, None, None, "falhou", "erro", quando)


# ---------------------------------------------------------------- FIDC


def _informe_zip(mes: date, fundos: dict[str, int]) -> bytes:
    """Um zip do informe com só a tabela I: o CNPJ do fundo e o crédito inadimplente (de 1.000)."""
    linhas = "".join(
        f"FIDC;{cnpj_base.formatar(cnpj)};FIDC EXEMPLO;{mes.isoformat()};1000;{inad}\n"
        for cnpj, inad in fundos.items()
    )
    cabecalho = "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TAB_I2_VL_CARTEIRA;TAB_I2A3_VL_CRED_INAD\n"
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            f"inf_mensal_fidc_tab_I_{mes:%Y%m}.csv", (cabecalho + linhas).encode()
        )
    return conteudo.getvalue()


def _endereco(mes: date) -> str:
    return FIDC_DO_MES.format(aaaamm=f"{mes:%Y%m}")


@pytest.fixture
def fidc_guardado(banco):
    """Julho com A, B, C (lido em 20/08); agosto sem B, com A em quebra (lido em 20/09) e, depois,
    uma regravação (20/10) que acrescenta D e não muda nada do que já se via."""
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(JULHO),
        _informe_zip(JULHO, {A: 10, B: 10, C: 10}),
        _quando(date(2026, 8, 20)),
    )
    agosto = {A: 120, C: 10}
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(AGOSTO),
        _informe_zip(AGOSTO, agosto),
        _quando(date(2026, 9, 20)),
    )
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(AGOSTO),
        _informe_zip(AGOSTO, {**agosto, D: 10}),
        _quando(date(2026, 10, 20)),
    )
    return banco


def _estados(eventos) -> list[tuple[str, str, str]]:
    return [(e.estado, e.objeto_id, e.assunto) for e in eventos]


def test_fidc_le_as_versoes_do_acervo_e_acha_os_tres_estados(fidc_guardado):
    with fidc_guardado.connect() as conexao:
        eventos = cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO])
    assert (NAO_OBSERVADO, B, "leitura") in _estados(eventos)  # B não entregou agosto
    assert (MUDOU, A, "fidc_inadimplencia_limite_quebra") in _estados(eventos)
    ausentes = [e for e in eventos if e.estado == NAO_OBSERVADO]
    assert {e.publico_em for e in ausentes} == {PRAZO_DE_AGOSTO}
    # D só apareceu na regravação de 20/10, depois do prazo: nunca foi "esperado" nem "ausente"
    assert D not in {e.objeto_id for e in eventos}


def test_fidc_mes_sem_leitura_boa_vira_fonte_falhou_e_nao_ausencia(banco):
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(JULHO),
        _informe_zip(JULHO, {A: 10, B: 10}),
        _quando(date(2026, 8, 20)),
    )
    _falhar(banco, FONTE_DO_FIDC, _endereco(AGOSTO), _quando(date(2026, 10, 1)))
    with banco.connect() as conexao:
        eventos = cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO])
    falhas = [e for e in eventos if e.estado == FONTE_FALHOU]
    assert {(e.objeto_id, e.publico_em) for e in falhas} == {
        (A, PRAZO_DE_AGOSTO),
        (B, PRAZO_DE_AGOSTO),
    }
    assert not [e for e in eventos if e.estado == NAO_OBSERVADO]


def test_fidc_as_tentativas_sao_do_mes_pelo_fim_do_mes(fidc_guardado):
    _falhar(fidc_guardado, FONTE_DO_FIDC, _endereco(AGOSTO), _quando(date(2026, 9, 1)))
    with fidc_guardado.connect() as conexao:
        tentativas = cola.tentativas_do_fidc(conexao, [AGOSTO])
    assert tentativas == [
        Tentativa(AGOSTO, date(2026, 9, 1), ok=False),
        Tentativa(AGOSTO, date(2026, 9, 20), ok=True),
        Tentativa(AGOSTO, date(2026, 10, 20), ok=True),
    ]


@pytest.mark.parametrize(
    "corte",
    [date(2026, 8, 25), date(2026, 9, 30), PRAZO_DE_AGOSTO, date(2026, 10, 25)],
)
def test_fidc_cortar_o_futuro_nao_muda_o_passado(fidc_guardado, corte):
    """Só com as versões guardadas até o corte, saem os mesmos eventos de antes do corte."""
    with fidc_guardado.connect() as conexao:
        com_tudo = cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO])
        so_o_passado = cola.eventos_do_fidc_do_acervo(
            conexao, [JULHO, AGOSTO], como_em=corte
        )
    assert so_o_passado == como_era_em(com_tudo, corte)
    assert all(e.publico_em <= corte for e in so_o_passado)


def test_fidc_a_versao_guardada_depois_do_corte_nao_aparece_no_passado(banco):
    """A regravação que corrige o valor (20/10) não reescreve o que se via em 30/09."""
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(JULHO),
        _informe_zip(JULHO, {A: 10}),
        _quando(date(2026, 8, 20)),
    )
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(AGOSTO),
        _informe_zip(AGOSTO, {A: 120}),
        _quando(date(2026, 9, 20)),
    )
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(AGOSTO),
        _informe_zip(AGOSTO, {A: 10}),  # a CVM corrigiu: já não quebra
        _quando(date(2026, 10, 20)),
    )
    with banco.connect() as conexao:
        antes = cola.eventos_do_fidc_do_acervo(
            conexao, [JULHO, AGOSTO], como_em=date(2026, 10, 16)
        )
        hoje = cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO])
    assert (MUDOU, A, "fidc_inadimplencia_limite_quebra") in _estados(antes)
    assert (MUDOU, A, "fidc_inadimplencia_limite_quebra") not in _estados(hoje)


def test_fidc_nada_existe_antes_do_dia_da_primeira_versao_guardada(banco):
    """Agosto só foi guardado em 20/11, bem depois do prazo (15/10): o evento é de 20/11."""
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(JULHO),
        _informe_zip(JULHO, {A: 10}),
        _quando(date(2026, 8, 20)),
    )
    _guardar(
        banco,
        FONTE_DO_FIDC,
        _endereco(AGOSTO),
        _informe_zip(AGOSTO, {A: 120}),
        _quando(date(2026, 11, 20)),
    )
    with banco.connect() as conexao:
        antes = cola.eventos_do_fidc_do_acervo(
            conexao, [JULHO, AGOSTO], como_em=date(2026, 11, 19)
        )
        depois = cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO])
    assert not [e for e in antes if e.estado == MUDOU]
    quebra = [e for e in depois if e.assunto == "fidc_inadimplencia_limite_quebra"]
    assert [e.publico_em for e in quebra] == [date(2026, 11, 20)]


def test_fidc_so_os_fundos_pedidos(fidc_guardado):
    with fidc_guardado.connect() as conexao:
        eventos = cola.eventos_do_fidc_do_acervo(
            conexao, [JULHO, AGOSTO], cnpjs=[cnpj_base.formatar(B)]
        )
    assert {e.objeto_id for e in eventos} == {B}


def test_fidc_sem_nada_no_acervo_nao_inventa_evento(banco):
    with banco.connect() as conexao:
        assert cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO]) == []


def test_fidc_original_fora_do_acervo_e_pulado_sem_erro(fidc_guardado, tmp_path):
    for arquivo in (tmp_path / "acervo").rglob("*"):
        if arquivo.is_file():
            arquivo.unlink()
    with fidc_guardado.connect() as conexao:
        eventos = cola.eventos_do_fidc_do_acervo(conexao, [JULHO, AGOSTO])
    assert not [e for e in eventos if e.estado == MUDOU]


def test_meses_ate_traz_os_ultimos_meses_em_ordem():
    assert cola.meses_ate(date(2026, 10, 3), 3) == [
        date(2026, 7, 31),
        date(2026, 8, 31),
        date(2026, 9, 30),
    ]
    assert cola.meses_ate(date(2026, 1, 15), 2) == [
        date(2025, 11, 30),
        date(2025, 12, 31),
    ]


# ---------------------------------------------------------------- cadastro de companhias abertas


def _cadastro_csv(*linhas: tuple[str, str, str]) -> bytes:
    cabecalho = (
        "CNPJ_CIA;DENOM_SOCIAL;DT_REG;DT_CANCEL;MOTIVO_CANCEL;SIT;SETOR_ATIV;UF\n"
    )
    corpo = "".join(
        f"{cnpj_base.formatar(cnpj)};{empresa};2010-01-04;"
        f"{'' if situacao == 'ATIVO' else '2026-09-10'};"
        f"{'' if situacao == 'ATIVO' else 'CANCELAMENTO VOLUNTARIO'};{situacao};"
        "Energia Eletrica;SP\n"
        for cnpj, empresa, situacao in linhas
    )
    return (cabecalho + corpo).encode("latin-1")


@pytest.fixture
def cadastro_guardado(banco):
    """Agosto (3/8), setembro (12/9, A cancelada) e outubro (2/10, B saiu do arquivo)."""
    versoes = [
        (date(2026, 8, 3), (A, "ALFA SA", "ATIVO"), (B, "BETA SA", "ATIVO")),
        (date(2026, 9, 12), (A, "ALFA SA", "CANCELADA"), (B, "BETA SA", "ATIVO")),
        (date(2026, 10, 2), (A, "ALFA SA", "CANCELADA")),
    ]
    for dia, *linhas in versoes:
        _guardar(
            banco,
            FONTE_DO_CADASTRO,
            URL_DO_CADASTRO,
            _cadastro_csv(*linhas),
            _quando(dia),
        )
    return banco


def test_cadastro_le_as_versoes_guardadas_e_acha_mudou_e_nao_observado(
    cadastro_guardado,
):
    with cadastro_guardado.connect() as conexao:
        eventos = cola.eventos_do_cadastro_cvm_do_acervo(
            conexao, ate=date(2026, 10, 31)
        )
    estados = _estados(eventos)
    assert (MUDOU, A, "situacao") in estados
    assert (NAO_OBSERVADO, B, "leitura") in estados
    # o evento é do dia em que a versão foi guardada, não do dia do fato (cancelamento de 10/09)
    mudou = next(e for e in eventos if e.estado == MUDOU and e.assunto == "situacao")
    assert mudou.publico_em == date(2026, 9, 12)
    saiu = next(e for e in eventos if e.estado == NAO_OBSERVADO)
    assert saiu.publico_em == date(2026, 10, 2)


def test_cadastro_mes_sem_nenhuma_tentativa_boa_vira_fonte_falhou(cadastro_guardado):
    _falhar(
        cadastro_guardado,
        FONTE_DO_CADASTRO,
        URL_DO_CADASTRO,
        _quando(date(2026, 8, 20)),
    )
    # novembro inteiro sem leitura boa: só uma tentativa que falhou
    _falhar(
        cadastro_guardado,
        FONTE_DO_CADASTRO,
        URL_DO_CADASTRO,
        _quando(date(2026, 11, 10)),
    )
    with cadastro_guardado.connect() as conexao:
        eventos = cola.eventos_do_cadastro_cvm_do_acervo(
            conexao, ate=date(2026, 11, 30)
        )
    falhas = [e for e in eventos if e.estado == FONTE_FALHOU]
    assert {e.publico_em for e in falhas} == {date(2026, 11, 30)}


@pytest.mark.parametrize(
    "corte",
    [date(2026, 8, 20), date(2026, 9, 12), date(2026, 9, 30), date(2026, 10, 2)],
)
def test_cadastro_cortar_o_futuro_nao_muda_o_passado(cadastro_guardado, corte):
    with cadastro_guardado.connect() as conexao:
        com_tudo = cola.eventos_do_cadastro_cvm_do_acervo(
            conexao, ate=date(2026, 10, 31)
        )
        so_o_passado = cola.eventos_do_cadastro_cvm_do_acervo(conexao, ate=corte)
    assert so_o_passado == como_era_em(com_tudo, corte)


def test_cadastro_so_as_companhias_pedidas(cadastro_guardado):
    with cadastro_guardado.connect() as conexao:
        eventos = cola.eventos_do_cadastro_cvm_do_acervo(
            conexao, ate=date(2026, 10, 31), cnpjs=[cnpj_base.formatar(B)]
        )
    assert {e.objeto_id for e in eventos} == {B}


def test_cadastro_as_versoes_chegam_com_o_dia_em_que_foram_guardadas(cadastro_guardado):
    with cadastro_guardado.connect() as conexao:
        versoes = cola.versoes_do_cadastro_cvm(conexao, ate=date(2026, 9, 30))
    assert [dia for dia, _ in versoes] == [date(2026, 8, 3), date(2026, 9, 12)]
    assert {"cnpj", "situacao", "registro"} <= set(versoes[0][1].columns)


def test_cadastro_sem_nada_guardado_nao_inventa_evento(banco):
    with banco.connect() as conexao:
        assert (
            cola.eventos_do_cadastro_cvm_do_acervo(conexao, ate=date(2026, 10, 31))
            == []
        )


def test_cadastro_original_fora_do_acervo_e_pulado_sem_erro(
    cadastro_guardado, tmp_path
):
    for arquivo in (tmp_path / "acervo").rglob("*"):
        if arquivo.is_file():
            arquivo.unlink()
    with cadastro_guardado.connect() as conexao:
        assert cola.versoes_do_cadastro_cvm(conexao, ate=date(2026, 10, 31)) == []


def test_o_dia_da_tentativa_e_o_de_sao_paulo_como_o_da_versao(banco):
    """01h de 21/09 em UTC ainda é 20/09 em São Paulo: o dia em que a base viu o arquivo."""
    _falhar(
        banco,
        FONTE_DO_CADASTRO,
        URL_DO_CADASTRO,
        datetime(2026, 9, 21, 1, tzinfo=UTC),
    )
    with banco.connect() as conexao:
        tentativas = cola.tentativas_do_cadastro_cvm(conexao, ate=date(2026, 9, 30))
    assert tentativas == [Tentativa(date(2026, 9, 20), date(2026, 9, 20), ok=False)]
