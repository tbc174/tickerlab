"""Monitoramento mensal de FIDC: eventos públicos de subordinação, inadimplência e concentração (B-15).

Parte dos informes mensais que a CVM publica (`base/fidc.py`, tabela `fidc_informe`) e devolve
`EventoDeMonitoramento` em tipos simples (`como_dict` dá JSON): o `MonitoringEvent` do `data_model.md`
no que ele tem de público. `usuario_id` é sempre `None` (evento público, de todos) e o evento só leva
CNPJ e nome do fundo, nunca nome de pessoa.

**Regras** (`REGRAS`, em dados): cada uma diz o campo, o sentido, o limite e a gravidade. São gatilhos
**genéricos de monitoramento**, não o regulamento de cada fundo: o regulamento (subordinação mínima,
gatilho de inadimplência) não está no informe. Por isso a gravidade mais alta se chama `quebra` só no
sentido do limite genérico, e o texto do evento diz qual foi.

- **Subordinação** = patrimônio líquido das classes subordinadas e mezanino ÷ patrimônio líquido das
  classes (quantidade de cotas × valor da cota, quadro X.2). Abaixo do mínimo: evento.
- **Inadimplência** = direitos creditórios vencidos e inadimplentes ÷ carteira de direitos creditórios
  (quadro I). Acima do limite, ou subindo (variação em pontos de fração contra o mês anterior): evento.
- **Concentração** = a maior participação de um cedente na carteira (quadro I, até 9 cedentes). Acima
  do limite: evento. A participação não identifica ninguém: CPF já sai na carga (`base/fidc.py`).

**Como era na data:** `como_era_em` só deixa o que já era público (`disponivel_em`) e, de cada
fundo-mês, a versão mais recente até então. Cortar o futuro não muda o passado (`tests/`).

**Evidência:** cada evento aponta o quadro e o campo do informe, com o valor lido, e leva o `Rastro`
(fórmula, versão do cálculo, fonte, dia em que o informe ficou público).

Limite honesto: fundo sem cota subordinada (ou com a classe zerada) tem subordinação 0 e gera o evento,
que diz só o que o informe mostra, não que o regulamento exija subordinação. O informe é entregue em até 15 dias e a CVM regrava meses passados; um fundo que não
entregou o mês não gera evento aqui (ausência de informe não é sinal de calma): o "não observado" e o
"fonte falhou" estão no evento de PJ (`src/eventos_de_pj/fidc.py`, N5), de que este evento é o caso
"mudou" (`como_evento_de_pj`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

import pandas as pd

from src.eventos_de_pj.evento import MUDOU, EventoDePJ, cnpj_do_objeto
from src.eventos_de_pj.evento import Evidencia as EvidenciaDePJ
from src.rastro import Rastro

VERSAO_DO_CALCULO = "monitoramento_fidc 1"
FONTE = "cvm"
OBJETO_TIPO = "entidade"
FONTE_DO_INFORME = (
    "cvm-fidc"  # o id da coleta do informe mensal (`base/arquivo/fontes.py`)
)
ONDE_DA_REGRA = "regra"  # a evidência que não vem do informe: o valor, o limite e a gravidade da regra
CASAS_DA_RAZAO = 10
TAMANHO_DO_ID = 16  # caracteres do hash que viram o id do evento

Gravidade = Literal["info", "atencao", "quebra"]
ORDEM_DA_GRAVIDADE = {"quebra": 0, "atencao": 1, "info": 2}
Sentido = Literal["abaixo", "acima", "subiu"]

INFORME_I, INFORME_IV, INFORME_X_2 = "tab_I", "tab_IV", "tab_X_2"
CAMPO_CARTEIRA = "TAB_I2_VL_CARTEIRA"
CAMPO_INADIMPLENTE = "TAB_I2A3_VL_CRED_INAD"
CAMPO_PL = "TAB_IV_A_VL_PL"
CAMPO_CLASSE, CAMPO_COTAS, CAMPO_VALOR_COTA = (
    "TAB_X_CLASSE_SERIE",
    "TAB_X_QT_COTA",
    "TAB_X_VL_COTA",
)
PARTICIPACAO_DO_CEDENTE = re.compile(r"_PR_CEDENTE_\d+$")
CLASSE_SUBORDINADA = re.compile(r"subord|mezanin", re.IGNORECASE)
CAMPO_CEDENTE = "maior TAB_I…_PR_CEDENTE_n (%)"
CAMPO_PL_SUBORDINADO = "Σ cotas × valor da cota, classes subordinadas"
CAMPO_PL_CLASSES = "Σ cotas × valor da cota, todas as classes"
PERCENTUAL = 100  # a CVM informa a participação do cedente em %

COLUNAS = (
    "cnpj_fundo",
    "nome",
    "competencia",
    "disponivel_em",
    "pl_das_classes",
    "pl_subordinado",
    "carteira",
    "inadimplente",
    "maior_cedente",
)


@dataclass(frozen=True)
class Regra:
    """Um gatilho em tipos simples (vira JSON): o que mede, em que sentido, com que limite."""

    regra_id: str
    medida: str  # "subordinacao", "inadimplencia" ou "maior_cedente"
    sentido: Sentido
    limite: float  # fração entre 0 e 1 (para `subiu`: a alta em pontos de fração)
    gravidade: Gravidade
    texto: str


REGRAS: tuple[Regra, ...] = (
    Regra("fidc_subordinacao_minima_atencao", "subordinacao", "abaixo", 0.10, "atencao",
          "subordinação abaixo de 10% do patrimônio das classes"),
    Regra("fidc_subordinacao_minima_quebra", "subordinacao", "abaixo", 0.05, "quebra",
          "subordinação abaixo de 5% do patrimônio das classes"),
    Regra("fidc_inadimplencia_limite_atencao", "inadimplencia", "acima", 0.05, "atencao",
          "inadimplência acima de 5% da carteira"),
    Regra("fidc_inadimplencia_limite_quebra", "inadimplencia", "acima", 0.10, "quebra",
          "inadimplência acima de 10% da carteira"),
    Regra("fidc_inadimplencia_subindo", "inadimplencia", "subiu", 0.02, "atencao",
          "inadimplência subiu 2 pontos percentuais ou mais contra o mês anterior"),
    Regra("fidc_concentracao_cedente_atencao", "maior_cedente", "acima", 0.50, "atencao",
          "um só cedente responde por mais de 50% da carteira"),
    Regra("fidc_concentracao_cedente_quebra", "maior_cedente", "acima", 0.80, "quebra",
          "um só cedente responde por mais de 80% da carteira"),
)  # fmt: skip
FORMULAS = {
    "subordinacao": "subordinação = PL das classes subordinadas e mezanino ÷ PL das classes (cotas × valor da cota)",
    "inadimplencia": "inadimplência = créditos vencidos e inadimplentes ÷ carteira de direitos creditórios",
    "maior_cedente": "maior cedente = maior participação de um cedente na carteira",
}


@dataclass(frozen=True)
class Evidencia:
    """Onde está o número: o quadro e o campo do informe, e o valor lido."""

    quadro: str
    campo: str
    valor: float | None


@dataclass(frozen=True)
class EventoDeMonitoramento:
    """O `MonitoringEvent` público do `data_model.md`: um fundo, um mês, uma regra."""

    evento_id: str
    usuario_id: None  # sempre None: evento público
    objeto_tipo: str
    objeto_id: str  # CNPJ do fundo
    nome_do_fundo: str
    regra_id: str
    gravidade: Gravidade
    ocorrido_em: date  # fim do mês do informe
    publico_em: date  # quando o informe ficou público
    valor: float
    limite: float
    texto: str
    evidencia: tuple[Evidencia, ...]
    rastro: Rastro

    def como_dict(self) -> dict[str, Any]:
        return _em_dicionario(self)  # type: ignore[return-value]

    def como_evento_de_pj(self) -> EventoDePJ:
        """O mesmo fato como evento de PJ no estado "mudou" (o assunto é a regra; o nome do fundo fica de fora)."""
        return EventoDePJ(
            evento_id=self.evento_id,
            usuario_id=None,
            objeto_tipo="fundo",
            objeto_id=cnpj_do_objeto(self.objeto_id),
            estado=MUDOU,
            fonte=FONTE_DO_INFORME,
            assunto=self.regra_id,
            ocorrido_em=self.ocorrido_em,
            publico_em=self.publico_em,
            evidencia=(
                *(
                    EvidenciaDePJ(e.quadro, e.campo, None, e.valor)
                    for e in self.evidencia
                ),
                EvidenciaDePJ(ONDE_DA_REGRA, "valor", None, self.valor),
                EvidenciaDePJ(ONDE_DA_REGRA, "limite", None, self.limite),
                EvidenciaDePJ(ONDE_DA_REGRA, "gravidade", None, self.gravidade),
            ),
            rastro=self.rastro,
        )


def _em_dicionario(objeto: object) -> object:
    if isinstance(objeto, date):
        return objeto.isoformat()
    if isinstance(objeto, dict):
        return {k: _em_dicionario(v) for k, v in objeto.items()}
    if isinstance(objeto, (list, tuple)):
        return [_em_dicionario(v) for v in objeto]
    if hasattr(objeto, "__dataclass_fields__"):
        return _em_dicionario(asdict(objeto))  # type: ignore[arg-type]
    return objeto


def _razao(parte: float, total: float) -> float | None:
    """A fração `parte/total`, ou None quando o total não existe (zero, vazio ou negativo)."""
    if pd.isna(parte) or pd.isna(total) or total <= 0:
        return None
    return round(float(parte) / float(total), CASAS_DA_RAZAO)


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _pl_das_classes(informe: pd.DataFrame) -> pd.DataFrame:
    """Por fundo-mês: PL das classes e a parte subordinada (cotas × valor da cota)."""
    classes = informe[["competencia", "cnpj_fundo", CAMPO_CLASSE]].copy()
    classes["pl"] = _numero(informe[CAMPO_COTAS]) * _numero(informe[CAMPO_VALOR_COTA])
    classes["subordinada"] = (
        classes[CAMPO_CLASSE].fillna("").str.contains(CLASSE_SUBORDINADA)
    )
    chave = ["competencia", "cnpj_fundo"]
    total = classes.groupby(chave)["pl"].sum(min_count=1).rename("pl_das_classes")
    sub = (
        classes[classes["subordinada"]]
        .groupby(chave)["pl"]
        .sum(min_count=1)
        .rename("pl_subordinado")
    )
    return pd.concat([total, sub], axis=1).fillna({"pl_subordinado": 0.0}).reset_index()


def _maior_cedente(quadro_i: pd.DataFrame) -> pd.Series:
    colunas = [c for c in quadro_i.columns if PARTICIPACAO_DO_CEDENTE.search(c)]
    if not colunas:
        return pd.Series(float("nan"), index=quadro_i.index)
    return quadro_i[colunas].apply(_numero).max(axis=1) / PERCENTUAL


def leituras_dos_informes(tabelas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Uma linha por fundo-mês com o que as regras leem, a partir das tabelas de `ler_informe`.

    Aceita a coluna `disponivel_em` (carga da base); sem ela, vale o piso da regra do prazo
    (`base.fidc.disponivel_em`). Fundo-mês repetido (regravação da CVM): fica a última linha.
    """
    from base import fidc

    quadro_i = tabelas[INFORME_I]
    base = quadro_i[["cnpj_fundo", "competencia"]].copy()
    base["nome"] = quadro_i.get("DENOM_SOCIAL")
    base["disponivel_em"] = (
        quadro_i["disponivel_em"]
        if "disponivel_em" in quadro_i
        else fidc.disponivel_em(quadro_i)
    )
    base["carteira"] = _numero(quadro_i[CAMPO_CARTEIRA])
    base["inadimplente"] = _numero(quadro_i[CAMPO_INADIMPLENTE])
    base["maior_cedente"] = _maior_cedente(quadro_i)
    chave = ["competencia", "cnpj_fundo"]
    classes = _pl_das_classes(tabelas[INFORME_X_2]) if INFORME_X_2 in tabelas else None
    if classes is not None:
        base = base.merge(classes, on=chave, how="left")
    for coluna in ("pl_das_classes", "pl_subordinado"):
        if coluna not in base:
            base[coluna] = float("nan")
    if INFORME_IV in tabelas:
        pl = tabelas[INFORME_IV][[*chave, CAMPO_PL]].drop_duplicates(chave, keep="last")
        base = base.merge(pl, on=chave, how="left")
    else:
        base[CAMPO_PL] = float("nan")
    base = base.drop_duplicates(chave, keep="last")
    return base[[*COLUNAS, CAMPO_PL]].reset_index(drop=True)


