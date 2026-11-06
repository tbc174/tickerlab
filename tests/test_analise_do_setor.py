"""A análise do setor pelo modelo (molde D, PR 6): a entrada, as portas, o molde e o pedido.

O que importa: o ano que a base ainda não fechou vira lacuna obrigatória e nunca passa por fato do
setor (linha 167 da fila); o gabarito do setor elétrico passa na porta 1 inteira; o molde do setor
é a reserva e não cita o ano parcial; o pedido leva o guia e o esquema do setor sem ensinar o
gabarito; a avaliação e a porta 2 servem aos dois roteiros. Nada vai para a rede.
"""

import copy
import dataclasses
import re
from collections.abc import Callable
from typing import Any

from src.analise_escrita import (
    avaliacao,
    molde,
    montagem,
    pedido,
    porta1,
    porta2,
    saida,
    setor,
)
from src.analise_escrita import entrada as en
from tests.ajudantes_da_analise_do_setor import (
    CORTE,
    PARTES_DO_SETOR,
    gabarito,
    ler_do_par,
)

ENTRADA = ler_do_par("entrada.json")
LACUNA = "lacuna.ano_parcial.2026"
MARCADAS = {
    "tamanho.mercado_aneel_consumidores",
    "tamanho.tamanho_aneel_consumidores.0",
    "concentracao.hhi_aneel_consumidores",
    "concentracao.cr4_aneel_consumidores",
    "concentracao.concentracao_aneel_consumidores.0",
    "o_que_os_dados_mostram.paragrafos.1",
    "o_que_os_dados_mostram.paragrafos.2",
}
# Os nomes que o gabarito usa e que o guia não pode ensinar (a prova é às cegas).
NOMES_DO_GABARITO = (
    "Neoenergia",
    "Equatorial",
    "ELPA",
    "CPFL",
    "Cemig",
    "Copel",
    "Energisa",
    "Light",
    "AXIA",
    "CEB",
    "Rede Energia",
    "Santa Catarina",
    "Afluente",
    "Alupar",
    "Engie",
)
NUMEROS_DO_GUIA = {str(n) for n in range(1, len(PARTES_DO_SETOR) + 1)} | {"100"}


def _frases(analise: saida.Analise) -> list[saida.Frase]:
    return [f for p in analise.partes for g in p.paragrafos for f in g.frases]


def _trocar_frases(
    analise: saida.Analise, trocar: Callable[[saida.Frase], saida.Frase]
) -> saida.Analise:
    return saida.Analise(
        tuple(
            dataclasses.replace(
                parte,
                paragrafos=tuple(
                    dataclasses.replace(g, frases=tuple(trocar(f) for f in g.frases))
                    for g in parte.paragrafos
                ),
            )
            for parte in analise.partes
        )
    )


def _sem_a_lacuna(frase: saida.Frase) -> saida.Frase:
    return dataclasses.replace(
        frase, notas=tuple(n for n in frase.notas if n != LACUNA)
    )


def _anos_inteiros(dado: Any) -> Any:
    """O relatório com todo ano fechado (12 meses), como se a base já tivesse o ano todo."""
    if isinstance(dado, dict):
        if setor.COLUNA_DOS_MESES in dado:
            dado[setor.COLUNA_DOS_MESES] = str(setor.MESES_DO_ANO)
        for valor in dado.values():
            _anos_inteiros(valor)
    elif isinstance(dado, list):
        for valor in dado:
            _anos_inteiros(valor)
    return dado


# --- a entrada --------------------------------------------------------------------------------------
def test_ano_parcial_vira_lacuna_obrigatoria():
    assert ENTRADA["tipo"] == saida.TIPO_SETOR
    assert ENTRADA["obrigatorias"] == [LACUNA]
    (lacuna,) = [linha for linha in ENTRADA["linhas"] if linha["id"] == LACUNA]
    assert lacuna["tipo"] == "lacuna"
    assert "8 meses" in lacuna["texto"] and "ago/2026" in lacuna["texto"]


def test_linhas_do_ano_parcial_levam_a_lacuna():
    """A linha da tabela, o número do topo que saiu dela e a frase por regra que cita o ano."""
    marcadas = {
        linha["id"]: linha[porta1.ANO_PARCIAL]
        for linha in ENTRADA["linhas"]
        if linha.get(porta1.ANO_PARCIAL)
    }
    assert marcadas == dict.fromkeys(MARCADAS, LACUNA)


