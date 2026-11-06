"""A seção "Ligações na rede" do dossiê (molde B, plano de 19/10/2026, PR 1).

O que a companhia é na rede de entidades (ADR 0077): controladas, controladoras, coligadas, auditor,
conglomerado e quantos valores mobiliários emite, cada ligação com a fonte. Só sai o que a vista
publicada deixa (sem pessoa, sem tipo negativo) e o que a licença da fonte de cada linha deixa mostrar.
"""

import pandas as pd
import pytest

from base import dossie
from tests.test_porta import _entidades, _identificadores, _ligacoes

D = pd.Timestamp
HOJE = D("2026-10-17")
CNPJ = "02429144000193"
RAIZ = CNPJ[:8]
CNPJ_DA_CONTROLADA = "33050196000188"
CNPJ_DA_DONA = "33333333000133"


def _ids_da_empresa(*extras: tuple) -> pd.DataFrame:
    return _identificadores(
        ("EA", "cnpj_raiz", RAIZ, None, None, "2010-01-01"),
        ("EA", "cnpj", CNPJ, None, None, "2010-01-01"),
        ("EC", "cnpj", CNPJ_DA_CONTROLADA, None, None, "2010-01-01"),
        ("ED", "cnpj", CNPJ_DA_DONA, None, None, "2010-01-01"),
        *extras,
    )


def _fre(companhia: str, sociedades: list[str], referencia: str) -> pd.DataFrame:
    """O FRE de `companhia` listando as `sociedades` (a regra do FRE em dia lê só isso)."""
    return pd.DataFrame(
        {
            "cnpj_companhia": companhia,
            "cnpj": sociedades,
            "referencia": D(referencia),
            "versao": 1,
            "conhecido_em": D(referencia) + pd.DateOffset(months=5),
            "razao_social": [f"Sociedade {s}" for s in sociedades],
            "tipo": "Controlada",
            "participacao": 100.0,
        }
    )


FRES_EM_DIA = pd.concat(
    [
        _fre(CNPJ, [CNPJ_DA_CONTROLADA], "2025-12-31"),
        _fre(CNPJ_DA_DONA, [CNPJ], "2025-12-31"),
    ],
    ignore_index=True,
)


def _secao(
    ligacoes: pd.DataFrame,
    entidades: pd.DataFrame | None = None,
    identificadores: pd.DataFrame | None = None,
    controladas: pd.DataFrame = FRES_EM_DIA,
) -> dict | None:
    rede = dossie.preparar_rede(
        ligacoes,
        _entidades("EA", "EC", "ED", "EAUD", "EB") if entidades is None else entidades,
        _ids_da_empresa() if identificadores is None else identificadores,
        controladas,
        HOJE,
    )
    return dossie.secao_rede(CNPJ, rede)


def _relacoes(secao: dict | None) -> list[tuple[str, str]]:
    assert secao is not None
    linhas = secao["tabelas"].get("ligacoes_da_rede", [])
    return [(linha["relacao"], linha["entidade"]) for linha in linhas]


def _item(secao: dict, chave: str) -> object:
    return next(i["valor"] for i in secao["itens"] if i["chave"] == chave)


# --- o que a seção mostra --------------------------------------------------------------------------


def test_cada_ligacao_aparece_do_ponto_de_vista_da_empresa() -> None:
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de", "participacao": 100.0},
            {"de": "EA", "para": "ED", "tipo": "controlada_de", "participacao": 51.0},
            {"de": "EAUD", "para": "EA", "tipo": "audita", "fonte": "cvm-fca"},
        )
    )
    assert sorted(_relacoes(secao)) == [
        ("Auditor", "Empresa EAUD"),
        ("Controlada", "Empresa EC"),
        ("Controladora", "Empresa ED"),
    ]
    assert secao is not None
    controlada = next(
        linha
        for linha in secao["tabelas"]["ligacoes_da_rede"]
        if linha["relacao"] == "Controlada"
    )
    assert controlada["cnpj"] == "33.050.196/0001-88"
    assert controlada["participacao"] == 100.0
    assert controlada["desde"] == "2015-01-01"
    assert controlada["documento"] == "Formulário de Referência (CVM)"
    assert _item(secao, "controladas") == 1
    assert _item(secao, "ligacoes") == 3


