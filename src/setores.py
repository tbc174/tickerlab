"""Grupos de setores para os padrões das notas (série 2 da base de ML, PR 4; ADR 0033).

Um lugar só para dizer com quem cada empresa é comparada. A base é o setor que a empresa informa à
CVM (cadastro, dado aberto): são 53 setores entre as empresas com DFP, muitos com 1 a 5 empresas,
pequenos demais para um padrão. Por isso viram 15 grupos. Regras:

- **Holdings** ("Emp. Adm. Part. - Energia Elétrica") vão para o grupo do setor que administram; a
  sem setor principal fica em "holdings".
- **Grupo com menos de `MINIMO_DE_EMPRESAS`** com o indicador compara com o mercado inteiro (só
  não financeiras), e o texto avisa.
- **Financeiro** (bancos, seguradoras, securitizadoras...) nunca cai no mercado das não
  financeiras: sem empresas suficientes, fica sem padrão.
"""

import unicodedata

SEM_GRUPO = "sem_grupo"
MERCADO = "mercado"
MINIMO_DE_EMPRESAS = 8  # abaixo disso, percentil por grupo é ruído
PREFIXO_DE_HOLDING = "emp. adm. part. -"

# grupo → (nome para a tela, trechos do setor da CVM, sem acento e em minúsculas)
GRUPOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "energia": ("Energia elétrica", ("energia eletrica",)),
    "saneamento": ("Saneamento, água e gás", ("saneamento",)),
    "transporte": ("Transporte e logística", ("transporte",)),
    "construcao": ("Construção e materiais", ("const",)),
    "comercio": ("Comércio", ("comercio",)),
    "bens_de_capital": ("Máquinas, veículos e peças", ("maq",)),
    "materiais_basicos": (
        "Materiais básicos",
        (
            "metalurgia",
            "petroquimicos",
            "papel e celulose",
            "embalagens",
            "reflorestamento",
            "extracao mineral",
        ),
    ),
    "petroleo": ("Petróleo e gás", ("petroleo",)),
    "consumo_nao_ciclico": (
        "Alimentos, bebidas e agro",
        ("alimentos", "bebidas", "agricultura"),
    ),
    "consumo_ciclico": (
        "Vestuário, lazer e turismo",
        ("textil", "brinquedos", "hospedagem"),
    ),
    "saude": ("Saúde", ("servicos medicos", "farmaceutico")),
    "telecom_ti": (
        "Telecomunicações e tecnologia",
        ("telecomunicacoes", "comunicacao e informatica"),
    ),
    "educacao": ("Educação", ("educacao",)),
    "financeiro": (
        "Financeiro",
        (
            "bancos",
            "intermediacao financeira",
            "seguradoras",
            "arrendamento",
            "credito imobiliario",
            "bolsas de valores",
            "securitizacao",
        ),
    ),
    "holdings": ("Holdings sem setor principal", ("sem setor principal",)),
}
NOMES = {
    MERCADO: "Mercado (todas as não financeiras)",
    **{g: n for g, (n, _) in GRUPOS.items()},
}


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def grupo_do_setor(setor: str) -> str:
    """O grupo de um setor da CVM (`SEM_GRUPO` se não reconhecer)."""
    texto = _sem_acento(setor)
    if texto.startswith(PREFIXO_DE_HOLDING):
        texto = texto.removeprefix(PREFIXO_DE_HOLDING).strip()
    if not texto:
        return SEM_GRUPO
    for grupo, (_, trechos) in GRUPOS.items():
        if any(trecho in texto for trecho in trechos):
            return grupo
    return SEM_GRUPO


def grupo_para_comparar(
    grupo: str, empresas_por_grupo: dict[str, int]
) -> tuple[str, str]:
    """(grupo usado no padrão, aviso). Grupo pequeno usa o mercado; financeiro nunca."""
    quantas = empresas_por_grupo.get(grupo, 0)
    if quantas >= MINIMO_DE_EMPRESAS:
        return grupo, ""
    nome = NOMES.get(grupo, grupo)
    if grupo == "financeiro":
        return SEM_GRUPO, (
            f"Só {quantas} empresas em {nome}, menos que as {MINIMO_DE_EMPRESAS} do mínimo: "
            "sem padrão (o mercado das não financeiras não serve de régua)."
        )
    return MERCADO, (
        f"Só {quantas} empresas em {nome}, menos que as {MINIMO_DE_EMPRESAS} do mínimo: "
        "comparado com o mercado inteiro (não financeiras)."
    )
