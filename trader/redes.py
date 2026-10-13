"""H4: deep learning (critério v0.2, seção 1). Três redes pequenas, arquitetura fixada antes de rodar.

- **MLP tabular:** os atributos do dia; camadas ocultas de 64 e 32, ReLU, dropout 0,2.
- **LSTM:** os últimos 60 pregões do ativo (os atributos de cada dia, que incluem o retorno dividido
  pela volatilidade); 1 camada de 32 unidades, dropout 0,2.
- **TCN:** a mesma janela de 60 pregões; 3 blocos convolucionais causais de 16 canais (dilatações 1,
  2 e 4; kernel 3, o padrão da arquitetura, que o critério não fixou), dropout 0,2.

Comum às três (seção 1): um modelo para todos os ativos, PyTorch só na CPU, Adam com taxa 1e-3 e
decaimento de peso 1e-4, lotes de 512, no máximo 30 épocas com parada antecipada (paciência 5) numa
validação com os últimos 20% dos dias de treino da divisão e expurgo de 21 pregões antes dela;
semente fixa e algoritmos determinísticos. As entradas são padronizadas só com o treino (como a
logística) e o que falta vira 0 (a média). Sem busca de hiperparâmetros.

A interface é a mesma do pipeline: `ajustar` com as linhas de treino do painel e `prever` com as
linhas pedidas. `contexto` traz o dia de cada linha (`dias`, posição no calendário de dias úteis) e,
para LSTM e TCN, a janela de linhas de cada linha (`janelas`, −1 onde a janela passa do começo).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn

TIPOS = ("mlp", "lstm", "tcn")
SEQUENCIAIS = ("lstm", "tcn")
JANELA = 60
COMUM = {
    "otimizador": "adam",
    "taxa": 1e-3,
    "decaimento_de_peso": 1e-4,
    "lote": 512,
    "epocas_max": 30,
    "paciencia": 5,
    "validacao": 0.20,
    "expurgo_da_validacao": 21,
    "dropout": 0.2,
    "dispositivo": "cpu",
}
PADROES: dict[str, dict[str, Any]] = {
    "mlp": {**COMUM, "camadas": [64, 32]},
    "lstm": {**COMUM, "janela": JANELA, "unidades": 32, "camadas_lstm": 1},
    "tcn": {
        **COMUM,
        "janela": JANELA,
        "canais": 16,
        "dilatacoes": [1, 2, 4],
        "kernel": 3,
    },
}


class _MLP(nn.Module):
    def __init__(self, entradas: int, camadas: list[int], dropout: float) -> None:
        super().__init__()
        partes: list[nn.Module] = []
        anterior = entradas
        for largura in camadas:
            partes += [nn.Linear(anterior, largura), nn.ReLU(), nn.Dropout(dropout)]
            anterior = largura
        partes.append(nn.Linear(anterior, 1))
        self.rede = nn.Sequential(*partes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.rede(x).squeeze(-1)


class _LSTM(nn.Module):
    def __init__(self, entradas: int, unidades: int, dropout: float) -> None:
        super().__init__()
        self.lstm = nn.LSTM(entradas, unidades, batch_first=True)
        self.saida = nn.Sequential(nn.Dropout(dropout), nn.Linear(unidades, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: (lote, janela, atributos)
        _, (h, _) = self.lstm(x)
        return self.saida(h[-1]).squeeze(-1)


class _BlocoCausal(nn.Module):
    """Convolução causal (o dia t só enxerga t e antes) com conexão residual."""

    def __init__(
        self, entrada: int, canais: int, kernel: int, dilatacao: int, dropout: float
    ) -> None:
        super().__init__()
        self.corte = (kernel - 1) * dilatacao
        self.conv = nn.Conv1d(
            entrada, canais, kernel, dilation=dilatacao, padding=self.corte
        )
        self.depois = nn.Sequential(nn.ReLU(), nn.Dropout(dropout))
        self.atalho = (
            nn.Conv1d(entrada, canais, 1) if entrada != canais else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.conv(x)[..., : -self.corte] if self.corte else self.conv(x)
        return self.depois(y) + self.atalho(x)


class _TCN(nn.Module):
    def __init__(
        self,
        entradas: int,
        canais: int,
        dilatacoes: list[int],
        kernel: int,
        dropout: float,
    ) -> None:
        super().__init__()
        blocos = []
        anterior = entradas
        for d in dilatacoes:
            blocos.append(_BlocoCausal(anterior, canais, kernel, d, dropout))
            anterior = canais
        self.blocos = nn.Sequential(*blocos)
        self.saida = nn.Linear(canais, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: (lote, janela, atributos)
        h = self.blocos(x.transpose(1, 2))  # (lote, canais, janela)
        return self.saida(h[:, :, -1]).squeeze(-1)  # o último dia da janela


def parametros(tipo: str, ajustes: dict[str, Any] | None = None) -> dict[str, Any]:
    if tipo not in PADROES:
        raise ValueError(f"Rede desconhecida: {tipo}. Use uma de {TIPOS}.")
    return {**PADROES[tipo], **(ajustes or {})}


def janelas_por_linha(
    linhas_por_ativo: list[np.ndarray], n: int, janela: int = JANELA
) -> np.ndarray:
    """(n × janela): as linhas dos últimos `janela` dias do mesmo ativo, terminando na própria."""
    saida = np.full((n, janela), -1, dtype=np.int64)
    deslocamentos = np.arange(-janela + 1, 1)
    for linhas in linhas_por_ativo:
        posicoes = np.arange(len(linhas))[:, None] + deslocamentos
        saida[linhas] = np.where(posicoes >= 0, linhas[np.clip(posicoes, 0, None)], -1)
    return saida


class Rede:
    """Classificador com `ajustar(x, y_treino, treino, contexto)` e `prever(x, linhas, contexto)`."""

    def __init__(
        self, tipo: str, ajustes: dict[str, Any] | None = None, semente: int = 0
    ) -> None:
        self.tipo = tipo
        self.p = parametros(tipo, ajustes)
        self.semente = semente
        self.media: np.ndarray | None = None
        self.desvio: np.ndarray | None = None
        self.modelo: nn.Module | None = None
        self.epocas_usadas = 0
        self._z: np.ndarray | None = None

    # --- preparo das entradas ---------------------------------------------------------------
    def _padronizado(self, x: np.ndarray) -> np.ndarray:
        """O painel inteiro padronizado com a média e o desvio do treino, NaN → 0, mais uma
        linha de zeros no fim (para onde apontam as janelas que passam do começo)."""
        z = (x - self.media) / self.desvio
        z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        return np.vstack([z, np.zeros((1, z.shape[1]), dtype=np.float32)])

    def _lote(self, z: np.ndarray, linhas: np.ndarray, contexto: dict) -> torch.Tensor:
        if self.tipo in SEQUENCIAIS:
            janelas = contexto["janelas"][linhas]  # −1 cai na linha de zeros do fim
            return torch.from_numpy(z[janelas])
        return torch.from_numpy(z[linhas])

    def _criar(self, entradas: int) -> nn.Module:
        p = self.p
        if self.tipo == "mlp":
            return _MLP(entradas, p["camadas"], p["dropout"])
        if self.tipo == "lstm":
            return _LSTM(entradas, p["unidades"], p["dropout"])
        return _TCN(entradas, p["canais"], p["dilatacoes"], p["kernel"], p["dropout"])

    # --- treino -----------------------------------------------------------------------------
    def ajustar(
        self, x: np.ndarray, y_treino: np.ndarray, treino: np.ndarray, contexto: dict
    ) -> Rede:
        torch.manual_seed(self.semente)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(1)  # cada divisão roda num processo do joblib
        p = self.p
        self.media = np.nanmean(x[treino], axis=0)
        self.desvio = np.nanstd(x[treino], axis=0)
        self.desvio[~(self.desvio > 0)] = 1.0
        z = self._padronizado(x)

        # validação: os últimos 20% dos dias de treino, com expurgo de 21 pregões antes dela
        dias = contexto["dias"][treino]
        unicos = np.unique(dias)
        corte = unicos[int(len(unicos) * (1 - p["validacao"]))]
        na_validacao = dias >= corte
        no_ajuste = dias < corte - p["expurgo_da_validacao"]
        linhas_ajuste, y_ajuste = treino[no_ajuste], y_treino[no_ajuste]
        linhas_val, y_val = treino[na_validacao], y_treino[na_validacao]

        self.modelo = self._criar(x.shape[1])
        otimizador = torch.optim.Adam(
            self.modelo.parameters(),
            lr=p["taxa"],
            weight_decay=p["decaimento_de_peso"],
        )
        perda = nn.BCEWithLogitsLoss()
        sorteio = np.random.default_rng(self.semente)
        y_val_t = torch.from_numpy(y_val.astype(np.float32))
        melhor, melhor_estado, sem_melhora = np.inf, None, 0
        for epoca in range(p["epocas_max"]):
            self.modelo.train()
            ordem = sorteio.permutation(len(linhas_ajuste))
            for inicio in range(0, len(ordem), p["lote"]):
                lote = ordem[inicio : inicio + p["lote"]]
                otimizador.zero_grad()
                saida = self.modelo(self._lote(z, linhas_ajuste[lote], contexto))
                alvo = torch.from_numpy(y_ajuste[lote].astype(np.float32))
                perda(saida, alvo).backward()
                otimizador.step()
            perda_val = float(perda(self._logits(z, linhas_val, contexto), y_val_t))
            if perda_val < melhor - 1e-6:
                melhor, sem_melhora = perda_val, 0
                melhor_estado = {
                    k: v.clone() for k, v in self.modelo.state_dict().items()
                }
                self.epocas_usadas = epoca + 1
            else:
                sem_melhora += 1
                if sem_melhora >= p["paciencia"]:
                    break
        if melhor_estado is not None:
            self.modelo.load_state_dict(melhor_estado)
        self._z = z
        return self

    # --- previsão ---------------------------------------------------------------------------
    def _logits(
        self, z: np.ndarray, linhas: np.ndarray, contexto: dict
    ) -> torch.Tensor:
        self.modelo.eval()
        with torch.no_grad():
            partes = [
                self.modelo(self._lote(z, linhas[inicio : inicio + 4096], contexto))
                for inicio in range(0, len(linhas), 4096)
            ]
        return torch.cat(partes) if partes else torch.zeros(0)

    def prever(self, x: np.ndarray, linhas: np.ndarray, contexto: dict) -> np.ndarray:
        """Probabilidade de "sobe" nas linhas pedidas (o painel `x` é o mesmo do ajuste)."""
        z = (
            self._z
            if self._z is not None and self._z.shape[0] == x.shape[0] + 1
            else self._padronizado(x)
        )
        return torch.sigmoid(self._logits(z, linhas, contexto)).numpy().astype(float)