def como_era_em(leituras: pd.DataFrame, data: object) -> pd.DataFrame:
    """Só o que já era público no dia `data` (`disponivel_em ≤ data`), um registro por fundo-mês."""
    dia = pd.Timestamp(data)  # type: ignore[arg-type]
    visivel = leituras[pd.to_datetime(leituras["disponivel_em"]) <= dia]
    return visivel.reset_index(drop=True)


def maiores_por_pl(leituras: pd.DataFrame, competencia: object, n: int) -> list[str]:
    """Os CNPJs dos `n` maiores fundos do mês pelo patrimônio líquido (empate: CNPJ em ordem)."""
    mes = leituras[leituras["competencia"] == pd.Timestamp(competencia)]  # type: ignore[arg-type]
    ordem = mes.dropna(subset=[CAMPO_PL]).sort_values(
        [CAMPO_PL, "cnpj_fundo"], ascending=[False, True]
    )
    return list(ordem["cnpj_fundo"].head(n))


def _medidas(linha: pd.Series) -> dict[str, float | None]:
    return {
        "subordinacao": _razao(linha["pl_subordinado"], linha["pl_das_classes"]),
        "inadimplencia": _razao(linha["inadimplente"], linha["carteira"]),
        "maior_cedente": None
        if pd.isna(linha["maior_cedente"])
        else float(linha["maior_cedente"]),
    }


