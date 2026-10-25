"""Seção do CNAE (IBGE, CNAE 2.x) de um código de 7 dígitos, no nome que o SCR do Banco Central usa.

O SCR.data (`scr_credito`) agrupa a carteira de pessoa jurídica pela **seção** do CNAE (`cnae_ocupacao`,
21 seções de A a U). Quem quer cruzar a carteira com uma empresa parte do CNAE fiscal dela (7 dígitos,
`cnae_principal` da Receita); os dois primeiros dígitos são a divisão, e cada divisão pertence a uma só
seção. A estrutura é a do IBGE e não muda de um mês para o outro; o teste confere os nomes contra o
arquivo do BC.
"""

SECOES: dict[str, str] = {
    "A": "Agricultura, pecuária, produção florestal, pesca e aquicultura",
    "B": "Indústrias extrativas",
    "C": "Indústrias de transformação",
    "D": "Eletricidade e gás",
    "E": "Água, esgoto, atividades de gestão de resíduos e descontaminação",
    "F": "Construção",
    "G": "Comércio; reparação de veículos automotores e motocicletas",
    "H": "Transporte, armazenagem e correio",
    "I": "Alojamento e alimentação",
    "J": "Informação e comunicação",
    "K": "Atividades financeiras, de seguros e serviços relacionados",
    "L": "Atividades imobiliárias",
    "M": "Atividades profissionais, científicas e técnicas",
    "N": "Atividades administrativas e serviços complementares",
    "O": "Administração pública, defesa e seguridade social",
    "P": "Educação",
    "Q": "Saúde humana e serviços sociais",
    "R": "Artes, cultura, esporte e recreação",
    "S": "Outras atividades de serviços",
    "T": "Serviços domésticos",
    "U": "Organismos internacionais e outras instituições extraterritoriais",
}

# primeira e última divisão de cada seção (as divisões que faltam entre elas não existem no CNAE)
_DIVISOES: dict[str, tuple[int, int]] = {
    "A": (1, 3), "B": (5, 9), "C": (10, 33), "D": (35, 35), "E": (36, 39), "F": (41, 43),
    "G": (45, 47), "H": (49, 53), "I": (55, 56), "J": (58, 63), "K": (64, 66), "L": (68, 68),
    "M": (69, 75), "N": (77, 82), "O": (84, 84), "P": (85, 85), "Q": (86, 88), "R": (90, 93),
    "S": (94, 96), "T": (97, 97), "U": (99, 99),
}  # fmt: skip
_DIVISAO_DA_SECAO = {
    divisao: secao
    for secao, (primeira, ultima) in _DIVISOES.items()
    for divisao in range(primeira, ultima + 1)
}


def secao_do_cnae(codigo: object) -> str | None:
    """O nome da seção (como no `cnae_ocupacao` do SCR) do CNAE de 7 dígitos, com ou sem pontuação
    (`4120400`, `41.20-4-00`) ou como número; None se não for um código com divisão do CNAE."""
    texto = f"{codigo:07d}" if isinstance(codigo, int) else str(codigo or "")
    digitos = "".join(c for c in texto if c.isdigit())
    if len(digitos) != 7:
        return None
    secao = _DIVISAO_DA_SECAO.get(int(digitos[:2]))
    return SECOES[secao] if secao else None
