"""Conferência cruzada das fontes do modelo 8 (ADR 0027, exigência 6; critério de pronto, PR C).

As tolerâncias foram escritas e publicadas antes de olhar (`docs/conferencia-cruzada-modelo-8.md`,
16/10/2026). Cada conferência é uma tabela em `base/conferidas/modelo_8/`, com a explicação de cada
divergência; estes testes guardam o resultado: se alguém mudar uma linha, ou tirar uma explicação,
eles falham. Nenhuma conferência cruza dado com o alvo (ADR 0027, item 2): cada uma compara a
mesma informação em duas fontes; o rótulo só é conferido contra o ENET.
"""

from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent / "base" / "conferidas" / "modelo_8"
UMA_UNIDADE_DA_ESCALA = 1  # tolerância 1: até R$ 1 mil num documento em milhares
LIMITE_DAS_PRORROGACOES = (
    3  # tolerância 5: 3 vezes a mediana das data-bases do documento
)
CONCORDANCIA_MINIMA = 0.9  # tolerância 3


def _ler(nome: str) -> pd.DataFrame:
    tabela = pd.read_csv(
        PASTA / f"{nome}.csv", sep=";", dtype=str, keep_default_na=False
    )
    assert (tabela["conferido_em"] != "").all()
    return tabela


def _sim(coluna: pd.Series) -> pd.Series:
    return coluna.str.lower() == "true"


def _divergencias_explicadas(tabela: pd.DataFrame) -> None:
    divergentes = tabela[~_sim(tabela["confere"])]
    assert (divergentes["explicacao"].str.len() > 20).all(), divergentes


def test_contas_da_base_como_era_conferem_com_o_documento_no_enet():
    """Tolerância 1: 10 empresas × 3 documentos, uma reapresentação (antes e depois) e uma cancelada."""
    contas = _ler("contas_enet")
    _divergencias_explicadas(contas)
    conferem = contas[_sim(contas["confere"]) & (contas["diferenca"] != "")]
    assert (conferem["diferenca"].astype(float) <= UMA_UNIDADE_DA_ESCALA).all()
    assert {"reapresentacao", "cancelada"} <= set(contas["tipo"])
    assert contas["cnpj"].nunique() == 10
    assert (len(contas), int(_sim(contas["confere"]).sum())) == (146, 142)
    # as 3 contas que não conferem: linha em branco no documento, 0 nos dados abertos
    branco = contas[~_sim(contas["confere"]) & (contas["conta"] == "2.01.04")]
    assert len(branco) == 3 and (branco["base_na_escala"].astype(float) == 0).all()


def test_auditor_da_tabela_e_quem_assina_o_relatorio_da_dfp():
    """Tolerância 2: 20 DFPs sorteadas; a firma do relatório do auditor no ENET é a vigente na tabela."""
    auditores = _ler("auditor_relatorio_enet")
    _divergencias_explicadas(auditores)
    assert len(auditores) == 20 and int(_sim(auditores["confere"]).sum()) == 19
    # a divergência é falta de informação, não outro auditor
    divergente = auditores[~_sim(auditores["confere"])].iloc[0]
    assert divergente["auditor_na_tabela"] == ""


def test_registro_e_cancelamento_conferem_com_a_consulta_da_cvm():
    """Tolerância 4: 0 dia, 20 companhias (10 ativas, 10 canceladas)."""
    cadastro = _ler("cadastro_cvmweb")
    assert len(cadastro) == 20 and _sim(cadastro["confere"]).all()
    assert (cadastro["cancelamento"] != "").sum() == 10


def test_insolvencia_do_ipe_x_receita_tem_cada_divergencia_explicada():
    """Tolerância 3: ≥ 90% em cada sentido. **Não passou** (76% e 55%): a recuperação judicial bate
    25 de 25 da Receita para o IPE, mas o rótulo do IPE marca eventos de outras empresas do grupo e a
    recuperação extrajudicial, e a Receita não marca casos conhecidos. A fonte fica pendente."""
    insolvencia = _ler("insolvencia_receita")
    _divergencias_explicadas(insolvencia)
    concordancia = insolvencia.groupby("direcao")["confere"].apply(
        lambda c: _sim(c).mean()
    )
    assert concordancia["receita_para_ipe"] < CONCORDANCIA_MINIMA
    assert concordancia["ipe_para_receita"] < CONCORDANCIA_MINIMA
    rj = insolvencia[
        (insolvencia["direcao"] == "receita_para_ipe")
        & (insolvencia["tipo_na_receita"] == "recuperacao_judicial")
    ]
    assert len(rj) == 25 and _sim(rj["confere"]).all()


