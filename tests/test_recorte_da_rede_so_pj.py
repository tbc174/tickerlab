"""A rede só de pessoa jurídica no recorte da API (linha 843): o degrau 3 e a trava de zero pessoa.

Base de mentira, sem internet; os CNPJs e os nomes são de ninguém. A rede tem três empresas e uma firma de
auditoria de verdade PJ (na lista sem pessoa da Receita) e, em volta, tudo o que nunca pode sair de casa: MEI,
empresário individual, natureza não informada, marca de pessoa vazia, pessoa natural (id `P`) sócia, empresa fora
da lista sem pessoa, empresa sem CNPJ, sinal negativo e tipos de ligação que a `links` não serve. Riscos: vazar
pessoa ao VPS (ADR 0075 e 0128) e a trava só avisar em vez de derrubar a montagem.
"""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from base.porta import abrir
from base.rede import recorte_so_pj as recorte
from base.rede.vistas import vista_publicada
from scripts import montar_recorte_da_api as envio
from src.api_externa.conjuntos import vinculos

PESSOA = "P" + "0" * 20


def _id(letra: str) -> str:
    return "E" + letra * 20


ALFA, BETA, GAMA, AUDITORA = _id("a"), _id("b"), _id("c"), _id("d")
MEI, INDIVIDUAL, ESTRANGEIRA, SEM_MARCA = _id("1"), _id("2"), _id("3"), _id("4")
FORA_DA_LISTA, SEM_CNPJ = _id("5"), _id("6")
AS_PJ = {ALFA, BETA, GAMA, AUDITORA}

# (id, tipo, nome, natureza, mei, trata como pessoa, raiz do CNPJ ou None)
ENTIDADES = [
    (ALFA, "empresa", "ALFA S.A.", "2054", False, False, "11111111"),
    (BETA, "empresa", "BETA LTDA", "2062", False, False, "22222222"),
    (GAMA, "empresa", "GAMA S.A.", "2054", False, False, "33333333"),
    (AUDITORA, "auditor", "AUDITORA UM", "2240", False, False, "44444444"),
    (MEI, "empresa", "NOME DE MENTIRA MEI", "2062", True, True, "55555555"),
    (INDIVIDUAL, "empresa", None, "2135", False, True, "66666666"),
    (ESTRANGEIRA, "empresa", "FOREIGN CO", "nao_informada", False, True, None),
    (SEM_MARCA, "empresa", "SEM MARCA LTDA", "2062", False, None, "77777777"),
    (FORA_DA_LISTA, "empresa", "FORA LTDA", "2062", False, False, "88888888"),
    (SEM_CNPJ, "empresa", "SEM CNPJ S.A.", "2054", False, False, None),
]  # fmt: skip
# (de, para, tipo)
LIGACOES = [
    (BETA, ALFA, "controlada_de"),
    (GAMA, ALFA, "coligada_de"),
    (AUDITORA, ALFA, "audita"),
    (GAMA, ALFA, "opera_para"),  # tipo que a `links` não serve
    (ALFA, GAMA, "sancionada_por"),  # sinal negativo
    (PESSOA, ALFA, "socio_de"),
    (MEI, ALFA, "controlada_de"),
    (INDIVIDUAL, ALFA, "participada_de"),
    (ESTRANGEIRA, ALFA, "controlada_de"),
    (SEM_MARCA, ALFA, "controlada_de"),
    (FORA_DA_LISTA, ALFA, "controlada_de"),
    (SEM_CNPJ, ALFA, "controlada_de"),
    (ALFA, None, "controlada_de"),
]


def _parquet(caminho: Path, quadro: pd.DataFrame) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    quadro.to_parquet(caminho, index=False)


def _entidades() -> pd.DataFrame:
    linhas = [
        {
            "id_entidade": i, "tipo": t, "nome": n, "natureza_juridica": nat, "natureza_fonte": "receita",
            "mei": m, "trata_como_pessoa": p, "fontes": "cvm-fre", "publico_em": pd.Timestamp("2020-01-01"),
        }
        for i, t, n, nat, m, p, _ in ENTIDADES
    ]  # fmt: skip
    quadro = pd.DataFrame(linhas)
    quadro["trata_como_pessoa"] = quadro["trata_como_pessoa"].astype("boolean")
    return quadro


