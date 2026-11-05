"""As conferências por CNPJ para a ficha do Ficha Clara (`base/conferencias_por_cnpj.py`; etapa 6).

Dados de mentira, sem internet: Parquets gravados à mão com as colunas das tabelas da base.
"""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pyarrow as pa
import pytest

from base import conferencias_por_cnpj as conferencias
from scripts import exportar_conferencias, montar_vista_do_cnpj
from tests import ajudantes_do_cnpj as exemplo

AGORA = datetime(2026, 10, 29, 12, tzinfo=UTC)
RAIZ, OUTRA, MEI = "11222333", "44555666", "77888999"


def _cnpj(raiz: str, filial: str = "0001") -> str:
    return f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:]}/{filial}-00"


def _sancao(raiz: str, id_na_fonte: str, visto: str, **campos) -> dict:
    return {
        "cadastro": "ceis",
        "id_na_fonte": id_na_fonte,
        "cnpj": _cnpj(raiz),
        "cnpj_basico": raiz,
        "categoria": campos.get("categoria", "Impedimento"),
        "situacao": "",
        "assunto": "texto livre com Fulano de Tal",
        "orgao": "Ministério de Teste",
        "inicio": pd.Timestamp(campos.get("inicio", "2025-01-10")),
        "valor_multa": None,
        "consta": campos.get("consta", True),
        "trata_como_pessoa": campos.get("pessoa", False),
        "visto_em": pd.Timestamp(visto),
        "disponivel_em": pd.Timestamp(campos.get("disponivel", visto)),
    }


def _gravar(base, tabela: str, linhas: list[dict], arquivo: str = "a") -> None:
    pasta = base / tabela
    pasta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_parquet(pasta / f"{arquivo}.parquet", index=False)


def _divida(raiz: str, retrato: str, valor: float, **campos) -> dict:
    return {
        "cnpj": _cnpj(raiz),
        "cnpj_basico": raiz,
        "tipo_divida": campos.get("tipo", "sida"),
        "situacao_inscricao": "Ativa",
        "inscricoes": 1,
        "valor_consolidado": valor,
        "data_do_retrato": pd.Timestamp(retrato),
        "trata_como_pessoa": False,
        "disponivel_em": pd.Timestamp(campos.get("disponivel", retrato)),
    }


@pytest.fixture
def base(tmp_path):
    pasta = tmp_path / "base"
    _gravar(
        pasta,
        "sancoes_cgu",
        [
            _sancao(RAIZ, "1", "2026-09-01", categoria="Suspensão"),
            _sancao(RAIZ, "1", "2026-10-01", categoria="Impedimento"),  # a mesma, mudou
            _sancao(RAIZ, "2", "2026-09-01"),
            _sancao(RAIZ, "2", "2026-10-01", consta=False),  # saiu da fonte
            _sancao(OUTRA, "3", "2026-11-01"),  # do futuro
            _sancao(MEI, "4", "2026-10-01", pessoa=True),
        ],
    )
    pgfn = pasta / "pgfn_divida"
    _gravar(pgfn, "2026-07", [_divida(RAIZ, "2026-06-30", 10.0)])
    _gravar(
        pgfn,
        "2026-10",
        [_divida(RAIZ, "2026-09-30", 25.5), _divida(OUTRA, "2026-09-30", 3.0)],
    )
    _gravar(
        pgfn, "2027-01", [_divida(RAIZ, "2026-12-31", 99.0, disponivel="2027-01-05")]
    )
    _gravar(
        pasta,
        "bcb_rde_ied",
        [
            {
                "id_na_fonte": "9",
                "cnpj_basico": OUTRA,
                "codigo_rde": "RDE1",
                "uf": "SP",
                "pais": "Portugal",
                "ocorrencia": "Registro",
                "mes": "2020-05",
                "consta": True,
                "trata_como_pessoa": False,
                "visto_em": pd.Timestamp("2026-10-29"),
                "disponivel_em": pd.Timestamp("2026-10-29"),
            }
        ],
    )
    return pasta


