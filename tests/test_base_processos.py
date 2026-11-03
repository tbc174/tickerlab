"""Processos judiciais por CNPJ (`base/processos.py`). Tudo aqui é inventado: as companhias, as
pessoas e os processos não existem (os números só têm o dígito verificador certo)."""

import hashlib
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import numero_cnj, processos
from base.arquivo import djen
from src.banco import coletas
from src.banco.coletas import com_registro

AGORA = datetime(2026, 11, 3, 6, tzinfo=UTC)
CNPJ_A = "11222333000181"
CNPJ_B = "44555666000199"
PESSOA = "FULANA INVENTADA DE TAL"
EMPRESINHA = "PADARIA INVENTADA LTDA"
CADASTRO = pd.DataFrame(
    {
        "cnpj": [
            "11.222.333/0001-81",
            "44.555.666/0001-99",
            "77.888.999/0001-00",
            "12.345.678/0001-00",
        ],
        "empresa": [
            "ENERGIA EXEMPLO S.A.",
            "CIA. FICTICIA DE AGUAS",
            "HOMONIMA SA",
            "HOMÔNIMA S/A",
        ],
    }
)


def _numero(sequencial: int, segmento: str = "8", tribunal: str = "26") -> str:
    partes = (f"{sequencial:07d}", "2024", segmento, tribunal, "0100")
    digito = numero_cnj.digito_esperado(*partes)
    return f"{partes[0]}{digito}{''.join(partes[1:])}"


def _item(hash_: str, numero: str, *partes: tuple[str, str], **outros) -> dict:
    return {
        "id": int(hashlib.sha256(hash_.encode()).hexdigest()[:6], 16),
        "hash": hash_,
        "numero_processo": numero,
        "siglaTribunal": "TJSP",
        "nomeOrgao": "1ª Vara Cível de Teste",
        "codigoClasse": "7",
        "nomeClasse": "PROCEDIMENTO COMUM CíVEL",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "SENTENçA",
        "data_disponibilizacao": "2026-10-28",
        "data_cancelamento": None,
        "destinatarios": [{"nome": n, "polo": p} for n, p in partes],
        "quantidade_de_advogados": 3,
        "texto": f"{PESSOA} contra a ENERGIA EXEMPLO S.A.",
        **outros,
    }


@pytest.mark.parametrize(
    ("nome", "normalizado"),
    [
        ("Energia Exemplo S.A.", "ENERGIA EXEMPLO SA"),
        ("ENERGIA EXEMPLO S/A", "ENERGIA EXEMPLO SA"),
        ("CIA. FICTÍCIA DE ÁGUAS", "COMPANHIA FICTICIA DE AGUAS"),
        (
            "COMPANHIA PIRATININGA DE FORçA E LUZ _CPFL",
            "COMPANHIA PIRATININGA DE FORCA E LUZ",
        ),
        ("EXEMPLO S.A. - EM RECUPERAÇÃO JUDICIAL", "EXEMPLO SA"),
        ("Padaria Ltda.", "PADARIA LTDA"),
    ],
)
def test_normalizar_nome(nome: str, normalizado: str):
    assert processos.normalizar_nome(nome) == normalizado


def test_homonimo_do_cadastro_nao_liga():
    razoes = processos.razoes_sociais(CADASTRO)
    assert razoes["ENERGIA EXEMPLO SA"] == (CNPJ_A, "ENERGIA EXEMPLO S.A.")
    assert razoes["COMPANHIA FICTICIA DE AGUAS"] == (CNPJ_B, "CIA. FICTICIA DE AGUAS")
    assert razoes["HOMONIMA SA"] is None
    assert processos.tipo_da_parte("HOMONIMA SA", razoes) == processos.PESSOA_JURIDICA