def _disparou(regra: Regra, valor: float, anterior: float | None) -> bool:
    if regra.sentido == "abaixo":
        return valor < regra.limite
    if regra.sentido == "acima":
        return valor > regra.limite
    return (
        anterior is not None and round(valor - anterior, CASAS_DA_RAZAO) >= regra.limite
    )


def _evidencia(regra: Regra, linha: pd.Series, valor: float) -> tuple[Evidencia, ...]:
    """O quadro, o campo e o valor lido de cada insumo da medida."""
    if regra.medida == "maior_cedente":
        return (Evidencia(INFORME_I, CAMPO_CEDENTE, round(valor * PERCENTUAL, 8)),)
    if regra.medida == "subordinacao":
        return (
            Evidencia(
                INFORME_X_2, CAMPO_PL_SUBORDINADO, _ou_none(linha["pl_subordinado"])
            ),
            Evidencia(INFORME_X_2, CAMPO_PL_CLASSES, _ou_none(linha["pl_das_classes"])),
        )
    return (
        Evidencia(INFORME_I, CAMPO_INADIMPLENTE, _ou_none(linha["inadimplente"])),
        Evidencia(INFORME_I, CAMPO_CARTEIRA, _ou_none(linha["carteira"])),
    )


def _ou_none(valor: float) -> float | None:
    return None if pd.isna(valor) else float(valor)


