"""Renda fixa com IR: CDB, LCI/LCA, Tesouro Selic, poupança, Tesouro Prefixado e IPCA+, pelo mesmo
prazo.

- CDB: um percentual do CDI, sobre a taxa de cada dia útil; IOF nos primeiros 30 dias; IR pela
  tabela regressiva (sobre o rendimento que sobra depois do IOF).
- LCI ou LCA: um percentual do CDI, isento de IR para pessoa física. A LCA tem IOF zero; a LCI paga
  IOF antes de 30 dias, mas na prática as duas têm carência maior que isso, então aqui não entra.
- Tesouro Selic: a Selic de cada dia, que na prática anda junto com o CDI; IOF, IR e a custódia da
  B3 (0,2% ao ano, isenta até R$ 10 mil por CPF no Selic).
- Poupança: rende só no aniversário (a cada 30 dias), isenta.
- Tesouro Prefixado e IPCA+: a taxa de compra de hoje, levando até o fim do prazo; IOF, IR e
  custódia. No IPCA+, a inflação de cada ano vem de fora (a expectativa do Focus, na página).

O CDI pode mudar de um ano para o outro: `cdi_por_ano[k]` vale do dia 365·k ao 365·(k+1) da
aplicação (o último vale para os anos seguintes); `cdi_pelo_focus` monta esse caminho pela Selic
esperada. Os dias corridos viram dias úteis pela proporção 252/365 (sem o calendário de feriados).
A custódia é aproximada pelo saldo médio (a média do começo e do fim). As regras de imposto vêm de
`src/regras_de_imposto.py`. Fica de fora: a marcação a mercado (vender o Tesouro antes do prazo), o
risco de cada emissor e o FGC.
"""

from dataclasses import dataclass

from src import regras_de_imposto as regras

DIAS_UTEIS_POR_ANO = 252
DIAS_POR_ANO = 365
DIAS_DO_ANIVERSARIO = 30  # a poupança rende a cada aniversário mensal
DIAS_MAXIMOS = 3650  # 10 anos
EMPATE_MAXIMO = 10.0  # 1.000% do CDI: a busca do ponto de empate não passa disso
PASSOS_DO_EMPATE = 100
FOLGA_DO_TETO = 1e-9  # a busca que encosta no teto não achou o empate


@dataclass(frozen=True)
class Opcao:
    nome: str
    bruto: float  # o valor no fim, antes de IOF, IR e custódia
    aliquota: float  # a do IR
    imposto: float  # o IR
    liquido: float
    iof: float = 0.0
    custodia: float = 0.0


def _dias_uteis(dias: float) -> float:
    return dias * DIAS_UTEIS_POR_ANO / DIAS_POR_ANO


def _conferir(valor: float, dias: int) -> None:
    if valor < 0:
        raise ValueError("O valor aplicado não pode ser negativo.")
    if dias < 1 or dias > DIAS_MAXIMOS:
        raise ValueError(f"O prazo precisa estar entre 1 e {DIAS_MAXIMOS} dias.")


