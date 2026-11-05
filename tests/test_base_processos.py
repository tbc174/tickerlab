"""Processos judiciais por CNPJ (`base/processos.py`). Tudo aqui é inventado: as companhias, as
pessoas e os processos não existem (os números só têm o dígito verificador certo)."""

import hashlib
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import sqlalchemy as sa

from base import conferencia_processos, numero_cnj, processos, processos_teor, tpu
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


def _carimbado(item: dict, dia: date, por: str = "nome") -> dict:
    return {
        **item,
        "_visto_em": pd.Timestamp(dia),
        "_achada_por": por,
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
        "ligadas_pelo_processo": 0,
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


def _coletar(
    banco, url: str, itens: list[dict], dia: date, fonte: str = djen.ID
) -> None:
    conteudo = json.dumps({"consulta": {}, "items": itens}).encode()
    com_registro(fonte, lambda _url: conteudo)(url)
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


def test_comando_monta_as_citacoes_da_dfp_mesmo_sem_djen(banco, tmp_path, monkeypatch):
    """As notas da DFP não dependem do DJEN: a carga monta `processos_nas_notas` de todo jeito."""
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    pastas = []
    monkeypatch.setattr(
        processos, "montar_citacoes", lambda pasta, _agora: pastas.append(pasta) or {}
    )
    from scripts import carga_processos

    assert carga_processos.main(["--pasta", str(tmp_path / "b")]) == 1
    assert pastas == [tmp_path / "b"]


# --- o segundo passo (pelo número) e a tabela `processos` (PR 1b) ----------------------------------


def _so_a_outra_parte(hash_: str, numero: str, dia: str) -> dict:
    """A comunicação do processo que intima só a outra parte (a companhia não está entre as partes)."""
    return _item(
        hash_,
        numero,
        (PESSOA, "A"),
        ("MUNICIPIO DE CAMPINAS", "P"),
        data_disponibilizacao=dia,
    )


def test_achada_pelo_numero_fica_se_o_processo_e_de_uma_companhia():
    ligado, solto = _numero(10), _numero(11)
    pelo_numero = date(2026, 11, 9)
    comunicacoes, partes, contagem = processos.tabelas(
        [
            _carimbado(
                _item("n", ligado, ("ENERGIA EXEMPLO SA", "P")), date(2026, 11, 2)
            ),
            _carimbado(
                _so_a_outra_parte("antes", ligado, "2026-10-20"), pelo_numero, "numero"
            ),
            _carimbado(
                _so_a_outra_parte("depois", ligado, "2026-11-04"), pelo_numero, "numero"
            ),
            _carimbado(
                _so_a_outra_parte("solto", solto, "2026-10-20"), pelo_numero, "numero"
            ),
        ],
        processos.razoes_sociais(CADASTRO),
    )
    por_id = comunicacoes.set_index("id_na_fonte")
    assert sorted(por_id.index) == ["antes", "depois", "n"]
    assert por_id.loc["antes", "achada_por"] == "numero"
    assert por_id.loc["n", "achada_por"] == "nome"
    assert por_id.loc["antes", "companhias"] == 0
    # a que saiu antes da ligação só vale a partir dela (cortar o futuro não muda o passado)
    assert por_id.loc["antes", "disponibilizada_em"] == pd.Timestamp("2026-10-20")
    assert por_id.loc["antes", "disponivel_em"] == pd.Timestamp("2026-10-28")
    assert por_id.loc["depois", "disponivel_em"] == pd.Timestamp("2026-11-04")
    das_outras = partes[partes["id_na_fonte"] == "antes"]
    assert das_outras["tipo_parte"].tolist() == ["orgao_publico"]
    assert das_outras["disponivel_em"].tolist() == [pd.Timestamp("2026-10-28")]
    assert (contagem["sem_companhia"], contagem["ligadas_pelo_processo"]) == (1, 2)
    gravado = comunicacoes.astype(str).to_csv() + partes.astype(str).to_csv()
    assert PESSOA not in gravado


def test_a_mesma_comunicacao_pelo_nome_e_pelo_numero_fica_achada_pelo_nome():
    item = _item("h", _numero(12), ("ENERGIA EXEMPLO SA", "P"))
    comunicacoes, _, _ = processos.tabelas(
        [
            _carimbado(item, date(2026, 11, 2)),
            _carimbado(item, date(2026, 11, 9), "numero"),
        ],
        processos.razoes_sociais(CADASTRO),
    )
    assert comunicacoes["achada_por"].tolist() == ["nome"]
    assert comunicacoes.iloc[0]["visto_em"] == pd.Timestamp("2026-11-09")


def _classe(codigo: int, pai: int | None, nome: str) -> dict:
    return {"cod_item": codigo, "cod_item_pai": pai, "nome": nome, "situacao": "A"}


CLASSES = tpu.ler_classes(
    json.dumps(
        [
            _classe(2, None, "PROCESSO CÍVEL E DO TRABALHO"),
            _classe(1106, 2, "Processo de Conhecimento"),
            _classe(65, 1106, "Ação Civil Pública"),
            _classe(7, 1106, "Procedimento Comum Cível"),
        ]
    ).encode()
)


def test_tabela_dos_processos_pela_primeira_comunicacao():
    numero = _numero(13)
    comunicacoes, _, _ = processos.tabelas(
        [
            _carimbado(
                _so_a_outra_parte("primeira", numero, "2026-10-01")
                | {"codigoClasse": "65", "nomeClasse": "AÇÃO CIVIL PÚBLICA"},
                date(2026, 11, 9),
                "numero",
            ),
            _carimbado(
                _item(
                    "n",
                    numero,
                    ("ENERGIA EXEMPLO SA", "P"),
                    codigoClasse="7",
                    data_disponibilizacao="2026-10-15",
                ),
                date(2026, 11, 2),
            ),
        ],
        processos.razoes_sociais(CADASTRO),
    )
    tabela = processos.tabela_dos_processos(comunicacoes, CLASSES)

    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert linha["numero_processo"] == numero_cnj.decodificar(numero).formatado
    assert (linha["classe_codigo"], linha["classe_tpu"], linha["ramo"]) == (
        "65",
        "Ação Civil Pública",
        "coletivo",
    )
    assert linha["classe_caminho"] == (
        "PROCESSO CÍVEL E DO TRABALHO > Processo de Conhecimento > Ação Civil Pública"
    )
    assert linha["primeira_comunicacao"] == pd.Timestamp("2026-10-01")
    # vale desde a primeira comunicação que liga o processo a uma companhia
    assert linha["disponivel_em"] == pd.Timestamp("2026-10-15")
    assert linha["visto_em"] == pd.Timestamp("2026-11-02")
    assert (linha["tribunal"], linha["justica"]) == ("TJSP", "Justiça Estadual")


def test_tabela_dos_processos_sem_a_tpu_fica_sem_o_ramo():
    comunicacoes, _, _ = _tabelas(
        _item("n", _numero(14), ("ENERGIA EXEMPLO SA", "P"), codigoClasse="X")
    )
    linha = processos.tabela_dos_processos(comunicacoes, None).iloc[0]
    assert pd.isna(linha["ramo"]) and pd.isna(linha["classe_tpu"])
    assert linha["classe_codigo"] == "X"


def _tres_tabelas(itens: list[dict]):
    comunicacoes, partes, _ = processos.tabelas(
        itens, processos.razoes_sociais(CADASTRO)
    )
    return comunicacoes, partes, processos.tabela_dos_processos(comunicacoes, CLASSES)


def _ate(tabela: pd.DataFrame, dia: pd.Timestamp) -> pd.DataFrame:
    return (
        tabela[tabela["disponivel_em"] <= dia]
        .sort_values(list(tabela.columns[:3]))
        .reset_index(drop=True)
        .astype(object)
        .pipe(lambda t: t.where(t.notna(), None))  # vazio é vazio (`nan` ou `None`)
    )


@pytest.mark.parametrize(
    "corte", ["2026-09-30", "2026-10-10", "2026-10-15", "2026-10-25", "2026-11-30"]
)
def test_cortar_o_futuro_nao_muda_o_passado(corte: str):
    """Montar só com o que tinha saído até o corte dá o mesmo que montar com tudo e cortar depois."""
    a, b = _numero(15), _numero(16)
    pelo_nome, pelo_numero = date(2026, 11, 2), date(2026, 11, 9)
    itens = [
        _carimbado(
            _so_a_outra_parte("a1", a, "2026-10-01") | {"codigoClasse": "65"},
            pelo_numero,
            "numero",
        ),
        _carimbado(
            _item(
                "a2",
                a,
                ("ENERGIA EXEMPLO SA", "P"),
                data_disponibilizacao="2026-10-15",
            ),
            pelo_nome,
        ),
        _carimbado(_so_a_outra_parte("a3", a, "2026-10-20"), pelo_numero, "numero"),
        _carimbado(
            _item(
                "b1",
                b,
                ("CIA FICTICIA DE AGUAS", "A"),
                data_disponibilizacao="2026-10-05",
            ),
            date(2026, 12, 1),
        ),
        _carimbado(
            _item(
                "b2",
                b,
                ("ENERGIA EXEMPLO SA", "P"),
                data_disponibilizacao="2026-10-25",
            ),
            pelo_nome,
        ),
        _carimbado(
            _so_a_outra_parte("solto", _numero(17), "2026-10-02"),
            pelo_numero,
            "numero",
        ),
    ]
    dia = pd.Timestamp(corte)
    com_tudo = _tres_tabelas(itens)

    def saiu_ate_o_corte(item: dict) -> bool:
        saiu = min(pd.Timestamp(item["data_disponibilizacao"]), item["_visto_em"])
        return saiu <= dia

    so_o_passado = _tres_tabelas([i for i in itens if saiu_ate_o_corte(i)])
    for inteira, cortada in zip(com_tudo, so_o_passado, strict=True):
        # vazia, a coluna de texto perde o tipo; os valores continuam conferidos
        pd.testing.assert_frame_equal(
            _ate(inteira, dia), _ate(cortada, dia), check_dtype=False
        )


def test_montar_le_as_duas_fontes_e_grava_os_processos(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    da_tpu = {"url": "https://tpu.exemplo/classes", "sha256": "t" * 64}
    monkeypatch.setattr(
        processos.tpu, "classes_do_acervo", lambda _conexao: (CLASSES, da_tpu)
    )
    numero = _numero(18)
    _coletar(
        banco,
        djen.consulta("ENERGIA EXEMPLO S.A.", date(2026, 10, 26), date(2026, 11, 1)),
        [_item("n", numero, ("ENERGIA EXEMPLO S.A.", "P"))],
        date(2026, 11, 2),
    )
    _coletar(
        banco,
        djen.consulta_do_processo(numero, date(2025, 1, 1), date(2026, 10, 31)),
        [_so_a_outra_parte("o", numero, "2026-10-20")],
        date(2026, 11, 3),
        fonte=djen.ID_DOS_PROCESSOS,
    )
    pasta = tmp_path / "base"
    with banco.connect() as conexao:
        resumo = processos.montar(conexao, pasta, AGORA, cadastro=CADASTRO)
        de_novo = processos.montar(conexao, pasta, AGORA, cadastro=CADASTRO)

    assert (resumo["consultas"], resumo["comunicacoes"], resumo["processos"]) == (
        2,
        2,
        1,
    )
    assert de_novo == processos.JA_MONTADO
    comunicacoes = pd.read_parquet(pasta / "processos_comunicacoes" / "djen.parquet")
    assert sorted(comunicacoes["achada_por"]) == ["nome", "numero"]
    tabela = pd.read_parquet(pasta / "processos" / "djen.parquet")
    assert tabela["ramo"].tolist() == ["conhecimento"]
    assert tabela["versao_do_codigo"].iloc[0] == "0123abc"
    for manifesto in pasta.rglob("*.json"):
        conferencia = json.loads(manifesto.read_text(encoding="utf-8"))
        assert conferencia["conferencia_do_contrato"]["aprovada"], manifesto.name
    assert da_tpu["sha256"] in (pasta / "processos" / "djen.json").read_text(
        encoding="utf-8"
    )
    gravado = "".join(
        p.read_bytes().decode("latin-1") for p in pasta.rglob("*") if p.is_file()
    )
    assert PESSOA not in gravado


# --- o teor (PR 2): lido pela regra, publicado só depois da conferência ---------------------------

TEOR = f"{PESSOA} contra a ENERGIA EXEMPLO S.A. JULGO PROCEDENTE o pedido. Custas de R$ 1.000,00."


def test_tabelas_leem_o_teor_pela_regra_sem_guardar_o_texto():
    item = _item("t", _numero(31), ("ENERGIA EXEMPLO S.A.", "P"), texto=TEOR)
    linha = _tabelas(item)[0].iloc[0]
    assert (linha["tipo_de_ato"], linha["resultado"]) == ("sentenca", "procedente")
    assert (linha["resultado_trecho"], linha["valor_citado"]) == (
        "JULGO PROCEDENTE",
        1000.0,
    )
    assert linha["teor_conferido_em"] is None
    assert "texto" not in linha.index


def test_montar_so_publica_o_teor_conferido(banco, tmp_path, monkeypatch):
    monkeypatch.setenv("TICKERLAB_VERSAO", "0123abc")
    _coletar(
        banco,
        djen.consulta("ENERGIA EXEMPLO S.A.", date(2026, 10, 26), date(2026, 11, 1)),
        [_item("t", _numero(32), ("ENERGIA EXEMPLO S.A.", "P"), texto=TEOR)],
        date(2026, 11, 2),
    )
    pasta = tmp_path / "base"
    arquivo = pasta / "processos_comunicacoes" / "djen.parquet"
    teor = ["tipo_de_ato", "resultado", "resultado_trecho", "valor_citado"]
    with banco.connect() as conexao:
        processos.montar(conexao, pasta, AGORA, cadastro=CADASTRO)
        assert pd.read_parquet(arquivo)[teor].isna().all().all()

        dia = date(2026, 11, 3)
        conferencia_processos.gravar(
            conferencia_processos.Conferencia(
                feita_em=dia,
                versao_da_regra=processos_teor.VERSAO_DA_REGRA,
                modelo=conferencia_processos.MODELO_DO_GABARITO,
                semente=20261103,
                cobre_ate=dia,
                campos={
                    c: conferencia_processos.Campo(100, 100)
                    for c in conferencia_processos.CAMPOS
                },
                discordantes={c: () for c in conferencia_processos.CAMPOS},
            ),
            pasta,
        )
        # a conferência nova é origem da tabela: refaz sem precisar de --refazer
        assert (
            processos.montar(conexao, pasta, AGORA, cadastro=CADASTRO)
            != processos.JA_MONTADO
        )
    linha = pd.read_parquet(arquivo).iloc[0]
    assert linha[teor].tolist() == [
        "sentenca",
        "procedente",
        "JULGO PROCEDENTE",
        1000.0,
    ]
    assert linha["teor_conferido_em"] == dia
