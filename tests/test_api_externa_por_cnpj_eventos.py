"""Os eventos de uma empresa na API externa (linha 736, PR 4): o leitor `conjuntos/eventos.py`.

Base de mentira, sem internet; os CNPJs são de ninguém. A ALFA entregou documentos ao IPE por dois
estabelecimentos da mesma raiz e trocou de auditor duas vezes; um documento e uma troca só ficaram públicos
depois do dia; outra empresa (BETA) tem os próprios documentos. Riscos: olhar o futuro, vazar pessoa (a rede
a trata como pessoa, o assunto livre do IPE, o auditor pessoa física) e a página perder ou repetir evento.
"""

import base64
from datetime import date

import pandas as pd
import pytest

from base import cnpj as cnpj_
from base.porta import Porta
from src.api_externa.conjuntos import eventos

DIA = date(2025, 6, 30)
IPE, FCA = "cvm-hist-ipe", "cvm-hist-fca"


def _cnpj(raiz: str, ordem: str = "0001") -> str:
    primeiros = f"{raiz}{ordem}"
    return primeiros + cnpj_.digitos_verificadores(primeiros)


ALFA = _cnpj("11111111")
ALFA_FILIAL = _cnpj("11111111", "0002")
BETA = _cnpj("22222222")
PESSOA = _cnpj("33333333")  # a rede a trata como pessoa
FORA_DA_REDE = _cnpj("44444444")
CONHECIDAS = [ALFA, BETA, PESSOA]

# (protocolo, cnpj, categoria, tipo, assunto, referência, publicado em)
DOCUMENTOS = [
    ("P1", ALFA, "Fato Relevante", "", "Aquisição da Gama por R$ 1 bi", "2025-05-02", "2025-05-02"),
    ("P2", ALFA, "Assembleia", "AGO", "Eleição do Sr. Fulano de Tal como conselheiro", "2025-04-28", "2025-03-28"),
    ("P3", ALFA_FILIAL, "Comunicado ao Mercado", "Outros Comunicados", "Aviso", "2025-03-28", "2025-03-28"),
    ("P4", ALFA, "Fato Relevante", "", "Venda depois do dia", "2025-07-10", "2025-07-10"),
    ("P5", BETA, "Fato Relevante", "", "Da outra empresa", "2025-05-02", "2025-05-02"),
    ("P6", PESSOA, "Fato Relevante", "", "De quem é tratada como pessoa", "2025-05-02", "2025-05-02"),
]  # fmt: skip

# (cnpj, conhecido em, efetiva em, anterior, novo, anos com o anterior, trata como pessoa)
TROCAS = [
    (ALFA, "2025-05-31", "2025-01-01", "AUDITORA UM", "AUDITORA DOIS", 5.0, False),
    (ALFA, "2025-05-31", "2024-06-01", "FULANO AUDITOR", "AUDITORA UM", 2.0, True),
    (ALFA, "2025-08-31", "2025-07-01", "AUDITORA DOIS", "AUDITORA TRES", 0.5, False),
]


def _eventos() -> pd.DataFrame:
    tabela = pd.DataFrame(
        DOCUMENTOS,
        columns=[
            "protocolo",
            "cnpj",
            "categoria",
            "tipo",
            "assunto",
            "referencia",
            "publicado_em",
        ],
    )
    tabela["cnpj"] = tabela["cnpj"].map(cnpj_.formatar)
    for coluna in ("referencia", "publicado_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela.assign(
        versao=1, empresa="X", rotulo="r", tema="t", materialidade=10,
        link=tabela["protocolo"].map(lambda p: f"https://www.rad.cvm.gov.br/ENET/doc?numProtocolo={p}"),
        ano_do_arquivo=2025, origem_sha256="0" * 64, origem_coletada_em="2025-08-01T00:00:00+00:00",
        montado_em="2025-08-01T00:00:00+00:00", versao_do_codigo="x",
    )  # fmt: skip