def _por_ano(dias: int, taxas: list[float]) -> list[tuple[int, float]]:
    """Os pedaços de até 365 dias da aplicação, cada um com a taxa do seu ano."""
    pedacos = []
    for comeco in range(0, dias, DIAS_POR_ANO):
        ano = min(comeco // DIAS_POR_ANO, len(taxas) - 1)
        pedacos.append((min(DIAS_POR_ANO, dias - comeco), taxas[ano]))
    return pedacos


def _pelo_cdi(
    valor: float, dias: int, cdi_por_ano: list[float], percentual: float
) -> float:
    fator = 1.0
    for dias_do_pedaco, cdi in _por_ano(dias, cdi_por_ano):
        diaria = ((1 + cdi) ** (1 / DIAS_UTEIS_POR_ANO) - 1) * percentual
        fator *= (1 + diaria) ** _dias_uteis(dias_do_pedaco)
    return valor * fator


def _custodia(valor: float, bruto: float, dias: int, isento_ate: float) -> float:
    """0,2% ao ano sobre o saldo médio que passa da isenção, pelo prazo."""
    taxa = float(regras.valor("custodia_do_tesouro"))
    saldo_medio = (valor + bruto) / 2
    return taxa * max(saldo_medio - isento_ate, 0.0) * dias / DIAS_POR_ANO


def _tributado(
    nome: str, valor: float, bruto: float, dias: int, custodia: float = 0.0
) -> Opcao:
    """IOF sobre o rendimento (antes de 30 dias), IR sobre o que sobra dele, custódia à parte."""
    rendimento = max(bruto - valor, 0.0)
    iof = rendimento * regras.aliquota_do_iof(dias)
    aliquota = regras.aliquota_da_renda_fixa(dias)
    imposto = (rendimento - iof) * aliquota
    return Opcao(
        nome, bruto, aliquota, imposto, bruto - iof - imposto - custodia, iof, custodia
    )


def _isento(nome: str, bruto: float) -> Opcao:
    return Opcao(nome, bruto, 0.0, 0.0, bruto)


def comparar(
    valor: float,
    dias: int,
    cdi_por_ano: list[float],
    percentual_do_cdb: float,
    percentual_da_lci: float,
    poupanca_ao_mes: float,
) -> list[Opcao]:
    """As quatro opções pelo CDI pelo mesmo `valor` e `dias` corridos (percentuais: 1,1 = 110% do
    CDI), na ordem fixa: CDB, LCI ou LCA, Tesouro Selic, poupança."""
    _conferir(valor, dias)
    if not cdi_por_ano:
        raise ValueError("Informe o CDI de pelo menos um ano.")
    if percentual_do_cdb < 0 or percentual_da_lci < 0:
        raise ValueError("O percentual do CDI não pode ser negativo.")
    aniversarios = dias // DIAS_DO_ANIVERSARIO
    selic = _pelo_cdi(valor, dias, cdi_por_ano, 1.0)
    isento_no_selic = float(regras.valor("custodia_isenta_no_selic_ate"))
    return [
        _tributado(
            "CDB", valor, _pelo_cdi(valor, dias, cdi_por_ano, percentual_do_cdb), dias
        ),
        _isento("LCI ou LCA", _pelo_cdi(valor, dias, cdi_por_ano, percentual_da_lci)),
        _tributado(
            "Tesouro Selic",
            valor,
            selic,
            dias,
            _custodia(valor, selic, dias, isento_no_selic),
        ),
        _isento("Poupança", valor * (1 + poupanca_ao_mes) ** aniversarios),
    ]


def tesouro_prefixado(valor: float, dias: int, taxa_ao_ano: float) -> Opcao:
    """O Tesouro Prefixado comprado hoje a `taxa_ao_ano`, levado até o fim de `dias`."""
    _conferir(valor, dias)
    bruto = valor * (1 + taxa_ao_ano) ** (_dias_uteis(dias) / DIAS_UTEIS_POR_ANO)
    return _tributado(
        "Tesouro Prefixado", valor, bruto, dias, _custodia(valor, bruto, dias, 0.0)
    )


def tesouro_ipca(
    valor: float, dias: int, juro_real: float, ipca_por_ano: list[float]
) -> Opcao:
    """O Tesouro IPCA+ comprado hoje a `juro_real`, com a inflação de cada ano de `ipca_por_ano`."""
    _conferir(valor, dias)
    if not ipca_por_ano:
        raise ValueError("Informe a inflação de pelo menos um ano.")
    fator = 1.0
    for dias_do_pedaco, ipca in _por_ano(dias, ipca_por_ano):
        fator *= (1 + ipca) ** (dias_do_pedaco / DIAS_POR_ANO)
    real = (1 + juro_real) ** (_dias_uteis(dias) / DIAS_UTEIS_POR_ANO)
    bruto = valor * real * fator
    return _tributado(
        "Tesouro IPCA+", valor, bruto, dias, _custodia(valor, bruto, dias, 0.0)
    )


def cdi_pelo_focus(
    cdi_hoje: float,
    selic_hoje: float,
    selic_esperada: dict[str, float],
    ano_inicial: int,
    anos: int,
) -> list[float]:
    """O CDI de cada ano da aplicação: a Selic esperada pelo Focus para o fim daquele ano, menos a
    diferença de hoje entre a Selic e o CDI. Depois do último ano do Focus, repete o último."""
    diferenca = selic_hoje - cdi_hoje
    caminho: list[float] = []
    for ano in range(ano_inicial, ano_inicial + anos):
        esperada = selic_esperada.get(str(ano))
        if esperada is None:
            caminho.append(caminho[-1] if caminho else cdi_hoje)
        else:
            caminho.append(esperada - diferenca)
    return caminho


def ponto_de_empate(
    valor: float, dias: int, cdi_por_ano: list[float], percentual_da_lci: float
) -> float | None:
    """O percentual do CDI que um CDB precisa pagar para render, depois do IR e do IOF, o mesmo que
    a LCI ou LCA isenta de `percentual_da_lci` (busca por bisseção); None se nem 1.000% do CDI
    empata (prazo de poucos dias, quando o IOF leva quase todo o rendimento)."""
    _conferir(valor, dias)
    alvo = _pelo_cdi(valor, dias, cdi_por_ano, percentual_da_lci)
    baixo, alto = 0.0, EMPATE_MAXIMO
    for _ in range(PASSOS_DO_EMPATE):
        meio = (baixo + alto) / 2
        cdb = _tributado(
            "CDB", valor, _pelo_cdi(valor, dias, cdi_por_ano, meio), dias
        ).liquido
        if cdb < alvo:
            baixo = meio
        else:
            alto = meio
    if baixo >= EMPATE_MAXIMO * (1 - FOLGA_DO_TETO):
        return None
    return (baixo + alto) / 2
