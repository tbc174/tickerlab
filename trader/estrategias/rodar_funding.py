"""Roda a ficha P0-6 (monitor de funding e basis em cripto): `python -m trader.estrategias.rodar_funding`.

Coleta (só os dados aprovados: funding e prêmio da Binance, cupom cambial da B3 e CDI), registra a tentativa
antes de calcular qualquer número, monta o monitor dos dois trechos (desenvolvimento e recente, nunca o
holdout) e escreve o relatório fora do Git. Não passa pelo critério da seção 5; orçamento de 2 tentativas
(só reexecução da coleta). Nenhuma ordem: nada aqui fala com uma corretora além de ler dados públicos.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trader import criterio_quant
from trader.custos_br import CustosBR
from trader.estrategias import dados_funding as df
from trader.estrategias import monitor_funding as mf
from trader.estrategias import rodar_p0_3
from trader.holdout import FIM_DO_DESENVOLVIMENTO
from trader.registro import Registro

FICHA = "P0-6"
NOME = "monitor_funding"
TRECHOS = ("desenvolvimento", "recente")
abrir_registro = rodar_p0_3.abrir_registro
PASTA_DOS_RELATORIOS = df.dados_p0_3.PASTA_DA_PESQUISA / "relatorios"


@dataclass
class Dados:
    """O que a coleta trouxe: por trecho e por par, os pagamentos de funding e o prêmio; por trecho, o
    cupom e o CDI."""

    fim: pd.Timestamp
    pagamentos: dict[tuple[str, str], pd.Series] = field(default_factory=dict)
    premio: dict[tuple[str, str], pd.Series] = field(default_factory=dict)
    cupom: dict[str, pd.Series] = field(default_factory=dict)
    cdi: dict[str, pd.Series] = field(default_factory=dict)
    hash_dos_arquivos: str = ""


def coletar(fim: pd.Timestamp, arquivos: df.Arquivos | None = None) -> Dados:
    """Baixa (ou lê da pasta) tudo o que a ficha usa, até a véspera de `fim`."""
    arquivos = arquivos or df.Arquivos()
    dados = Dados(fim=fim)
    meses = df.meses_do_desenvolvimento()
    for par in df.PARES:
        dados.pagamentos["desenvolvimento", par] = df.historico_mensal(
            par, df.FUNDING, arquivos, meses
        )
        dados.premio["desenvolvimento", par] = df.historico_mensal(
            par, df.PREMIO, arquivos, meses
        )
        dados.pagamentos["recente", par] = df.recente_da_api(
            par, df.FUNDING, arquivos, fim
        )
        dados.premio["recente", par] = df.recente_da_api(par, df.PREMIO, arquivos, fim)
    dados.cupom["desenvolvimento"] = df.cupom_do_desenvolvimento(arquivos)
    dados.cupom["recente"] = df.cupom_recente(arquivos, fim)
    primeiro = min(
        s.index.min()
        for (t, _), s in dados.pagamentos.items()
        if t == "desenvolvimento"
    )
    dados.cdi["desenvolvimento"] = df.carregar_cdi(
        pd.Timestamp(primeiro).normalize() - pd.Timedelta(days=10),
        FIM_DO_DESENVOLVIMENTO,
    )
    dados.cdi["recente"] = df.carregar_cdi(df.INICIO_DO_TRECHO_RECENTE, fim)
    dados.hash_dos_arquivos = df.hash_dos_arquivos(arquivos)
    return dados


def especificacao(dados: Dados, custos: CustosBR | None = None) -> dict:
    """O que identifica a tentativa: as definições fixas, as fontes e a impressão digital dos dados."""
    custos = CustosBR() if custos is None else custos
    return {
        "ficha": FICHA,
        "escopo": "coleta e monitor; nenhuma ordem, nenhum backtest; sem critério da seção 5",
        "pares": list(df.PARES),
        "trechos": {
            "desenvolvimento": f"até {FIM_DO_DESENVOLVIMENTO.date()}",
            "recente": f"{df.INICIO_DO_TRECHO_RECENTE.date()} até a véspera de {dados.fim.date()}",
        },
        "definicoes": {
            "funding_do_dia": "soma dos pagamentos no dia de Brasília",
            "anualizado": f"média de {mf.DIAS_DA_MEDIA} dias × {mf.DIAS_NO_ANO}",
            "custo_anualizado": mf.custo_anualizado(custos),
            "ir": custos.ir_cripto,
            "limite_do_funding": mf.LIMITE_DO_FUNDING,
            "carry_em_reais": "funding líquido + CDI − cupom de 30 dias (conhecidos antes do dia)",
            "prazo_do_cupom": df.PRAZO_DO_CUPOM,
            "curva_do_cupom": df.CURVA_DO_CUPOM,
        },
        "fontes": {
            "binance": "data.binance.vision (meses) e fapi/v1 (recente); uso interno, CC BY-NC-SA",
            "b3": "taxas referenciais TSaammdd (curva DOC)",
            "cdi": "SGS 12",
        },
        "hash_dos_arquivos": dados.hash_dos_arquivos,
        "periodos": {
            f"{t}/{par}": [s.index.min().isoformat(), s.index.max().isoformat()]
            for (t, par), s in dados.pagamentos.items()
        },
    }


def montar(
    dados: Dados, custos: CustosBR | None = None
) -> dict[tuple[str, str], pd.DataFrame]:
    return {
        (trecho, par): mf.monitorar(
            dados.pagamentos[trecho, par],
            dados.premio[trecho, par],
            dados.cupom[trecho],
            dados.cdi[trecho],
            custos,
        )
        for trecho in TRECHOS
        for par in df.PARES
    }


def executar(dados: Dados, registro: Registro, custos: CustosBR | None = None) -> dict:
    """Registra a tentativa antes de qualquer número, monta o monitor e guarda no registro."""
    criterio_quant.conferir()
    tentativa = registro.registrar(FICHA, NOME, especificacao(dados, custos))
    tabelas = montar(dados, custos)
    saida = {
        "id": tentativa,
        "custo_anualizado": mf.custo_anualizado(custos),
        "resumos": {f"{t}/{par}": mf.resumir(tab) for (t, par), tab in tabelas.items()},
        "hoje": {par: mf.ultimo_dia(tabelas["recente", par]) for par in df.PARES},
    }
    registro.salvar_resultado(tentativa, saida)
    return saida


# --- o relatório -----------------------------------------------------------------------------------------


def _pct(valor: float | None, casas: int = 1) -> str:
    return "-" if valor is None else f"{valor:.{casas}%}".replace(".", ",")


def _sim(valor: bool) -> str:
    return "**ligado**" if valor else "desligado"


def escrever_relatorio(saida: dict, pasta: Path = PASTA_DOS_RELATORIOS) -> Path:
    linhas = [
        f"# Monitor de funding e basis (P0-6): tentativa {saida['id']}",
        "",
        "Nada aqui é recomendação de investimento; funding passado não garante funding futuro.",
        "",
        f"Custo do carry anualizado (4 pernas, rolagem a cada 30 dias): {_pct(saida['custo_anualizado'], 2)}.",
        "",
        "## Hoje",
        "",
        (
            "| Par | Dia | Funding bruto | Líquido | Alerta 1 (> 10%) | CDI | Cupom 30d | "
            "Carry em reais | Alerta 2 (> CDI) | Basis |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for par, h in saida["hoje"].items():
        linhas.append(
            f"| {par} | {h['dia']} | {_pct(h['funding_bruto'])} | {_pct(h['funding_liquido'])} | "
            f"{_sim(h['alerta_funding'])} | {_pct(h['cdi'])} | {_pct(h['cupom'])} | "
            f"{_pct(h['carry_em_reais'])} | {_sim(h['alerta_carry'])} | {_pct(h['basis'], 3)} |"
        )
    linhas += [
        "",
        "## Quanto tempo cada alerta ficou ligado",
        "",
        (
            "| Trecho / par | Dias | Alerta 1 | Maior sequência | Alerta 2 | Maior sequência | "
            "Líquido p10 / p50 / p90 | Cupom p50 | Basis p50 |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for nome, r in saida["resumos"].items():
        liq = r["funding_liquido"]
        linhas.append(
            f"| {nome} | {r['dias']} | {_pct(r['alerta_funding'], 0)} | {r['maior_sequencia_funding']} | "
            f"{_pct(r['alerta_carry'], 0)} | {r['maior_sequencia_carry']} | "
            f"{_pct(liq['p10'])} / {_pct(liq['p50'])} / {_pct(liq['p90'])} | {_pct(r['cupom']['p50'])} | "
            f"{_pct(r['basis']['p50'], 3)} |"
        )
    linhas += [
        "",
        "## Por ano",
        "",
        "| Trecho / par | Ano | Dias | Líquido mediano | Alerta 1 | Alerta 2 |",
    ]
    linhas.append("|---|---|---|---|---|---|")
    for nome, r in saida["resumos"].items():
        for ano, a in r["por_ano"].items():
            linhas.append(
                f"| {nome} | {ano} | {a['dias']} | {_pct(a['funding_liquido_mediano'])} | "
                f"{_pct(a['alerta_funding'], 0)} | {_pct(a['alerta_carry'], 0)} |"
            )
    linhas += [
        "",
        "## Limites e cuidados",
        "",
        "- Monitor, não estratégia: nenhum backtest, nenhuma ordem e nenhum critério de aprovação (ficha P0-6).",
        "- O holdout (10/10/2023 a 09/10/2026) não foi baixado; os dois trechos são o desenvolvimento e o recente.",
        "- O custo supõe montar e desfazer o carry a cada 30 dias, sem impacto, spread nem margem parada.",
        "- O carry em reais segue a fórmula da ficha; não inclui IOF, câmbio nem o risco da corretora.",
        "- No desenvolvimento o cupom é o do fim do mês anterior (atraso de até um mês); no recente, o da véspera.",
        "- O cupom de 30 dias perto da virada do mês sofre o efeito da PTAX; a curva curta da B3 é ruidosa.",
        "- Binance só para uso interno (CC BY-NC-SA).",
        "- Toda execução conta como tentativa da ficha P0-6 (orçamento 2).",
        "- Nada aqui é recomendação de investimento.",
    ]
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"rodada_funding_{datetime.now(UTC):%Y%m%d_%H%M}.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> int:
    hoje = pd.Timestamp.now(tz=df.FUSO_DE_BRASILIA).normalize().tz_localize(None)
    saida = executar(coletar(hoje), abrir_registro())
    print(escrever_relatorio(saida).read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