def test_recuperacao_judicial_propria_pela_raiz_x_receita_tem_cada_falta_explicada():
    """Remedida de 17/10 com a regra do PR 3 (só a recuperação judicial da própria companhia, pela
    raiz do CNPJ): 25 de 25 da Receita para o IPE, 22 de 32 do IPE para a Receita. **Decisão do
    Tiago (17/10):** a tolerância continua em 90% e a exigência 6 do IPE passa porque cada uma das
    10 faltas tem causa conhecida do lado da Receita, nenhuma é erro do IPE. Se aparecer uma falta
    de outro tipo, este teste falha e a fonte volta a ser pendência."""
    rj = _ler("insolvencia_receita_rj_propria")
    _divergencias_explicadas(rj)
    # Receita → IPE confere quando o IPE marca a raiz; IPE → Receita, quando a Receita marca
    lado = rj["rj_propria_no_ipe"].where(
        rj["direcao"] == "receita_para_ipe", rj["receita_marca_a_raiz"]
    )
    assert (rj["confere"] == lado).all()
    confere = _sim(rj["confere"])
    receita = rj["direcao"] == "receita_para_ipe"
    assert (confere[receita].sum(), receita.sum()) == (25, 25)
    assert (confere[~receita].sum(), (~receita).sum()) == (22, 32)
    assert confere[~receita].mean() < CONCORDANCIA_MINIMA
    # as 10 faltas do IPE para a Receita: só as três causas conhecidas
    faltas = rj.loc[~receita & ~confere, "explicacao"]
    causas = {
        "a Receita não tem a marca": 7,  # registro na Junta incompleto (como o da Americanas)
        "a Receita já tirou a marca": 2,  # recuperação já encerrada
        "CNPJ de uma filial": 1,
    }
    for causa, quantas in causas.items():
        assert faltas.str.contains(causa, regex=False).sum() == quantas, causa
    assert len(faltas) == sum(causas.values())


def test_prorrogacoes_de_2022_a_2026_estao_no_codigo_e_nas_entregas():
    """Tolerância 5: nenhuma norma de prorrogação fora de `src/prazos.py` (buscas de 16/10: só a
    Resolução CVM 202/2024) e nenhuma data-base acima do limite sem explicação."""
    prazos = (Path(__file__).resolve().parent.parent / "src" / "prazos.py").read_text(
        encoding="utf-8"
    )
    assert "Resolução 202" in prazos
    datas = _ler("prorrogacoes_por_data_base")
    acima = datas[_sim(datas["acima_do_limite"])]
    assert (acima["explicacao"].str.len() > 20).all(), acima
    assert (
        datas["razao"].replace("", "0").astype(float) > LIMITE_DAS_PRORROGACOES
    ).sum() == len(acima)


def test_rotulo_confere_com_o_envio_no_enet():
    """Tolerância 6: 0 dia e 0 rótulo diferente fora do grupo do pedido de registro."""
    rotulo = _ler("rotulo_enet")
    enviado = pd.to_datetime(rotulo["enviado_no_enet"].replace("", None)).dt.normalize()
    recebido = pd.to_datetime(rotulo["recebido_em"])
    fora_do_grupo = ~_sim(rotulo["entregue_antes_do_registro"]) & enviado.notna()
    assert (enviado[fora_do_grupo] == recebido[fora_do_grupo]).all()
    assert (rotulo.loc[~fora_do_grupo & enviado.notna(), "explicacao"] != "").all()
    casos = rotulo[rotulo["amostra"] == "30_casos_rotulo"]
    atrasou = pd.to_datetime(casos["enviado_no_enet"]).dt.normalize() > pd.to_datetime(
        casos["prazo"]
    )
    assert len(casos) == 30 and (atrasou == _sim(casos["atrasou"])).all()
    assert int(fora_do_grupo.sum()) == 30 + 298