def _trocas() -> pd.DataFrame:
    tabela = pd.DataFrame(
        TROCAS,
        columns=["cnpj", "conhecido_em", "efetiva_em", "anterior", "novo", "anos_com_o_anterior",
                 "trata_como_pessoa"],
    )  # fmt: skip
    tabela["cnpj"] = tabela["cnpj"].map(cnpj_.formatar)
    for coluna in ("conhecido_em", "efetiva_em"):
        tabela[coluna] = pd.to_datetime(tabela[coluna]).dt.date
    return tabela.assign(
        empresa="ALFA S.A.", anterior_id="rede:a", novo_id=tabela["novo"].str.lower(),
        id_documento="1", montado_em="2025-09-01T00:00:00+00:00", versao_do_codigo="x",
    )  # fmt: skip


def _gravar_rede(base) -> None:
    rede = pd.DataFrame(
        {
            "id_entidade": [f"E{c[:8]}{'0' * 12}" for c in CONHECIDAS],
            "valor": [c[:8] for c in CONHECIDAS],
            "sistema": "cnpj_raiz",
            "tipo": "empresa",
            "mei": False,
            "trata_como_pessoa": [c == PESSOA for c in CONHECIDAS],
        }
    )
    (base / "rede").mkdir(parents=True, exist_ok=True)
    rede[["id_entidade", "tipo", "mei", "trata_como_pessoa"]].assign(
        nome=None, natureza_juridica="2046", natureza_fonte="receita", fontes="cvm-cadastro",
        publico_em=date(2020, 1, 1),
    ).to_parquet(base / "rede" / "entidades.parquet", index=False)  # fmt: skip
    rede[["id_entidade", "sistema", "valor"]].assign(
        desde=None, ate=None, publico_em=date(2020, 1, 1), regra=2, conferido_por="regra",
        fontes="cvm-cadastro",
    ).to_parquet(base / "rede" / "identificadores.parquet", index=False)  # fmt: skip


def gravar_base(base, documentos: pd.DataFrame | None = None):
    """A base de mentira dos eventos (também a da rota, em `..._eventos_rota.py`)."""
    _gravar_rede(base)
    (base / "eventos").mkdir(parents=True)
    (_eventos() if documentos is None else documentos).to_parquet(
        base / "eventos" / "2025.parquet", index=False
    )
    (base / "trocas_de_auditor").mkdir(parents=True)
    _trocas().to_parquet(base / "trocas_de_auditor" / "trocas.parquet", index=False)
    return base


@pytest.fixture
def pasta(tmp_path):
    return gravar_base(tmp_path / "base")


def _tudo(_fonte: str, _campo: str, _derivado: bool) -> bool:
    return True


def _ler(
    pasta,
    cnpj: str = ALFA,
    dia: date = DIA,
    permitido=_tudo,
    linhas_maximas=1000,
    **pedido,
):
    with Porta(pasta) as porta:
        return eventos.LeitorDeEventos(porta, permitido, linhas_maximas).eventos(
            cnpj, dia, **pedido
        )


def _corpo(pasta, **pedido) -> dict:
    servidos = _ler(pasta, **pedido)
    assert servidos is not None
    return servidos.corpo


def _valores(evento: dict) -> dict:
    return {
        nome: envelope["valor"] if isinstance(envelope, dict) else envelope
        for nome, envelope in evento.items()
    }


def _ids(corpo: dict) -> list[str]:
    return [
        str(v.get("protocolo") or v.get("efetiva_em"))
        for v in map(_valores, corpo["eventos"])
    ]


# ---------------------------------------------------------------- o que sai


def test_os_eventos_da_empresa_saem_do_mais_novo_ao_mais_velho(pasta):
    corpo = _corpo(pasta)
    assert corpo["cnpj"] == ALFA and corpo["como_era_em"] == "2025-06-30"
    # P1 (02/05) e a troca (31/05) ...; P2 e P3 no mesmo dia (28/03): o desempate é o tipo e o protocolo
    assert _ids(corpo) == ["2025-01-01", "P1", "P2", "P3"]
    assert corpo["cortada"] is False and corpo["proximo_cursor"] is None
    assert corpo["limites"] == list(eventos.LIMITES)


