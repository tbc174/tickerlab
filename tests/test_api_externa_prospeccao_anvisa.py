"""Registros da Anvisa na busca de empresas (linha 860): `GET /data/v1/companies` com `anvisa_type`,
`anvisa_active_min`, `anvisa_total_min` e `sort=anvisa`.

Base de mentira, sem internet; os CNPJs são de ninguém. A tabela `anvisa_por_empresa` tem dois retratos por dia
(01/11 e 09/11) e a busca usa o mais novo já público em `known_at`. Riscos: olhar o futuro (retrato de depois do
`known_at`), servir sem o portão (campo ou tabela não pronta), filtrar por campo negado (oráculo), pessoa
(a tabela é só de pessoa jurídica e a resposta não ganha campo de pessoa) e prometer o que a contagem não é
(sinal de porte, não faturamento).
"""

import dataclasses
from datetime import UTC, datetime

import pandas as pd
import pytest

from base import anvisa_porte as porte
from base import prontidao
from base.porta import Porta
from base.prontidao import Prontidao, Prova
from src import portao_externo as portao
from src.api_externa import rotas
from src.api_externa.conjuntos import prospeccao
from src.banco.coletas import Coleta, ColetaEGuarda, Guarda
from tests import ajudantes_da_api_externa as aj

AGORA = datetime(2026, 11, 10, 12, tzinfo=UTC)
ROTA = "/data/v1/companies"
CARIMBOS = {
    "origem_sha256": "0" * 64,
    "montado_em": pd.Timestamp("2026-11-05", tz="UTC"),
    "versao_do_codigo": "teste",
}
ABERTA_SEM_PRAZO = ColetaEGuarda(Coleta.ABERTA, Guarda.SEM_PRAZO)
COSMETICOS = "2063100"  # fabricação de cosméticos
# fmt: off
ESTABELECIMENTOS = [
    # cnpj, raiz, UF, município
    ("11111111000191", "11111111", "SP", "7107"),
    ("22222222000191", "22222222", "SP", "7107"),
    ("33333333000191", "33333333", "SP", "7107"),
    ("44444444000191", "44444444", "RJ", "6001"),
]
EMPRESAS = [
    ("11111111", "ALFA COSMETICOS LTDA"),
    ("22222222", "BETA COSMETICOS LTDA"),
    ("33333333", "GAMA COSMETICOS LTDA"),
    ("44444444", "DELTA COSMETICOS S.A."),
]
# raiz, retrato, cosméticos (total, ativos), saneantes (total, ativos); a 33333333 não tem registro nenhum
ANVISA = [
    ("11111111", "2026-11-01", (300, 250), (0, 0)),
    ("22222222", "2026-11-01", (250, 150), (40, 40)),
    ("44444444", "2026-11-01", (500, 450), (0, 0)),
    ("11111111", "2026-11-09", (310, 260), (0, 0)),
    ("22222222", "2026-11-09", (250, 150), (40, 40)),
    ("44444444", "2026-11-09", (500, 450), (0, 0)),
]
# fmt: on


def _estabelecimentos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        ESTABELECIMENTOS, columns=["cnpj", "cnpj_basico", "uf", "municipio"]
    )
    return tabela.assign(
        matriz=True,
        situacao_cadastral="02",
        data_inicio_atividade=pd.Timestamp("2010-05-01"),
        cnae_principal=COSMETICOS,
        mes_do_retrato="2026-09",
        disponivel_em=pd.Timestamp("2026-09-30").date(),
        **CARIMBOS,
    )


def _empresas() -> pd.DataFrame:
    tabela = pd.DataFrame(EMPRESAS, columns=["cnpj_basico", "razao_social"])
    return tabela.assign(
        natureza_juridica="2062",
        porte="demais",
        capital_social=1_000_000.0,
        n_estabelecimentos=1,
        mes_do_retrato="2026-09",
        disponivel_em=pd.Timestamp("2026-09-30").date(),
        **CARIMBOS,
    )