def test_desde_e_o_dia_em_que_a_ligacao_ficou_publica() -> None:
    """Sem olhar o futuro: a CVM dá ao FRE de 2026 a referência nominal 31/12/2026, mas a ligação só
    ficou pública no dia da entrega (regressão da ficha de exemplo da CPFL, 28/10/2026)."""
    secao = _secao(
        _ligacoes(
            {
                "de": "EC",
                "para": "EA",
                "tipo": "controlada_de",
                "aconteceu_em": "2026-12-31",
                "publico_em": "2026-08-31",
            }
        )
    )
    assert secao is not None
    (controlada,) = secao["tabelas"]["ligacoes_da_rede"]
    assert controlada["desde"] == "2026-08-31"


def test_valores_mobiliarios_emitidos_entram_so_como_contagem() -> None:
    entidades = _entidades("EA", "EC", "ED", "EV1", "EV2")
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "EA", "para": "EV1", "tipo": "emite", "fonte": "cvm-cda"},
            {"de": "EA", "para": "EV2", "tipo": "emite", "fonte": "cvm-cda"},
        ),
        entidades,
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]
    assert secao is not None
    assert _item(secao, "valores_mobiliarios") == 2


def test_empresa_que_so_emite_tem_a_secao_sem_lista_de_ligacoes() -> None:
    secao = _secao(
        _ligacoes({"de": "EA", "para": "EV1", "tipo": "emite", "fonte": "cvm-cda"}),
        _entidades("EA", "EV1"),
        identificadores=_identificadores(
            ("EA", "cnpj_raiz", RAIZ, None, None, "2010-01-01")
        ),
    )
    assert secao is not None
    assert _relacoes(secao) == []
    assert _item(secao, "valores_mobiliarios") == 1
    assert "identificadores_da_empresa" not in secao["tabelas"]  # tabela vazia não vai
    assert secao["fontes"] == [dossie.licenca_da_fonte("cvm")]


def test_conglomerado_do_banco_central_traz_a_licenca_dele() -> None:
    secao = _secao(
        _ligacoes(
            {
                "de": "EA",
                "para": "EB",
                "tipo": "do_conglomerado_de",
                "papel": "lider",
                "fonte": "bcb-ifdata",
            },
        )
    )
    assert _relacoes(secao) == [("Líder do conglomerado", "Empresa EB")]
    assert secao is not None
    assert any("Banco Central" in fonte for fonte in secao["fontes"])


def test_identificadores_publicos_da_empresa_vao_numa_tabela() -> None:
    secao = _secao(
        _ligacoes({"de": "EC", "para": "EA", "tipo": "controlada_de"}),
        identificadores=_ids_da_empresa(
            ("EA", "ticker", "CPFE3", "2010-01-01", None, "2010-01-01"),
            ("EA", "lei", "549300LEIDACPFL00001", None, None, "2015-01-01"),
            ("EA", "codigo_bcb_ifdata", "123", None, None, "2015-01-01"),
        ),
    )
    assert secao is not None
    identificadores = {
        linha["identificador"]: linha["valor"]
        for linha in secao["tabelas"]["identificadores_da_empresa"]
    }
    assert identificadores == {
        "CNPJ": "02.429.144/0001-93",
        "Ticker": "CPFE3",
        "LEI (GLEIF)": "549300LEIDACPFL00001",
        "Código no IF.data (Banco Central)": "123",
    }
    assert any("GLEIF" in fonte for fonte in secao["fontes"])