def test_o_documento_do_ipe_sai_com_o_que_a_cvm_classifica_e_o_endereco(pasta):
    p1 = _valores(_corpo(pasta)["eventos"][1])
    assert p1 == {
        "tipo_de_evento": "ipe_filing",
        "protocolo": "P1",
        "categoria": "Fato Relevante",
        "referencia": "2025-05-02",
        "link": "https://www.rad.cvm.gov.br/ENET/doc?numProtocolo=P1",
    }  # o tipo vazio some, nunca vira ""
    envelope = _corpo(pasta)["eventos"][1]["protocolo"]
    assert envelope["fonte"] == IPE and envelope["publico_em"] == "2025-05-02"


def test_o_assunto_livre_da_companhia_nunca_sai(pasta):
    corpo = _corpo(pasta)
    assert all("assunto" not in evento for evento in corpo["eventos"])
    assert "Fulano" not in repr(corpo)


def test_a_troca_de_auditor_sai_com_as_firmas_e_os_anos(pasta):
    troca = _corpo(pasta)["eventos"][0]
    assert _valores(troca) == {
        "tipo_de_evento": "auditor_change",
        "efetiva_em": "2025-01-01",
        "anterior": "AUDITORA UM",
        "novo": "AUDITORA DOIS",
        "anos_com_o_anterior": 5.0,
    }
    assert troca["novo"]["fonte"] == FCA and troca["novo"]["publico_em"] == "2025-05-31"


def test_a_troca_com_auditor_que_pode_ser_pessoa_nao_sai(pasta):
    assert "FULANO" not in repr(_corpo(pasta))


def test_os_documentos_de_outro_estabelecimento_da_mesma_raiz_entram(pasta):
    assert "P3" in _ids(_corpo(pasta))
    assert _ids(_corpo(pasta, cnpj=ALFA_FILIAL)) == _ids(_corpo(pasta))


def test_os_documentos_de_outra_empresa_nao_entram(pasta):
    assert _ids(_corpo(pasta, cnpj=BETA)) == ["P5"]


def test_as_fontes_sao_as_dos_eventos_servidos(pasta):
    assert _ler(pasta).fontes == {IPE, FCA}
    assert _ler(pasta, tipos=("ipe_filing",)).fontes == {IPE}
    assert _ler(pasta).linhas == 4


# ---------------------------------------------------------------- sem olhar o futuro


def test_o_que_ficou_publico_depois_do_dia_nao_entra(pasta):
    ids = _ids(_corpo(pasta))
    assert "P4" not in ids and "2025-07-01" not in ids
    depois = _ids(_corpo(pasta, dia=date(2025, 9, 1)))
    assert depois[:2] == ["2025-07-01", "P4"]


@pytest.mark.parametrize(
    "dia", [date(2025, 3, 27), date(2025, 3, 28), date(2025, 5, 2), DIA]
)
def test_nenhum_campo_servido_ficou_publico_depois_do_dia(pasta, dia):
    for evento in _corpo(pasta, dia=dia)["eventos"]:
        for nome, envelope in evento.items():
            if nome != "tipo_de_evento":
                assert envelope["publico_em"] <= dia.isoformat()


def test_cortar_o_futuro_da_base_nao_muda_a_resposta(tmp_path):
    inteira = gravar_base(tmp_path / "inteira")
    documentos = _eventos()
    cortada = gravar_base(
        tmp_path / "cortada", documentos[documentos["publicado_em"] <= DIA]
    )
    assert _corpo(inteira) == _corpo(cortada)


def test_antes_de_qualquer_evento_a_lista_sai_vazia(pasta):
    corpo = _corpo(pasta, dia=date(2024, 1, 1))
    assert corpo["eventos"] == [] and corpo["cortada"] is False


# ---------------------------------------------------------------- tipos e páginas