def test_ano_dentro_de_uma_data_nao_e_o_ano_parcial():
    assert setor._menciona_o_ano("Em 2026, o HHI ficou em 689 pontos.", "2026")
    assert not setor._menciona_o_ano(
        "Dados da base do TickerLab de 21/10/2026.", "2026"
    )


def test_relatorio_com_os_anos_inteiros_nao_tem_lacuna():
    relatorio = _anos_inteiros(copy.deepcopy(ler_do_par("relatorio.json")))
    entrada = setor.entrada_do_setor(relatorio, CORTE)
    assert entrada["obrigatorias"] == []
    assert not any(linha.get(porta1.ANO_PARCIAL) for linha in entrada["linhas"])


# --- a porta 1 --------------------------------------------------------------------------------------
def test_gabarito_do_setor_passa_na_porta1_inteira():
    """Estrutura do roteiro do setor, lacuna obrigatória, ano parcial e cada parte."""
    assert porta1.conferir(gabarito(), ENTRADA).reprovacoes == ()


def test_frase_que_cita_o_ano_parcial_sem_a_lacuna_reprova():
    certo = gabarito()
    alvo = next(
        f for f in _frases(certo) if LACUNA in f.notas and MARCADAS & set(f.notas)
    )
    analise = _trocar_frases(certo, lambda f: _sem_a_lacuna(f) if f is alvo else f)
    regras = [r.regra for r in porta1.conferir(analise, ENTRADA).reprovacoes]
    assert regras == [porta1.ANO_PARCIAL]


def test_analise_que_cala_o_ano_parcial_reprova():
    analise = _trocar_frases(gabarito(), _sem_a_lacuna)
    regras = {r.regra for r in porta1.conferir(analise, ENTRADA).reprovacoes}
    assert {porta1.LACUNA, porta1.ANO_PARCIAL} <= regras


def test_analise_do_setor_com_o_roteiro_da_empresa_reprova_na_estrutura():
    partes = gabarito().partes[:-1]
    regras = [
        r.regra for r in porta1.conferir(saida.Analise(partes), ENTRADA).reprovacoes
    ]
    assert porta1.ESTRUTURA in regras


# --- o molde (a reserva) ----------------------------------------------------------------------------
def test_molde_do_setor_tem_o_roteiro_do_setor_e_passa_na_porta1():
    reserva = molde.molde(ENTRADA)
    assert tuple(p.chave for p in reserva.partes) == PARTES_DO_SETOR
    assert {p.origem for p in reserva.partes} == {saida.ORIGEM_MOLDE}
    assert porta1.conferir(reserva, ENTRADA).reprovacoes == ()


def test_molde_do_setor_nao_cita_o_ano_parcial_e_diz_a_lacuna():
    reserva = molde.molde(ENTRADA)
    citadas = {nota for f in _frases(reserva) for nota in f.notas}
    assert citadas & MARCADAS == set()
    limites = reserva.parte("limites")
    assert any(LACUNA in f.notas for g in limites.paragrafos for f in g.frases)


def test_parte_do_setor_sem_linha_no_roteiro_diz_que_nao_tem_dado():
    """Participação e lado a lado ficam nas tabelas da tela: o molde não as repete em frase."""
    (frase,) = _frases(saida.Analise((molde.molde(ENTRADA).parte("participacao"),)))
    assert frase.texto == molde.SEM_DADOS_DO_SETOR


# --- a montagem -------------------------------------------------------------------------------------
def _resposta() -> dict[str, Any]:
    return ler_do_par("gabarito.json")["analise"]


def test_montagem_do_setor_com_resposta_boa_e_toda_do_modelo():
    m = montagem.analise_final(_resposta(), ENTRADA, en.hash_da_entrada(ENTRADA))
    assert m.motivo is None
    assert tuple(p.chave for p in m.analise.partes) == PARTES_DO_SETOR
    assert {p.origem for p in m.analise.partes} == {saida.ORIGEM_MODELO}