def test_lista_de_cada_relacao_para_em_20_mas_a_contagem_e_toda() -> None:
    controladas = [f"EC{i:02d}" for i in range(25)]
    secao = _secao(
        _ligacoes(
            *({"de": c, "para": "EA", "tipo": "controlada_de"} for c in controladas)
        ),
        _entidades("EA", *controladas),
        controladas=_fre(CNPJ, [], "2025-12-31").iloc[
            0:0
        ],  # FRE da própria empresa: não vale
    )
    # sem o FRE em dia nada do FRE sai: a contagem também respeita a regra
    assert secao is None
    pares = [(c, f"{i:08d}000100") for i, c in enumerate(controladas, start=10)]
    identificadores = _ids_da_empresa(
        *((c, "cnpj", cnpj, None, None, "2010-01-01") for c, cnpj in pares)
    )
    secao = _secao(
        _ligacoes(
            *({"de": c, "para": "EA", "tipo": "controlada_de"} for c in controladas)
        ),
        _entidades("EA", *controladas),
        identificadores,
        _fre(CNPJ, [cnpj for _, cnpj in pares], "2025-12-31"),
    )
    assert secao is not None
    assert len(secao["tabelas"]["ligacoes_da_rede"]) == dossie.LINHAS_NAS_LISTAS
    assert _item(secao, "controladas") == len(controladas)


def test_sem_ligacao_nao_ha_secao() -> None:
    assert (
        _secao(_ligacoes({"de": "EX", "para": "EY", "tipo": "controlada_de"})) is None
    )


def test_cnpj_fora_da_rede_nao_ha_secao() -> None:
    rede = dossie.preparar_rede(
        _ligacoes({"de": "EC", "para": "EA", "tipo": "controlada_de"}),
        _entidades("EA", "EC"),
        _ids_da_empresa(),
        FRES_EM_DIA,
        HOJE,
    )
    assert dossie.secao_rede("11111111000111", rede) is None


# --- o que nunca sai -------------------------------------------------------------------------------


def test_rede_sem_aresta_de_pessoa() -> None:
    pessoa = "P" + "0" * 20
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": pessoa, "para": "EA", "tipo": "controlada_de"},
            {"de": pessoa, "para": "EA", "tipo": "socio_de"},
        ),
        _entidades("EA", "EC", pessoa),
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]


def test_rede_sem_entidade_tratada_como_pessoa() -> None:
    entidades = _entidades("EA", "EC", "EMEI")
    entidades.loc[entidades["id_entidade"] == "EMEI", "trata_como_pessoa"] = True
    identificadores = _ids_da_empresa(
        ("EMEI", "cnpj", "44444444000144", None, None, "2010-01-01")
    )
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "EMEI", "para": "EA", "tipo": "controlada_de"},
        ),
        entidades,
        identificadores,
        pd.concat(
            [FRES_EM_DIA, _fre(CNPJ, ["44444444000144"], "2025-12-31")],
            ignore_index=True,
        ),
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]
    assert "Empresa EMEI" not in str(secao)


def test_entidade_que_nao_esta_na_rede_conta_como_pessoa() -> None:
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "ESUMIU", "para": "EA", "tipo": "audita", "fonte": "cvm-fca"},
        )
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]


@pytest.mark.parametrize("tipo", ["sancionada_por", "deve_a"])
def test_rede_sem_tipo_negativo(tipo: str) -> None:
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "EA", "para": "EB", "tipo": tipo, "fonte": "cgu-ceis"},
        )
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]
    assert tipo not in str(secao)


@pytest.mark.parametrize(
    ("tipo", "fonte"),
    [
        ("opera_para", "empresa_serie"),  # já está no setor regulado
        ("controlada_de", "fonte-nova"),  # fonte sem família conhecida: não sai
    ],
)
def test_ligacao_de_fonte_desconhecida_nao_sai(tipo: str, fonte: str) -> None:
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "ED", "para": "EA", "tipo": tipo, "fonte": fonte},
        )
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]