def test_o_filtro_de_tipos(pasta):
    assert _ids(_corpo(pasta, tipos=("auditor_change",))) == ["2025-01-01"]
    assert _ids(_corpo(pasta, tipos=("ipe_filing",))) == ["P1", "P2", "P3"]


def test_tipo_que_nao_existe_e_pedido_invalido():
    assert eventos.tipos_do_pedido([]) == ("ipe_filing", "auditor_change")
    assert eventos.tipos_do_pedido(["auditor_change"]) == ("auditor_change",)
    with pytest.raises(eventos.PedidoInvalido) as erro:
        eventos.tipos_do_pedido(["rumor"])
    assert erro.value.codigo == "invalid_event_type"


@pytest.mark.parametrize("tamanho", [1, 2, 3])
def test_as_paginas_nao_perdem_nem_repetem_evento(pasta, tamanho):
    vistos, cursor = [], None
    for _ in range(10):
        corpo = _corpo(pasta, linhas_maximas=tamanho, cursor=cursor)
        assert len(corpo["eventos"]) <= tamanho
        vistos += _ids(corpo)
        cursor = corpo["proximo_cursor"]
        assert (cursor is not None) == corpo["cortada"]
        if cursor is None:
            break
    assert vistos == _ids(_corpo(pasta))


def test_a_pagina_conta_as_linhas_servidas(pasta):
    servidos = _ler(pasta, linhas_maximas=3)
    assert servidos.linhas == 3 and servidos.corpo["cortada"] is True


@pytest.mark.parametrize(
    "cursor",
    [
        "nao-e-base64!",
        "eyJhIjogMX0",
        eventos.cursor_de((1, "x", "y"))[:-3] + "AAA",
        # JSON forjado com colchetes aninhados demais: era RecursionError (500), revisão cruzada do PR 4
        base64.urlsafe_b64encode(b"[" * 20000).decode(),
    ],
)
def test_cursor_que_nao_e_nosso_e_pedido_invalido(pasta, cursor):
    with pytest.raises(eventos.PedidoInvalido) as erro:
        _ler(pasta, cursor=cursor)
    assert erro.value.codigo == "invalid_cursor"


def test_a_mesma_troca_na_matriz_e_na_filial_nao_some_na_quebra_da_pagina(tmp_path):
    """Duas trocas iguais (dia, auditor novo) entregues por dois estabelecimentos da raiz: o CNPJ desempata,
    e a página de um evento não pula a segunda (revisão cruzada do PR 4)."""
    base = gravar_base(tmp_path / "base")
    trocas = _trocas()
    repetida = trocas.iloc[[0]].assign(cnpj=cnpj_.formatar(ALFA_FILIAL))
    pd.concat([trocas, repetida]).to_parquet(
        base / "trocas_de_auditor" / "trocas.parquet", index=False
    )
    inteira = _corpo(base, tipos=(eventos.TROCA_DE_AUDITOR,))
    vistos, cursor = 0, None
    for _ in range(5):
        corpo = _corpo(
            base, tipos=(eventos.TROCA_DE_AUDITOR,), linhas_maximas=1, cursor=cursor
        )
        vistos += len(corpo["eventos"])
        cursor = corpo["proximo_cursor"]
        if cursor is None:
            break
    assert len(inteira["eventos"]) == vistos == 2


def test_o_cursor_ida_e_volta():
    chave = (-739000, "ipe_filing", "P1")
    assert eventos.chave_do_cursor(eventos.cursor_de(chave)) == chave


# ---------------------------------------------------------------- sem pessoa e o portão


@pytest.mark.parametrize("cnpj", [PESSOA, FORA_DA_REDE])
def test_quem_a_rede_nao_conhece_como_empresa_nao_sai(pasta, cnpj):
    assert _ler(pasta, cnpj=cnpj) is None


def test_sem_nenhum_campo_liberado_nada_sai(pasta):
    assert _ler(pasta, permitido=lambda *_: False) is None