@pytest.mark.parametrize(
    ("nome", "tipo"),
    [
        ("ENERGIA EXEMPLO SA", processos.COMPANHIA),
        ("MUNICIPIO DE CAMPINAS", processos.ORGAO_PUBLICO),
        ("ESTADO DE SAO PAULO", processos.ORGAO_PUBLICO),
        ("FAZENDA NACIONAL", processos.ORGAO_PUBLICO),
        ("FAZENDA PUBLICA DO ESTADO DE SAO PAULO", processos.ORGAO_PUBLICO),
        ("FAZENDA DO ESTADO DE MINAS GERAIS", processos.ORGAO_PUBLICO),
        # imóvel rural, às vezes de pessoa física: o nome não pode ir para `orgao_publico`
        ("FAZENDA BOA VISTA", processos.PESSOA_OU_DESCONHECIDA),
        ("MINISTERIO PUBLICO DO ESTADO DE SAO PAULO", processos.ORGAO_PUBLICO),
        ("PADARIA INVENTADA LTDA", processos.PESSOA_JURIDICA),
        ("FULANA INVENTADA DE TAL", processos.PESSOA_OU_DESCONHECIDA),
    ],
)
def test_tipo_da_parte(nome: str, tipo: str):
    assert processos.tipo_da_parte(nome, processos.razoes_sociais(CADASTRO)) == tipo


def _carimbado(item: dict, dia: date) -> dict:
    return {
        **item,
        "_visto_em": pd.Timestamp(dia),
        "origem_sha256": "s" * 64,
        "origem_coletada_em": f"{dia}T03:00:00+00:00",
    }


def _tabelas(*itens: dict, dia: date = date(2026, 11, 2)):
    return processos.tabelas(
        [_carimbado(i, dia) for i in itens], processos.razoes_sociais(CADASTRO)
    )


def test_partes_viram_tipos_sem_nome_de_pessoa():
    item = _item(
        "h1",
        _numero(1),
        (PESSOA, "A"),
        (EMPRESINHA, "A"),
        ("Energia Exemplo S.A.", "P"),
        ("MUNICIPIO DE CAMPINAS", "P"),
    )
    comunicacoes, partes, contagem = _tabelas(item)

    linha = comunicacoes.iloc[0]
    assert linha["numero_processo"] == numero_cnj.decodificar(_numero(1)).formatado
    assert (linha["ano_do_processo"], linha["justica"]) == (2024, "Justiça Estadual")
    assert (linha["classe"], linha["tipo_documento"]) == (
        "PROCEDIMENTO COMUM CÍVEL",
        "SENTENÇA",
    )
    assert (linha["companhias"], linha["orgaos_publicos"]) == (1, 1)
    assert (linha["pessoas_juridicas"], linha["pessoas_ou_desconhecidas"]) == (1, 1)
    assert linha["advogados"] == 3
    assert linha["disponivel_em"] == pd.Timestamp("2026-10-28")
    assert partes[["polo", "tipo_parte", "cnpj"]].fillna("").to_dict("records") == [
        {"polo": "passivo", "tipo_parte": "companhia", "cnpj": CNPJ_A},
        {"polo": "passivo", "tipo_parte": "orgao_publico", "cnpj": ""},
    ]
    gravado = comunicacoes.astype(str).to_csv() + partes.astype(str).to_csv()
    assert PESSOA not in gravado
    assert "PADARIA" not in gravado
    assert "texto" not in comunicacoes
    assert contagem["lidas"] == 1


def test_sai_o_trabalho_o_numero_errado_e_a_comunicacao_sem_companhia():
    errado = _numero(2)[:7] + "00" + _numero(2)[9:]
    _, _, contagem = _tabelas(
        _item(
            "t", _numero(3, segmento="5", tribunal="02"), ("ENERGIA EXEMPLO SA", "P")
        ),
        _item("e", errado, ("ENERGIA EXEMPLO SA", "P")),
        _item("s", _numero(4), (PESSOA, "A"), ("HOMONIMA S.A.", "P")),
        _item("ok", _numero(5), ("ENERGIA EXEMPLO SA", "P")),
    )
    assert contagem == {
        "lidas": 4,
        "do_trabalho": 1,
        "numero_invalido": 1,
        "sem_companhia": 1,
        "homonimos": 1,
    }


def test_a_mesma_comunicacao_em_duas_consultas_fica_a_mais_recente():
    antes = _carimbado(
        _item("h", _numero(6), ("ENERGIA EXEMPLO SA", "P")), date(2026, 11, 2)
    )
    depois = _carimbado(
        _item(
            "h", _numero(6), ("ENERGIA EXEMPLO SA", "P"), data_cancelamento="2026-11-10"
        ),
        date(2026, 12, 1),
    )
    comunicacoes, partes, _ = processos.tabelas(
        [depois, antes], processos.razoes_sociais(CADASTRO)
    )
    assert len(comunicacoes) == len(partes) == 1
    assert comunicacoes.iloc[0]["cancelada_em"] == pd.Timestamp("2026-11-10")
    assert comunicacoes.iloc[0]["visto_em"] == pd.Timestamp("2026-12-01")


