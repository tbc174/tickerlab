"""Os bancos na seção `setor` (molde D, plano de 19/10/2026, PR 2): o IF.data do Banco Central.

O participante é o conglomerado prudencial (tipo 1 do IF.data), ligado à companhia aberta pela
`ligacao_dos_bancos`. O mercado de exemplo: Caixa, BB, Itaú, um conglomerado fechado e dois pequenos;
o BB e o Itaú têm ticker. Os números são trimestrais (a data-base), e o estoque do ano é o de dezembro.
"""

import pandas as pd
import pytest

from base import dossie

D = pd.Timestamp
ITAU, BB, SEM_TICKER = "60872504000123", "00000000000191", "77777777000177"
C_ITAU, C_BB, C_CAIXA, C_FECHADO = "C0080099", "C0080329", "C0080000", "C0080075"
PEQUENO_1, PEQUENO_2 = (
    "C0089991",
    "12345678",
)  # um sem conglomerado (código de 8 dígitos)
C_ITAU_FINANCEIRO = "C0010069"  # o mesmo Itaú no tipo 2: não está nas séries do tipo 1
BANCOS = next(s for s in dossie.SETORES_DO_LANCAMENTO if s.chave == "bancos")
HOJE = D("2026-10-17")
DEZEMBRO = {  # a carteira de crédito no fim de cada ano (o estoque que conta)
    2024: {C_CAIXA: 30, C_BB: 25, C_ITAU: 20, C_FECHADO: 15, PEQUENO_1: 5, PEQUENO_2: 5},
    2025: {C_CAIXA: 28, C_BB: 26, C_ITAU: 22, C_FECHADO: 14, PEQUENO_1: 6, PEQUENO_2: 4},
}  # fmt: skip


def _serie(nome: str) -> dossie.SerieDaAgencia:
    return next(s for s in dossie.SERIES_DOS_BANCOS if s.nome == nome)


def _trimestral() -> pd.DataFrame:
    """(competencia, chave, valor) por data-base: os outros trimestres valem o dobro de dezembro, e
    2026 só tem março (o ano corrente)."""
    linhas = []
    for ano, valores in DEZEMBRO.items():
        for mes in (3, 6, 9, 12):
            data = D(year=ano, month=mes, day=1) + pd.offsets.MonthEnd(0)
            fator = 1 if mes == 12 else 2
            linhas += [(data, chave, float(v * fator)) for chave, v in valores.items()]
    linhas += [(D("2026-03-31"), chave, 10.0) for chave in DEZEMBRO[2025]]
    return pd.DataFrame(linhas, columns=["competencia", "chave", "valor"])


def _credito() -> pd.DataFrame:
    serie = _serie("bcb_carteira_de_credito")
    return dossie.serie_anual(_trimestral(), serie.modo, serie.meses_por_periodo)


def _ligacao() -> pd.DataFrame:
    """A `ligacao_dos_bancos` como a base grava: todas as instituições, a maioria sem CNPJ."""
    linhas = [
        (D("2025-12-31"), C_ITAU, "ITAU - PRUDENCIAL", "60.872.504/0001-23", "ITUB4"),
        (D("2025-12-31"), C_ITAU_FINANCEIRO, "ITAU", "60.872.504/0001-23", "ITUB4"),
        (D("2025-12-31"), C_BB, "BB - PRUDENCIAL", "00.000.000/0001-91", "BBAS3"),
        (D("2025-12-31"), C_CAIXA, "CAIXA ECONOMICA FEDERAL - PRUDENCIAL", None, None),
        (D("2024-12-31"), C_BB, "BB - PRUDENCIAL", "00.000.000/0001-91", "BBAS3"),
        # a data-base de junho de 2026 só fica pública no fim de outubro: não vale na ficha de 17/10
        (
            D("2026-06-30"),
            C_FECHADO,
            "FECHADO - PRUDENCIAL",
            "77.777.777/0001-77",
            None,
        ),
    ]
    tabela = pd.DataFrame(
        linhas, columns=["data_base", "cod_inst", "instituicao", "cnpj", "tickers"]
    )
    return tabela.assign(
        cnpj_raiz=tabela["cnpj"].str[:10], ligado_por="líder do conglomerado"
    )


def _ligacoes() -> pd.DataFrame:
    chaves = set(_credito()["chave"])
    return dossie.ligacoes_dos_bancos(_ligacao(), chaves, HOJE)


def _empresas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cnpj": [ITAU, BB, SEM_TICKER],
            "empresa": [
                "ITAU UNIBANCO HOLDING S.A.",
                "BCO BRASIL S.A.",
                "FECHADO S.A.",
            ],
        }
    )