def _anvisa() -> pd.DataFrame:
    linhas = []
    for raiz, retrato, (cos_total, cos_ativos), (san_total, san_ativos) in ANVISA:
        contagens = dict.fromkeys(porte.colunas_de_contagem(), 0)
        contagens |= {
            "cosmeticos_total": cos_total,
            "cosmeticos_ativos": cos_ativos,
            "saneantes_total": san_total,
            "saneantes_ativos": san_ativos,
            "produtos_total": cos_total + san_total,
            "produtos_ativos": cos_ativos + san_ativos,
        }
        linhas.append(
            {
                "cnpj_basico": raiz,
                "disponivel_em": pd.Timestamp(retrato).date(),
                "trata_como_pessoa": False,
                **contagens,
                "montado_em": pd.Timestamp("2026-11-10", tz="UTC"),
                "versao_do_codigo": "teste",
            }
        )
    return pd.DataFrame(linhas)


def _gravar(base, nome: str, tabela: pd.DataFrame) -> None:
    pasta = base / nome
    pasta.mkdir(parents=True)
    for prefixo, linhas in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        linhas.to_parquet(pasta / f"{prefixo}.parquet", index=False)


@pytest.fixture
def com_anvisa() -> bool:
    return True


@pytest.fixture
def pasta(tmp_path, monkeypatch, com_anvisa):
    base = tmp_path / "base"
    _gravar(base, prospeccao.ESTABELECIMENTOS, _estabelecimentos())
    _gravar(base, prospeccao.EMPRESAS, _empresas())
    if com_anvisa:
        _gravar(base, prospeccao.ANVISA, _anvisa())
    monkeypatch.setattr(rotas, "abrir_porta", lambda banco_: Porta(base, banco_))
    return base


def _regras(tabelas: tuple[str, ...]) -> portao.Regras:
    prova = Prova(AGORA.date(), "conferida no teste", "teste")
    versoes = prontidao.versoes_maiores()
    vigentes = portao.regras_vigentes()
    return dataclasses.replace(
        vigentes,
        # a coleta e a guarda da família "anvisa" é o que o PR de licença decide; aqui ela está resolvida
        coleta_e_guarda={**vigentes.coleta_e_guarda, "anvisa": ABERTA_SEM_PRAZO},
        prontidao={t: Prontidao(versoes[t], prova, prova, prova) for t in tabelas},
    )


@pytest.fixture
def tabelas_prontas() -> tuple[str, ...]:
    return (prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS, prospeccao.ANVISA)


@pytest.fixture
def cenario(banco, monkeypatch, pasta, tabelas_prontas):
    ator = aj.admin(banco)
    org = aj.organizacao(banco, ator)
    chave = aj.chave(banco, ator, org)
    aj.contrato(banco, ator, org, conjunto=prospeccao.CONJUNTO)
    monkeypatch.setattr(rotas, "regras_da_api", lambda: _regras(tabelas_prontas))
    return ator, org, chave


@pytest.fixture
def cliente(monkeypatch, cenario):
    return aj.cliente_da_api(monkeypatch, AGORA)


def _get(cliente, cenario, **parametros):
    _ator, _org, chave = cenario
    return cliente.get(ROTA, params=parametros, headers=aj.bearer(chave.valor))


def _cnpjs(resposta) -> list[str]:
    return [e["cnpj"] for e in resposta.json()["companies"]]


# ---------------------------------------------------------------- o que sai