def test_disponivel_em_nunca_depois_do_dia_em_que_vimos():
    item = _item(
        "h", _numero(7), ("ENERGIA EXEMPLO SA", "P"), data_disponibilizacao="2026-12-31"
    )
    comunicacoes, _, _ = _tabelas(item, dia=date(2026, 11, 2))
    assert comunicacoes.iloc[0]["disponivel_em"] == pd.Timestamp("2026-11-02")


def _coletar(banco, url: str, itens: list[dict], dia: date) -> None:
    conteudo = json.dumps({"consulta": {}, "items": itens}).encode()
    com_registro(djen.ID, lambda _url: conteudo)(url)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(coletas.coletas)
            .where(coletas.coletas.c.url == url)
            .values(baixado_em=datetime(dia.year, dia.month, dia.day, 3, tzinfo=UTC))
        )


def test_montar_grava_as_duas_tabelas_e_pula_o_ja_montado(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    semana = djen.consulta(
        "ENERGIA EXEMPLO S.A.", date(2026, 10, 26), date(2026, 11, 1)
    )
    _coletar(
        banco,
        semana,
        [_item("h1", _numero(8), (PESSOA, "A"), ("ENERGIA EXEMPLO S.A.", "P"))],
        date(2026, 11, 2),
    )
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        resumo = processos.montar(conexao, pasta, AGORA, cadastro=CADASTRO)
        de_novo = processos.montar(conexao, pasta, AGORA, cadastro=CADASTRO)

    assert (resumo["comunicacoes"], resumo["partes"], resumo["consultas"]) == (1, 1, 1)
    assert de_novo == processos.JA_MONTADO
    comunicacoes = pd.read_parquet(pasta / "processos_comunicacoes" / "djen.parquet")
    partes = pd.read_parquet(pasta / "processos_partes" / "djen.parquet")
    assert comunicacoes["versao_do_codigo"].iloc[0] == "0123abc"
    assert len(comunicacoes["origem_sha256"].iloc[0]) == 64
    assert partes["cnpj"].tolist() == [CNPJ_A]
    for manifesto in pasta.rglob("*.json"):
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name
    gravado = "".join(
        p.read_bytes().decode("latin-1") for p in pasta.rglob("*") if p.is_file()
    )
    assert PESSOA not in gravado


def test_montar_sem_consulta_guardada_e_vazio(banco, tmp_path):
    with banco.connect() as conexao:
        assert processos.montar(conexao, tmp_path, AGORA, cadastro=CADASTRO) == {}


def test_montar_sem_cadastro_no_acervo_falha(banco, tmp_path, monkeypatch):
    monkeypatch.setattr(processos, "cadastro_do_acervo", lambda _conexao: None)
    url = djen.consulta("ENERGIA EXEMPLO S.A.", date(2026, 10, 26), date(2026, 11, 1))
    _coletar(banco, url, [], date(2026, 11, 2))
    with banco.connect() as conexao, pytest.raises(ValueError, match="cadastro"):
        processos.montar(conexao, tmp_path, AGORA)


def test_comando_monta_e_sem_nada_guardado_sai_com_1(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    origem = {"url": "https://exemplo.invalid/cadastro.csv", "sha256": "c" * 64}
    monkeypatch.setattr(
        processos, "cadastro_do_acervo", lambda _conexao: (CADASTRO, origem)
    )
    from scripts import carga_processos

    assert carga_processos.main(["--pasta", str(tmp_path / "b")]) == 1
    url = djen.consulta("ENERGIA EXEMPLO S.A.", date(2026, 10, 26), date(2026, 11, 1))
    item = _item("h", _numero(9), ("ENERGIA EXEMPLO SA", "P"))
    _coletar(banco, url, [item], date(2026, 11, 2))
    assert carga_processos.main(["--pasta", str(tmp_path / "b")]) == 0
    partes = pd.read_parquet(tmp_path / "b" / "processos_partes" / "djen.parquet")
    assert partes["cnpj"].tolist() == [CNPJ_A]
