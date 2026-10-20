"""As seções do PR 3 dos relatórios v2 no dossiê: governança e crédito.

Tabelas de mentira, pequenas, já só com a empresa da ficha (o script separa por CNPJ antes). Só contagens e
somas: nenhum nome de pessoa (ADRs 0018 e 0075); cada número com a data e sem olhar o futuro.
"""

import pandas as pd

from base import dossie

D = pd.Timestamp
HOJE = D("2026-10-17")
CNPJ = "02429144000193"
MILHAO = 1_000_000.0
SO_CONSELHO = "Pertence apenas ao Conselho de Administração"
OS_DOIS = "Pertence à Diretoria e ao Conselho de Administração"
SO_DIRETORIA = "Pertence apenas à Diretoria"
FISCAL = "Conselho Fiscal"
# (referência, versão, entregue em) de cada FRE; o de 2027 só é entregue depois de hoje
FRE_2025 = ("2025-01-01", 1, "2025-05-31")
FRE_2026_V1 = ("2026-01-01", 1, "2026-05-29")
FRE_2026_V2 = ("2026-01-01", 2, "2026-07-10")
FRE_2027 = ("2027-01-01", 1, "2026-11-30")


def _itens(secao: dict) -> dict[str, dict]:
    return {item["chave"]: item for item in secao["itens"]}


def _do_fre(fre: tuple[str, int, str], **colunas: object) -> dict[str, object]:
    referencia, versao, entregue_em = fre
    return {
        "cnpj": "02.429.144/0001-93",
        "referencia": D(referencia),
        "versao": versao,
        "conhecido_em": D(entregue_em),
        **colunas,
    }


# --- governança ----------------------------------------------------------------------------------


def _conselho() -> pd.DataFrame:
    linhas = [
        (FRE_2025, SO_CONSELHO, 7, 2, 1),
        (FRE_2025, OS_DOIS, 1, 0, 0),
        (FRE_2025, SO_DIRETORIA, 6, 0, 0),
        (FRE_2025, FISCAL, 3, 0, 1),
        (FRE_2026_V1, SO_CONSELHO, 8, 3, 1),
        (FRE_2026_V1, OS_DOIS, 1, 0, 0),
        (FRE_2026_V2, SO_CONSELHO, 9, 4, 2),
        (FRE_2026_V2, OS_DOIS, 1, 0, 0),
        (FRE_2026_V2, SO_DIRETORIA, 6, 0, 0),
        (FRE_2026_V2, FISCAL, 3, 0, 1),
        (FRE_2027, SO_CONSELHO, 11, 5, 2),
    ]
    return pd.DataFrame(
        [
            _do_fre(
                fre,
                orgao=orgao,
                membros=membros,
                independentes=independentes,
                eleitos_por_minoritarios=minoritarios,
            )
            for fre, orgao, membros, independentes, minoritarios in linhas
        ]
    )


def _comites() -> pd.DataFrame:
    linhas = [
        (FRE_2025, "Comitê de Auditoria", 3),
        (FRE_2026_V1, "Comitê de Auditoria", 3),
        (FRE_2026_V2, "Comitê de Auditoria", 3),
        (FRE_2026_V2, "Comitê de Pessoas", 3),
        (FRE_2026_V2, "Comitê de Riscos", 4),
    ]
    return pd.DataFrame(
        [
            _do_fre(fre, tipo_de_comite=tipo, membros=membros)
            for fre, tipo, membros in linhas
        ]
    )


def _diversidade() -> pd.DataFrame:
    linhas = [
        (FRE_2025, "Conselho de Administração", 2, 6),
        (FRE_2026_V2, "Conselho de Administração", 3, 7),
        (FRE_2026_V2, "Diretoria", 1, 5),
    ]
    return pd.DataFrame(
        [
            _do_fre(fre, orgao=orgao, genero_feminino=mulheres, genero_masculino=homens)
            for fre, orgao, mulheres, homens in linhas
        ]
    )


def _remuneracao() -> pd.DataFrame:
    # o FRE de 2026 refaz 2024 (45 mi contra 44 mi) e traz a prevista de 2026, ainda não encerrada
    linhas = [
        (FRE_2025, "2023-12-31", "Diretoria Estatutária", 40),
        (FRE_2025, "2024-12-31", "Diretoria Estatutária", 44),
        (FRE_2026_V2, "2024-12-31", "Diretoria Estatutária", 45),
        (FRE_2026_V2, "2025-12-31", "Conselho de Administração", 10),
        (FRE_2026_V2, "2025-12-31", "Diretoria Estatutária", 40),
        (FRE_2026_V2, "2025-12-31", "Conselho Fiscal", 1),
        (FRE_2026_V2, "2026-12-31", "Diretoria Estatutária", 60),
    ]
    return pd.DataFrame(
        [
            _do_fre(
                fre,
                fim_do_exercicio=D(fim),
                orgao=orgao,
                membros_remunerados=6.0,
                total_remuneracao=milhoes * MILHAO,
            )
            for fre, fim, orgao, milhoes in linhas
        ]
    )