def test_cosmeticos_em_sp_com_mais_de_200_registros_ativos(cliente, cenario):
    resposta = _get(
        cliente,
        cenario,
        cnae="2063",
        state="SP",
        anvisa_type="cosmetics",
        anvisa_active_min=200,
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert _cnpjs(resposta) == ["11111111000191"]  # a BETA tem 150; a DELTA é do RJ
    (empresa,) = corpo["companies"]
    assert empresa["anvisa_registrations_active"] == {
        "value": 260,
        "source": "anvisa-produtos",
        "published_at": "2026-11-09",
        "observed_at": None,
    }
    assert empresa["anvisa_registrations_total"]["value"] == 310
    assert corpo["anvisa_type"] == "cosmetics"
    assert "não faturamento" in corpo["anvisa_notice"]
    fontes = {f["source"]: f for f in corpo["sources"]}
    assert set(fontes) == {"rfb-cnpj", "anvisa-produtos"}
    assert "Anvisa" in fontes["anvisa-produtos"]["attribution"]
    assert fontes["anvisa-produtos"]["license"].startswith("CC BY")


def test_sem_tipo_vale_a_soma_dos_produtos(cliente, cenario):
    resposta = _get(cliente, cenario, cnae="2063", anvisa_active_min=190, state="SP")
    corpo = resposta.json()
    assert corpo["anvisa_type"] == "products"
    valores = {
        e["cnpj"]: e["anvisa_registrations_active"]["value"] for e in corpo["companies"]
    }
    # a BETA soma 150 cosméticos e 40 saneantes ativos; a GAMA não tem registro
    assert valores == {"11111111000191": 260, "22222222000191": 190}


def test_filtro_pelo_total(cliente, cenario):
    resposta = _get(
        cliente, cenario, cnae="2063", anvisa_type="cosmetics", anvisa_total_min=300
    )
    assert _cnpjs(resposta) == ["11111111000191", "44444444000191"]


def test_o_tipo_escolhido_conta_so_ele(cliente, cenario):
    resposta = _get(
        cliente, cenario, cnae="2063", anvisa_type="sanitizers", anvisa_active_min=1
    )
    assert _cnpjs(resposta) == ["22222222000191"]


def test_so_o_tipo_mostra_a_contagem_e_empresa_sem_registro_vale_zero(cliente, cenario):
    resposta = _get(cliente, cenario, cnae="2063", state="SP", anvisa_type="cosmetics")
    corpo = resposta.json()
    por_cnpj = {
        e["cnpj"]: e["anvisa_registrations_active"]["value"] for e in corpo["companies"]
    }
    assert por_cnpj == {
        "11111111000191": 260,
        "22222222000191": 150,
        "33333333000191": 0,
    }


def test_busca_sem_anvisa_nao_traz_campo_nem_fonte_da_anvisa(cliente, cenario):
    corpo = _get(cliente, cenario, cnae="2063").json()
    assert "anvisa_type" not in corpo
    assert "anvisa_notice" not in corpo
    assert {f["source"] for f in corpo["sources"]} == {"rfb-cnpj"}
    assert not any("anvisa" in chave for chave in corpo["companies"][0])


# ---------------------------------------------------------------- como era


def test_o_retrato_e_o_mais_novo_ja_publico_no_dia_pedido(cliente, cenario):
    antes = _get(
        cliente,
        cenario,
        cnae="2063",
        state="SP",
        anvisa_type="cosmetics",
        anvisa_active_min=200,
        known_at="2026-11-05",
    ).json()
    (empresa,) = antes["companies"]
    assert empresa["anvisa_registrations_active"]["value"] == 250  # o retrato de 01/11
    assert empresa["anvisa_registrations_active"]["published_at"] == "2026-11-01"


def test_retrato_vale_desde_o_proprio_dia_e_nao_na_vespera(cliente, cenario):
    no_dia = _get(
        cliente, cenario, cnae="2063", anvisa_active_min=1, known_at="2026-11-01"
    )
    assert no_dia.status_code == 200
    vespera = _get(
        cliente, cenario, cnae="2063", anvisa_active_min=1, known_at="2026-10-31"
    )
    assert (
        vespera.status_code == 404
    )  # nenhum retrato era público: nada de olhar o futuro


def test_antes_do_primeiro_retrato_a_busca_sem_anvisa_continua(cliente, cenario):
    resposta = _get(cliente, cenario, cnae="2063", known_at="2026-10-31")
    assert resposta.status_code == 200
    assert len(_cnpjs(resposta)) == 4


# ---------------------------------------------------------------- ordem e páginas


def test_ordem_por_registros_ativos_decrescente_com_cnpj_no_desempate(cliente, cenario):
    resposta = _get(cliente, cenario, cnae="2063", sort="-anvisa")
    assert _cnpjs(resposta) == [
        "44444444000191",  # 450
        "11111111000191",  # 260
        "22222222000191",  # 190 (150 cosméticos + 40 saneantes)
        "33333333000191",  # 0: sem registro
    ]
    assert _cnpjs(_get(cliente, cenario, cnae="2063", sort="anvisa"))[0] == (
        "33333333000191"
    )


@pytest.mark.parametrize("sort", ["anvisa", "-anvisa"])
def test_cursor_da_ordem_por_anvisa_percorre_tudo_sem_repetir_nem_pular(
    cliente, cenario, sort
):
    vistos: list[str] = []
    cursor = None
    for _ in range(10):
        parametros = {
            "cnae": "2063",
            "sort": sort,
            "limit": 1,
            "anvisa_type": "cosmetics",
        }
        if cursor:
            parametros["cursor"] = cursor
        corpo = _get(cliente, cenario, **parametros).json()
        vistos += [e["cnpj"] for e in corpo["companies"]]
        cursor = corpo["next_cursor"]
        if not cursor:
            break
    esperado = [
        "44444444000191",
        "11111111000191",
        "22222222000191",
        "33333333000191",
    ]
    assert vistos == (esperado if sort == "-anvisa" else esperado[::-1])


def test_cursor_de_outra_ordem_nao_serve_na_ordem_por_anvisa(cliente, cenario):
    pagina = _get(
        cliente, cenario, cnae="2063", sort="-anvisa", anvisa_type="cosmetics", limit=1
    ).json()
    outra = _get(
        cliente, cenario, cnae="2063", sort="-capital", cursor=pagina["next_cursor"]
    )
    assert outra.status_code == 400
    assert outra.json()["detail"] == "invalid_cursor"


# ---------------------------------------------------------------- pedidos inválidos


@pytest.mark.parametrize(
    "parametros",
    [
        {"anvisa_type": "toys", "anvisa_active_min": 1},
        {"anvisa_type": "cosmeticos", "anvisa_active_min": 1},  # o nome é o de fora
        # tipos com a tabela montada mas a ficha de licença ainda não lida: a API não os serve (linha 860)
        {"anvisa_type": "medicines", "anvisa_active_min": 1},
        {"anvisa_type": "food", "anvisa_active_min": 1},
        {"anvisa_type": "operating_license", "anvisa_active_min": 1},
        {"anvisa_type": "gmp_certificate", "anvisa_active_min": 1},
        {"anvisa_active_min": 0},
        {"anvisa_total_min": -3},
        {"anvisa_active_min": 10_000_001},
    ],
)
def test_pedido_fora_do_vocabulario_ou_da_forma_e_400(cliente, cenario, parametros):
    resposta = _get(cliente, cenario, cnae="2063", **parametros)
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "invalid_filter"


def test_so_o_filtro_da_anvisa_ja_conta_como_filtro(cliente, cenario):
    resposta = _get(cliente, cenario, anvisa_type="cosmetics", anvisa_active_min=400)
    assert resposta.status_code == 200
    assert _cnpjs(resposta) == ["44444444000191"]


def test_so_o_tipo_ou_so_a_ordem_nao_basta_como_filtro(cliente, cenario):
    assert _get(cliente, cenario, anvisa_type="cosmetics").status_code == 400
    assert _get(cliente, cenario, sort="-anvisa").status_code == 400


# ---------------------------------------------------------------- portão e tabela


@pytest.mark.parametrize(
    "tabelas_prontas",
    [(prospeccao.ESTABELECIMENTOS, prospeccao.EMPRESAS)],
    ids=["anvisa_sem_prontidao"],
)
def test_tabela_da_anvisa_sem_prontidao_nao_sai_e_a_busca_comum_segue(cliente, cenario):
    negada = _get(cliente, cenario, cnae="2063", anvisa_active_min=1)
    assert negada.status_code == 404
    assert "anvisa" not in negada.text.lower().replace("not_available", "")
    ordem = _get(cliente, cenario, cnae="2063", sort="-anvisa", state="SP")
    assert ordem.status_code == 404
    assert _get(cliente, cenario, cnae="2063").status_code == 200


def test_filtro_por_campo_negado_da_anvisa_nao_serve_de_oraculo(
    cliente, cenario, monkeypatch
):
    def portao_sem_conjuntos(_conexao, _contexto, _conjunto):
        return lambda fonte, campo, _publico: campo != "registros_anvisa_ativos"

    monkeypatch.setattr(rotas, "_portao", portao_sem_conjuntos)
    assert _get(cliente, cenario, cnae="2063", anvisa_active_min=1).status_code == 404
    assert _get(cliente, cenario, cnae="2063", sort="-anvisa").status_code == 404
    # o total continua liberado: filtrar por ele é permitido, e só o campo liberado sai
    liberado = _get(cliente, cenario, cnae="2063", anvisa_total_min=1)
    assert liberado.status_code == 200
    empresa = liberado.json()["companies"][0]
    assert "anvisa_registrations_total" in empresa
    assert "anvisa_registrations_active" not in empresa


@pytest.mark.parametrize("com_anvisa", [False])
def test_base_sem_a_tabela_da_anvisa_nao_serve_a_anvisa_e_a_busca_comum_segue(
    cliente, cenario
):
    assert _get(cliente, cenario, cnae="2063", anvisa_active_min=1).status_code == 404
    assert _get(cliente, cenario, cnae="2063").status_code == 200


def test_resposta_da_anvisa_nao_ganha_campo_de_pessoa(cliente, cenario):
    corpo = _get(
        cliente, cenario, cnae="2063", anvisa_type="cosmetics", anvisa_active_min=1
    ).json()
    texto = str(corpo).lower()
    for palavra in ("cpf", "socio", "partner", "email", "telefone", "responsavel"):
        assert palavra not in texto
    assert set(corpo["companies"][0]) <= {
        "cnpj", "legal_name", "legal_nature_code", "size", "registration_status",
        "opened_at", "cnae_code", "state_code", "municipality", "head_office",
        "share_capital", "active_establishments",
        "anvisa_registrations_total", "anvisa_registrations_active",
    }  # fmt: skip


# ---------------------------------------------------------------- só os tipos de licença lida


def test_so_os_tres_tipos_de_licenca_lida_podem_ser_somados():
    """Medicamentos, alimentos, AFE e CBPF vão na tabela, mas a API não os serve até a ficha de cada um ser lida."""
    somados = {p for prefixos in prospeccao.TIPOS_DA_ANVISA.values() for p in prefixos}
    assert somados == {"cosmeticos", "saneantes", "produtos_saude"}


def test_registro_de_medicamento_alimento_afe_e_cbpf_nao_conta_nem_aparece(
    cliente, cenario, pasta
):
    """A GAMA só tem esses quatro tipos na tabela: nenhuma busca da API a enxerga nem mostra a contagem deles."""
    contagens = dict.fromkeys(porte.colunas_de_contagem(), 0)
    contagens |= {
        "medicamentos_total": 900, "medicamentos_ativos": 800,
        "alimentos_total": 700, "alimentos_ativos": 600,
        "afe_total": 50, "afe_ativos": 40, "cbpf_total": 30, "cbpf_ativos": 20,
    }  # fmt: skip
    linha = {
        "cnpj_basico": "33333333",
        "disponivel_em": pd.Timestamp("2026-11-09").date(),
        "trata_como_pessoa": False,
        **contagens,
        "montado_em": pd.Timestamp("2026-11-10", tz="UTC"),
        "versao_do_codigo": "teste",
    }
    pd.DataFrame([linha]).to_parquet(
        pasta / prospeccao.ANVISA / "33.parquet", index=False
    )
    for tipo in prospeccao.TIPOS_DA_ANVISA:
        resposta = _get(
            cliente, cenario, cnae="2063", state="SP", anvisa_type=tipo,
            anvisa_total_min=1,
        )  # fmt: skip
        assert "33333333000191" not in _cnpjs(resposta), tipo
    resposta = _get(cliente, cenario, cnae="2063", state="SP", anvisa_type="products")
    (gama,) = [e for e in resposta.json()["companies"] if e["cnpj"] == "33333333000191"]
    assert gama["anvisa_registrations_active"]["value"] == 0
    assert gama["anvisa_registrations_total"]["value"] == 0
    assert not {
        c
        for c in aj.chaves_de(resposta.json())
        if "medic" in c or "alimento" in c or "afe" in c or "cbpf" in c
    }
