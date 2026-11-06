"""Cenários da cascata: inadimplência, atraso com recuperação e pré-pagamento (protótipo D, etapa 5).

Pega uma carteira e uma estrutura (tipos simples, fáceis de virar JSON), projeta o fluxo mensal do pool
em cada cenário e roda a mesma cascata de `cascata.py` em todos. Dinheiro em **centavos inteiros**; os
números dos testes são 100% sintéticos (nenhuma operação, oferta ou rating real).

Convenções (escritas antes do código, ADR 0006):

1. Taxas anuais viram mensais pela forma de **sobrevivência**, não pela divisão por 12:
   MDR = 1 - (1 - CDR)^(1/12) e SMM = 1 - (1 - CPR)^(1/12). CDR é a inadimplência anual acumulada
   (*conditional default rate*), CPR o pré-pagamento anual (*conditional prepayment rate*).
2. Em cada mês, sobre o saldo vivo: a perda é `saldo × MDR` (reconhecida no mês, abate o pool); o juros
   recebido é a taxa do pool sobre o que sobrou; o principal programado é o saldo dividido pelos meses que
   faltam; o pré-pagamento é `SMM` sobre o que resta depois do programado. Tudo arredondado para baixo.
3. A recuperação é uma fração da perda do mês que volta ao caixa `defasagem` meses depois (atraso).
   O horizonte é o prazo da carteira mais a defasagem, para a última recuperação ainda caber.
4. Os cenários mudam só os parâmetros acima; carteira, estrutura e motor da cascata são os mesmos, então a
   diferença entre dois cenários vem só deles.
5. **CDR de equilíbrio** de uma classe: o maior CDR anual em que ela ainda não perde principal, com o resto
   do cenário fixo (padrão: o base). Achado por bissecção entre 0 e 100%: o limite de baixo nunca perde e o
   de cima sempre perde, então a resposta vale mesmo que a perda não cresça sempre com o CDR (arredondamento,
   gatilho). Perde já com CDR zero: None; não perde nem com 100%: 1,0. Sem preço nem taxa de desconto (o
   dossiê pede a convenção brasileira, DU/252, antes de qualquer preço).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import asdict, dataclass

from src.securitizacao.cascata import (
    MESES_POR_ANO,
    PRO_RATA,
    REGRAS_DA_0_1_0,
    Classe,
    Operacao,
    Periodo,
    Regras,
    Resultado,
    reconciliar,
    rodar,
    vida_media_em_anos,
)

CENTAVOS_POR_REAL = 100
TOLERANCIA_DO_EQUILIBRIO = 1e-4  # 0,01 ponto percentual de CDR anual


def cdr_para_mdr(cdr_anual: float) -> float:
    """Inadimplência anual (CDR) → mensal (MDR), na forma de sobrevivência."""
    if not 0.0 <= cdr_anual <= 1.0:
        raise ValueError("CDR fora de 0 a 1")
    return 1.0 - (1.0 - cdr_anual) ** (1.0 / MESES_POR_ANO)


def cpr_para_smm(cpr_anual: float) -> float:
    """Pré-pagamento anual (CPR) → mensal (SMM), na forma de sobrevivência."""
    if not 0.0 <= cpr_anual <= 1.0:
        raise ValueError("CPR fora de 0 a 1")
    return 1.0 - (1.0 - cpr_anual) ** (1.0 / MESES_POR_ANO)


@dataclass(frozen=True)
class Carteira:
    """O pool de recebíveis: saldo em centavos, taxa mensal que ele rende e prazo de amortização linear."""

    saldo: int
    taxa_mensal: float
    prazo_meses: int

    def __post_init__(self) -> None:
        if self.saldo < 0 or self.prazo_meses < 1 or self.taxa_mensal < 0:
            raise ValueError("carteira inválida")


@dataclass(frozen=True)
class Estrutura:
    """As classes (da mais sênior à mais subordinada), a reserva mínima, a despesa mensal fixa e as regras."""

    classes: tuple[Classe, ...]
    reserva_minima: int
    despesas_mensais: int
    regras: Regras = REGRAS_DA_0_1_0  # entra no hash da entrada

    def operacao(self, saldo_do_pool: int) -> Operacao:
        """Uma operação nova (a cascata guarda saldos enquanto roda: cada cenário usa a sua)."""
        return Operacao(
            classes=list(self.classes),
            saldo_do_pool=saldo_do_pool,
            reserva_minima=self.reserva_minima,
            regras=self.regras,
        )

    @property
    def subordinada(self) -> str:
        """Nome da classe que perde primeiro e recebe o residual."""
        return max(self.classes, key=lambda c: c.senioridade).nome


@dataclass(frozen=True)
class Cenario:
    """Os parâmetros que diferenciam um cenário do outro."""

    nome: str
    cdr_anual: float
    cpr_anual: float = 0.0
    taxa_de_recuperacao: float = 0.0  # fração da perda que volta ao caixa
    defasagem_da_recuperacao: int = 0  # meses entre a perda e a recuperação

    def __post_init__(self) -> None:
        if not 0.0 <= self.taxa_de_recuperacao <= 1.0:
            raise ValueError("recuperação fora de 0 a 1")
        if self.defasagem_da_recuperacao < 0:
            raise ValueError("defasagem negativa")
        cdr_para_mdr(self.cdr_anual)
        cpr_para_smm(self.cpr_anual)


@dataclass
class ResultadoDoCenario:
    """O que um cenário produziu: mês a mês, totais por classe e a reconciliação do caixa."""

    cenario: Cenario
    meses: list[Resultado]
    totais_por_classe: dict[str, dict[str, int]]
    residual: int
    pago_a_subordinada: int
    perda_total: int
    reconciliacao: dict[str, int]
    vida_media_em_anos: dict[str, float | None]


# Cenários de referência (CDR 6% a.a. é o base; o dobro é o estresse de inadimplência).
CDR_BASE = 0.06
CPR_PRE_PAGAMENTO = 0.20
RECUPERACAO_DO_ATRASO = 0.40
DEFASAGEM_DO_ATRASO = 6

CENARIO_BASE = Cenario("base", CDR_BASE)
CENARIO_INADIMPLENCIA_x2 = Cenario("inadimplência ×2", 2 * CDR_BASE)
CENARIO_ATRASO_E_RECUPERACAO = Cenario(
    "atraso e recuperação",
    2 * CDR_BASE,
    taxa_de_recuperacao=RECUPERACAO_DO_ATRASO,
    defasagem_da_recuperacao=DEFASAGEM_DO_ATRASO,
)
CENARIO_PRE_PAGAMENTO = Cenario("pré-pagamento", CDR_BASE, cpr_anual=CPR_PRE_PAGAMENTO)
CENARIOS_PADRAO = (
    CENARIO_BASE,
    CENARIO_INADIMPLENCIA_x2,
    CENARIO_ATRASO_E_RECUPERACAO,
    CENARIO_PRE_PAGAMENTO,
)

# As quatro regras da 0.2.0 ligadas, com parâmetros de referência (sintéticos): na carteira sintética, a perda
# acumulada do base fica em ~6% do pool original e a do estresse passa de 12%, então o gatilho de 8% dispara
# só no estresse; a meta de sobrecolateralização de 10% fica acima dos 5% da estrutura sintética, então o
# turbo trabalha desde o primeiro mês.
GATILHO_DE_PERDA_DE_REFERENCIA = 0.08
META_DE_SOBRECOLATERALIZACAO_DE_REFERENCIA = 0.10
REGRAS_DA_0_2_0_LIGADAS = Regras(
    juros_acumulam=True,
    principal=PRO_RATA,
    gatilho_de_perda=GATILHO_DE_PERDA_DE_REFERENCIA,
    meta_de_sobrecolateralizacao=META_DE_SOBRECOLATERALIZACAO_DE_REFERENCIA,
)


def projetar_fluxos(
    carteira: Carteira, estrutura: Estrutura, cenario: Cenario
) -> list[Periodo]:
    """O fluxo mensal do pool no cenário, na convenção do módulo (itens 2 e 3)."""
    mdr = cdr_para_mdr(cenario.cdr_anual)
    smm = cpr_para_smm(cenario.cpr_anual)
    horizonte = carteira.prazo_meses + cenario.defasagem_da_recuperacao
    recuperacoes = [0] * horizonte
    meses: list[tuple[int, int, int]] = []  # principal, juros, perda
    saldo = carteira.saldo
    for mes in range(horizonte):
        restantes = carteira.prazo_meses - mes
        if saldo == 0 or restantes < 1:
            meses.append((0, 0, 0))
            continue
        perda = int(saldo * mdr)
        vivo = saldo - perda
        juros = int(vivo * carteira.taxa_mensal)
        programado = vivo // restantes
        pre_pago = int((vivo - programado) * smm)
        principal = programado + pre_pago
        saldo = vivo - principal
        recuperacoes[mes + cenario.defasagem_da_recuperacao] += int(
            perda * cenario.taxa_de_recuperacao
        )
        meses.append((principal, juros, perda))
    return [
        Periodo(principal, juros, recuperacao, perda, estrutura.despesas_mensais)
        for (principal, juros, perda), recuperacao in zip(
            meses, recuperacoes, strict=True
        )
    ]


def _totais_por_classe(
    estrutura: Estrutura, meses: list[Resultado]
) -> dict[str, dict[str, int]]:
    return {
        c.nome: {
            "juros": sum(r.juros_pagos[c.nome] for r in meses),
            "principal": sum(r.principal_pago[c.nome] for r in meses),
            "perda": sum(r.perda_alocada[c.nome] for r in meses),
        }
        for c in estrutura.classes
    }


def rodar_cenario(
    carteira: Carteira, estrutura: Estrutura, cenario: Cenario
) -> ResultadoDoCenario:
    """Projeta o fluxo e roda a cascata; o motor lança erro se o caixa não conservar."""
    meses = rodar(
        estrutura.operacao(carteira.saldo),
        projetar_fluxos(carteira, estrutura, cenario),
    )
    totais = _totais_por_classe(estrutura, meses)
    sub = totais[estrutura.subordinada]
    residual = sum(r.residual for r in meses)
    return ResultadoDoCenario(
        cenario=cenario,
        meses=meses,
        totais_por_classe=totais,
        residual=residual,
        pago_a_subordinada=sub["juros"] + sub["principal"] + residual,
        perda_total=sum(
            r.perda_alocada[c.nome] for r in meses for c in estrutura.classes
        ),
        reconciliacao=reconciliar(0, meses),
        vida_media_em_anos={
            c.nome: vida_media_em_anos(meses, c.nome) for c in estrutura.classes
        },
    )


def rodar_cenarios(
    carteira: Carteira,
    estrutura: Estrutura,
    cenarios: tuple[Cenario, ...] = CENARIOS_PADRAO,
) -> list[ResultadoDoCenario]:
    """Todos os cenários sobre a mesma carteira e estrutura, na ordem dada."""
    return [rodar_cenario(carteira, estrutura, c) for c in cenarios]


def _perde_principal(
    carteira: Carteira, estrutura: Estrutura, cenario: Cenario, classe: str
) -> bool:
    resultado = rodar_cenario(carteira, estrutura, cenario)
    return resultado.totais_por_classe[classe]["perda"] > 0


def cdr_de_equilibrio(
    carteira: Carteira,
    estrutura: Estrutura,
    classe: str,
    cenario: Cenario = CENARIO_BASE,
    tolerancia: float = TOLERANCIA_DO_EQUILIBRIO,
) -> float | None:
    """O maior CDR anual em que a classe não perde principal, por bissecção (convenção 5 do módulo)."""
    if classe not in {c.nome for c in estrutura.classes}:
        raise ValueError(f"classe desconhecida: {classe}")

    def perde(cdr: float) -> bool:
        com_cdr = dataclasses.replace(cenario, cdr_anual=cdr)
        return _perde_principal(carteira, estrutura, com_cdr, classe)

    if perde(0.0):
        return None
    if not perde(1.0):
        return 1.0
    nao_perde, perde_com = 0.0, 1.0
    while perde_com - nao_perde > tolerancia:
        meio = (nao_perde + perde_com) / 2
        if perde(meio):
            perde_com = meio
        else:
            nao_perde = meio
    return nao_perde


def cdrs_de_equilibrio(
    carteira: Carteira, estrutura: Estrutura, cenario: Cenario = CENARIO_BASE
) -> dict[str, float | None]:
    """O CDR de equilíbrio de cada classe, da mais sênior à mais subordinada."""
    ordenadas = sorted(estrutura.classes, key=lambda c: c.senioridade)
    return {
        c.nome: cdr_de_equilibrio(carteira, estrutura, c.nome, cenario)
        for c in ordenadas
    }


def hash_da_entrada(carteira: Carteira, estrutura: Estrutura) -> str:
    """SHA-256 da carteira e da estrutura em JSON canônico: quem recebe o relatório confere a entrada."""
    canonico = json.dumps(
        {"carteira": asdict(carteira), "estrutura": asdict(estrutura)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def carteira_sintetica() -> tuple[Carteira, Estrutura]:
    """A carteira e a estrutura sintéticas dos testes e do relatório de exemplo (as do #504)."""
    r = CENTAVOS_POR_REAL
    carteira = Carteira(saldo=1_000_000 * r, taxa_mensal=0.025, prazo_meses=24)
    estrutura = Estrutura(
        classes=(
            Classe("senior", 1, 800_000 * r, 0.010),
            Classe("mezanino", 2, 150_000 * r, 0.015),
            Classe("subordinada", 3, 50_000 * r, 0.0),
        ),
        reserva_minima=10_000 * r,
        despesas_mensais=1_000 * r,
    )
    return carteira, estrutura
