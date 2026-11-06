"""As tabelas internas do DataJud (plano dos processos de 03/11/2026, PR 3): cada consulta guardada vira
um retrato do processo e os movimentos dele, sem olhar o futuro. Só uso interno (`FONTES_SO_INTERNAS`)."""

import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import dossie, processos_datajud
from base.arquivo import datajud
from base.dicionario import TABELAS
from base.numero_cnj import digito_esperado
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 11, 9, 4, tzinfo=UTC)


def _numero(
    sequencial: str = "0001234", segmento: str = "8", tribunal: str = "26"
) -> str:
    ano, origem = "2024", "0100"
    digito = digito_esperado(sequencial, ano, segmento, tribunal, origem)
    return f"{sequencial}{digito}{ano}{segmento}{tribunal}{origem}"


def _processo(
    numero: str, grau: str = "G1", movimentos: list[dict] | None = None
) -> dict:
    return {
        "numeroProcesso": numero,
        "tribunal": "TJSP",
        "grau": grau,
        "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
        "assuntos": [
            {"codigo": 7771, "nome": "Indenização"},
            {"codigo": 10439, "nome": "Dano"},
        ],
        "orgaoJulgador": {"codigo": 1234, "nome": "1ª Vara Cível"},
        "dataAjuizamento": "2024-02-03T00:00:00.000Z",
        "dataHoraUltimaAtualizacao": "2026-10-20T12:00:00.000Z",
        "nivelSigilo": 0,
        "sistema": {"codigo": 1, "nome": "Pje"},
        "formato": {"codigo": 1, "nome": "Eletrônico"},
        "movimentos": movimentos
        if movimentos is not None
        else [
            {
                "codigo": 26,
                "nome": "Distribuição",
                "dataHora": "2024-02-03T10:00:00.000Z",
            },
            {
                "codigo": 219,
                "nome": "Procedência",
                "dataHora": "2026-10-01T15:00:00.000Z",
                "complementosTabelados": [
                    {"codigo": 1, "nome": "tipo", "descricao": "sentença"}
                ],
            },
        ],
    }


def _coletar(banco, numero: str, ate: date, processos: list[dict], dia: date) -> None:
    url = datajud.alvo(numero, ate).url
    conteudo = json.dumps(
        {
            "consulta": {"numero": numero},
            "total_na_fonte": len(processos),
            "processos": processos,
        }
    ).encode()
    com_registro(datajud.ID, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(coletas.coletas.c.url == url)
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def test_montar_grava_o_retrato_e_os_movimentos(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    numero = _numero()
    _coletar(banco, numero, date(2026, 10, 1), [_processo(numero)], date(2026, 11, 2))
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        resumo = processos_datajud.montar(conexao, pasta, AGORA)
        de_novo = processos_datajud.montar(conexao, pasta, AGORA)

    assert resumo == {"consultas": 1, "retratos": 1, "movimentos": 2}
    assert de_novo == processos_datajud.JA_MONTADO
    retratos = pd.read_parquet(pasta / "processos_datajud" / "datajud.parquet")
    linha = retratos.iloc[0]
    assert linha["numero_processo"] == "0001234-" + numero[7:9] + ".2024.8.26.0100"
    assert (linha["tribunal"], linha["grau"], linha["classe_codigo"]) == (
        "TJSP",
        "G1",
        "7",
    )
    assert linha["assuntos_codigos"] == "7771;10439"
    assert linha["movimentos"] == 2
    assert str(linha["disponivel_em"]) == "2026-11-02"
    assert linha["versao_do_codigo"] == "0123abc"
    movimentos = pd.read_parquet(
        pasta / "processos_datajud_movimentos" / "datajud.parquet"
    )
    assert movimentos["movimento_codigo"].tolist() == ["26", "219"]
    assert movimentos["complementos"].tolist()[1] == "tipo: sentença"
    for manifesto in pasta.rglob("*.json"):
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name


def test_movimento_vale_desde_o_primeiro_dia_em_que_o_vimos(banco, tmp_path):
    """Sem olhar o futuro: o movimento de 01/10 visto em 02/11 só vale de 02/11; consultado de novo em
    09/11, continua valendo de 02/11, e o movimento novo vale de 09/11."""
    numero = _numero()
    primeiro = _processo(numero)
    segundo = _processo(
        numero,
        movimentos=[
            *primeiro["movimentos"],
            {
                "codigo": 848,
                "nome": "Trânsito em julgado",
                "dataHora": "2026-11-05T10:00:00Z",
            },
        ],
    )
    _coletar(banco, numero, date(2026, 10, 1), [primeiro], date(2026, 11, 2))
    _coletar(banco, numero, date(2026, 11, 6), [segundo], date(2026, 11, 9))
    with banco.connect() as conexao:
        processos_datajud.montar(conexao, tmp_path, AGORA)

    retratos = pd.read_parquet(tmp_path / "processos_datajud" / "datajud.parquet")
    assert [str(d) for d in retratos["disponivel_em"]] == ["2026-11-02", "2026-11-09"]
    movimentos = pd.read_parquet(
        tmp_path / "processos_datajud_movimentos" / "datajud.parquet"
    )
    por_codigo = dict(
        zip(
            movimentos["movimento_codigo"],
            movimentos["disponivel_em"].astype(str),
            strict=True,
        )
    )
    assert por_codigo == {"26": "2026-11-02", "219": "2026-11-02", "848": "2026-11-09"}


def test_processo_da_justica_do_trabalho_ou_com_numero_errado_nao_entra(
    banco, tmp_path
):
    numero = _numero()
    errado = {**_processo(numero), "numeroProcesso": "00012340020248260100"}
    _coletar(
        banco,
        numero,
        date(2026, 10, 1),
        [errado, _processo(numero, "G2")],
        date(2026, 11, 2),
    )
    with banco.connect() as conexao:
        processos_datajud.montar(conexao, tmp_path, AGORA)
    retratos = pd.read_parquet(tmp_path / "processos_datajud" / "datajud.parquet")
    assert retratos["grau"].tolist() == ["G2"]


def test_montar_sem_consulta_guardada_e_vazio(banco, tmp_path):
    with banco.connect() as conexao:
        assert processos_datajud.montar(conexao, tmp_path, AGORA) == {}


# --- só uso interno ---------------------------------------------------------------------------


@pytest.mark.parametrize("tabela", processos_datajud.TABELAS)
def test_as_tabelas_sao_so_internas(tabela):
    assert TABELAS[tabela].familia_da_fonte == "datajud"
    assert coletas.so_interna(TABELAS[tabela].familia_da_fonte)
    assert not dossie.pode_mostrar(tabela)
    with pytest.raises(dossie.TabelaProibidaError):
        dossie.exigir_que_pode_mostrar([tabela])


def test_a_carga_dos_processos_monta_o_datajud_mesmo_sem_djen(
    banco, tmp_path, monkeypatch
):
    """O DataJud lê só as consultas que o arquivista guardou: a carga monta as duas tabelas internas
    toda semana, com ou sem consulta nova do DJEN."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    numero = _numero()
    _coletar(banco, numero, date(2026, 10, 1), [_processo(numero)], date(2026, 11, 2))
    from scripts import carga_processos

    assert carga_processos.main(["--pasta", str(tmp_path / "b")]) == 1  # sem DJEN
    assert (tmp_path / "b" / "processos_datajud" / "datajud.parquet").exists()