def _identificadores() -> pd.DataFrame:
    linhas = [(i, "cnpj_raiz", raiz) for i, *_, raiz in ENTIDADES if raiz is not None]
    linhas += [(ALFA, "ticker", "ALFA3"), (PESSOA, "cpf_hash", "abc")]
    quadro = pd.DataFrame(linhas, columns=["id_entidade", "sistema", "valor"])
    quadro["desde"] = pd.NaT
    quadro["ate"] = pd.NaT
    quadro["publico_em"] = pd.Timestamp("2020-01-01")
    quadro["regra"] = 2
    quadro["conferido_por"] = "regra"
    quadro["fontes"] = "cvm-fre"
    return quadro


def _ligacoes() -> pd.DataFrame:
    quadro = pd.DataFrame(LIGACOES, columns=["de", "para", "tipo"])
    quadro["papel"] = (
        None  # faz parte da chave da ligação (`base/rede/ligacoes.py::CHAVE`)
    )
    quadro["participacao"] = 50.0
    quadro["aconteceu_em"] = pd.Timestamp("2019-12-31")
    quadro["publico_em"] = pd.Timestamp("2020-05-31")
    quadro["ate"] = pd.NaT
    quadro["fonte"] = "cvm-fre"
    return quadro


# A lista sem pessoa da Receita: as quatro PJ, mais a raiz do MEI com natureza de empresa (sem estabelecimento na
# lista de estabelecimentos, é tirada por `tirar_raizes_de_mei`) e a do empresário individual nunca entra.
EMPRESAS_PJ = [
    ("11111111", "ALFA S.A.", "2054", "demais"),
    ("22222222", "BETA LTDA", "2062", "demais"),
    ("33333333", "GAMA S.A.", "2054", "demais"),
    ("44444444", "AUDITORA UM", "2240", "demais"),
    ("55555555", "NOME DE MENTIRA MEI", "2062", "micro"),
    ("77777777", "SEM MARCA LTDA", "2062", "demais"),
]


def _base(raiz: Path) -> Path:
    base = raiz / "base"
    _parquet(
        base / "cnpj_empresas_pj" / "00.parquet",
        pd.DataFrame(
            EMPRESAS_PJ,
            columns=["cnpj_basico", "razao_social", "natureza_juridica", "porte"],
        ),
    )
    com_estabelecimento = [
        r for r, *_ in EMPRESAS_PJ if r != "55555555"
    ]  # o MEI não tem
    _parquet(
        base / "cnpj_estabelecimentos_pj" / "00.parquet",
        pd.DataFrame({"cnpj_basico": com_estabelecimento}),
    )
    _parquet(base / "rede" / "entidades.parquet", _entidades())
    _parquet(base / "rede" / "identificadores.parquet", _identificadores())
    _parquet(base / "rede" / "ligacoes.parquet", _ligacoes())
    return base


TABELAS = ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj", *recorte.REDE)


def _montar(tmp_path: Path) -> Path:
    saida = tmp_path / "saida"
    envio.montar(_base(tmp_path), saida, TABELAS)
    return saida


def _ler(saida: Path, nome: str) -> pd.DataFrame:
    return pd.read_parquet(saida / "rede" / f"{nome}.parquet")


# --- a lista e o degrau ----------------------------------------------------------------------------


def test_o_degrau_3_e_o_2_mais_a_rede():
    assert envio.tabelas_do_degrau(3) == (*envio.tabelas_do_degrau(2), *recorte.REDE)
    assert not set(recorte.REDE) & set(envio.FICAM_EM_CASA)
    assert not set(recorte.REDE) & set(envio.tabelas_do_degrau(2))


def test_os_tipos_de_ligacao_sao_os_que_a_links_serve():
    """Lista fechada (Diretoria, 11/11/2026): tipo novo só com a leitura da norma (linha 838)."""
    assert set(recorte.TIPOS_DE_LIGACAO) == set(vinculos.TIPOS)