def test_parte_do_setor_reprovada_volta_ao_molde():
    m = montagem.analise_final(
        _resposta(), ENTRADA, en.hash_da_entrada(ENTRADA), reprovadas={"participacao"}
    )
    origens = {p.chave: p.origem for p in m.analise.partes}
    assert origens.pop("participacao") == saida.ORIGEM_MOLDE
    assert set(origens.values()) == {saida.ORIGEM_MODELO}


def test_resposta_com_parte_da_empresa_vira_molde_do_setor():
    resposta = _resposta()
    resposta["partes"][1]["chave"] = "quem_manda"
    m = montagem.analise_final(resposta, ENTRADA, en.hash_da_entrada(ENTRADA))
    assert m.motivo is not None and m.motivo.startswith(montagem.FORA_DO_FORMATO)
    assert tuple(p.chave for p in m.analise.partes) == PARTES_DO_SETOR


# --- o pedido ---------------------------------------------------------------------------------------
def test_pedido_do_setor_leva_o_guia_o_esquema_e_a_instrucao_do_setor():
    parametros = pedido.pedido(ENTRADA, pedido.OPUS)
    (sistema,) = parametros["system"]
    assert sistema["text"] == pedido.GUIA_DO_SETOR
    assert sistema["cache_control"] == {"type": "ephemeral"}
    esquema = parametros["output_config"]["format"]["schema"]
    chave = esquema["properties"]["partes"]["items"]["properties"]["chave"]
    assert chave["enum"] == list(PARTES_DO_SETOR)
    assert parametros["messages"][0]["content"].startswith(pedido.INSTRUCAO_DO_SETOR)
    assert pedido.guia_de(ENTRADA).versao == pedido.VERSAO_DO_GUIA_DO_SETOR


def test_guia_do_setor_nao_ensina_o_gabarito():
    """O gabarito do setor é a prova às cegas: nenhum número nem nome dele no guia."""
    guia = pedido.GUIA_DO_SETOR
    assert set(re.findall(r"\d+(?:[.,]\d+)*", guia)) <= NUMEROS_DO_GUIA
    assert [nome for nome in NOMES_DO_GABARITO if nome in guia] == []


def test_guia_do_setor_cita_partes_ano_parcial_contas_e_proibicoes():
    guia = pedido.GUIA_DO_SETOR
    assert all(f"`{chave}`" in guia for chave in PARTES_DO_SETOR)
    assert all(f"`{operacao}`" in guia for operacao in saida.OPERACOES)
    for trecho in (
        "**fato**",
        "**leitura**",
        "`obrigatorias`",
        "`ano_parcial`",
        "conta nossa",
        "`corte`",
        "ranking",
    ):
        assert trecho in guia
    for proibida in ("preço-alvo", "vai", "forte", "fraude", "Nome de pessoa", "nota"):
        assert proibida in guia


# --- a porta 2 e a avaliação ------------------------------------------------------------------------
def test_porta2_do_setor_confere_com_os_cuidados_do_setor():
    parametros = porta2.pedido(gabarito(), ENTRADA, pedido.SONNET)
    assert parametros["system"][0]["text"] == porta2.SISTEMA_DO_SETOR
    assert "ano_parcial" in porta2.SISTEMA_DO_SETOR
    assert "ano_parcial" not in porta2.SISTEMA


def test_gabarito_do_setor_contra_ele_mesmo_passa_nos_5_criterios():
    criterios = avaliacao.avaliar(gabarito(), ENTRADA, gabarito())
    assert [c.falhas for c in criterios] == [()] * len(avaliacao.NOMES)


def test_ano_parcial_sem_a_lacuna_conta_no_criterio_dos_buracos():
    analise = _trocar_frases(gabarito(), _sem_a_lacuna)
    criterios = {c.numero: c for c in avaliacao.avaliar(analise, ENTRADA, gabarito())}
    assert not criterios[2].passou
    assert all(criterios[n].passou for n in (1, 3, 4))


def test_relatorio_da_avaliacao_mostra_as_partes_do_setor():
    texto = avaliacao.relatorio({"Gabarito": gabarito()}, {})
    titulos = re.findall(r"^## (.+)$", texto, re.MULTILINE)
    assert titulos == [saida.TITULOS[chave] for chave in PARTES_DO_SETOR]