def _id_do_evento(regra: Regra, cnpj: str, competencia: date) -> str:
    texto = f"{regra.regra_id}|{cnpj}|{competencia.isoformat()}|{VERSAO_DO_CALCULO}"
    return hashlib.sha256(texto.encode()).hexdigest()[:TAMANHO_DO_ID]


def _evento(
    regra: Regra, linha: pd.Series, valor: float, anterior: float | None
) -> EventoDeMonitoramento:
    competencia = pd.Timestamp(linha["competencia"]).date()
    publico_em = pd.Timestamp(linha["disponivel_em"]).date()
    formula = FORMULAS[regra.medida]
    cnpj = str(linha["cnpj_fundo"])
    texto = f"{regra.texto} ({valor:.2%})"
    if regra.sentido == "subiu" and anterior is not None:
        texto = f"{regra.texto} ({anterior:.2%} para {valor:.2%})"
    return EventoDeMonitoramento(
        evento_id=_id_do_evento(regra, cnpj, competencia),
        usuario_id=None,
        objeto_tipo=OBJETO_TIPO,
        objeto_id=cnpj,
        nome_do_fundo=str(linha["nome"]) if pd.notna(linha["nome"]) else "",
        regra_id=regra.regra_id,
        gravidade=regra.gravidade,
        ocorrido_em=competencia,
        publico_em=publico_em,
        valor=valor,
        limite=regra.limite,
        texto=texto,
        evidencia=_evidencia(regra, linha, valor),
        rastro=Rastro(formula, VERSAO_DO_CALCULO, FONTE, publico_em),
    )