def _abrir(arquivo):
    banco = sqlite3.connect(arquivo)
    estado = json.loads(
        banco.execute("SELECT valor FROM meta WHERE chave = 'estado'").fetchone()[0]
    )
    return banco, estado


def _registros(banco, raiz: str, tabela: str) -> tuple[int, list[dict]] | None:
    linha = banco.execute(
        "SELECT total, linhas FROM registros WHERE raiz = ? AND tabela = ?",
        (raiz, tabela),
    ).fetchone()
    return None if linha is None else (linha[0], json.loads(linha[1]))


def test_sancao_vigente_e_a_mais_nova_ja_publica_e_que_ainda_consta(base, tmp_path):
    destino = tmp_path / "conferencias.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "sancoes_cgu")
    assert total == 1
    assert linhas[0]["categoria"] == "Impedimento" and linhas[0]["cnpj"] == _cnpj(RAIZ)
    assert linhas[0]["inicio"] == "2025-01-10"
    assert _registros(banco, OUTRA, "sancoes_cgu") is None  # ainda não era pública
    assert _registros(banco, MEI, "sancoes_cgu") is None  # pessoa não entra


def test_divida_e_o_retrato_mais_novo_ja_publico(base, tmp_path):
    destino = tmp_path / "conferencias.sqlite"
    estado = conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "pgfn_divida")
    assert total == 1 and linhas[0]["valor_consolidado"] == 25.5
    assert linhas[0]["data_do_retrato"] == "2026-09-30"
    (divida,) = [f for f in estado["fontes"] if f["tabela"] == "pgfn_divida"]
    assert divida["conferido_ate"] == "2026-09-30" and divida["empresas"] == 2


def test_fonte_sem_arquivo_fica_nao_conferida(base, tmp_path):
    estado = conferencias.montar(base, tmp_path / "c.sqlite", agora=AGORA)
    presentes = {f["tabela"] for f in estado["fontes"]}
    assert presentes == {"sancoes_cgu", "pgfn_divida", "bcb_rde_ied"}
    (sancoes,) = [f for f in estado["fontes"] if f["tabela"] == "sancoes_cgu"]
    assert sancoes["conferido_ate"] == "2026-10-01"  # o dia do retrato mais novo lido
    assert sancoes["orgao"] == "CGU" and sancoes["endereco"].startswith("https://")
    assert estado["grupo"] is None and estado["esquema"] == conferencias.ESQUEMA


def test_fonte_pela_raiz(base, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, (linha,) = _registros(banco, OUTRA, "bcb_rde_ied")
    assert total == 1 and linha == {
        "codigo_rde": "RDE1",
        "uf": "SP",
        "pais": "Portugal",
        "ocorrencia": "Registro",
        "mes": "2020-05",
    }


def test_limite_de_linhas_mostra_as_mais_novas_e_conta_todas(tmp_path):
    base = tmp_path / "base"
    _gravar(
        base,
        "sancoes_cgu",
        [
            _sancao(RAIZ, str(i), "2026-10-01")
            | {"inicio": pd.Timestamp("2000-01-01") + pd.Timedelta(days=i)}
            for i in range(conferencias.LINHAS_POR_FONTE + 7)
        ],
    )
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "sancoes_cgu")
    assert total == conferencias.LINHAS_POR_FONTE + 7
    assert len(linhas) == conferencias.LINHAS_POR_FONTE
    assert linhas[0]["inicio"] > linhas[-1]["inicio"]


