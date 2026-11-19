"""Fonte, data e atribuição em cada campo da API externa (B-32a; cliente-norte, Emenda 2).

Cada campo sai com o valor, a fonte, o dia em que ficou público (`publico_em`, que o `known_at` corta)
e o momento em que o TickerLab o viu (`visto_em`). A resposta junta, uma vez cada, a licença e a frase
de atribuição de cada fonte usada: as licenças abertas (ODbL da CVM, CC BY da Receita) pedem que quem
redistribui cite a fonte.

As chaves saem em português daqui; a rota traduz tudo de uma vez na saída (`nomes.traduzir_chaves`).
"""

from collections.abc import Iterable
from datetime import date, datetime

from src.banco.coletas import FRASES_DAS_FONTES, SEM_LICENCA_CONHECIDA, licenca_da_fonte

# A frase da CVM fica aqui, não em `FRASES_DAS_FONTES`: lá ela entraria nas citações de toda tela e de
# todo PDF do app (`citacoes_das_fontes`), que hoje só citam as fontes restritas.
ATRIBUICOES_DA_API = {
    "cvm": "Fonte: CVM, Portal de Dados Abertos (ODbL)",
    "anvisa": "Fonte: Anvisa, dados abertos (CC BY); contagem de registros feita pelo TickerLab",
    # as agências do setor (molde D, linha 781), só as séries que a rota `sectors` serve
    "aneel-samp": "Fonte: ANEEL, Dados Abertos, SAMP (ODbL)",
    "bcb-ifdata": "Fonte: Banco Central do Brasil, IF.data (ODbL)",
    "susep-ses": "Fonte: SUSEP, SES, dados abertos (CC BY)",
    "ans-beneficiarios": "Fonte: ANS, dados abertos (CC BY)",
    "anatel-acessos": "Fonte: Anatel, dados abertos (CC BY)",
    # os ativos da empresa (linha 845)
    "anp-concessionarios": "Fonte: ANP, dados abertos, concessionários de E&P (CC BY)",
    "anm-sigbm-barragens": "Fonte: ANM, SIGBM, dados abertos",
    "anm-cfem-arrecadacao": "Fonte: ANM, arrecadação da CFEM, dados abertos",
    # as tabelas ligadas pelo CNPJ do registro (linha 978, `src/api_externa/tabelas_por_cnpj.py`)
    "aneel-fiscalizacao": "Fonte: ANEEL, Dados Abertos, indicadores comerciais das distribuidoras (ODbL)",
    "ans-qualidade": "Fonte: ANS, dados abertos, IDSS (CC BY)",
    # CGU, IBAMA e MTE no conjunto de integridade (ADR 0122, Emenda 1): a fonte citada em cada bloco
    "cgu-ceis": "Fonte: CGU, Portal da Transparência, CEIS (dados abertos, Decreto 8.777/2016)",
    "cgu-cnep": "Fonte: CGU, Portal da Transparência, CNEP (dados abertos, Decreto 8.777/2016)",
    "cgu-cepim": "Fonte: CGU, Portal da Transparência, CEPIM (dados abertos, Decreto 8.777/2016)",
    "cgu-leniencia": "Fonte: CGU, Portal da Transparência, acordos de leniência (dados abertos, Decreto 8.777/2016)",
    "ibama-embargos": "Fonte: IBAMA, Dados Abertos, termos de embargo (licença aberta do IBAMA)",
    "mte-lista-suja": (
        "Fonte: Ministério do Trabalho e Emprego, Cadastro de Empregadores (gov.br, CC BY-ND 3.0); registro "
        "como publicado, sem alteração"
    ),
}


def _data(momento: date | datetime | None) -> str | None:
    return None if momento is None else momento.isoformat()


def campo(
    valor: object,
    *,
    fonte: str,
    publico_em: date | datetime | None,
    visto_em: date | datetime | None,
) -> dict[str, object]:
    """Um campo servido. Sem `publico_em` não sai: não haveria como cortá-lo pelo `known_at`."""
    if publico_em is None:
        raise ValueError(
            f"Campo da fonte {fonte} sem data de publicação: não sai pela API."
        )
    return {
        "valor": valor,
        "fonte": fonte,
        "publico_em": _data(publico_em),
        "visto_em": _data(visto_em),
    }


def _familia(fonte: str) -> str:
    return fonte.split("-", 1)[0]


def _atribuicao(fonte: str) -> str:
    frase = (
        FRASES_DAS_FONTES.get(fonte)
        or FRASES_DAS_FONTES.get(_familia(fonte))
        or ATRIBUICOES_DA_API.get(fonte)
        or ATRIBUICOES_DA_API.get(_familia(fonte))
    )
    if frase is None or licenca_da_fonte(fonte) == SEM_LICENCA_CONHECIDA:
        raise ValueError(
            f"A fonte {fonte} não tem licença e atribuição: não sai pela API."
        )
    return frase


def fontes_da_resposta(fontes: Iterable[str]) -> list[dict[str, str]]:
    """A licença e a frase de cada fonte usada na resposta, uma vez cada, em ordem alfabética."""
    return [
        {
            "fonte": fonte,
            "licenca": licenca_da_fonte(fonte),
            "atribuicao": _atribuicao(fonte),
        }
        for fonte in sorted(set(fontes))
    ]