def _extremos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _do_fre(
                FRE_2026_V2,
                fim_do_exercicio=D("2025-12-31"),
                orgao="Diretoria Estatutária",
                maior=12 * MILHAO,
                media=6.5 * MILHAO,
                menor=4 * MILHAO,
            )
        ]
    )


def _governanca(hoje: pd.Timestamp = HOJE, **tabelas: pd.DataFrame) -> dict | None:
    vazia = pd.DataFrame()
    return dossie.secao_governanca(
        tabelas.get("conselho", vazia),
        tabelas.get("comites", vazia),
        tabelas.get("remuneracao", vazia),
        tabelas.get("extremos", vazia),
        tabelas.get("diversidade", vazia),
        hoje,
    )


def _governanca_completa(hoje: pd.Timestamp = HOJE) -> dict | None:
    return _governanca(
        hoje,
        conselho=_conselho(),
        comites=_comites(),
        remuneracao=_remuneracao(),
        extremos=_extremos(),
        diversidade=_diversidade(),
    )


def test_conselho_conta_quem_esta_tambem_na_diretoria_no_fre_mais_novo_ja_entregue() -> (
    None
):
    secao = _governanca_completa()
    assert secao is not None
    itens = _itens(secao)
    # a versão 2 do FRE de 2026 (9 + 1); o de 2027 só é entregue depois de hoje
    assert itens["conselho_membros"]["valor"] == 10
    assert itens["conselho_membros"]["base"] == "2026-07-10"
    assert itens["conselho_independentes"]["valor"] == 4
    assert itens["conselho_eleitos_por_minoritarios"]["valor"] == 2
    assert itens["comites"]["valor"] == 3
    assert itens["mulheres_no_conselho"]["valor"] == 3


def test_governanca_por_ano_traz_o_fre_anterior_para_comparar() -> None:
    secao = _governanca_completa()
    assert secao is not None
    assert secao["tabelas"]["governanca_por_ano"] == [
        {
            "ano": 2026,
            "entregue_em": "2026-07-10",
            "conselho": 10,
            "independentes": 4,
            "eleitos_por_minoritarios": 2,
            "comites": 3,
            "mulheres_no_conselho": 3,
        },
        {
            "ano": 2025,
            "entregue_em": "2025-05-31",
            "conselho": 8,
            "independentes": 2,
            "eleitos_por_minoritarios": 1,
            "comites": 1,
            "mulheres_no_conselho": 2,
        },
    ]


def test_comites_contam_os_tipos_sem_as_pessoas() -> None:
    secao = _governanca_completa()
    assert secao is not None
    assert secao["tabelas"]["comites"] == [
        {"comite": "Comitê de Auditoria", "membros": 3},
        {"comite": "Comitê de Pessoas", "membros": 3},
        {"comite": "Comitê de Riscos", "membros": 4},
    ]


def test_remuneracao_e_a_do_ultimo_exercicio_encerrado_no_fre_mais_novo() -> None:
    secao = _governanca_completa()
    assert secao is not None
    item = _itens(secao)["remuneracao_da_administracao"]
    assert item["valor"] == 51 * MILHAO  # a prevista de 2026 fica de fora
    assert item["base"] == "2025-12-31"
    assert secao["tabelas"]["remuneracao_por_exercicio"] == [
        {"exercicio": 2025, "total": 51 * MILHAO},
        {"exercicio": 2024, "total": 45 * MILHAO},  # o FRE mais novo refez 2024
        {"exercicio": 2023, "total": 40 * MILHAO},
    ]


def test_remuneracao_por_orgao_traz_a_maior_a_media_e_a_menor() -> None:
    secao = _governanca_completa()
    assert secao is not None
    por_orgao = {
        linha["orgao"]: linha for linha in secao["tabelas"]["remuneracao_por_orgao"]
    }
    assert set(por_orgao) == {
        "Conselho de Administração",
        "Diretoria Estatutária",
        "Conselho Fiscal",
    }
    assert por_orgao["Diretoria Estatutária"] == {
        "orgao": "Diretoria Estatutária",
        "membros_remunerados": 6.0,
        "total": 40 * MILHAO,
        "maior": 12 * MILHAO,
        "media": 6.5 * MILHAO,
        "menor": 4 * MILHAO,
    }


