"""O pré-registro vigente da Pesquisa 2 e a trava que impede rodar com um texto diferente.

O texto aprovado pelo Tiago fica em `docs/pre-registro-p2-v0.1.md`. Mudar qualquer coisa nele gera
uma versão nova, com data, motivo e +25 tentativas no registro (seção 8 do próprio texto); o hash
abaixo só muda junto com essa versão nova.
"""

from __future__ import annotations

from pathlib import Path

from trader.holdout import hash_do_texto

VERSAO = "0.1"
ARQUIVO = Path(__file__).resolve().parents[2] / "docs" / "pre-registro-p2-v0.1.md"
# SHA-256 do texto aprovado em 11/10/2026 (quebras de linha normalizadas para \n).
HASH_DO_CRITERIO = "0c9ea794a144693646d4ed2b4f42e41c84f7a49a903cb30757f14aa7f8108af2"

# Números do critério usados pelo código (repetidos aqui para o código não ler o texto).
TENTATIVAS_DA_M2 = 101
ORCAMENTO_DE_TENTATIVAS = 20
VOLATILIDADE_ALVO = 0.12
PESOS_DOS_GRUPOS = {
    "moedas": 0.30,
    "indices": 0.30,
    "metais": 0.15,
    "energia": 0.15,
    "titulos": 0.10,
}


class PreRegistroAlteradoError(RuntimeError):
    """O texto do pré-registro não é o aprovado: rodar seria mudar o critério escondido."""


def conferir(arquivo: Path = ARQUIVO, esperado: str = HASH_DO_CRITERIO) -> None:
    """Recusa seguir se o texto do pré-registro mudou desde a aprovação."""
    encontrado = hash_do_texto(arquivo)
    if encontrado != esperado:
        raise PreRegistroAlteradoError(
            f"O pré-registro em {arquivo.name} mudou (hash {encontrado[:12]}…). "
            "Uma mudança exige versão nova aprovada pelo Tiago e +25 tentativas."
        )