@pytest.mark.parametrize("nome", recorte.REDE)
def test_a_rede_nunca_passa_pela_copia_por_arquivo(nome):
    with pytest.raises(envio.RecorteErro, match="degrau 3"):
        envio.conferir_a_lista((nome,))


def test_a_rede_vai_inteira_ou_nao_vai(tmp_path):
    base = _base(tmp_path)
    with pytest.raises(envio.RecorteErro, match="inteira"):
        envio.montar(
            base,
            tmp_path / "saida",
            ("cnpj_empresas_pj", "cnpj_estabelecimentos_pj", "ligacoes"),
        )


def test_a_rede_nao_vai_sem_empresas_pj(tmp_path):
    base = _base(tmp_path)
    with pytest.raises(envio.RecorteErro, match="cnpj_empresas_pj"):
        envio.montar(base, tmp_path / "saida", recorte.REDE)


def test_main_aceita_o_degrau_3(tmp_path):
    base = _base(tmp_path)
    saida = tmp_path / "saida"
    # só a rede e a lista sem pessoa existem nesta base: o núcleo vazio é falha, mas a rede tem de sair limpa
    assert (
        envio.main(["--degrau", "3", "--base", str(base), "--saida", str(saida)]) == 1
    )
    assert set(_ler(saida, "entidades")["id_entidade"]) == AS_PJ


# --- o filtro --------------------------------------------------------------------------------------


def test_so_as_entidades_pj_saem_e_sem_o_nome(tmp_path):
    saida = _montar(tmp_path)
    entidades = _ler(saida, "entidades")
    assert set(entidades["id_entidade"]) == AS_PJ
    assert "nome" not in entidades.columns
    assert not entidades["trata_como_pessoa"].any()
    assert not entidades["mei"].any()


def test_so_as_ligacoes_entre_pj_dos_quatro_tipos_saem(tmp_path):
    saida = _montar(tmp_path)
    ligacoes = _ler(saida, "ligacoes")
    assert set(map(tuple, ligacoes[["de", "para", "tipo"]].to_numpy())) == {
        (BETA, ALFA, "controlada_de"),
        (GAMA, ALFA, "coligada_de"),
        (AUDITORA, ALFA, "audita"),
    }


def test_as_ligacoes_que_saem_estao_todas_na_vista_publicada(tmp_path):
    """O recorte é mais estreito que a vista publicada (`base/rede/vistas.py`), nunca mais largo."""
    saida = _montar(tmp_path)
    publicadas, _ = vista_publicada(
        _ligacoes(), _entidades().fillna({"trata_como_pessoa": True})
    )
    chave = ["de", "para", "tipo"]
    fora = _ler(saida, "ligacoes")[chave].merge(
        publicadas[chave], how="left", indicator=True
    )
    assert (fora["_merge"] == "both").all()


def test_so_os_identificadores_das_pj_e_dos_sistemas_da_lista_saem(tmp_path):
    saida = _montar(tmp_path)
    ids = _ler(saida, "identificadores")
    assert set(ids["id_entidade"]) == AS_PJ
    assert set(ids["sistema"]) == {"cnpj_raiz", "ticker"}
    assert not ids["id_entidade"].str.startswith("P").any()


def test_os_resultados_contam_o_que_ficou_em_casa(tmp_path):
    resultados = {
        r.tabela: r for r in envio.montar(_base(tmp_path), tmp_path / "saida", TABELAS)
    }
    assert resultados["entidades"].linhas_tiradas == len(ENTIDADES) - len(AS_PJ)
    assert resultados["ligacoes"].linhas_tiradas == len(LIGACOES) - 3


def test_a_porta_le_a_rede_do_recorte(tmp_path):
    """No VPS a porta lê o recorte como lê a base de casa: sem a coluna `nome`, a rede ainda anda."""
    saida = _montar(tmp_path)
    with abrir(saida) as porta:
        rede = porta.rede("11111111")
    assert rede.centro == ALFA
    assert set(rede.ligacoes["de"]) == {BETA, GAMA, AUDITORA}


# --- a trava ---------------------------------------------------------------------------------------