def test_ligacao_de_familia_bloqueada_nao_sai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dossie, "pode_usar", lambda _, familia: familia != "bcb")
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {
                "de": "EA",
                "para": "EB",
                "tipo": "do_conglomerado_de",
                "fonte": "bcb-ifdata",
            },
        ),
        identificadores=_ids_da_empresa(
            ("EA", "codigo_bcb_ifdata", "123", None, None, "2015-01-01")
        ),
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]
    assert secao is not None
    assert not any("Banco Central" in fonte for fonte in secao["fontes"])
    valores = [
        linha["valor"] for linha in secao["tabelas"]["identificadores_da_empresa"]
    ]
    assert "123" not in valores


def test_ligacao_do_fre_de_quem_parou_de_entregar_nao_sai() -> None:
    """A dona que parou de entregar o FRE (a VBC, que deixou a CPFL em 2011) não aparece como dona hoje."""
    velho = pd.concat(
        [
            _fre(CNPJ, [CNPJ_DA_CONTROLADA], "2025-12-31"),
            _fre(CNPJ_DA_DONA, [CNPJ], "2011-12-31"),
        ],
        ignore_index=True,
    )
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "EA", "para": "ED", "tipo": "controlada_de"},
        ),
        controladas=velho,
    )
    assert _relacoes(secao) == [("Controlada", "Empresa EC")]


def test_fre_em_dia_que_nao_lista_mais_a_sociedade_nao_a_mostra() -> None:
    sem_a_controlada = pd.concat(
        [
            _fre(CNPJ, ["55555555000155"], "2025-12-31"),
            _fre(CNPJ_DA_DONA, [CNPJ], "2025-12-31"),
        ],
        ignore_index=True,
    )
    secao = _secao(
        _ligacoes(
            {"de": "EC", "para": "EA", "tipo": "controlada_de"},
            {"de": "EA", "para": "ED", "tipo": "controlada_de"},
        ),
        controladas=sem_a_controlada,
    )
    assert _relacoes(secao) == [("Controladora", "Empresa ED")]


def test_fre_que_so_ficou_publico_depois_de_hoje_nao_conta() -> None:
    """Sem olhar o futuro: o FRE entregue depois do dia da ficha não deixa a ligação em dia."""
    futuro = _fre(CNPJ, [CNPJ_DA_CONTROLADA], "2026-09-30")
    futuro["conhecido_em"] = D("2027-01-15")
    secao = _secao(
        _ligacoes({"de": "EC", "para": "EA", "tipo": "controlada_de"}),
        controladas=pd.concat(
            [_fre(CNPJ, [], "2023-12-31"), futuro], ignore_index=True
        ),
    )
    assert secao is None


# --- o registro ------------------------------------------------------------------------------------


def test_secoes_do_molde_b_so_com_tabelas_que_podem_ser_mostradas() -> None:
    registro = {secao.chave: secao for secao in dossie.SECOES}
    assert set(dossie.SECOES_DO_MOLDE_B) == {"rede"}
    for chave in dossie.SECOES_DO_MOLDE_B:
        dossie.exigir_que_pode_mostrar(registro[chave].tabelas)
        assert dossie.LIMITES[chave]


def test_secao_rede_passa_no_filtro_de_pessoas() -> None:
    secao = _secao(_ligacoes({"de": "EC", "para": "EA", "tipo": "controlada_de"}))
    ficha = dossie.montar_ficha(CNPJ, "CPFL", [secao], "2026-10-17T07:00:00")
    dossie.conferir_sem_pessoas(ficha, {"empresa ed"})


def test_base_sem_a_rede_nao_tem_secao() -> None:
    vazia = pd.DataFrame()
    rede = dossie.preparar_rede(vazia, vazia, vazia, vazia, HOJE)
    assert dossie.secao_rede(CNPJ, rede) is None


def test_fre_sem_a_data_de_entrega_nao_deixa_nada_em_dia() -> None:
    assert (
        dossie.raizes_do_fre_em_dia(FRES_EM_DIA.drop(columns="conhecido_em"), HOJE)
        == set()
    )
