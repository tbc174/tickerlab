"""O PDF dos cenários da cascata (protótipo D, etapa 6): feito para outra pessoa auditar.

Estrutura da operação, os cenários lado a lado (com a vida média de cada classe), o CDR de equilíbrio, os
mesmos cenários com as regras da 0.2.0 ligadas, a reconciliação do caixa, a versão do motor e o SHA-256 da
carteira de entrada. "Limites e cuidados" sai sempre. Usa o mesmo `RelatorioPDF` dos demais
relatórios; nenhuma rota nem tela chama esta função ainda (a rota que a exporia seria
`POST /v1/securitizacao/cenarios`, a definir com o B-10).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from src.estilos_pdf import PADRAO, Estilo
from src.relatorio_empresa_pdf import FUSO
from src.relatorio_pdf import RelatorioPDF
from src.securitizacao.cascata import PRO_RATA, VERSAO_DO_CALCULO, Regras
from src.securitizacao.cenarios import (
    CENTAVOS_POR_REAL,
    REGRAS_DA_0_2_0_LIGADAS,
    TOLERANCIA_DO_EQUILIBRIO,
    Carteira,
    Estrutura,
    ResultadoDoCenario,
    cdrs_de_equilibrio,
    hash_da_entrada,
    rodar_cenarios,
)

TITULO_DOS_LIMITES = "Limites e cuidados"
TITULO_DO_EQUILIBRIO = "Vida média e CDR de equilíbrio"
TITULO_DAS_REGRAS_LIGADAS = "Com as regras da 0.2.0 ligadas"
SEM_VALOR = "—"
TOLERANCIA_EM_TEXTO = f"{TOLERANCIA_DO_EQUILIBRIO:.2%}".replace(".", ",")
AVISO_DO_RODAPE = "Protótipo com carteira sintética. Nada aqui é recomendação de investimento, oferta ou rating."
LIMITES = [
    (
        f"Protótipo: o motor é a {VERSAO_DO_CALCULO} e ainda não cobre juros de mora, custo variável, "
        "indexador, gatilhos de caixa ou de inadimplência (só o de perda acumulada) nem recomposição de "
        "perda já alocada."
    ),
    "A carteira é sintética: nenhum número representa operação, oferta, rating ou condição de mercado real.",
    (
        "Os cenários são hipóteses de inadimplência (CDR), pré-pagamento (CPR) e recuperação com atraso, "
        "aplicadas de forma uniforme à carteira. Não são previsão."
    ),
    (
        "O modelo não captura concentração de devedores, correlação entre inadimplências, fraude, risco "
        "operacional e jurídico, recompra de créditos nem renegociação."
    ),
    (
        "A recuperação volta ao caixa como principal das classes de cima: não restitui perda já alocada "
        "às de baixo."
    ),
    (
        "A vida média (WAL) pondera o principal recebido pelo mês em que entrou, em anos; a classe que "
        "perde tem a vida média do que recebeu. Sem preço, taxa interna nem duration: esses pedem a "
        "convenção brasileira (DU/252) e ficam para depois."
    ),
    (
        "O CDR de equilíbrio é o maior CDR anual em que a classe ainda não perde principal, com o resto do "
        "cenário base (sem pré-pagamento nem recuperação), achado por bissecção: erra por no máximo "
        f"{TOLERANCIA_EM_TEXTO} de CDR anual, sempre para menos. Não conta os juros que ficaram sem pagar."
    ),
    (
        "Os parâmetros das regras da 0.2.0 ligadas (gatilho de perda e meta de sobrecolateralização) são "
        "de referência, não de uma operação real."
    ),
    "Nada aqui é recomendação de investimento.",
]


def _reais(centavos: int) -> str:
    """Centavos em reais no formato brasileiro (1.234,56)."""
    reais, resto = divmod(abs(centavos), CENTAVOS_POR_REAL)
    texto = f"{reais:,}".replace(",", ".") + f",{resto:02d}"
    return f"-{texto}" if centavos < 0 else texto


def _percentual(fracao: float) -> str:
    """Fração em percentual com vírgula decimal (0.05 → 5,0%)."""
    return f"{fracao:.1%}".replace(".", ",")


def _anos(anos: float | None) -> str:
    """Vida média em anos com vírgula decimal; classe sem principal recebido fica sem valor."""
    return SEM_VALOR if anos is None else f"{anos:.2f}".replace(".", ",")


def _cdr(cdr: float | None) -> str:
    """CDR de equilíbrio em percentual; None é perda mesmo sem inadimplência, 1,0 é nunca perder."""
    if cdr is None:
        return "perde com CDR 0"
    if cdr >= 1.0:
        return "não perde"
    if cdr < TOLERANCIA_DO_EQUILIBRIO:
        return f"menos de {TOLERANCIA_EM_TEXTO}"
    return f"{cdr:.2%}".replace(".", ",")


def descrever_regras(regras: Regras) -> str:
    """As regras da cascata em uma frase, para quem audita saber com que regime o motor rodou."""
    if regras.principal == PRO_RATA and regras.gatilho_de_perda is not None:
        principal = (
            "principal pro rata até a perda acumulada passar de "
            f"{_percentual(regras.gatilho_de_perda)} do pool original, depois sequencial"
        )
    elif regras.principal == PRO_RATA:
        principal = "principal pro rata, sem gatilho"
    else:
        principal = "principal sequencial"
    meta = regras.meta_de_sobrecolateralizacao
    turbo = (
        "sem turbo"
        if meta is None
        else f"turbo até a sobrecolateralização de {_percentual(meta)} do pool"
    )
    acumulam = "sim" if regras.juros_acumulam else "não"
    return f"Regras da cascata: juros não pagos acumulam: {acumulam}; {principal}; {turbo}."


def _tabela_da_estrutura(estrutura: Estrutura) -> tuple[list[str], list[list[str]]]:
    cabecalho = ["Classe", "Senioridade", "Saldo inicial (R$)", "Taxa mensal"]
    linhas = [
        [c.nome, str(c.senioridade), _reais(c.saldo_inicial), f"{c.taxa_mensal:.2%}"]
        for c in sorted(estrutura.classes, key=lambda c: c.senioridade)
    ]
    return cabecalho, linhas


def _tabela_dos_cenarios(
    estrutura: Estrutura, resultados: list[ResultadoDoCenario]
) -> tuple[list[str], list[list[str]]]:
    cabecalho = ["R$", *(r.cenario.nome for r in resultados)]
    linhas = [
        ["CDR anual", *(_percentual(r.cenario.cdr_anual) for r in resultados)],
        ["CPR anual", *(_percentual(r.cenario.cpr_anual) for r in resultados)],
        [
            "Recuperação (atraso em meses)",
            *(
                f"{r.cenario.taxa_de_recuperacao:.0%} ({r.cenario.defasagem_da_recuperacao})"
                for r in resultados
            ),
        ],
    ]
    for c in sorted(estrutura.classes, key=lambda c: c.senioridade):
        linhas.append(
            [
                f"Juros pagos: {c.nome}",
                *(_reais(r.totais_por_classe[c.nome]["juros"]) for r in resultados),
            ]
        )
        linhas.append(
            [
                f"Principal pago: {c.nome}",
                *(_reais(r.totais_por_classe[c.nome]["principal"]) for r in resultados),
            ]
        )
        linhas.append(
            [
                f"Perda alocada: {c.nome}",
                *(_reais(r.totais_por_classe[c.nome]["perda"]) for r in resultados),
            ]
        )
    linhas.extend(
        [
            f"Vida média (anos): {c.nome}",
            *(_anos(r.vida_media_em_anos[c.nome]) for r in resultados),
        ]
        for c in sorted(estrutura.classes, key=lambda c: c.senioridade)
    )
    linhas.append(["Residual", *(_reais(r.residual) for r in resultados)])
    linhas.append(
        [
            f"Total à subordinada ({estrutura.subordinada})",
            *(_reais(r.pago_a_subordinada) for r in resultados),
        ]
    )
    return cabecalho, linhas


def _tabela_do_equilibrio(
    estrutura: Estrutura, colunas: list[tuple[str, dict[str, float | None]]]
) -> tuple[list[str], list[list[str]]]:
    cabecalho = ["CDR de equilíbrio", *(rotulo for rotulo, _ in colunas)]
    linhas = [
        [c.nome, *(_cdr(cdrs[c.nome]) for _, cdrs in colunas)]
        for c in sorted(estrutura.classes, key=lambda c: c.senioridade)
    ]
    return cabecalho, linhas


def _tabela_da_reconciliacao(
    resultados: list[ResultadoDoCenario],
) -> tuple[list[str], list[list[str]]]:
    cabecalho = ["R$", *(r.cenario.nome for r in resultados)]
    chaves = [
        ("Entradas", "entradas"),
        ("Saídas", "saidas"),
        ("Reserva final", "reserva_final"),
        ("Diferença (deve ser zero)", "diferenca"),
    ]
    linhas = [
        [rotulo, *(_reais(r.reconciliacao[chave]) for r in resultados)]
        for rotulo, chave in chaves
    ]
    return cabecalho, linhas


def relatorio_dos_cenarios(
    carteira: Carteira,
    estrutura: Estrutura,
    resultados: list[ResultadoDoCenario],
    gerado_em: datetime | None = None,
    estilo: Estilo = PADRAO,
    regras_comparadas: Regras | None = REGRAS_DA_0_2_0_LIGADAS,
) -> bytes:
    """Os bytes do PDF: estrutura, cenários, equilíbrio, regras comparadas, reconciliação, versão, hash e limites.

    `regras_comparadas` roda os mesmos cenários com outras regras (padrão: as da 0.2.0 ligadas); None, ou as
    mesmas regras da estrutura, tira essa seção.
    """
    gerado_em = gerado_em or datetime.now(FUSO)
    hash_da_carteira = hash_da_entrada(carteira, estrutura)
    comparada = None
    if regras_comparadas is not None and regras_comparadas != estrutura.regras:
        comparada = dataclasses.replace(estrutura, regras=regras_comparadas)
    pdf = RelatorioPDF(
        "Cenários da cascata de securitização",
        "Protótipo · carteira sintética",
        gerado_em,
        estilo,
        AVISO_DO_RODAPE,
    )
    titulos = [
        "Estrutura da operação",
        "Cenários lado a lado",
        TITULO_DO_EQUILIBRIO,
        *([TITULO_DAS_REGRAS_LIGADAS] if comparada else []),
        "Reconciliação do caixa",
    ]
    pdf.capa(
        [
            ("Versão do motor", VERSAO_DO_CALCULO),
            ("SHA-256 da carteira", hash_da_carteira[:16] + "…"),
            ("Gerado em", f"{gerado_em:%d/%m/%Y às %H:%M}"),
        ],
        [*titulos, "Reprodutibilidade", TITULO_DOS_LIMITES],
    )
    pdf.add_page()
    pdf.secao("Estrutura da operação", numerada=True, reservar=50)
    pdf.paragrafo(
        f"Carteira: saldo de R$ {_reais(carteira.saldo)}, rendimento de "
        f"{carteira.taxa_mensal:.2%} ao mês e amortização linear em {carteira.prazo_meses} meses. "
        f"Reserva mínima de R$ {_reais(estrutura.reserva_minima)} e despesas de "
        f"R$ {_reais(estrutura.despesas_mensais)} por mês."
    )
    pdf.paragrafo(descrever_regras(estrutura.regras))
    pdf.tabela_de_texto(*_tabela_da_estrutura(estrutura))
    pdf.secao("Cenários lado a lado", numerada=True, reservar=60)
    pdf.tabela_de_texto(*_tabela_dos_cenarios(estrutura, resultados))
    _secao_do_equilibrio(pdf, carteira, estrutura, comparada)
    if comparada is not None:
        _secao_das_regras_ligadas(pdf, carteira, comparada, resultados)
    pdf.secao("Reconciliação do caixa", numerada=True, reservar=40)
    pdf.tabela_de_texto(*_tabela_da_reconciliacao(resultados))
    pdf.secao("Reprodutibilidade", numerada=True, reservar=40)
    pdf.pares(
        [
            ("Versão do motor", VERSAO_DO_CALCULO),
            ("SHA-256 da carteira", hash_da_carteira),
        ]
    )
    pdf.secao(TITULO_DOS_LIMITES, reservar=40, numerada=True)
    pdf.lista(LIMITES)
    return pdf.para_bytes()


def _secao_do_equilibrio(
    pdf: RelatorioPDF,
    carteira: Carteira,
    estrutura: Estrutura,
    comparada: Estrutura | None,
) -> None:
    """O CDR de equilíbrio de cada classe, com as regras da estrutura e, se houver, com as comparadas."""
    colunas = [("regras da estrutura", cdrs_de_equilibrio(carteira, estrutura))]
    if comparada is not None:
        colunas.append(
            ("regras da 0.2.0 ligadas", cdrs_de_equilibrio(carteira, comparada))
        )
    pdf.secao(TITULO_DO_EQUILIBRIO, numerada=True, reservar=40)
    pdf.paragrafo(
        "A vida média de cada classe está na tabela dos cenários. O CDR de equilíbrio é o maior CDR anual "
        "em que a classe ainda não perde principal, com o resto do cenário base."
    )
    pdf.tabela_de_texto(*_tabela_do_equilibrio(estrutura, colunas))


def _secao_das_regras_ligadas(
    pdf: RelatorioPDF,
    carteira: Carteira,
    comparada: Estrutura,
    resultados: list[ResultadoDoCenario],
) -> None:
    """Os mesmos cenários, a mesma carteira e as mesmas classes, só com as regras trocadas."""
    ligados = rodar_cenarios(carteira, comparada, tuple(r.cenario for r in resultados))
    pdf.secao(TITULO_DAS_REGRAS_LIGADAS, numerada=True, reservar=60)
    pdf.paragrafo(
        "Mesma carteira, mesmas classes e mesmos cenários; só as regras da cascata mudam. "
        f"SHA-256 desta entrada: {hash_da_entrada(carteira, comparada)}."
    )
    pdf.paragrafo(descrever_regras(comparada.regras))
    pdf.tabela_de_texto(*_tabela_dos_cenarios(comparada, ligados))
    pdf.paragrafo("Reconciliação do caixa com as regras ligadas:")
    pdf.tabela_de_texto(*_tabela_da_reconciliacao(ligados))