def _enfiar(saida: Path, nome: str, selecao: str) -> None:
    """Põe na saída, à mão, uma linha que o filtro nunca deixaria passar (a trava tem de pegar sozinha)."""
    arquivo = saida / "rede" / f"{nome}.parquet"
    novo = arquivo.with_suffix(".novo")
    duckdb.sql(
        f"COPY (SELECT * FROM '{arquivo.as_posix()}' UNION ALL BY NAME {selecao}) "
        f"TO '{novo.as_posix()}' (FORMAT PARQUET)"
    )
    novo.replace(arquivo)


def _conferir(saida: Path) -> dict:
    con = duckdb.connect()
    try:
        return recorte.conferir_rede_so_pj(
            con,
            {n: saida / "rede" / f"{n}.parquet" for n in recorte.REDE},
            sorted((saida / "cnpj_empresas_pj").glob("*.parquet")),
        )
    finally:
        con.close()


def _entidade(id_: str, **trocas: object) -> str:
    valores = {
        "id_entidade": f"'{id_}'", "tipo": "'empresa'", "natureza_juridica": "'2054'", "mei": "false",
        "trata_como_pessoa": "false",
    } | {k: str(v) for k, v in trocas.items()}  # fmt: skip
    return "SELECT " + ", ".join(f"{v} AS {k}" for k, v in valores.items())


def test_a_saida_limpa_passa_e_da_as_contagens(tmp_path):
    contagens = _conferir(_montar(tmp_path))
    assert contagens["entidades"] == {"auditor": 1, "empresa": 3}
    assert contagens["ligacoes"] == {"audita": 1, "coligada_de": 1, "controlada_de": 1}
    assert contagens["identificadores"] == {"cnpj_raiz": 4, "ticker": 1}


@pytest.mark.parametrize(
    "nome, selecao",
    [
        ("entidades", _entidade(ALFA, trata_como_pessoa="true")),
        ("entidades", _entidade(ALFA, trata_como_pessoa="NULL::BOOLEAN")),
        ("entidades", _entidade(ALFA, mei="true")),
        ("entidades", _entidade(ALFA, mei="NULL::BOOLEAN")),
        ("entidades", _entidade(ALFA, natureza_juridica="'2135'")),
        ("entidades", _entidade(ALFA, natureza_juridica="'4090'")),
        ("entidades", _entidade(ALFA, natureza_juridica="'nao_informada'")),
        ("entidades", _entidade(ALFA, natureza_juridica="NULL")),
        ("entidades", _entidade(PESSOA)),
        ("entidades", _entidade("NULL")),
        ("entidades", _entidade(SEM_CNPJ)),  # sem CNPJ: não dá para conferir na lista sem pessoa
        ("identificadores", f"SELECT '{MEI}' AS id_entidade, 'cnpj_raiz' AS sistema, '55555555' AS valor"),
        ("identificadores", f"SELECT '{ALFA}' AS id_entidade, 'cpf_hash' AS sistema, 'x' AS valor"),
        ("identificadores", f"SELECT '{ALFA}' AS id_entidade, 'cnpj_raiz' AS sistema, '88888888' AS valor"),
        ("identificadores", f"SELECT '{ALFA}' AS id_entidade, 'cnpj' AS sistema, '66666666000191' AS valor"),
        ("identificadores", f"SELECT '{PESSOA}' AS id_entidade, 'cnpj_raiz' AS sistema, '11111111' AS valor"),
        ("ligacoes", f"SELECT '{PESSOA}' AS de, '{ALFA}' AS para, 'controlada_de' AS tipo"),
        ("ligacoes", f"SELECT '{MEI}' AS de, '{ALFA}' AS para, 'controlada_de' AS tipo"),  # ponta órfã
        ("ligacoes", f"SELECT '{BETA}' AS de, NULL AS para, 'controlada_de' AS tipo"),
        ("ligacoes", f"SELECT '{BETA}' AS de, '{ALFA}' AS para, 'socio_de' AS tipo"),
        ("ligacoes", f"SELECT '{BETA}' AS de, '{ALFA}' AS para, NULL AS tipo"),
    ],
)  # fmt: skip
def test_pessoa_enfiada_na_saida_derruba_a_montagem(tmp_path, nome, selecao):
    saida = _montar(tmp_path)
    _enfiar(saida, nome, selecao)
    with pytest.raises(recorte.RedeComPessoa):
        _conferir(saida)