def test_governanca_cortar_o_futuro_nao_muda_o_passado() -> None:
    dia = D("2026-06-15")  # a versão 2 do FRE de 2026 ainda não tinha sido entregue

    def ate(tabela: pd.DataFrame) -> pd.DataFrame:
        return tabela[tabela["conhecido_em"] <= dia]

    cortada = _governanca(
        dia,
        conselho=ate(_conselho()),
        comites=ate(_comites()),
        remuneracao=ate(_remuneracao()),
        extremos=ate(_extremos()),
        diversidade=ate(_diversidade()),
    )
    assert cortada == _governanca_completa(dia)
    assert cortada is not None
    assert _itens(cortada)["conselho_membros"]["valor"] == 9


def test_governanca_sem_nenhuma_tabela_nao_tem_secao() -> None:
    assert _governanca() is None


def test_secao_governanca_esta_no_registro_e_pode_mostrar() -> None:
    registro = {secao.chave: secao for secao in dossie.SECOES}
    governanca = registro["governanca"]
    dossie.exigir_que_pode_mostrar(governanca.tabelas)
    assert governanca.chave in dossie.LIMITES


# --- crédito -------------------------------------------------------------------------------------


def _rating(
    agencia: str | None,
    escala: str,
    nota_original: str,
    perspectiva: str,
    acao: str,
    publico_em: str,
    protocolo: str,
    situacao: str = "extraido",
    data_acao: str | None = None,
) -> dict[str, object]:
    return {
        "cnpj": "02.429.144/0001-93",
        "agencia": agencia,
        "escala": escala,
        "nota": nota_original.split("(")[0],
        "nota_original": nota_original,
        "perspectiva": perspectiva,
        "acao": acao,
        "data_acao": D(data_acao)
        if data_acao
        else D(publico_em) - pd.Timedelta(days=1),
        "publico_em": D(publico_em),
        "protocolo": protocolo,
        "link": f"https://cvm/{protocolo}",
        "situacao_extracao": situacao,
    }


def _ratings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _rating("fitch", "nacional", "AA+(bra)", "positiva", "elevacao", "2014-05-02", "p0"),
            _rating("fitch", "nacional", "AA(bra)", "estavel", "afirmacao", "2024-09-11", "p1"),
            _rating("fitch", "nacional", "AA-(bra)", "negativa", "rebaixamento", "2026-03-03", "p2"),
            # o mesmo rebaixamento de novo (mesma data da ação), no fato relevante do dia seguinte
            _rating("fitch", "nacional", "AA-(bra)", "negativa", "rebaixamento", "2026-03-04", "p3",
                    data_acao="2026-03-02"),
            _rating("sp", "nacional", "brAAA", "estavel", "afirmacao", "2025-06-02", "p4"),
            _rating("moodys", "global", "Ba2", "estavel", "retirada", "2026-05-11", "p5"),
            _rating(None, "nacional", "", "", "", "2026-08-01", "p6", "nao_extraido"),
            _rating("sp", "nacional", "brAAA", "positiva", "elevacao", "2026-11-01", "p7"),
        ]
    )  # fmt: skip


def _assembleia(
    documento: str,
    especie: str,
    assunto: str,
    publico_em: str,
    protocolo: str,
    versao: int = 1,
    **temas: bool,
) -> dict[str, object]:
    return {
        "cnpj": "02.429.144/0001-93",
        "documento": documento,
        "especie": especie,
        "assunto": assunto,
        "publico_em": D(publico_em),
        "protocolo": protocolo,
        "versao": versao,
        "link": f"https://cvm/{protocolo}/{versao}",
        **{
            f"tema_{tema}": temas.get(tema, False)
            for tema in (
                "vencimento_antecipado",
                "waiver",
                "covenant",
                "repactuacao",
                "inadimplemento",
            )
        },
    }


def _assembleias() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _assembleia("assembleia", "Edital de Convocação", "AGD 5ª emissão: waiver de covenant",
                        "2026-02-10", "a1", waiver=True, covenant=True),
            _assembleia("assembleia", "Ata", "AGD 5ª emissão: waiver", "2026-03-01", "a2",
                        waiver=True),
            # a mesma ata reentregue: conta uma vez
            _assembleia("assembleia", "Ata", "AGD 5ª emissão: waiver", "2026-03-05", "a2", 2,
                        waiver=True),
            _assembleia("aviso", "", "Pagamento de juros da 5ª emissão", "2026-04-01", "a3"),
            _assembleia("assembleia", "Edital de Convocação",
                        "AGD 4ª emissão: não declarar o vencimento antecipado", "2025-05-05", "a4",
                        vencimento_antecipado=True),
            _assembleia("assembleia", "Edital de Convocação", "AGD 6ª emissão", "2026-11-02", "a5"),
        ]
    )  # fmt: skip