def test_nada_de_texto_livre_nem_de_pessoa_no_arquivo(base, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    conteudo = "\n".join(
        str(linha)
        for linha in sqlite3.connect(destino).execute("SELECT * FROM registros")
    )
    assert "Fulano" not in conteudo and "assunto" not in conteudo
    assert MEI not in conteudo


def test_grupo_leva_as_ligacoes_da_vista_sem_pessoa(base, tmp_path):
    vista = tmp_path / "vista"
    montar_vista_do_cnpj.montar(exemplo.gravar_base(tmp_path / "cnpj"), vista)
    destino = tmp_path / "c.sqlite"
    estado = conferencias.montar(base, destino, vista=vista, agora=AGORA)
    assert estado["grupo"]["retrato"] == exemplo.ULTIMO_MES
    assert estado["grupo"]["ligacoes"] == 1
    banco = sqlite3.connect(destino)
    assert banco.execute("SELECT socia, empresa FROM ligacoes").fetchall() == [
        (exemplo.SOCIO_PJ, exemplo.LIMITADA)
    ]
    texto = "\n".join(str(linha) for linha in banco.execute("SELECT * FROM ligacoes"))
    assert exemplo.NOME_DO_SOCIO not in texto and exemplo.ID_DO_SOCIO not in texto


def test_arquivo_novo_substitui_o_velho_por_inteiro(base, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    assert banco.execute("SELECT count(*) FROM registros").fetchone()[0] == 4
    assert not (tmp_path / "c.sqlite.parcial").exists()


def test_comando_grava_o_arquivo(base, tmp_path, monkeypatch):
    monkeypatch.setattr(
        exportar_conferencias, "exigir_versao_do_codigo", lambda: "teste"
    )
    destino = tmp_path / "saida" / "conferencias.sqlite"
    assert (
        exportar_conferencias.main(["--base", str(base), "--destino", str(destino)])
        == 0
    )
    _, estado = _abrir(destino)
    assert len(estado["fontes"]) == 3


def _financiamento(raiz: str, id_na_fonte: str, visto: str, **campos) -> dict:
    return {
        "id_na_fonte": id_na_fonte,
        "fonte": campos.get("fonte", "bndes"),
        "modalidade": "bndes_nao_automatica",
        "cnpj": _cnpj(raiz),
        "cnpj_basico": raiz,
        "uf": "SP",
        "contrato": "12345",
        "contratado_em": pd.Timestamp(campos.get("contratado", "2024-03-10")),
        "valor_contratado": Decimal("1000.00"),
        "valor_desembolsado": campos.get("desembolsado", Decimal("100.00")),
        "financiador": "BNDES",
        "agente_papel": "financiador_direto",
        "cnpj_do_executor": "99.888.777/0001-00",
        "situacao": "LIQUIDADA",
        "situacao_classe": "liquidado",
        "consta": campos.get("consta", True),
        "trata_como_pessoa": campos.get("pessoa", False),
        "visto_em": pd.Timestamp(visto),
        "disponivel_em": pd.Timestamp(campos.get("disponivel", visto)),
    }


@pytest.fixture
def base_com_financiamentos(base):
    _gravar(
        base,
        "financiamentos_bndes",
        [
            _financiamento(RAIZ, "b1", "2026-09-01"),
            _financiamento(RAIZ, "b1", "2026-10-01", desembolsado=Decimal("250.04")),
            _financiamento(
                RAIZ, "b2", "2026-10-01", desembolsado=None, contratado="2025-06-01"
            ),
            _financiamento(OUTRA, "b3", "2026-11-01"),  # do futuro
            _financiamento(MEI, "b4", "2026-10-01", pessoa=True),
        ],
        arquivo="bndes",
    )
    _gravar(
        base,
        "financiamentos_finep",
        [_financiamento(OUTRA, "f1", "2026-10-01", fonte="finep")],
        arquivo="finep",
    )
    return base


def test_financiamento_vigente_e_o_valor_mais_novo_com_o_dinheiro_exato(
    base_com_financiamentos, tmp_path
):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base_com_financiamentos, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, (b2, b1) = _registros(banco, RAIZ, "financiamentos_bndes")
    assert total == 2  # o mais novo primeiro (contratado em 2025)
    assert b1["valor_desembolsado"] == "250.04" and b1["valor_contratado"] == "1000.00"
    assert b2["valor_desembolsado"] is None  # vazio fica vazio, nunca zero
    assert b1["situacao_classe"] == "liquidado" and b1["contratado_em"] == "2024-03-10"
    assert "cnpj_do_executor" not in b1 and "id_na_fonte" not in b1
    assert (
        _registros(banco, OUTRA, "financiamentos_bndes") is None
    )  # ainda não era pública
    assert _registros(banco, MEI, "financiamentos_bndes") is None  # pessoa não entra
    assert _registros(banco, OUTRA, "financiamentos_finep")[0] == 1


def test_financiamentos_tem_tema_proprio_e_a_licenca_de_cada_banco(
    base_com_financiamentos, tmp_path
):
    estado = conferencias.montar(
        base_com_financiamentos, tmp_path / "c.sqlite", agora=AGORA
    )
    assert "financiamentos" in estado["temas"]
    fontes = {f["tabela"]: f for f in estado["fontes"]}
    assert fontes["financiamentos_bndes"]["tema"] == "financiamentos"
    assert fontes["financiamentos_finep"]["tema"] == "financiamentos"
    assert "ODbL" in fontes["financiamentos_bndes"]["licenca"]
    assert "a confirmar" in fontes["financiamentos_finep"]["licenca"]
    assert all(f["licenca"] for f in estado["fontes"])  # toda fonte leva a sua


def test_ordem_pelo_valor_decimal_e_a_do_numero_e_nao_a_do_texto(tmp_path):
    base = tmp_path / "base"
    _gravar(
        base / "pgfn_divida",
        "2026-10",
        [
            _divida(RAIZ, "2026-09-30", 0, tipo="sida")
            | {"valor_consolidado": Decimal("99.00")},
            _divida(RAIZ, "2026-09-30", 0, tipo="fgts")
            | {"valor_consolidado": Decimal("1000.00")},
        ],
    )
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    _, linhas = _registros(banco, RAIZ, "pgfn_divida")
    assert [linha["valor_consolidado"] for linha in linhas] == ["1000.00", "99.00"]


# ---- preços máximos da CMED: uma fonte por lista ---------------------------------------------
PRECOS_DA_CMED = (
    "pf_sem_impostos", "pf_0", "pf_18", "pmc_sem_impostos", "pmc_0", "pmc_18",
    "pmvg_sem_impostos", "pmvg_0", "pmvg_18",
)  # fmt: skip


def _apresentacao(raiz: str, id_na_fonte: str, visto: str, **campos) -> dict:
    lista = campos.get("lista", "consumidor")
    pf = Decimal(campos.get("pf", "2123.68"))
    maximo = {"pmc": None, "pmvg": None}
    maximo["pmc" if lista == "consumidor" else "pmvg"] = campos.get("maximo")
    return {
        "lista": lista,
        "id_na_fonte": id_na_fonte,
        "cnpj": _cnpj(raiz, campos.get("filial", "0001")),
        "cnpj_basico": raiz,
        "ggrem": f"5{id_na_fonte:0>14}",
        "registro": "1018004200017",
        "produto": "PRODUTO DE TESTE",
        "apresentacao": "250 MG PO LIOF SOL INJ CT FA VD TRANS",
        "substancia": "SUBSTÂNCIA DE TESTE",
        "tipo_de_produto": "Biológico",
        "regime_de_preco": "Regulado",
        "pf_sem_impostos": pf,
        "pf_0": pf,
        "pf_18": (pf * Decimal("1.2195")).quantize(Decimal("0.01")),
        **{
            f"{sigla}_{sufixo}": maximo[sigla]
            for sigla in maximo
            for sufixo in ("sem_impostos", "0")
        },
        "pmc_18": None,
        "pmvg_18": None,
        "precos_com_asterisco": False,
        "restricao_hospitalar": True,
        "cap": False,
        "confaz_87": True,
        "lista_publicada_em": pd.Timestamp("2026-10-09").date(),
        "consta": campos.get("consta", True),
        "trata_como_pessoa": campos.get("pessoa", False),
        "visto_em": pd.Timestamp(visto),
        "disponivel_em": pd.Timestamp(campos.get("disponivel", visto)),
    }


def _gravar_cmed(base, lista: str, linhas: list[dict]) -> None:
    """Como a carga grava: um Parquet por lista, os preços em decimal exato."""
    pasta = base / "cmed_precos"
    pasta.mkdir(parents=True, exist_ok=True)
    decimal = pd.ArrowDtype(pa.decimal128(18, 2))
    tabela = pd.DataFrame(linhas)
    tabela = tabela.astype({c: decimal for c in PRECOS_DA_CMED})
    tabela.to_parquet(pasta / f"{lista}.parquet", index=False)


@pytest.fixture
def base_com_cmed(base):
    _gravar_cmed(
        base,
        "consumidor",
        [
            _apresentacao(RAIZ, "1", "2026-09-01", pf="2000.00"),
            _apresentacao(RAIZ, "1", "2026-10-01", maximo=Decimal("2935.98")),
            _apresentacao(
                RAIZ, "1", "2026-11-01", pf="9999.99"
            ),  # reajuste ainda não público
            _apresentacao(RAIZ, "2", "2026-10-01", filial="0002", pf="10.50"),
            _apresentacao(RAIZ, "3", "2026-10-01", consta=False),  # saiu da lista
            _apresentacao(MEI, "4", "2026-10-01", pessoa=True),
        ],
    )
    _gravar_cmed(
        base,
        "governo",
        [
            _apresentacao(
                RAIZ, "1", "2026-09-01", lista="governo", maximo=Decimal("1666.43")
            ),
        ],
    )
    return base


def test_cmed_cada_lista_e_uma_fonte_com_o_proprio_total(base_com_cmed, tmp_path):
    destino = tmp_path / "c.sqlite"
    estado = conferencias.montar(base_com_cmed, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "cmed_precos_consumidor")
    assert total == 2  # a que saiu da lista não conta; o reajuste do futuro não duplica
    assert [linha["cnpj"] for linha in linhas] == [_cnpj(RAIZ), _cnpj(RAIZ, "0002")]
    governo_total, (governo,) = _registros(banco, RAIZ, "cmed_precos_governo")
    assert governo_total == 1 and governo["pmvg_0"] == "1666.43"
    assert "pmc_0" not in governo and "pmvg_0" not in linhas[0]
    assert _registros(banco, MEI, "cmed_precos_consumidor") is None  # pessoa não entra
    fontes = {f["tabela"]: f for f in estado["fontes"]}
    assert fontes["cmed_precos_consumidor"]["conferido_ate"] == "2026-10-01"
    assert (
        fontes["cmed_precos_governo"]["conferido_ate"] == "2026-09-01"
    )  # a da própria lista
    assert fontes["cmed_precos_governo"]["empresas"] == 1


def test_cmed_valor_em_texto_exato_sem_o_icms_de_cada_estado(base_com_cmed, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base_com_cmed, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    _, (orencia, filial) = _registros(banco, RAIZ, "cmed_precos_consumidor")
    assert orencia["pf_0"] == "2123.68" and orencia["pf_sem_impostos"] == "2123.68"
    assert orencia["pmc_0"] == "2935.98"  # nunca 2935.9799999
    assert filial["pmc_0"] is None  # sem PMC fica vazio, nunca zero
    assert "pf_18" not in orencia and "pmc_18" not in orencia  # alíquotas ficam na base
    assert orencia["lista_publicada_em"] == "2026-10-09"
    assert orencia["publico_desde"] == "2026-10-01"
    assert orencia["restricao_hospitalar"] is True and orencia["confaz_87"] is True
    assert "id_na_fonte" not in orencia and "consta" not in orencia


def test_cmed_tem_tema_proprio_e_a_licenca_a_confirmar(base_com_cmed, tmp_path):
    estado = conferencias.montar(base_com_cmed, tmp_path / "c.sqlite", agora=AGORA)
    assert estado["temas"]["precos"].startswith("Preços máximos")
    fontes = {f["tabela"]: f for f in estado["fontes"]}
    for nome in ("cmed_precos_consumidor", "cmed_precos_governo"):
        assert (
            fontes[nome]["tema"] == "precos"
            and fontes[nome]["orgao"] == "CMED (Anvisa)"
        )
        assert "a confirmar" in fontes[nome]["licenca"]  # não a CC BY da Anvisa
    assert estado["esquema"] == "1"  # fonte nova não muda o esquema


def test_cmed_ausente_ou_sem_arquivo_fica_nao_conferida(base, tmp_path):
    estado = conferencias.montar(base, tmp_path / "a.sqlite", agora=AGORA)
    assert not [f for f in estado["fontes"] if f["tema"] == "precos"]
    (base / "cmed_precos").mkdir()  # a pasta existe, mas nenhuma lista foi montada
    estado = conferencias.montar(base, tmp_path / "b.sqlite", agora=AGORA)
    assert not [f for f in estado["fontes"] if f["tema"] == "precos"]
    _gravar_cmed(
        base, "governo", [_apresentacao(OUTRA, "9", "2026-10-01", lista="governo")]
    )
    estado = conferencias.montar(base, tmp_path / "c.sqlite", agora=AGORA)
    temas = {f["tabela"] for f in estado["fontes"] if f["tema"] == "precos"}
    assert temas == {"cmed_precos_governo"}  # a lista que falta não vira zero


def test_cmed_limite_de_linhas_pelo_preco_numerico_e_conta_todas(tmp_path):
    base = tmp_path / "base"
    _gravar_cmed(
        base,
        "consumidor",
        [
            _apresentacao(RAIZ, str(i), "2026-10-01", pf=f"{i}.50")
            for i in range(conferencias.LINHAS_POR_FONTE + 10)
        ],
    )
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "cmed_precos_consumidor")
    assert total == conferencias.LINHAS_POR_FONTE + 10
    assert len(linhas) == conferencias.LINHAS_POR_FONTE
    valores = [Decimal(linha["pf_0"]) for linha in linhas]
    assert valores[0] == Decimal("59.50") and valores == sorted(valores, reverse=True)


# --- processos judiciais do DJEN (plano dos processos de 03/11/2026, PR 4) ------------------------

PROCESSO_A = "0000011-00.2019.8.26.0100"
PROCESSO_B = "0000012-00.2019.8.26.0100"
PROCESSO_FUTURO = "0000013-00.2019.8.26.0100"
HASH_VELHA, HASH_NOVA, HASH_CANCELADA = "AbC123xyz0", "DeF456uvw1", "GhI789rst2"


def _parte(numero: str, id_na_fonte: str, dia: str, **campos) -> dict:
    return {
        "id_na_fonte": id_na_fonte,
        "numero_processo": numero,
        "polo": campos.get("polo", "passivo"),
        "tipo_parte": campos.get("tipo", "companhia"),
        "parte": campos.get("parte", "EMPRESA DE TESTE S.A."),
        "cnpj": campos.get("cnpj", _cnpj(RAIZ)),
        "empresa": "EMPRESA DE TESTE S.A.",
        "orgao_publico": None,
        "disponivel_em": pd.Timestamp(dia),
        "visto_em": pd.Timestamp(campos.get("visto", dia)),
    }


def _comunicacao_djen(numero: str, id_na_fonte: str, dia: str, **campos) -> dict:
    cancelada = campos.get("cancelada")
    return {
        "id_na_fonte": id_na_fonte,
        "numero_processo": numero,
        "tribunal": "TJSP",
        "link": "https://pje.tribunal.exemplo/validacao/123",
        "advogados": 3,
        "cancelada_em": pd.Timestamp(cancelada) if cancelada else pd.NaT,
        "disponivel_em": pd.Timestamp(dia),
        "visto_em": pd.Timestamp(campos.get("visto", dia)),
    }


def _processo(numero: str, dia: str, **campos) -> dict:
    return {
        "numero_processo": numero,
        "ano_do_processo": 2019,
        "justica": "Justiça Estadual",
        "tribunal": "TJSP",
        "orgao": "1ª Vara Cível",
        "classe_codigo": "1116",
        "classe": "EXECUÇÃO FISCAL",
        "classe_tpu": campos.get("classe_tpu", "Execução Fiscal"),
        "ramo": campos.get("ramo", "execucao_fiscal"),
        "disponivel_em": pd.Timestamp(dia),
        "visto_em": pd.Timestamp(dia),
    }


@pytest.fixture
def base_com_processos(base):
    _gravar(
        base,
        "processos_partes",
        [
            _parte(PROCESSO_A, HASH_VELHA, "2025-03-01"),
            _parte(PROCESSO_A, HASH_NOVA, "2026-10-01", polo="ativo"),  # a mesma ligação
            _parte(PROCESSO_A, HASH_VELHA, "2025-03-01", tipo="pessoa_ou_desconhecida",
                   parte="FULANO DE TAL", cnpj=None, polo="ativo"),
            _parte(PROCESSO_B, "id-b", "2026-06-01", polo="ativo"),
            _parte(PROCESSO_FUTURO, "id-f", "2026-11-01"),  # depois do dia da montagem
        ],
    )  # fmt: skip
    _gravar(
        base,
        "processos_comunicacoes",
        [
            _comunicacao_djen(PROCESSO_A, HASH_VELHA, "2025-03-01"),
            _comunicacao_djen(PROCESSO_A, HASH_NOVA, "2026-10-01"),
            _comunicacao_djen(PROCESSO_B, "771885778", "2026-06-01"),  # sem hash, só o id
            _comunicacao_djen(PROCESSO_B, HASH_CANCELADA, "2026-07-01", cancelada="2026-07-05"),
            _comunicacao_djen(PROCESSO_FUTURO, "id-f", "2026-11-01"),
        ],
    )  # fmt: skip
    _gravar(
        base,
        "processos",
        [
            _processo(PROCESSO_A, "2025-03-01"),
            _processo(PROCESSO_B, "2026-06-01", classe_tpu=None, ramo=None),
            _processo(PROCESSO_FUTURO, "2026-11-01"),
        ],
    )
    return base


def test_processos_com_tribunal_classe_polo_datas_e_a_certidao_do_djen(
    base_com_processos, tmp_path
):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base_com_processos, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "processos")
    assert total == 2  # o processo que só ficou público depois do dia não entra
    a, b = linhas  # a comunicação mais nova primeiro
    assert a == {
        "cnpj": _cnpj(RAIZ),
        "numero_processo": PROCESSO_A,
        "tribunal": "TJSP",
        "orgao": "1ª Vara Cível",
        "classe": "Execução Fiscal",
        "ramo": "execucao_fiscal",
        "polo": "passivo",  # o da primeira comunicação que liga o processo à companhia
        "ligado_em": "2025-03-01",
        "ultima_comunicacao": "2026-10-01",
        "certidao": f"{conferencias.CERTIDAO_DO_DJEN}/{HASH_NOVA}/certidao",
    }
    assert b["numero_processo"] == PROCESSO_B and b["polo"] == "ativo"
    assert b["classe"] == "EXECUÇÃO FISCAL"  # sem a TPU, a classe como o DJEN escreve
    assert b["ramo"] is None


def test_certidao_e_so_a_da_comunicacao_valida_e_com_hash(base_com_processos, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base_com_processos, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    _, linhas = _registros(banco, RAIZ, "processos")
    b = linhas[1]
    # a de julho foi cancelada; a de junho só tem o id numérico, sem endereço de certidão
    assert b["ultima_comunicacao"] == "2026-06-01"
    assert b["certidao"] is None


def test_certidao_so_com_hash_de_letras_e_numeros():
    assert conferencias.certidao_do_djen(HASH_NOVA).endswith(f"/{HASH_NOVA}/certidao")
    for estranho in ("771885778", "", None, "abc/../x", "abc?x=1", "a b"):
        assert conferencias.certidao_do_djen(estranho) is None


def test_processos_por_ano_contam_polo_e_ramo(base_com_processos, tmp_path):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base_com_processos, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "processos_por_ano")
    assert total == 2
    assert [linha["ano"] for linha in linhas] == [
        2026,
        2025,
    ]  # o ano mais novo primeiro
    ano_2026, ano_2025 = linhas
    assert (ano_2026["processos"], ano_2026["como_autora"], ano_2026["como_re"]) == (
        1,
        1,
        0,
    )
    assert ano_2026["sem_ramo"] == 1
    assert (
        ano_2025["processos"],
        ano_2025["como_re"],
        ano_2025["execucao_fiscal"],
    ) == (1, 1, 1)


def test_processos_sem_nome_de_pessoa_nem_advogado_nem_link_do_tribunal(
    base_com_processos, tmp_path
):
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base_com_processos, destino, agora=AGORA)
    conteudo = "\n".join(
        str(linha)
        for linha in sqlite3.connect(destino).execute("SELECT * FROM registros")
    )
    assert "FULANO" not in conteudo and "EMPRESA DE TESTE" not in conteudo
    assert "advogados" not in conteudo and "pje.tribunal.exemplo" not in conteudo