def _membros() -> pd.DataFrame:
    return dossie.membros_do_setor(BANCOS, _empresas().iloc[:2], _ligacoes())


def _series(credito: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    basileia = pd.DataFrame(
        {
            "ano": [2024, 2025, 2025],
            "chave": [C_ITAU, C_ITAU, C_BB],
            "valor": [0.16, 0.152, 0.14],
            "meses": [12, 12, 12],
            "ultimo_mes": [D("2024-12-31"), D("2025-12-31"), D("2025-12-31")],
        }
    )
    modalidades = pd.DataFrame(
        {
            "ano": [2025, 2025, 2025],
            "chave": [C_ITAU, C_ITAU, C_CAIXA],
            "abertura": ["Cartão de Crédito", "Habitação", "Habitação"],
            "valor": [154.0, 141.0, 900.0],
            "meses": [12, 12, 12],
            "ultimo_mes": [D("2025-12-31")] * 3,
        }
    )
    return {
        "bcb_carteira_de_credito": _credito() if credito is None else credito,
        "bcb_indice_de_basileia": basileia,
        "bcb_carteira_pf_por_modalidade": modalidades,
    }


def _secao(credito: pd.DataFrame | None = None) -> dict:
    secao = dossie.secao_setor(BANCOS, _membros(), _series(credito), _ligacoes(), {})
    assert secao is not None
    return secao


# --- as séries ------------------------------------------------------------------------------------


def test_bancos_series_leem_as_colunas_que_existem_no_ifdata() -> None:
    """Os nomes do relatório 1 conferidos no acervo (201403 a 202606): a carteira mudou de nome com a
    contabilidade de 2025, e as duas valem."""
    colunas = {
        s.nome: dict(s.filtros)["coluna"]
        for s in dossie.SERIES_DOS_BANCOS
        if dict(s.filtros)["relatorio"] == 1
    }
    assert colunas == {
        "bcb_ativo_total": ("Ativo Total",),
        "bcb_carteira_de_credito": ("Carteira de Crédito Classificada", "Carteira de Crédito"),
        "bcb_captacoes": ("Captações",),
        "bcb_indice_de_basileia": ("Índice de Basileia",),
    }  # fmt: skip
    for serie in dossie.SERIES_DOS_BANCOS:
        assert dict(serie.filtros)["tipo_instituicao"] == 1  # o conglomerado prudencial
        assert serie.data == "data_base" and serie.como_era


def test_bancos_estoque_e_o_ultimo_trimestre_e_quatro_datas_fazem_o_ano() -> None:
    credito = _credito().set_index(["ano", "chave"])
    assert (
        credito.loc[(2025, C_ITAU), "valor"] == 22.0
    )  # dezembro, não a soma dos trimestres
    assert credito.loc[(2025, C_ITAU), "meses"] == 12
    assert (
        credito.loc[(2026, C_ITAU), "meses"] == 3
    )  # só março: o ano corrente não compara


def test_setores_do_lancamento_tem_os_bancos() -> None:
    assert BANCOS.series == (
        "bcb_ativo_total",
        "bcb_carteira_de_credito",
        "bcb_captacoes",
    )
    assert BANCOS.lado_a_lado == (
        "bcb_indice_de_basileia",
        "bcb_carteira_pf_por_modalidade",
        "bcb_carteira_pj_por_modalidade",
    )
    assert BANCOS.fontes_b13 == ("bcb-ifdata",)


# --- a concentração ---------------------------------------------------------------------------------


def test_bancos_concentracao_de_credito() -> None:
    linhas = {
        r["ano"]: r for r in _secao()["tabelas"]["concentracao_bcb_carteira_de_credito"]
    }
    # dezembro de 2025: Caixa 28, BB 26, Itaú 22, o fechado 14, os pequenos 6 e 4 (de 100)
    assert linhas[2025]["cr4"] == pytest.approx(0.90)
    assert linhas[2025]["hhi"] == pytest.approx(
        28**2 + 26**2 + 22**2 + 14**2 + 6**2 + 4**2
    )
    assert linhas[2025]["delta_hhi"] == pytest.approx(
        linhas[2025]["hhi"] - (30**2 + 25**2 + 20**2 + 15**2 + 5**2 + 5**2)
    )
    assert linhas[2026]["meses"] == 3 and linhas[2026]["delta_hhi"] is None
    # março de 2026 é só 1 das 4 datas-base do ano: o topo fica com dezembro de 2025, o ano completo
    itens = {item["chave"]: item for item in _secao()["itens"]}
    assert itens["cr4_bcb_carteira_de_credito"]["base"] == "2025-12"
    assert itens["cr4_bcb_carteira_de_credito"]["valor"] == pytest.approx(0.90)


def test_bancos_conglomerado_e_um_participante() -> None:
    participantes = dossie.participantes(
        _serie("bcb_carteira_de_credito"), _credito(), _ligacoes(), None
    )
    de_2025 = participantes[participantes["ano"] == 2025].set_index("participante")
    # cada conglomerado é um participante, ligado ou não a uma companhia aberta
    assert de_2025["valor"].to_dict() == {
        f"grupo:{chave}": float(valor) for chave, valor in DEZEMBRO[2025].items()
    }
    assert set(de_2025["por"]) == {"grupo"}
    secao = _secao()
    assert "parecem menores" not in " ".join(secao["paragrafos"])
    itau = [
        r
        for r in secao["tabelas"]["participacao_dos_membros"]
        if r["cnpj"] == ITAU and r["ano"] == 2025
    ]
    assert [r["participacao"] for r in itau] == [pytest.approx(0.22)]


def test_bancos_membros_pela_ligacao_dos_bancos() -> None:
    assert _membros().to_dict("records") == [
        {"cnpj": BB, "empresa": "BCO BRASIL S.A.", "motivo": "ligada ao Banco Central por 1 entidade"},
        # o código do tipo 2 (C0010069) é o mesmo Itaú: não conta
        {"cnpj": ITAU, "empresa": "ITAU UNIBANCO HOLDING S.A.", "motivo": "ligada ao Banco Central por 1 entidade"},
    ]  # fmt: skip


def test_ligacao_dos_bancos_so_a_ja_publica() -> None:
    ligacoes = _ligacoes()
    assert set(ligacoes["chave"]) == {C_ITAU, C_BB}  # a do fechado é de junho de 2026
    bb = ligacoes.set_index("chave").loc[C_BB]
    assert bb["cnpj_companhia"] == BB and bb["principal"]
    assert bb["desde"] == D("2024-12-31")
    assert set(ligacoes["fonte"]) == {"bcb-ifdata"}


# --- o lado a lado ---------------------------------------------------------------------------------


def test_bancos_lado_a_lado_traz_basileia_e_carteira_por_modalidade() -> None:
    tabelas = _secao()["tabelas"]
    basileia = {
        (r["cnpj"], r["ano"]): r["valor"]
        for r in tabelas["lado_a_lado_bcb_indice_de_basileia"]
    }
    assert basileia == {(ITAU, 2025): 0.152, (ITAU, 2024): 0.16, (BB, 2025): 0.14}
    modalidades = tabelas["lado_a_lado_bcb_carteira_pf_por_modalidade"]
    # só os membros: a Caixa não tem ticker
    assert [(r["cnpj"], r["abertura"], r["valor"]) for r in modalidades] == [
        (ITAU, "Cartão de Crédito", 154.0),
        (ITAU, "Habitação", 141.0),
    ]
    assert modalidades[0]["chave"] == C_ITAU
    assert modalidades[0]["entidade"] == "ITAU - PRUDENCIAL"
    assert "lado_a_lado_bcb_carteira_pj_por_modalidade" not in tabelas  # sem dado


def test_bancos_fontes_e_registro_da_secao() -> None:
    assert _secao()["fontes"] == dossie.fontes_do_setor(
        [*BANCOS.series[1:2], *BANCOS.lado_a_lado[:2]]
    )
    registro = next(s for s in dossie.SECOES if s.chave == "setor")
    assert {"ifdata_valores", "ligacao_dos_bancos"} <= set(registro.tabelas)
    assert all(dossie.pode_mostrar(t) for t in registro.tabelas)


def test_bancos_limites_explicam_a_base_e_a_conferencia() -> None:
    texto = dossie.LIMITES["setor"]
    for trecho in ("conglomerado prudencial", "REB", "carteira classificada", "revis"):
        assert trecho in texto, trecho


def test_bancos_cortar_o_futuro_nao_muda_o_passado() -> None:
    """O corte na seção (a noite corta pela data de publicação: `test_gerar_dossies_bancos`)."""
    cortada = _secao(_credito().query("ano <= 2025"))
    inteira = _secao()
    for tabela in ("concentracao_bcb_carteira_de_credito", "participacao_dos_membros"):
        ate_2025 = [r for r in inteira["tabelas"][tabela] if r["ano"] <= 2025]
        assert ate_2025 == cortada["tabelas"][tabela]