def test_campo_negado_some_e_o_evento_sem_campo_some(pasta):
    so_o_ipe_sem_link = _ler(
        pasta, permitido=lambda fonte, nome, _d: fonte == IPE and nome != "link"
    )
    assert so_o_ipe_sem_link is not None
    corpo = so_o_ipe_sem_link.corpo
    assert _ids(corpo) == ["P1", "P2", "P3"]
    assert all("link" not in evento for evento in corpo["eventos"])
    assert so_o_ipe_sem_link.fontes == {IPE}


# o tipo barrado no portão não some em silêncio (linha 878, achado do ensaio da 739): a lista vazia de um tipo
# que nem foi consultado parecia "a empresa não tem evento"
def _so_o_auditor(fonte: str, _campo: str, _derivado: bool) -> bool:
    return fonte == FCA


def test_tipo_barrado_vem_listado_como_nao_disponivel(pasta):
    corpo = _corpo(pasta, permitido=_so_o_auditor)
    assert corpo["tipos_nao_disponiveis"] == [eventos.DOCUMENTO_DO_IPE]
    assert _ids(corpo) == ["2025-01-01"]


def test_com_o_tipo_barrado_a_lista_vazia_nao_parece_que_nao_ha_evento(pasta):
    # antes de qualquer troca de auditor: a lista sai vazia, mas o corpo diz que o IPE não foi consultado
    corpo = _corpo(pasta, permitido=_so_o_auditor, dia=date(2025, 5, 1))
    assert corpo["eventos"] == []
    assert corpo["tipos_nao_disponiveis"] == [eventos.DOCUMENTO_DO_IPE]


def test_com_o_tipo_barrado_os_limites_nao_falam_dele(pasta):
    corpo = _corpo(pasta, permitido=_so_o_auditor)
    assert corpo["limites"] == [
        eventos.LIMITES_GERAIS[0],
        eventos.LIMITES_DO_TIPO[eventos.TROCA_DE_AUDITOR],
        eventos.LIMITE_DO_TIPO_NAO_DISPONIVEL,
        *eventos.LIMITES_GERAIS[1:],
    ]
    assert not any("IPE" in frase for frase in corpo["limites"])


def test_so_o_tipo_barrado_pedido_nada_sai(pasta):
    assert (
        _ler(pasta, permitido=_so_o_auditor, tipos=(eventos.DOCUMENTO_DO_IPE,)) is None
    )


def test_tipo_nao_pedido_nao_entra_como_nao_disponivel(pasta):
    corpo = _corpo(pasta, permitido=_so_o_auditor, tipos=(eventos.TROCA_DE_AUDITOR,))
    assert corpo["tipos_nao_disponiveis"] == []
    assert eventos.LIMITE_DO_TIPO_NAO_DISPONIVEL not in corpo["limites"]


def test_com_tudo_liberado_nenhum_tipo_fica_de_fora(pasta):
    corpo = _corpo(pasta, dia=date(2024, 1, 1))
    assert corpo["eventos"] == [] and corpo["tipos_nao_disponiveis"] == []
    assert corpo["limites"] == list(eventos.LIMITES)


def test_todo_tipo_tem_a_frase_de_limite():
    assert set(eventos.LIMITES_DO_TIPO) == set(eventos.ORIGENS)


def test_os_anos_com_o_anterior_pedem_o_direito_de_derivado(pasta):
    pedidos = []

    def anota(fonte, nome, derivado):
        pedidos.append((fonte, nome, derivado))
        return True

    _ler(pasta, permitido=anota)
    assert (FCA, "anos_com_o_anterior", True) in pedidos
    assert all(
        not derivado for _f, nome, derivado in pedidos if nome != "anos_com_o_anterior"
    )


def test_cnpj_invalido_e_erro_de_quem_chama(pasta):
    with pytest.raises(ValueError):
        _ler(pasta, cnpj="123")


def test_sem_as_tabelas_a_empresa_sai_sem_eventos(tmp_path):
    base = tmp_path / "base"
    _gravar_rede(base)
    assert _corpo(base)["eventos"] == []
