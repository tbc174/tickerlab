"""O que cada tela do painel mostra, lido dos arquivos da pesquisa (sem nada de Qt, fácil de testar).

Tudo aqui só LÊ. Os caminhos partem de `raiz` (o repositório), para os testes usarem pastas
temporárias.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader import armazem, avaliacao
from trader.holdout import (
    FIM_DO_DESENVOLVIMENTO,
    FIM_DO_HOLDOUT,
    INICIO_DO_HOLDOUT,
    NOME_DA_INVALIDACAO,
    NOME_DO_LACRE,
)
from trader.registro import ORCAMENTO_DE_TENTATIVAS, Registro

RAIZ = Path(__file__).resolve().parents[2]
DIAS_PARA_DADOS_VELHOS = 7
DIAS_UTEIS_PARA_BOLETIM_VELHO = 3
DIAS_PARA_JUROS_VELHOS = 30


@dataclass(frozen=True)
class Frescor:
    fonte: str
    atualizado_em: pd.Timestamp | None
    detalhe: str
    velho: bool


@dataclass(frozen=True)
class Alerta:
    nivel: str  # "atencao" ou "critico"
    texto: str
    acao: str  # o que fazer, em português claro


def _local(momento: pd.Timestamp) -> pd.Timestamp:
    """Horário local sem fuso (o registro guarda em UTC)."""
    if momento.tzinfo is None:
        return momento
    return momento.tz_convert(datetime.now(UTC).astimezone().tzinfo).tz_localize(None)


def _mtime(caminho: Path) -> pd.Timestamp | None:
    if not caminho.exists():
        return None
    return _local(pd.Timestamp(datetime.fromtimestamp(caminho.stat().st_mtime, tz=UTC)))


class Fontes:
    def __init__(self, raiz: Path = RAIZ, agora: pd.Timestamp | None = None) -> None:
        self.raiz = Path(raiz)
        self.pasta_mt5 = self.raiz / "dados_mt5"
        self.pasta_b3 = self.raiz / "dados_b3" / "futuros"
        self.arquivo_juros = self.raiz / "dados_juros" / "taxas_basicas.parquet"
        self.pasta_pesquisa = self.raiz / "pesquisa_m2"
        self.pasta_series = self.pasta_pesquisa / "series"
        self.pasta_relatorios = self.pasta_pesquisa / "relatorios"
        self._agora = agora

    @property
    def agora(self) -> pd.Timestamp:
        return self._agora if self._agora is not None else pd.Timestamp.now()

    # --- pesquisa -------------------------------------------------------------------------
    def registro(self) -> Registro:
        return Registro(self.pasta_pesquisa / "registro.db")

    def tentativas(self) -> pd.DataFrame:
        """Uma linha por tentativa do desenvolvimento, com o veredito resumido."""
        registro = self.registro()
        linhas = []
        for t in registro.listar("desenvolvimento"):
            dados = registro.obter(t["id"])
            resultado = dados["resultado"] or {}
            sharpe, t_est = np.nan, np.nan
            if "itens" in resultado:
                veredito = "aprovado" if resultado.get("aprovado") else "reprovado"
                sharpes = resultado.get("sharpes_dos_caminhos") or []
                sharpe = float(np.nanmedian(sharpes)) if sharpes else np.nan
                t_est = next(
                    (i["valor"] for i in resultado["itens"] if i["codigo"] == "A3"),
                    np.nan,
                )
            elif "carteira" in resultado:
                veredito = "régua"
                sharpe = resultado["carteira"]["x1"]["sharpe"]
                t_est = resultado["carteira"]["x1"]["t"]
            else:
                veredito = "sem resultado"
            linhas.append(
                {
                    "id": t["id"],
                    "familia": t["familia"],
                    "nome": t["nome"],
                    "criada_em": _local(pd.Timestamp(t["criada_em"])),
                    "veredito": veredito,
                    "sharpe": sharpe,
                    "t": t_est,
                    "reprovados": ", ".join(resultado.get("reprovados", [])),
                    "execucoes": t["execucoes"],
                }
            )
        colunas = [
            "id",
            "familia",
            "nome",
            "criada_em",
            "veredito",
            "sharpe",
            "t",
            "reprovados",
            "execucoes",
        ]
        return pd.DataFrame(linhas, columns=colunas).sort_values("id", ascending=False)

    def detalhe_da_tentativa(self, tentativa_id: int) -> dict:
        dados = self.registro().obter(tentativa_id)
        serie = None
        with contextlib.suppress(FileNotFoundError):
            serie = armazem.carregar(dados["hash"], self.pasta_series)
        return {**dados, "serie": serie}

    def contagem(self) -> dict:
        registro = self.registro()
        total = registro.total_para_o_dsr()
        return {
            "total": total,
            "orcamento": ORCAMENTO_DE_TENTATIVAS,
            "restante": ORCAMENTO_DE_TENTATIVAS - total,
            "holdout": registro.contar("holdout"),
        }

    def holdout(self) -> dict:
        lacrado = (self.pasta_pesquisa / NOME_DO_LACRE).exists()
        invalidado = (self.pasta_pesquisa / NOME_DA_INVALIDACAO).exists()
        if invalidado:
            estado, texto = "critico", "invalidado (destrancado)"
        elif lacrado:
            estado, texto = "atencao", "já pontuado (lacrado)"
        else:
            estado, texto = "bom", "intacto (nunca lido)"
        return {
            "estado": estado,
            "texto": texto,
            "periodo": f"{INICIO_DO_HOLDOUT:%d/%m/%Y} a {FIM_DO_HOLDOUT:%d/%m/%Y}",
            "fim_do_desenvolvimento": f"{FIM_DO_DESENVOLVIMENTO:%d/%m/%Y}",
        }

    # --- baselines ------------------------------------------------------------------------
    def baseline(self, nome: str) -> pd.DataFrame | None:
        try:
            return armazem.carregar(f"baseline_{nome}", self.pasta_series)
        except FileNotFoundError:
            return None

    def curvas_das_baselines(self) -> dict[str, pd.Series]:
        """Curva de capital (começa em 1) de B0, B1 e B2, custos ×1."""
        curvas = {}
        for nome in ("B0", "B1", "B2"):
            tabela = self.baseline(nome)
            if tabela is not None:
                curvas[nome] = (1 + tabela["x1"].fillna(0)).cumprod()
        return curvas

    def resumo_das_baselines(self) -> pd.DataFrame:
        linhas = []
        for nome in ("B0", "B1", "B2"):
            tabela = self.baseline(nome)
            if tabela is None:
                continue
            x1 = avaliacao.resumir_serie(tabela["x1"])
            linhas.append(
                {
                    "baseline": nome,
                    "sharpe": x1["sharpe"],
                    "sharpe_x2": avaliacao.sharpe(tabela["x2"]),
                    "t": x1["t"],
                    "retorno_anual": x1["retorno_anual"],
                    "volatilidade_anual": x1["volatilidade_anual"],
                    "maior_queda": x1["maior_queda"],
                    "anos_positivos": x1["anos_positivos"],
                }
            )
        colunas = [
            "baseline",
            "sharpe",
            "sharpe_x2",
            "t",
            "retorno_anual",
            "volatilidade_anual",
            "maior_queda",
            "anos_positivos",
        ]
        return pd.DataFrame(linhas, columns=colunas)  # vazio continua com as colunas

    def baselines_por_ativo(self) -> pd.DataFrame:
        caminho = self.pasta_relatorios / "baselines_por_ativo.csv"
        return pd.read_csv(caminho) if caminho.exists() else pd.DataFrame()

    def viabilidade(self) -> tuple[pd.DataFrame, dict]:
        tabela = self.pasta_relatorios / "viabilidade.csv"
        resumo = self.pasta_relatorios / "viabilidade_resumo.json"
        return (
            pd.read_csv(tabela) if tabela.exists() else pd.DataFrame(),
            json.loads(resumo.read_text(encoding="utf-8")) if resumo.exists() else {},
        )

    # --- dados ----------------------------------------------------------------------------
    def qualidade(self) -> pd.DataFrame:
        caminho = self.pasta_mt5 / "relatorio_de_qualidade.csv"
        return pd.read_csv(caminho) if caminho.exists() else pd.DataFrame()

    def taxas_de_juro(
        self, moedas: tuple[str, ...] = ("BRL", "USD", "EUR", "JPY")
    ) -> pd.DataFrame:
        if not self.arquivo_juros.exists():
            return pd.DataFrame()
        tabela = pd.read_parquet(self.arquivo_juros).ffill()
        return tabela[[m for m in moedas if m in tabela.columns]]

    def frescor(self) -> list[Frescor]:
        agora = self.agora
        itens = []
        relatorio = self.pasta_mt5 / "relatorio_de_qualidade.csv"
        quando = _mtime(relatorio)
        itens.append(
            Frescor(
                "Histórico (MT5 + yfinance)",
                quando,
                f"{len(self.qualidade())} séries" if quando else "nunca baixado",
                quando is None or (agora - quando).days > DIAS_PARA_DADOS_VELHOS,
            )
        )
        dias_b3 = (
            sorted(self.pasta_b3.glob("*.parquet")) if self.pasta_b3.exists() else []
        )
        ultimo_b3 = pd.Timestamp(dias_b3[-1].stem) if dias_b3 else None
        itens.append(
            Frescor(
                "Boletim da B3",
                ultimo_b3,
                f"{len(dias_b3)} pregões acumulados" if dias_b3 else "nada acumulado",
                ultimo_b3 is None
                or np.busday_count(ultimo_b3.date(), agora.date())
                > DIAS_UTEIS_PARA_BOLETIM_VELHO,
            )
        )
        juros = None
        if self.arquivo_juros.exists():
            juros = pd.read_parquet(self.arquivo_juros).index.max()
        itens.append(
            Frescor(
                "Taxas de juro (BIS)",
                juros,
                "11 moedas" if juros is not None else "nunca baixado",
                juros is None or (agora - juros).days > DIAS_PARA_JUROS_VELHOS,
            )
        )
        return itens

    def alertas(self) -> list[Alerta]:
        """A lista 'o que fazer agora' da tela inicial."""
        alertas = []
        for f in self.frescor():
            if f.atualizado_em is None:
                alertas.append(
                    Alerta(
                        "critico",
                        f"{f.fonte}: nunca baixado.",
                        "Abra Dados e atualize.",
                    )
                )
            elif f.velho:
                alertas.append(
                    Alerta(
                        "atencao",
                        f"{f.fonte}: última atualização em {f.atualizado_em:%d/%m/%Y}.",
                        "Abra Dados e atualize.",
                    )
                )
        if self.baseline("B1") is None:
            alertas.append(
                Alerta(
                    "atencao",
                    "As baselines ainda não foram rodadas.",
                    "Abra Dados e rode as baselines.",
                )
            )
        sem_resultado = self.tentativas().query("veredito == 'sem resultado'")
        if len(sem_resultado):
            ids = ", ".join(f"#{i}" for i in sem_resultado["id"])
            alertas.append(
                Alerta(
                    "atencao",
                    f"Tentativas registradas sem resultado: {ids} (rodada interrompida?).",
                    "Rode a mesma configuração de novo; ela não conta duas vezes.",
                )
            )
        return alertas