@pytest.mark.parametrize("nome", recorte.REDE)
@pytest.mark.parametrize("coluna", ["nome", "cpf", "socio"])
def test_coluna_de_nome_ou_de_pessoa_em_qualquer_tabela_derruba(tmp_path, nome, coluna):
    saida = _montar(tmp_path)
    arquivo = saida / "rede" / f"{nome}.parquet"
    duckdb.sql(
        f"COPY (SELECT *, 'x' AS {coluna} FROM '{arquivo.as_posix()}') "
        f"TO '{arquivo.with_suffix('.novo').as_posix()}' (FORMAT PARQUET)"
    )
    arquivo.with_suffix(".novo").replace(arquivo)
    with pytest.raises(recorte.RedeComPessoa, match=coluna):
        _conferir(saida)


@pytest.mark.parametrize(
    "nome, coluna",
    [("entidades", "trata_como_pessoa"), ("entidades", "mei"), ("ligacoes", "tipo"), ("identificadores", "sistema")],
)  # fmt: skip
def test_sem_a_coluna_que_diz_quem_e_pessoa_derruba(tmp_path, nome, coluna):
    saida = _montar(tmp_path)
    arquivo = saida / "rede" / f"{nome}.parquet"
    duckdb.sql(
        f"COPY (SELECT * EXCLUDE ({coluna}) FROM '{arquivo.as_posix()}') "
        f"TO '{arquivo.with_suffix('.novo').as_posix()}' (FORMAT PARQUET)"
    )
    arquivo.with_suffix(".novo").replace(arquivo)
    with pytest.raises(recorte.RedeComPessoa, match=coluna):
        _conferir(saida)


def test_sem_a_lista_sem_pessoa_derruba(tmp_path):
    saida = _montar(tmp_path)
    con = duckdb.connect()
    try:
        with pytest.raises(recorte.RedeComPessoa, match="cnpj_empresas_pj"):
            recorte.conferir_rede_so_pj(
                con, {n: saida / "rede" / f"{n}.parquet" for n in recorte.REDE}, []
            )
    finally:
        con.close()


def test_a_mensagem_da_trava_nao_leva_id_nem_valor(tmp_path):
    """A mensagem vai ao log e ao aviso do Kuma: só contagens, nunca o dado que era de pessoa."""
    saida = _montar(tmp_path)
    _enfiar(
        saida,
        "identificadores",
        f"SELECT '{ALFA}' AS id_entidade, 'cnpj_raiz' AS sistema, '88888888' AS valor",
    )
    with pytest.raises(recorte.RedeComPessoa) as erro:
        _conferir(saida)
    assert "88888888" not in str(erro.value)
    assert ALFA not in str(erro.value)


def test_a_trava_roda_dentro_da_montagem(tmp_path, monkeypatch):
    """Um filtro com defeito não passa: a montagem cai na trava (e vira `RecorteErro`, que derruba o envio)."""
    monkeypatch.setattr(
        recorte, "TIPOS_DE_LIGACAO", (*recorte.TIPOS_DE_LIGACAO, "socio_de")
    )
    original = recorte.conferir_rede_so_pj

    def trava_com_a_lista_certa(con, arquivos, empresas):
        monkeypatch.setattr(recorte, "TIPOS_DE_LIGACAO", tuple(vinculos.TIPOS))
        return original(con, arquivos, empresas)

    monkeypatch.setattr(recorte, "conferir_rede_so_pj", trava_com_a_lista_certa)
    base = _base(tmp_path)
    ligacoes = _ligacoes()
    extra = pd.DataFrame(
        [{"de": BETA, "para": ALFA, "tipo": "socio_de", "fonte": "cvm-fre"}]
    )
    ligacoes = pd.concat([ligacoes, extra], ignore_index=True)
    _parquet(base / "rede" / "ligacoes.parquet", ligacoes)
    with pytest.raises(envio.RecorteErro, match="pessoa"):
        envio.montar(base, tmp_path / "saida", TABELAS)