def test_processos_tem_tema_proprio_licenca_do_djen_e_a_data_da_busca(
    base_com_processos, tmp_path
):
    estado = conferencias.montar(base_com_processos, tmp_path / "c.sqlite", agora=AGORA)
    assert estado["temas"]["processos"].startswith("Processos judiciais")
    fontes = {f["tabela"]: f for f in estado["fontes"] if f["tema"] == "processos"}
    assert set(fontes) == {"processos", "processos_por_ano"}
    for fonte in fontes.values():
        assert fonte["orgao"] == "CNJ (DJEN)"
        assert fonte["licenca"].startswith("DJEN do CNJ")
        # "não encontrado" só com a data da busca: a comunicação mais nova vista até o dia
        assert fonte["conferido_ate"] == "2026-10-01"
    assert (
        fontes["processos"]["empresas"] == 1 and fontes["processos"]["registros"] == 2
    )
    assert estado["esquema"] == "1"


def test_processos_sem_as_tabelas_ficam_nao_conferidos(base, tmp_path):
    estado = conferencias.montar(base, tmp_path / "a.sqlite", agora=AGORA)
    assert not [f for f in estado["fontes"] if f["tema"] == "processos"]
    _gravar(base, "processos_partes", [_parte(PROCESSO_A, HASH_VELHA, "2025-03-01")])
    estado = conferencias.montar(base, tmp_path / "b.sqlite", agora=AGORA)
    assert not [
        f for f in estado["fontes"] if f["tema"] == "processos"
    ]  # faltam as outras


def test_processos_limite_de_linhas_mostra_os_mais_novos_e_conta_todos(tmp_path):
    base = tmp_path / "base"
    numeros = [
        f"{i:07d}-00.2019.8.26.0100" for i in range(conferencias.LINHAS_POR_FONTE + 5)
    ]
    dias = [
        (pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)).date().isoformat()
        for i in range(len(numeros))
    ]
    pares = list(enumerate(zip(numeros, dias, strict=True)))
    _gravar(base, "processos_partes", [_parte(n, f"h{i}", d) for i, (n, d) in pares])
    _gravar(
        base,
        "processos_comunicacoes",
        [_comunicacao_djen(n, f"h{i}", d) for i, (n, d) in pares],
    )
    _gravar(base, "processos", [_processo(n, d) for _, (n, d) in pares])
    destino = tmp_path / "c.sqlite"
    conferencias.montar(base, destino, agora=AGORA)
    banco, _ = _abrir(destino)
    total, linhas = _registros(banco, RAIZ, "processos")
    assert total == conferencias.LINHAS_POR_FONTE + 5
    assert len(linhas) == conferencias.LINHAS_POR_FONTE
    assert linhas[0]["numero_processo"] == numeros[-1]
