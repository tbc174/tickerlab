"""Roda a ficha C-1 (carteira combinada das camadas) contra o critério do pré-registro quant v0.2.

    python -m trader.estrategias.rodar_c1

**Cada execução conta como duas tentativas** no registro `pesquisa_quant/registro.db` (orçamento da
ficha: 6): a candidata (as seis camadas que operam) e a comparação (as três de maior Sharpe, lista
escolhida olhando o resultado). As duas são registradas **antes** de qualquer conta. Depois, cada
camada roda de novo (`camadas_da_combinada`) e precisa reproduzir o Sharpe do excesso gravado na
linha dela; se uma não reproduzir, a rodada para ali e fica gravada como defeito (seção 9).

Os vizinhos do platô (A3: ±20% na janela da σ, no teto e na banda), o estresse (camadas e troca com
custos × 2 e Y = 2), o bruto, as réguas (60/40 e CDI), as verificações e os testes do Brasil ficam
dentro da tentativa de cada carteira. Só com dados até o fim do desenvolvimento.

Convenções desta rodada, fixadas antes dos números:

- **Calendário:** os pregões da B3 (`trader.calendario`) do primeiro ao último dia das camadas. Cada
  camada recebe o freio de 40% no calendário dela e depois vai aos pregões por `compor_no_pregao` (a
  cripto compõe o fim de semana na segunda; um pregão sem dado da camada rende o CDI).
- **Período comum das leituras:** vizinhos, estresse e bruto são medidos no período da carteira
  (do primeiro pregão avaliado ao fim), com CDI nos dias em que a leitura ainda não começou.
- **A6:** os pesos diários da carteira deslocados no tempo (`carteira_rp.p_valor_do_acaso`), com o
  custo à vista por lado da troca.
- **Teste (b):** correlação dos excessos mensais entre as camadas, e por ano a correlação média dos
  excessos diários contra o ganho de Sharpe (C-1 menos a média das camadas no ano).
- **Teste (c):** aproximação marcada a mercado: o resultado mensal de cada camada de bolsa (peso ×
  retorno) como se fosse realizado; imposto sem compensar (15% do lucro de cada camada) contra
  compensando entre as camadas de bolsa, com o prejuízo levado adiante. Só medida.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from trader import avaliacao, calendario, criterio_quant, freios
from trader.criterio import Veredito
from trader.custos_br import PADRAO, CustosBR
from trader.estrategias import camadas_da_combinada as cdc
from trader.estrategias import combinada, dados_congelados, dados_p0_3
from trader.estrategias.carteira_rp import p_valor_do_acaso
from trader.holdout import FIM_DO_DESENVOLVIMENTO, exigir_sem_holdout
from trader.registro import Registro

PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
FICHA = "C-1"
CANDIDATA = "c1_candidata"
COMPARACAO = "c1_comparacao"
CARTEIRAS = {
    CANDIDATA: combinada.CAMADAS_DA_CANDIDATA,
    COMPARACAO: combinada.CAMADAS_DA_COMPARACAO,
}
NOMES = {
    CANDIDATA: "candidata (as seis camadas que operam)",
    COMPARACAO: "comparação (as três de maior Sharpe; escolhida olhando o resultado)",
}
VERSOES = ("base", "estresse", "bruto")
FRACAO_DO_CORTE = 0.7  # V (4): corta o futuro em 70% dos dias
IR_DA_BOLSA = PADRAO.ir_swing
CUSTOS_NO_ESTRESSE = PADRAO.em_estresse(criterio_quant.FATOR_DE_IMPACTO_NO_ESTRESSE)

abrir_registro = criterio_quant.abrir_registro


@dataclass(frozen=True)
class Preparadas:
    """As camadas freadas e no calendário dos pregões, nas três versões."""

    tabelas: dict[str, pd.DataFrame]  # versão -> uma coluna por camada
    cdi: pd.Series  # CDI nos pregões
    regua_60_40: pd.Series
    freios: dict[str, dict]  # disparos e voltas do freio da base de cada camada
    dados_conforme: bool


def _excesso(retorno: pd.Series, cdi: pd.Series) -> pd.Series:
    return retorno - cdi.reindex(retorno.index)


def sharpe_do_excesso(retorno: pd.Series, cdi: pd.Series) -> float:
    return avaliacao.sharpe(_excesso(retorno, cdi))


def pregoes_das(camadas: cdc.Camadas) -> pd.DatetimeIndex:
    inicio = min(c.base.dropna().index.min() for c in camadas.camadas.values())
    fim = max(c.base.dropna().index.max() for c in camadas.camadas.values())
    return pd.DatetimeIndex(calendario.pregoes(inicio.date(), fim.date()))


def no_pregao(serie: pd.Series, cdi: pd.Series, pregoes: pd.DatetimeIndex) -> pd.Series:
    """A série freada no calendário da camada, levada aos pregões da B3."""
    freada = combinada.serie_freada(serie, cdi).dropna()
    return combinada.compor_no_pregao(freada, pregoes)


def preparar(
    camadas: cdc.Camadas,
    cdi: pd.Series,
    pregoes: pd.DatetimeIndex | None = None,
) -> Preparadas:
    pregoes = pregoes if pregoes is not None else pregoes_das(camadas)
    tabelas = {
        versao: pd.DataFrame(
            {
                nome: no_pregao(getattr(c, versao), c.cdi, pregoes)
                for nome, c in camadas.camadas.items()
            },
            index=pregoes,
        )
        for versao in VERSOES
    }
    disparos = {}
    for nome, c in camadas.camadas.items():
        freio = combinada.freio_da_camada(c.base, c.cdi)
        disparos[nome] = _resumo_do_freio(freio)
    return Preparadas(
        tabelas=tabelas,
        cdi=cdi.reindex(pregoes),
        regua_60_40=camadas.regua_60_40,
        freios=disparos,
        dados_conforme=all(c.conforme for c in camadas.camadas.values()),
    )


def _resumo_do_freio(freio: freios.Freio | None) -> dict:
    if freio is None:
        return {"disparos": [], "voltas": []}
    return {
        "disparos": [d.date().isoformat() for d in freio.disparos],
        "voltas": [d.date().isoformat() for d in freio.voltas],
    }


def _no_periodo(retorno: pd.Series, periodo: pd.Index, cdi: pd.Series) -> pd.Series:
    return retorno.reindex(periodo).fillna(cdi.reindex(periodo))


def _cdi_em_tudo(tabela: pd.DataFrame, cdi: pd.Series) -> pd.DataFrame:
    """Os dias sem retorno da camada rendem o CDI (como em `combinada.combinar`)."""
    caixa = pd.DataFrame({nome: cdi.reindex(tabela.index) for nome in tabela.columns})
    return tabela.fillna(caixa)


def cortar_o_futuro_nao_muda_o_passado(
    tabela: pd.DataFrame, cdi: pd.Series, parametros: combinada.ParametrosC1
) -> bool:
    inteiro = combinada.combinar(tabela, cdi, parametros)
    corte = tabela.index[int(len(tabela) * FRACAO_DO_CORTE)]
    cortado = combinada.combinar(tabela.loc[:corte], cdi, parametros)
    comum = cortado.retorno.index[:-1]  # o último dia do corte não tem D+1 para decidir
    return bool(
        np.allclose(
            inteiro.retorno.loc[comum].to_numpy(),
            cortado.retorno.loc[comum].to_numpy(),
            rtol=0,
            atol=1e-12,
        )
    )


def correlacao_e_ganho(
    tabela: pd.DataFrame, resultado: combinada.ResultadoC1, cdi: pd.Series
) -> dict:
    """Teste (b): correlação entre as camadas contra o ganho de Sharpe da combinação."""
    periodo = resultado.retorno.index
    excesso = tabela.reindex(periodo).sub(cdi.reindex(periodo), axis=0)
    mensal = (1 + excesso.fillna(0.0)).groupby(periodo.to_period("M")).prod() - 1
    matriz = mensal.corr()
    por_ano = {}
    excesso_c1 = _excesso(resultado.retorno, cdi)
    for ano, trecho in excesso.groupby(periodo.year):
        ativas = trecho.dropna(axis=1, how="all")
        pares_de_camadas = list(combinations(ativas.columns, 2))
        correlacoes = [ativas[a].corr(ativas[b]) for a, b in pares_de_camadas]
        sharpes = [avaliacao.sharpe(ativas[n]) for n in ativas.columns]
        sharpes = [s for s in sharpes if np.isfinite(s)]
        sharpe_c1 = avaliacao.sharpe(excesso_c1[excesso_c1.index.year == ano])
        media = float(np.mean(sharpes)) if sharpes else float("nan")
        por_ano[int(ano)] = {
            "correlacao_media": float(np.nanmean(correlacoes))
            if correlacoes
            else float("nan"),
            "sharpe_da_c1": sharpe_c1,
            "sharpe_medio_das_camadas": media,
            "ganho": sharpe_c1 - media,
        }
    return {
        "correlacao_mensal": {
            a: {b: float(matriz.loc[a, b]) for b in matriz.columns}
            for a in matriz.index
        },
        "por_ano": por_ano,
    }


def imposto_compensado(
    tabela: pd.DataFrame,
    resultado: combinada.ResultadoC1,
    camadas_de_bolsa: tuple[str, ...],
    ir: float = IR_DA_BOLSA,
) -> dict:
    """Teste (c), aproximação marcada a mercado: o IR por ano sem compensar e compensando.

    O resultado mensal de cada camada de bolsa (peso do dia × retorno do dia, somado no mês) faz o
    papel do lucro realizado. Sem compensar: 15% do lucro de cada camada, camada por camada.
    Compensando: 15% da soma das camadas no mês, com o prejuízo levado para os meses seguintes.
    """
    periodo = resultado.retorno.index
    bolsa = [n for n in camadas_de_bolsa if n in tabela.columns]
    contribuicao = (resultado.pesos[bolsa] * tabela.reindex(periodo)[bolsa]).fillna(0.0)
    mensal = contribuicao.groupby(periodo.to_period("M")).sum()
    sem_compensar = (mensal.clip(lower=0.0) * ir).sum(axis=1)
    compensando = []
    prejuizo = 0.0
    for total in mensal.sum(axis=1):
        base = total - prejuizo
        if base > 0:
            compensando.append(base * ir)
            prejuizo = 0.0
        else:
            compensando.append(0.0)
            prejuizo = -base
    compensado = pd.Series(compensando, index=mensal.index)
    troca = resultado.imposto.groupby(periodo.year).sum()
    anos = sorted({p.year for p in mensal.index})
    return {
        int(ano): {
            "sem_compensar": float(
                sem_compensar[sem_compensar.index.year == ano].sum()
            ),
            "compensando": float(compensado[compensado.index.year == ano].sum()),
            "ir_da_troca_da_c1": float(troca.get(ano, 0.0)),
        }
        for ano in anos
    }


def _nome_do_vizinho(p: combinada.ParametrosC1) -> str:
    base = combinada.ParametrosC1()
    for campo in ("janela", "teto", "banda"):
        valor = getattr(p, campo)
        if valor != getattr(base, campo):
            return f"{campo}_{valor:g}"
    return "base"


def resumo(resultado: combinada.ResultadoC1, cdi: pd.Series) -> dict:
    pesos = resultado.pesos
    return {
        **avaliacao.resumir_serie(resultado.retorno),
        "sharpe_do_excesso": sharpe_do_excesso(resultado.retorno, cdi),
        "custo": float(resultado.custo.sum()),
        "imposto": float(resultado.imposto.sum()),
        "rebalanceamentos": len(resultado.decisoes),
        "pesos_medios": {n: float(pesos[n].mean()) for n in pesos.columns},
        "caixa_medio": float((1 - pesos.sum(axis=1)).mean()),
    }


def avaliar_carteira(
    nome: str,
    preparadas: Preparadas,
    tentativas_totais: int,
) -> tuple[Veredito, dict]:
    """Toda a evidência de uma carteira (candidata ou comparação) e o veredito dela."""
    camadas = list(CARTEIRAS[nome])
    cdi = preparadas.cdi
    base = preparadas.tabelas["base"][camadas]
    parametros = combinada.ParametrosC1()

    def rodar(
        tabela: pd.DataFrame,
        p: combinada.ParametrosC1 = parametros,
        custos: CustosBR = PADRAO,
    ) -> combinada.ResultadoC1:
        return combinada.combinar(tabela, cdi, p, custos)

    candidato = rodar(base)
    periodo = candidato.retorno.index
    cdi_do_periodo = cdi.reindex(periodo)

    def serie(resultado: combinada.ResultadoC1) -> pd.Series:
        return _no_periodo(resultado.retorno, periodo, cdi)

    vizinhas = {
        _nome_do_vizinho(p): rodar(base, p) for p in combinada.variacoes_do_plato()
    }
    estresse_das_camadas = preparadas.tabelas["estresse"][camadas]
    estresse = {
        nome: rodar(estresse_das_camadas, custos=CUSTOS_NO_ESTRESSE),
        **{
            _nome_do_vizinho(p): rodar(estresse_das_camadas, p, CUSTOS_NO_ESTRESSE)
            for p in combinada.variacoes_do_plato()
        },
    }
    bruto = rodar(
        preparadas.tabelas["bruto"][camadas], custos=combinada.SEM_CUSTOS_DA_TROCA
    )
    futuro = rodar(base, replace(parametros, olhar_o_futuro=True))
    de_novo = rodar(base)
    sem_cripto = rodar(
        base[[c for c in camadas if c not in combinada.CAMADAS_DE_CRIPTO]]
    )
    acaso = p_valor_do_acaso(
        candidato.pesos.shift(-1).fillna(0.0),  # o peso do fechamento de D rende D+1
        _cdi_em_tudo(base, cdi),
        cdi,
        PADRAO.emolumentos_a_vista,
        sorteios=criterio_quant.SINAIS_DESLOCADOS,
    )
    reguas = {
        "60/40": preparadas.regua_60_40.reindex(periodo).dropna(),
        "CDI": cdi_do_periodo,
    }
    evidencia = criterio_quant.Evidencia(
        candidato=candidato.retorno,
        cdi=cdi_do_periodo,
        candidatos=pd.DataFrame(
            {nome: candidato.retorno, **{n: serie(r) for n, r in vizinhas.items()}}
        ),
        candidatos_estresse=pd.DataFrame({n: serie(r) for n, r in estresse.items()}),
        sharpe_bruto=sharpe_do_excesso(serie(bruto), cdi),
        sharpes_vizinhos={
            n: sharpe_do_excesso(serie(r), cdi) for n, r in vizinhas.items()
        },
        reguas=reguas,
        p_valor_do_acaso=acaso["p_valor"],
        sharpe_olhando_o_futuro=sharpe_do_excesso(serie(futuro), cdi),
        reexecucao_identica=combinada.hash_do_resultado(de_novo)
        == combinada.hash_do_resultado(candidato),
        cortar_o_futuro_nao_muda=cortar_o_futuro_nao_muda_o_passado(
            base, cdi, parametros
        ),
        tentativas_totais=tentativas_totais,
        nome_do_candidato=nome,
        dados_conforme=preparadas.dados_conforme,
    )
    veredito = criterio_quant.avaliar(evidencia)
    camadas_de_bolsa = tuple(c for c in camadas if c not in combinada.CAMADAS_DE_CRIPTO)
    saida = {
        "camadas": camadas,
        "resumo": resumo(candidato, cdi),
        "estresse": resumo(estresse[nome], cdi),
        "bruto": resumo(bruto, cdi),
        "vizinhos": {n: resumo(r, cdi) for n, r in vizinhas.items()},
        "futuro": resumo(futuro, cdi),
        "reguas": {n: avaliacao.resumir_serie(r) for n, r in reguas.items()},
        "camadas_no_periodo": {
            c: {
                "sharpe_do_excesso": sharpe_do_excesso(base[c].dropna(), cdi),
                "maior_queda": avaliacao.maior_queda(base[c].reindex(periodo)),
                "pregoes_sem_dado": int(
                    base[c].loc[base[c].first_valid_index() :].isna().sum()
                ),
            }
            for c in camadas
        },
        "brasil": {
            "sem_cripto": resumo(sem_cripto, cdi),
            "correlacao": correlacao_e_ganho(base, candidato, cdi),
            "imposto": imposto_compensado(base, candidato, camadas_de_bolsa),
        },
        "acaso": acaso,
        "decisoes": [d.date().isoformat() for d in candidato.decisoes],
        "periodo": (periodo.min().date().isoformat(), periodo.max().date().isoformat()),
        "hash": combinada.hash_do_resultado(candidato),
    }
    return veredito, saida


def especificacao(nome: str, fim: date, marca_dos_dados: str | None = None) -> dict:
    return {
        "pesquisa": FICHA,
        "pre_registro": criterio_quant.HASH_DO_CRITERIO,
        "versao_do_codigo": combinada.VERSAO,
        "camadas": list(CARTEIRAS[nome]),
        "linhas_das_camadas": {c: cdc.REGISTRADO[c].linha for c in CARTEIRAS[nome]},
        "parametros": asdict(combinada.ParametrosC1()),
        "fim": fim.isoformat(),
        **({} if marca_dos_dados is None else {"dados": marca_dos_dados}),
    }


def executar(
    carregar: Callable[[], tuple[cdc.Camadas, pd.Series]],
    registro: Registro,
    pregoes: pd.DatetimeIndex | None = None,
    marca_dos_dados: str | None = None,
) -> dict:
    """Registra as duas tentativas, confere as camadas, avalia as duas carteiras e grava.

    `carregar` devolve as camadas e o CDI diário (pregões); só é chamado depois do registro, porque
    reproduzir as camadas já faz parte da rodada (seção 9).
    """
    criterio_quant.conferir()
    fim = FIM_DO_DESENVOLVIMENTO.date()
    ids = {
        nome: registro.registrar(FICHA, nome, especificacao(nome, fim, marca_dos_dados))
        for nome in CARTEIRAS
    }
    camadas, cdi = carregar()
    reproducao = {
        nome: {
            "linha": cdc.REGISTRADO[nome].linha,
            "gravado": cdc.REGISTRADO[nome].sharpe,
            "reexecucao": c.sharpe,
            "reproduz": cdc.reproduz(c),
            "hash_da_serie": cdc.hash_da_serie(c),
        }
        for nome, c in camadas.camadas.items()
    }
    if not all(r["reproduz"] for r in reproducao.values()):
        defeito = {
            "defeito": "uma camada não reproduziu o registro; a rodada parou (seção 9)",
            "reproducao": reproducao,
        }
        for tentativa in ids.values():
            registro.salvar_resultado(tentativa, defeito)
        return {"ids": ids, **defeito}
    preparadas = preparar(camadas, cdi, pregoes)
    for tabela in preparadas.tabelas.values():
        exigir_sem_holdout(tabela)
    tentativas_totais = (
        criterio_quant.tentativas_anteriores() + registro.total_para_o_dsr()
    )
    carteiras = {}
    for nome, tentativa in ids.items():
        veredito, saida = avaliar_carteira(nome, preparadas, tentativas_totais)
        registro.salvar_resultado(
            tentativa,
            {
                "veredito": veredito.para_registro(),
                **{k: v for k, v in saida.items() if k != "periodo"},
                "reproducao": reproducao,
                "freios": preparadas.freios,
                "tentativas_totais": tentativas_totais,
            },
        )
        carteiras[nome] = {"veredito": veredito, **saida}
    return {
        "ids": ids,
        "reproducao": reproducao,
        "freios": preparadas.freios,
        "tentativas_totais": tentativas_totais,
        "carteiras": carteiras,
    }


def carregar_do_desenvolvimento() -> tuple[cdc.Camadas, pd.Series]:
    """As camadas da main e o CDI por pregão de 2009 ao fim do desenvolvimento."""
    camadas = cdc.montar()
    fim = FIM_DO_DESENVOLVIMENTO
    inicio = min(c.base.dropna().index.min() for c in camadas.camadas.values())
    cdi = dados_p0_3.carregar_cdi(inicio, fim, PASTA_DA_PESQUISA)
    exigir_sem_holdout(cdi)
    return camadas, cdi


def _numero(valor: float | None, formato: str = ".2f") -> str:
    if valor is None or not np.isfinite(valor):
        return "-"
    return format(valor, formato)


def _linha(nome: str, r: dict) -> str:
    return (
        f"| {nome} | {_numero(r.get('sharpe_do_excesso'))} | {_numero(r.get('retorno_anual'), '.1%')} | "
        f"{_numero(r.get('volatilidade_anual'), '.1%')} | {_numero(r.get('maior_queda'), '.1%')} | "
        f"{_numero(r.get('custo'), '.2%')} | {_numero(r.get('imposto'), '.2%')} |"
    )


CABECALHO = (
    "| Leitura | Sharpe do excesso | Retorno anual | Volatilidade | Maior queda | Custo da troca | IR da troca |\n"
    "|---|---|---|---|---|---|---|"
)


def escrever_relatorio(
    saida: dict, pasta: Path = PASTA_DA_PESQUISA / "relatorios"
) -> Path:
    linhas = [
        f"# Ficha C-1: rodada do pré-registro quant v{criterio_quant.VERSAO}",
        "",
        f"Gerado em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC. Registro: linhas {saida['ids']}.",
        "",
        "## Reprodução das camadas",
        "",
        "| Camada | Linha | Gravado | Reexecução | Reproduz |",
        "|---|---|---|---|---|",
        *(
            f"| {n} | {r['linha']} | {r['gravado']:.4f} | {r['reexecucao']:.4f} | {'sim' if r['reproduz'] else 'NÃO'} |"
            for n, r in saida["reproducao"].items()
        ),
        "",
    ]
    if "defeito" in saida:
        linhas += [f"**DEFEITO:** {saida['defeito']}", ""]
    for nome, c in saida.get("carteiras", {}).items():
        v: Veredito = c["veredito"]
        inicio, fim = c["periodo"]
        linhas += [
            f"## {NOMES[nome]}: {'APROVADA' if v.aprovado else 'REPROVADA'}"
            + (f" (falhou em {', '.join(v.reprovados)})" if v.reprovados else ""),
            "",
            f"Período avaliado: {inicio} a {fim}. Tentativas no DSR: {saida['tentativas_totais']}.",
            "",
            "| Item | O quê | Valor | Limite | Passou |",
            "|---|---|---|---|---|",
            *(
                f"| {i.codigo} | {i.descricao} | {_numero(i.valor, '.3f')} | {i.limite} | {'sim' if i.passou else 'NÃO'} |"
                for i in v.itens
            ),
            "",
            CABECALHO,
            _linha("carteira", c["resumo"]),
            _linha("estresse", c["estresse"]),
            _linha("bruto", c["bruto"]),
            _linha("sem a cripto (teste a)", c["brasil"]["sem_cripto"]),
            *(_linha(f"vizinho {n}", r) for n, r in c["vizinhos"].items()),
            "",
            "Pesos médios: "
            + ", ".join(f"{n} {p:.0%}" for n, p in c["resumo"]["pesos_medios"].items())
            + f"; caixa {c['resumo']['caixa_medio']:.0%}.",
            "",
        ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_c1_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    marca = dados_congelados.congelar_hoje()
    saida = executar(
        carregar_do_desenvolvimento, abrir_registro(), marca_dos_dados=marca
    )
    dados_congelados.exigir_a_mesma_marca(marca)
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0 if "defeito" not in saida else 1


if __name__ == "__main__":
    sys.exit(main())