def _mes_anterior(
    leituras: pd.DataFrame, cnpj: str, competencia: pd.Timestamp
) -> pd.Series | None:
    antes = leituras[
        (leituras["cnpj_fundo"] == cnpj) & (leituras["competencia"] < competencia)
    ]
    return antes.sort_values("competencia").iloc[-1] if len(antes) else None


def eventos_do_mes(
    leituras: pd.DataFrame,
    competencia: object,
    *,
    como_em: object | None = None,
    cnpjs: list[str] | None = None,
    regras: tuple[Regra, ...] = REGRAS,
) -> list[EventoDeMonitoramento]:
    """Os eventos do mês `competencia`, só com o que era público em `como_em` (padrão: tudo).

    `cnpjs` limita aos fundos pedidos (os 20 maiores, por exemplo). Ordem estável: gravidade,
    fundo, regra. Um fundo sem o campo da regra não gera evento dela.
    """
    visivel = leituras if como_em is None else como_era_em(leituras, como_em)
    mes_pedido = pd.Timestamp(competencia)  # type: ignore[arg-type]
    mes = visivel[visivel["competencia"] == mes_pedido]
    if cnpjs is not None:
        mes = mes[mes["cnpj_fundo"].isin(cnpjs)]
    eventos = []
    por_gravidade = sorted(regras, key=lambda r: ORDEM_DA_GRAVIDADE[r.gravidade])
    for _, linha in mes.iterrows():
        medidas = _medidas(linha)
        antes = _mes_anterior(visivel, linha["cnpj_fundo"], mes_pedido)
        anterior = None if antes is None else _medidas(antes)
        disparadas: set[tuple[str, str]] = (
            set()
        )  # só a regra mais grave de cada medida e sentido
        for regra in por_gravidade:
            valor = medidas[regra.medida]
            ant = None if anterior is None else anterior[regra.medida]
            marca = (regra.medida, regra.sentido)
            if marca in disparadas or valor is None or not _disparou(regra, valor, ant):
                continue
            disparadas.add(marca)
            eventos.append(_evento(regra, linha, valor, ant))
    return sorted(
        eventos,
        key=lambda e: (ORDEM_DA_GRAVIDADE[e.gravidade], e.objeto_id, e.regra_id),
    )
