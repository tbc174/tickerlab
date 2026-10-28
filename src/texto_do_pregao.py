"""O texto do pregão do dia, montado só com as frases do molde aprovado.

O molde (`conteudo/molde_do_pregao.json`) tem as frases com lacunas; aqui só se escolhe a variante
(alta, queda, de lado...) e se preenchem as lacunas com os números do resumo de `src.pregao_do_dia`,
escritos do jeito brasileiro. Nenhuma frase nasce fora do molde, e o texto leva a impressão digital
do molde usado: a página recusa um texto cuja impressão digital não seja a do molde aprovado pelo
Tiago (mudar uma letra do molde é texto público novo, que espera o "pode").
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

CAMINHO_DO_MOLDE = (
    Path(__file__).resolve().parent.parent / "conteudo" / "molde_do_pregao.json"
)

# Abaixo disto, para cima ou para baixo, o Ibovespa "variou pouco" e o dia não ganha a frase da
# história (metade dos pregões desde 2000 variou mais que isso).
VARIACAO_DE_LADO = 0.005
CASAS_DA_VARIACAO = 1
CASAS_DA_TAXA = 2
CASAS_DO_DOLAR = 4
REAIS_POR_MILHAO = 1_000_000
MENOS = "−"  # o sinal de menos tipográfico, como no Raio-X

# O texto descreve o que os preços fizeram: não recomenda, não promete, não explica a causa e não
# fala de política. "Nada aqui é recomendação" passa (o \b não separa "recomenda" de "ção").
_PROIBIDAS = re.compile(
    r"\brecomend(o|a|am|amos|ar|a-se)\b|\bcompr(a|ar|e|em)\b|\bvend(a|er|em)\b|oportunidade|"
    r"barat|\bcar[oa]s?\b|garant|promet|aproveit|lucro certo|sem risco|"
    r"\b(deve|devem|vai|vão|tende a) (subir|cair|continuar|voltar)\b|"
    r"por causa|devido|em razão|reflet|reagi|motivad|"
    r"partido|candidat|governo|president|eleiç|lula|bolsonaro",
    re.IGNORECASE,
)
_SIGLAS_DE_PARTIDO = re.compile(r"\b(PT|PL|PSDB|MDB|PSOL|PSD|PP|PDT|PSB|NOVO)\b")


def ler_molde(caminho: Path | None = None) -> dict[str, Any]:
    """O molde aprovado, como está no arquivo."""
    return json.loads((caminho or CAMINHO_DO_MOLDE).read_text(encoding="utf-8"))


def impressao_digital(molde: dict[str, Any]) -> str:
    """SHA-256 do molde em JSON canônico: muda com qualquer letra, não com a ordem das chaves."""
    canonico = json.dumps(
        molde, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def palavras_proibidas(frase: str) -> list[str]:
    """As palavras da frase que o texto do pregão não pode usar."""
    achadas = [m.group(0) for m in _PROIBIDAS.finditer(frase)]
    return achadas + [m.group(0) for m in _SIGLAS_DE_PARTIDO.finditer(frase)]


# --- números do jeito brasileiro -------------------------------------------------------------------


def _numero(valor: float, casas: int) -> str:
    """12345.6 → "12.345,6"; o menos vira o sinal tipográfico."""
    texto = f"{valor:,.{casas}f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return texto.replace("-", MENOS)


def _com_sinal(valor: float, casas: int) -> str:
    texto = _numero(valor, casas)
    return f"+{texto}" if float(f"{valor:.{casas}f}") > 0 else texto


def _percentual(fracao: float) -> str:
    """0.0921 → "+9,2%"; −0.13879 → "−13,9%"."""
    return f"{_com_sinal(fracao * 100, CASAS_DA_VARIACAO)}%"


def _sem_mudanca_visivel(fracao: float) -> bool:
    """Variação que some na casa mostrada: o texto não diz "subiu 0,0%"."""
    return round(fracao * 100, CASAS_DA_VARIACAO) == 0


def _pontos_base(valor: float) -> str:
    """140.5 → "140,5"; 12.0 → "12" (o DI tem três casas, então meio ponto-base existe)."""
    texto = _numero(abs(valor), 1)
    return texto.removesuffix(",0")


def _data(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _milhoes(reais: float) -> str:
    return _numero(reais / REAIS_POR_MILHAO, 0)


# --- uma frase por bloco ---------------------------------------------------------------------------


def _frase(
    molde: dict[str, Any], grupo: str, variante: str, **lacunas: str
) -> dict[str, Any]:
    texto = molde["frases"][grupo][variante].format_map(lacunas)
    return {"grupo": grupo, "variante": variante, "texto": texto, "lacunas": lacunas}


def _sentido(fracao: float) -> str:
    return "alta" if fracao > 0 else "queda"


def _abertura(resumo: dict[str, Any], molde: dict[str, Any]) -> dict[str, Any]:
    indice = resumo["ibovespa"]
    variante = (
        "de_lado"
        if abs(indice["variacao"]) < VARIACAO_DE_LADO
        else _sentido(indice["variacao"])
    )
    return _frase(
        molde,
        "abertura",
        variante,
        variacao=_percentual(indice["variacao"]),
        pregao=_data(resumo["pregao"]),
        pontos=_numero(indice["pontos"], 0),
    )


def _historia(resumo: dict[str, Any], molde: dict[str, Any]) -> list[dict[str, Any]]:
    indice = resumo["ibovespa"]
    if abs(indice["variacao"]) < VARIACAO_DE_LADO or indice["desde"] is None:
        return []
    quantos = indice["pregoes_tao_extremos"]
    contagem = "nenhum" if quantos == 0 else "um" if quantos == 1 else "varios"
    lacunas = {
        "comparados": _numero(indice["pregoes_comparados"], 0),
        "desde": _data(indice["desde"]),
        "tao_extremos": _numero(quantos, 0),
    }
    if indice["ultima_vez"]:
        lacunas["ultima_vez"] = _data(indice["ultima_vez"])
    variante = f"{_sentido(indice['variacao'])}_{contagem}"
    return [_frase(molde, "historia", variante, **lacunas)]


def _amplitude(resumo: dict[str, Any], molde: dict[str, Any]) -> dict[str, Any]:
    bloco = resumo["amplitude"]
    empresas = bloco["subiram"] + bloco["cairam"] + bloco["estaveis"]
    return _frase(
        molde,
        "amplitude",
        "contagem",
        empresas=_numero(empresas, 0),
        liquidez=_milhoes(bloco["liquidez_minima"]),
        subiram=_numero(bloco["subiram"], 0),
        cairam=_numero(bloco["cairam"], 0),
        estaveis=_numero(bloco["estaveis"], 0),
    )


def _ponta_dos_setores(
    molde: dict[str, Any], variante: str, setor: dict[str, Any]
) -> dict[str, Any]:
    return _frase(
        molde,
        "setores",
        variante,
        setor=setor["setor"],
        mediana=_percentual(setor["mediana"]),
        empresas=_numero(setor["empresas"], 0),
        contra=_com_sinal(setor["contra_o_indice"] * 100, CASAS_DA_VARIACAO),
    )


def _setores(resumo: dict[str, Any], molde: dict[str, Any]) -> list[dict[str, Any]]:
    """A ponta de cima e a de baixo; com menos de dois setores não há pontas."""
    lista = resumo["setores"]["lista"]
    if len(lista) < 2:
        return []
    return [
        _ponta_dos_setores(molde, "ponta_de_cima", lista[0]),
        _ponta_dos_setores(molde, "ponta_de_baixo", lista[-1]),
    ]


def _maiores(resumo: dict[str, Any], molde: dict[str, Any]) -> list[dict[str, Any]]:
    frases = []
    for lista, variante in (("altas", "alta"), ("quedas", "queda")):
        papeis = resumo["maiores"][lista]
        if not papeis:
            frases.append(_frase(molde, "maiores", f"sem_{variante}"))
            continue
        primeiro = papeis[0]
        frases.append(
            _frase(
                molde,
                "maiores",
                variante,
                empresa=primeiro["empresa"],
                simbolo=primeiro["simbolo"],
                variacao=_percentual(primeiro["variacao"]),
            )
        )
    return frases


def _ano_do_vencimento(simbolo: str) -> str:
    """DI1F29 → "2029" (os dois últimos dígitos do código são o ano)."""
    return f"20{simbolo[-2:]}"


def _juros(resumo: dict[str, Any], molde: dict[str, Any]) -> dict[str, Any]:
    bloco = resumo["juros"]
    pontos_base = _pontos_base(bloco["variacao_em_pontos_base"])
    variante = (
        "estavel" if pontos_base == "0" else _sentido(bloco["variacao_em_pontos_base"])
    )
    return _frase(
        molde,
        "juros",
        variante,
        ano=_ano_do_vencimento(bloco["simbolo"]),
        simbolo=bloco["simbolo"],
        pontos_base=pontos_base,
        taxa=f"{_numero(bloco['taxa'], CASAS_DA_TAXA)}%",
    )


def _dolar(resumo: dict[str, Any], molde: dict[str, Any]) -> dict[str, Any]:
    bloco = resumo["dolar"]
    variante = (
        "estavel"
        if _sem_mudanca_visivel(bloco["variacao"])
        else _sentido(bloco["variacao"])
    )
    return _frase(
        molde,
        "dolar",
        variante,
        simbolo=bloco["simbolo"],
        variacao=_percentual(bloco["variacao"]),
        cotacao=_numero(bloco["reais_por_dolar"], CASAS_DO_DOLAR),
    )


def _a_conferir(resumo: dict[str, Any], molde: dict[str, Any]) -> list[dict[str, Any]]:
    simbolos = [papel["simbolo"] for papel in resumo["a_conferir"]]
    if not simbolos:
        return []
    return [_frase(molde, "a_conferir", "lista", simbolos=", ".join(simbolos))]


def _limites(resumo: dict[str, Any], molde: dict[str, Any]) -> list[str]:
    lacunas = {
        "liquidez": _milhoes(resumo["amplitude"]["liquidez_minima"]),
        "minimo_por_setor": _numero(resumo["setores"]["empresas_por_setor_minimo"], 0),
    }
    return [limite.format_map(lacunas) for limite in molde["limites"]]


def _fontes(resumo: dict[str, Any]) -> list[str]:
    """As fontes dos blocos, sem repetir, na ordem do texto."""
    blocos = ("ibovespa", "amplitude", "setores", "maiores", "juros", "dolar")
    return list(dict.fromkeys(resumo[bloco]["fonte"] for bloco in blocos))


def conferir_molde(molde: dict[str, Any]) -> None:
    """Levanta erro se alguma frase do molde tem palavra proibida. Confere o molde, não o texto
    pronto: as lacunas trazem nomes de empresa e de setor, que podem coincidir com a lista."""
    modelos = [m for grupo in molde["frases"].values() for m in grupo.values()]
    for modelo in [*modelos, *molde["limites"]]:
        if achadas := palavras_proibidas(modelo):
            raise ValueError(
                f"palavra proibida no molde do pregão: {achadas} em {modelo!r}"
            )


def texto_do_pregao(resumo: dict[str, Any], molde: dict[str, Any]) -> dict[str, Any]:
    """O texto do dia em tipos simples: as frases (com o grupo e a variante do molde de cada uma), os
    limites, as fontes e a impressão digital do molde. Recusa molde com palavra proibida."""
    conferir_molde(molde)
    frases = [
        _abertura(resumo, molde),
        *_historia(resumo, molde),
        _amplitude(resumo, molde),
        *_setores(resumo, molde),
        *_maiores(resumo, molde),
        _juros(resumo, molde),
        _dolar(resumo, molde),
        *_a_conferir(resumo, molde),
    ]
    limites = _limites(resumo, molde)
    return {
        "pregao": resumo["pregao"],
        "frases": frases,
        "limites": limites,
        "fontes": _fontes(resumo),
        "impressao_digital": impressao_digital(molde),
    }
