"""Ficha da tentativa: o "run card" de uma rodada, montado só com o que está no registro.

Ideia trazida do Vibe-Trading (HKUDS, licença MIT; reescrita aqui do nosso jeito, 20/10/2026): cada
rodada ganha uma ficha curta que diz o que foi testado, contra qual critério, com quais dados, qual
foi a tentativa de número tantos e o veredito. A ficha **só lê**: não grava nada e não decide nada.
O que não foi anotado aparece como ausente (`None`, "não registrado"), nunca adivinhado.

A ficha sai em tipos simples (vira JSON sem conversão) para o painel, o relatório e, um dia, a API.
"""

from __future__ import annotations

from trader.holdout import CAMINHO_DO_CRITERIO, HASH_DO_CRITERIO
from trader.registro import Registro

CODIGO_DO_DSR = "A1"  # item do critério com o Sharpe deflacionado
SEM_VEREDITO = "sem veredito"
LIMITES_E_CUIDADOS = (
    (
        "Resultado de simulação com dados do passado, só no período de desenvolvimento; "
        "o holdout continua lacrado."
    ),
    (
        "O Sharpe deflacionado depende do número total de tentativas: fica mais exigente "
        "a cada rodada nova."
    ),
    "Custos e execução são os do critério, não os de uma corretora real.",
    "Isto não é recomendação de investimento nem promessa de rentabilidade.",
)


def _veredito(resultado: dict | None) -> str:
    """Só há veredito quando o resultado traz os itens do critério (baselines guardam só a carteira)."""
    if not resultado or not resultado.get("itens"):
        return SEM_VEREDITO
    if resultado.get("inconclusivo"):
        return "inconclusivo"
    return "aprovado" if resultado.get("aprovado") else "reprovado"


def _dsr(resultado: dict | None) -> float | None:
    for item in (resultado or {}).get("itens", []):
        if item.get("codigo") == CODIGO_DO_DSR:
            return item.get("valor")
    return None


def _numero_na_fase(registro: Registro, tentativa_id: int, fase: str) -> int:
    """A posição da tentativa entre as da mesma fase (a 1ª, a 2ª...), na ordem do registro."""
    ids = [t["id"] for t in registro.listar(fase)]
    return ids.index(tentativa_id) + 1


def montar_ficha(
    registro: Registro,
    tentativa_id: int,
    versao_do_criterio: str = HASH_DO_CRITERIO,
    nome_do_criterio: str = CAMINHO_DO_CRITERIO.name,
) -> dict:
    """A ficha da tentativa. O critério padrão é o vigente da M2 (SHA-256 em `holdout.py`)."""
    tentativa = registro.obter(tentativa_id)
    spec = tentativa["spec"]
    resultado = tentativa["resultado"]
    return {
        "tentativa_id": tentativa_id,
        "hipotese": f"{tentativa['familia']} · {tentativa['nome']}",
        "fase": tentativa["fase"],
        "numero_da_tentativa": _numero_na_fase(
            registro, tentativa_id, tentativa["fase"]
        ),
        "total_para_o_dsr": registro.total_para_o_dsr(),
        "execucoes": tentativa["execucoes"],
        "criada_em": tentativa["criada_em"],
        "commit_do_codigo": tentativa["commit_do_codigo"],
        "nome_do_criterio": nome_do_criterio,
        "versao_do_criterio": versao_do_criterio,
        "hash_da_especificacao": tentativa["hash"],
        "hash_dos_dados": spec.get("hash_dos_dados"),
        "parametros": spec,
        "dsr": _dsr(resultado),
        "veredito": _veredito(resultado),
        "reprovados": list((resultado or {}).get("reprovados", [])),
        "proveniencia": registro.obter_proveniencia(tentativa_id),
        "limites_e_cuidados": list(LIMITES_E_CUIDADOS),
    }


def _ou(valor: object, ausente: str) -> str:
    return ausente if valor is None else str(valor)


def ficha_em_markdown(ficha: dict) -> str:
    """A ficha como texto para o relatório da rodada."""
    prov = ficha["proveniencia"]
    quem = (
        "não anotado"
        if prov is None
        else prov["autor"] + (f" (com {prov['modelo']})" if prov["modelo"] else "")
    )
    dsr = "-" if ficha["dsr"] is None else f"{ficha['dsr']:.3f}"
    reprovados = ", ".join(ficha["reprovados"]) or "-"
    linhas = [
        f"# Ficha da tentativa #{ficha['numero_da_tentativa']}: {ficha['hipotese']}",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Fase | {ficha['fase']} |",
        f"| Veredito | {ficha['veredito']} |",
        f"| Itens reprovados | {reprovados} |",
        f"| Sharpe deflacionado ({CODIGO_DO_DSR}) | {dsr} |",
        f"| Tentativas para o DSR | {ficha['total_para_o_dsr']} |",
        f"| Execuções desta configuração | {ficha['execucoes']} |",
        f"| Critério | {ficha['nome_do_criterio']} (`{ficha['versao_do_criterio'][:12]}`) |",
        f"| Hash da especificação | `{ficha['hash_da_especificacao'][:12]}` |",
        f"| Hash dos dados | {_ou(ficha['hash_dos_dados'], 'não registrado')} |",
        f"| Commit do código | `{ficha['commit_do_codigo']}` |",
        f"| Quem escreveu | {quem} |",
        f"| Registrada em | {ficha['criada_em']} |",
        "",
        "## Limites e cuidados",
        "",
        *(f"- {texto}" for texto in ficha["limites_e_cuidados"]),
    ]
    return "\n".join(linhas) + "\n"
