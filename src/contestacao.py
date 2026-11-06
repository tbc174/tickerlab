"""O direito de resposta (ADR 0103, ponto 9): a frase fixa ao pé de toda ficha pública.

O texto foi aprovado pelo Tiago em 19/10/2026 ("pode com esse texto"), sem prazo e sem ajuste: não mude
uma palavra sem o "pode" dele. Ele promete que a contestação aparece ao lado do fato; quem cumpre a
promessa é `base.dossie.registros_de_insolvencia` (o fato ganha `situacao: contestada`).
"""

EMAIL_DE_CONTATO = "contato@tickerlab.com.br"
FRASE_DE_CONTESTACAO = (
    "Representa esta empresa e viu um fato errado? "
    f"Escreva para {EMAIL_DE_CONTATO} com o CNPJ e o fato. "
    "A contestação aparece ao lado do fato até a conferência."
)


def com_a_contestacao(limites: list[str]) -> list[str]:
    """Os limites com a frase de contestação no fim (uma vez só), que é o pé da ficha."""
    return [*(p for p in limites if p != FRASE_DE_CONTESTACAO), FRASE_DE_CONTESTACAO]
