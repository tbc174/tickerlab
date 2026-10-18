"""O molde: o texto de reserva por regras, montado das linhas da entrada, que sempre passa na porta 1."""

import copy
import json

from src.analise_escrita import molde, porta1, saida
from tests.ajudantes_da_analise import PAR_DA_CPFL

ENTRADA_CPFL = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))
PEQUENA = {
    "corte": "2026-10-17",
    "linhas": [
        {
            "secao": "retorno",
            "id": "retorno.roe",
            "tipo": "numero",
            "nome": "ROE",
            "texto": "26,4%",
            "valor": 0.26433,
            "medido_em": "12 meses até 30/06/2026",
            "comparacao": {"contra": "setor", "texto": "mediana 11,8%", "valor": None},
            "so_pro": False,
        },
        {
            "secao": "limites",
            "id": "limites.paragrafos.0",
            "tipo": "paragrafo",
            "texto": "A margem é forte. A base é de 17/10/2026.",
            "so_pro": False,
        },
        {
            "secao": "negocios",
            "id": "negocios.negocios",
            "tipo": "numero",
            "nome": "Documentos de negócios",
            "texto": "89",
            "valor": 89.0,
            "medido_em": "02/02/2026",
            "so_pro": True,
        },
        {
            "secao": "lacuna",
            "id": "lacuna.segmentos",
            "tipo": "lacuna",
            "texto": "A base não separa a receita por segmento.",
            "so_pro": False,
        },
    ],
    "obrigatorias": ["lacuna.segmentos"],
}


def _frases(analise: saida.Analise, chave: str | None = None) -> list[saida.Frase]:
    return [
        frase
        for parte in analise.partes
        if chave is None or parte.chave == chave
        for paragrafo in parte.paragrafos
        for frase in paragrafo.frases
    ]


def _so_pro(entrada: dict) -> set[str]:
    return {linha["id"] for linha in entrada["linhas"] if linha.get("so_pro")}


def test_molde_da_cpfl_passa_na_porta1():
    analise = molde.molde(ENTRADA_CPFL)
    assert porta1.conferir(analise, ENTRADA_CPFL).reprovacoes == ()
    assert tuple(p.chave for p in analise.partes) == saida.PARTES
    assert {p.origem for p in analise.partes} == {saida.ORIGEM_MOLDE}


def test_molde_sem_o_dossie_nao_cita_linha_so_pro_e_passa():
    analise = molde.molde(ENTRADA_CPFL, incluir_so_pro=False)
    citadas = {nota for frase in _frases(analise) for nota in frase.notas}
    assert citadas & _so_pro(ENTRADA_CPFL) <= set(ENTRADA_CPFL["obrigatorias"])
    assert porta1.conferir(analise, ENTRADA_CPFL).reprovacoes == ()


def test_numero_vira_frase_com_medido_em_e_comparacao():
    (frase,) = _frases(molde.molde(PEQUENA), "o_que_os_numeros_mostram")
    assert frase.texto == "ROE: 26,4% (12 meses até 30/06/2026); setor: mediana 11,8%."
    assert frase.notas == ("retorno.roe",)


def test_frase_da_ficha_que_a_porta_reprovaria_fica_de_fora():
    textos = [f.texto for f in _frases(molde.molde(PEQUENA), "limites")]
    assert "A base é de 17/10/2026." in textos
    assert not any("forte" in texto for texto in textos)


def test_lacuna_obrigatoria_entra_nos_limites():
    notas = [n for f in _frases(molde.molde(PEQUENA), "limites") for n in f.notas]
    assert "lacuna.segmentos" in notas


def test_parte_sem_dados_ganha_o_aviso_e_o_molde_passa():
    analise = molde.molde(PEQUENA, incluir_so_pro=False)
    (frase,) = _frases(analise, "quem_manda")
    assert frase.texto == molde.SEM_DADOS
    assert porta1.conferir(analise, PEQUENA).reprovacoes == ()


def test_obrigatoria_so_pro_entra_mesmo_sem_o_dossie():
    entrada = copy.deepcopy(PEQUENA)
    entrada["linhas"][3]["so_pro"] = True
    notas = [
        n for f in _frases(molde.molde(entrada, incluir_so_pro=False)) for n in f.notas
    ]
    assert "lacuna.segmentos" in notas
    assert "negocios.negocios" not in notas


def test_nota_de_metodo_da_secao_fica_de_fora():
    entrada = copy.deepcopy(PEQUENA)
    entrada["linhas"].append(
        {
            "secao": "setor_regulado",
            "id": "setor_regulado.paragrafos.0",
            "tipo": "paragrafo",
            "texto": "Fonte: ODbL (dados abertos da ANEEL; citar).",
            "so_pro": False,
        }
    )
    textos = [f.texto for f in _frases(molde.molde(entrada))]
    assert not any(texto.startswith("Fonte") for texto in textos)