def _credito(hoje: pd.Timestamp = HOJE, **tabelas: pd.DataFrame) -> dict | None:
    vazia = pd.DataFrame()
    return dossie.secao_credito(
        tabelas.get("ratings", vazia), tabelas.get("assembleias", vazia), hoje
    )


def _credito_completo(hoje: pd.Timestamp = HOJE) -> dict | None:
    return _credito(hoje, ratings=_ratings(), assembleias=_assembleias())


def test_ratings_trazem_a_ultima_acao_de_cada_agencia_ja_publica() -> None:
    secao = _credito_completo()
    assert secao is not None
    assert [
        (r["agencia"], r["escala"], r["nota"], r["acao"], r["publico_em"])
        for r in secao["tabelas"]["ratings"]
    ] == [
        ("moodys", "global", "Ba2", "retirada", "2026-05-11"),
        ("fitch", "nacional", "AA-(bra)", "rebaixamento", "2026-03-03"),
        ("sp", "nacional", "brAAA", "afirmacao", "2025-06-02"),
    ]


def test_rebaixamentos_e_elevacoes_em_12_meses_contra_os_12_anteriores() -> None:
    secao = _credito_completo()
    assert secao is not None
    itens = _itens(secao)
    assert (
        itens["ratings_rebaixamentos_12m"]["valor"] == 1
    )  # o fato relevante repetido não conta
    assert (
        itens["ratings_elevacoes_12m"]["valor"] == 0
    )  # a de novembro ainda não é pública
    assert itens["ratings_rebaixamentos_12m"]["base"] == "2026-10-17"
    assert secao["tabelas"]["ratings_janelas"] == [
        {
            "janela": "últimos 12 meses",
            "ate": "2026-10-17",
            "acoes": 2,
            "rebaixamentos": 1,
            "elevacoes": 0,
        },
        {
            "janela": "12 meses anteriores",
            "ate": "2025-10-17",
            "acoes": 1,
            "rebaixamentos": 0,
            "elevacoes": 0,
        },
    ]


def test_assembleias_de_debenturistas_em_12_meses_por_tema() -> None:
    secao = _credito_completo()
    assert secao is not None
    item = _itens(secao)["assembleias_de_debenturistas_12m"]
    assert (
        item["valor"] == 2
    )  # edital e ata, a ata reentregue conta uma vez; o aviso fica fora
    assert secao["tabelas"]["assembleias_janelas"] == [
        {"janela": "últimos 12 meses", "ate": "2026-10-17", "documentos": 2},
        {"janela": "12 meses anteriores", "ate": "2025-10-17", "documentos": 1},
    ]
    assert secao["tabelas"]["assembleias_por_tema"] == [
        {"tema": "Waiver", "ultimos_12_meses": 2, "12_meses_anteriores": 0},
        {"tema": "Covenant", "ultimos_12_meses": 1, "12_meses_anteriores": 0},
        {
            "tema": "Vencimento antecipado",
            "ultimos_12_meses": 0,
            "12_meses_anteriores": 1,
        },
    ]


def test_assembleias_recentes_trazem_o_assunto_e_o_link() -> None:
    secao = _credito_completo()
    assert secao is not None
    recentes = secao["tabelas"]["assembleias_recentes"]
    assert [(a["publico_em"], a["especie"], a["link"]) for a in recentes] == [
        ("2026-03-05", "Ata", "https://cvm/a2/2"),
        ("2026-02-10", "Edital de Convocação", "https://cvm/a1/1"),
        ("2025-05-05", "Edital de Convocação", "https://cvm/a4/1"),
    ]


def test_credito_cortar_o_futuro_nao_muda_o_passado() -> None:
    dia = D("2026-03-03")

    def ate(tabela: pd.DataFrame) -> pd.DataFrame:
        return tabela[tabela["publico_em"] <= dia]

    cortada = _credito(dia, ratings=ate(_ratings()), assembleias=ate(_assembleias()))
    assert cortada == _credito_completo(dia)


def test_credito_sem_nenhuma_tabela_nao_tem_secao() -> None:
    assert _credito() is None


def test_secao_credito_esta_no_registro_e_pode_mostrar() -> None:
    registro = {secao.chave: secao for secao in dossie.SECOES}
    credito = registro["credito"]
    dossie.exigir_que_pode_mostrar(credito.tabelas)
    assert set(credito.tabelas) == {"ratings", "debentures_assembleias"}
    assert credito.chave in dossie.LIMITES


def test_ficha_com_governanca_e_credito_passa_pelo_filtro_de_pessoas() -> None:
    secoes = [_governanca_completa(), _credito_completo()]
    ficha = dossie.montar_ficha(CNPJ, "CPFL Energia", secoes, "2026-10-17")
    dossie.conferir_sem_pessoas(ficha, {"fulano de tal"})
    assert [s["chave"] for s in ficha["secoes"]] == ["governanca", "credito"]
