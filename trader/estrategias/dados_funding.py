"""Dados da ficha P0-6: funding e basis de BTC e ETH na Binance, cupom cambial da B3 e CDI.

Ficha de dados (aprovada pelo Tiago em 03/11/2026: "Pode baixar"; só estes, poucos MB):
- **Funding:** contratos perpétuos USD-M BTCUSDT e ETHUSDT. Histórico pelos arquivos mensais do Binance
  Vision (`data.binance.vision`, `fundingRate`); o mês mais antigo que existe é achado tentando (404 antes
  dele). O trecho recente (depois do holdout) vem da API pública (`fapi/v1/fundingRate`), a partir do 1º
  dia depois do holdout, para não baixar nenhum dia dele.
- **Basis:** fechamento diário (UTC) do índice de prêmio (`premiumIndexKlines`, a diferença entre o perpétuo
  e o índice à vista, em fração), pelos mesmos dois caminhos.
- **Cupom cambial:** curva DOC ("DIxXDOL Cupom limpo", linear 360) das taxas referenciais da B3 (arquivo
  `TSaammdd.ex_`). O arquivo é um executável que se descompacta (MZ): **nunca é executado**; o zip que vem
  dentro dele é lido com `zipfile`. No histórico, um arquivo por fim de mês; no trecho recente, um por dia.
- **CDI:** SGS 12 do Banco Central (o mesmo cache da P0-3).

Dois trechos, nunca o holdout (10/10/2023 a 09/10/2026, lacrado): o desenvolvimento (até 08/09/2023) e o
trecho recente (de 10/10/2026 até o dia da coleta). Todo pedido passa por `conferir_fora_do_holdout`.

Licença: Binance só para uso interno (CC BY-NC-SA, ficha P0-6); esta pesquisa é interna. Os arquivos
baixados são dado de fora: ficam na própria pasta, fora do Git, só são lidos e têm o SHA-256 anotado em
`sha256.json`.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd

from src import rede
from trader.estrategias import dados_p0_3
from trader.estrategias.dados_tendencia_cripto import ler_kline_zip
from trader.holdout import FIM_DO_DESENVOLVIMENTO, FIM_DO_HOLDOUT, INICIO_DO_HOLDOUT

PASTA_DO_FUNDING = dados_p0_3.PASTA_DA_PESQUISA / "funding"
PARES = ("BTCUSDT", "ETHUSDT")
PRIMEIRO_MES_POSSIVEL = pd.Period(
    "2019-09", "M"
)  # o perpétuo BTCUSDT da Binance abriu em 09/2019
INICIO_DO_TRECHO_RECENTE = FIM_DO_HOLDOUT + pd.Timedelta(days=1)
FUSO_DE_BRASILIA = "America/Sao_Paulo"
LIMITE_DA_API = 1_000  # linhas por chamada na API pública da Binance
FUNDING = "fundingRate"
PREMIO = "premiumIndexKlines"

URL_DO_VISION = "https://data.binance.vision/data/futures/um/monthly"
URL_DA_API = "https://fapi.binance.com/fapi/v1"
URL_DA_B3 = "https://www.b3.com.br/pesquisapregao/download?filelist=TS{dia:%y%m%d}.ex_"

CURVA_DO_CUPOM = "DOC"
ARQUIVO_DAS_TAXAS = "TaxaSwap.txt"
# Colunas do TaxaSwap.txt (largura fixa; conferidas no arquivo de 30/10/2020).
COLUNA_DA_DATA = slice(11, 19)
COLUNA_DA_CURVA = slice(21, 26)
COLUNA_DOS_DIAS_CORRIDOS = slice(41, 46)
COLUNA_DO_SINAL = 51
COLUNA_DA_TAXA = slice(52, 66)
DIVISOR_DA_TAXA = 1e7 * 100  # 14 dígitos com 7 casas, em % a.a. → fração
PRAZO_DO_CUPOM = 30  # dias corridos
DIAS_PARA_PROCURAR_UM_PREGAO = 7

Baixar = Callable[[str], bytes | None]


class DadoNoHoldoutError(ValueError):
    """Um pedido de dados cairia no holdout (10/10/2023 a 09/10/2026), que segue lacrado."""


def _baixar_da_internet(url: str) -> bytes | None:
    """O conteúdo, ou None quando o arquivo não existe (404)."""
    resposta = rede.get_com_agente(url, timeout=120)
    if resposta.status_code == 404:
        return None
    resposta.raise_for_status()
    return resposta.content


def conferir_fora_do_holdout(inicio: pd.Timestamp, fim: pd.Timestamp) -> None:
    """Recusa qualquer período que toque o holdout (o expurgo antes dele pode: não é pontuado)."""
    if inicio <= FIM_DO_HOLDOUT and fim >= INICIO_DO_HOLDOUT:
        raise DadoNoHoldoutError(f"{inicio.date()} a {fim.date()} toca o holdout")


class Arquivos:
    """Uma pasta de arquivos baixados, com o SHA-256 de cada um em `sha256.json`."""

    def __init__(
        self, pasta: Path = PASTA_DO_FUNDING, baixar: Baixar = _baixar_da_internet
    ) -> None:
        self.pasta = pasta
        self.baixar = baixar
        self._hashes = pasta / "sha256.json"

    def hashes(self) -> dict[str, str]:
        return (
            json.loads(self._hashes.read_text("utf-8")) if self._hashes.exists() else {}
        )

    def obter(
        self, nome: str, url: str, valido: Callable[[bytes], bool]
    ) -> bytes | None:
        """O arquivo da pasta ou baixado; None se a fonte não tem (404 ou conteúdo que não é o esperado)."""
        destino = self.pasta / nome
        if destino.exists():
            return destino.read_bytes()
        conteudo = self.baixar(url)
        if conteudo is None or not valido(conteudo):
            return None
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        hashes = self.hashes()
        hashes[nome] = hashlib.sha256(conteudo).hexdigest()
        self._hashes.write_text(json.dumps(hashes, indent=1, sort_keys=True), "utf-8")
        return conteudo


def _e_zip(conteudo: bytes) -> bool:
    return zipfile.is_zipfile(io.BytesIO(conteudo))


def _e_lista_json(conteudo: bytes) -> bool:
    try:
        return isinstance(json.loads(conteudo), list)
    except ValueError:
        return False


# --- Binance: arquivos mensais (desenvolvimento) ----------------------------------------------------


def ler_funding_zip(conteudo: bytes) -> pd.Series:
    """Os pagamentos de funding de um mês (fração por pagamento), pela hora UTC, sem fuso."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        tabela = pd.read_csv(z.open(nome))
    horas = pd.to_datetime(tabela["calc_time"].astype("int64"), unit="ms")
    valores = tabela["last_funding_rate"].astype(float).to_numpy()
    return pd.Series(valores, index=pd.DatetimeIndex(horas)).sort_index()


def ler_premio_zip(conteudo: bytes) -> pd.Series:
    """O fechamento diário (UTC) do índice de prêmio, em fração."""
    return ler_kline_zip(conteudo)["fechamento"]


def meses_do_desenvolvimento() -> pd.PeriodIndex:
    return pd.period_range(
        PRIMEIRO_MES_POSSIVEL, FIM_DO_DESENVOLVIMENTO.to_period("M"), freq="M"
    )


def _nome_mensal(par: str, tipo: str, mes: pd.Period) -> tuple[str, str]:
    """O nome do arquivo e a URL dele no Binance Vision."""
    if tipo == FUNDING:
        nome = f"{par}-fundingRate-{mes}.zip"
        return nome, f"{URL_DO_VISION}/{FUNDING}/{par}/{nome}"
    nome = f"{par}-1d-{mes}.zip"
    return f"{par}-premio-{mes}.zip", f"{URL_DO_VISION}/{PREMIO}/{par}/1d/{nome}"


def historico_mensal(
    par: str, tipo: str, arquivos: Arquivos, meses: Iterable[pd.Period]
) -> pd.Series:
    """A série de `tipo` nos meses pedidos, cortada no fim do desenvolvimento.

    Os meses antes do primeiro que existe são pulados (404); um buraco depois dele é erro.
    """
    ler = ler_funding_zip if tipo == FUNDING else ler_premio_zip
    partes: list[pd.Series] = []
    for mes in meses:
        conferir_fora_do_holdout(mes.start_time, mes.end_time.normalize())
        nome, url = _nome_mensal(par, tipo, mes)
        conteudo = arquivos.obter(nome, url, _e_zip)
        if conteudo is None:
            if partes:
                raise FileNotFoundError(f"falta {nome} no meio do histórico")
            continue
        partes.append(ler(conteudo))
    if not partes:
        raise FileNotFoundError(f"nenhum mês de {tipo} de {par}")
    serie = pd.concat(partes).sort_index()
    serie = serie[~serie.index.duplicated(keep="last")]
    dia_seguinte = FIM_DO_DESENVOLVIMENTO + pd.Timedelta(days=1)
    corte = inicio_em_brasilia(dia_seguinte) if tipo == FUNDING else dia_seguinte
    return serie[serie.index < corte]


# --- Binance: API pública (trecho recente) ----------------------------------------------------------


def _em_milissegundos(momento: pd.Timestamp) -> int:
    return int(momento.value // 1_000_000)


def inicio_em_brasilia(dia: pd.Timestamp) -> pd.Timestamp:
    """A meia-noite de Brasília de `dia`, em UTC sem fuso."""
    return dia.tz_localize(FUSO_DE_BRASILIA).tz_convert("UTC").tz_localize(None)


def ler_funding_da_api(conteudo: bytes) -> pd.Series:
    linhas = json.loads(conteudo)
    horas = pd.to_datetime([int(linha["fundingTime"]) for linha in linhas], unit="ms")
    valores = [float(linha["fundingRate"]) for linha in linhas]
    return pd.Series(valores, index=pd.DatetimeIndex(horas), dtype=float).sort_index()


def ler_premio_da_api(conteudo: bytes) -> pd.Series:
    linhas = json.loads(conteudo)
    dias = pd.to_datetime([int(linha[0]) for linha in linhas], unit="ms").normalize()
    valores = [float(linha[4]) for linha in linhas]
    return pd.Series(valores, index=pd.DatetimeIndex(dias), dtype=float).sort_index()


def recente_da_api(
    par: str, tipo: str, arquivos: Arquivos, fim: pd.Timestamp
) -> pd.Series:
    """De 10/10/2026 (meia-noite de Brasília no funding; dia UTC no prêmio) até `fim` (exclusivo)."""
    if fim <= INICIO_DO_TRECHO_RECENTE:
        raise DadoNoHoldoutError(
            f"o trecho recente começa em {INICIO_DO_TRECHO_RECENTE.date()}"
        )
    conferir_fora_do_holdout(INICIO_DO_TRECHO_RECENTE, fim)
    if tipo == FUNDING:
        inicio, final = (
            inicio_em_brasilia(INICIO_DO_TRECHO_RECENTE),
            inicio_em_brasilia(fim),
        )
        parametros = {"symbol": par}
        ler = ler_funding_da_api
    else:
        inicio, final = INICIO_DO_TRECHO_RECENTE, fim
        parametros = {"symbol": par, "interval": "1d"}
        ler = ler_premio_da_api
    parametros |= {
        "startTime": _em_milissegundos(inicio),
        "endTime": _em_milissegundos(final) - 1,
        "limit": LIMITE_DA_API,
    }
    nome = f"{par}-{tipo}-api-{INICIO_DO_TRECHO_RECENTE:%Y%m%d}-{fim:%Y%m%d}.json"
    url = f"{URL_DA_API}/{tipo}?{urlencode(parametros)}"
    conteudo = arquivos.obter(nome, url, _e_lista_json)
    if conteudo is None:
        raise FileNotFoundError(f"a API da Binance não devolveu {tipo} de {par}")
    serie = ler(conteudo)
    if len(serie) >= LIMITE_DA_API:
        raise ValueError(f"{nome}: a API cortou no limite; pedir em partes")
    return serie


# --- cupom cambial (B3) -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Curva:
    """Uma curva das taxas referenciais da B3: a data e a taxa (fração a.a.) por dias corridos."""

    data: pd.Timestamp
    taxas: pd.Series

    def a_prazo(self, dias: int = PRAZO_DO_CUPOM) -> float:
        """Interpolação linear nos dias corridos (a curva DOC é linear 360)."""
        return float(
            np.interp(
                dias, self.taxas.index.to_numpy(float), self.taxas.to_numpy(float)
            )
        )


def ler_taxas_da_b3(conteudo: bytes, curva: str = CURVA_DO_CUPOM) -> Curva:
    """Lê uma curva do arquivo TS da B3 sem executar nada: zip → `.ex_` (zip dentro do MZ) → TaxaSwap.txt."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as fora:
        autoextraivel = fora.read(fora.namelist()[0])
    with zipfile.ZipFile(io.BytesIO(autoextraivel)) as dentro:
        nome = next(
            n for n in dentro.namelist() if n.lower() == ARQUIVO_DAS_TAXAS.lower()
        )
        linhas = dentro.read(nome).decode("latin-1").splitlines()
    escolhidas = [linha for linha in linhas if linha[COLUNA_DA_CURVA].strip() == curva]
    if not escolhidas:
        raise ValueError(f"curva {curva} não está no arquivo")
    data = pd.Timestamp(escolhidas[0][COLUNA_DA_DATA])
    dias = [int(linha[COLUNA_DOS_DIAS_CORRIDOS]) for linha in escolhidas]
    taxas = [
        (-1 if linha[COLUNA_DO_SINAL] == "-" else 1)
        * int(linha[COLUNA_DA_TAXA])
        / DIVISOR_DA_TAXA
        for linha in escolhidas
    ]
    serie = pd.Series(taxas, index=pd.Index(dias, name="dias_corridos"), dtype=float)
    return Curva(data, serie.groupby(level=0).last().sort_index())


def _e_arquivo_da_b3(conteudo: bytes) -> bool:
    try:
        ler_taxas_da_b3(conteudo)
    except (zipfile.BadZipFile, StopIteration, ValueError, IndexError, KeyError):
        return False
    return True


def curva_do_dia(dia: pd.Timestamp, arquivos: Arquivos) -> Curva | None:
    """A curva DOC publicada em `dia` (None se não houve pregão ou a B3 não tem o arquivo)."""
    conferir_fora_do_holdout(dia, dia)
    conteudo = arquivos.obter(
        f"TS{dia:%y%m%d}.zip", URL_DA_B3.format(dia=dia), _e_arquivo_da_b3
    )
    return None if conteudo is None else ler_taxas_da_b3(conteudo)


def ultima_curva_ate(dia: pd.Timestamp, arquivos: Arquivos) -> Curva:
    """A última curva publicada até `dia`, voltando até uma semana (feriados e fins de semana)."""
    for atras in range(DIAS_PARA_PROCURAR_UM_PREGAO):
        curva = curva_do_dia(dia - pd.Timedelta(days=atras), arquivos)
        if curva is not None:
            return curva
    raise FileNotFoundError(f"nenhum arquivo da B3 na semana até {dia.date()}")


def cupom_do_desenvolvimento(arquivos: Arquivos) -> pd.Series:
    """O cupom de 30 dias no último pregão de cada mês, do mês antes do 1º funding até 08/09/2023."""
    fins = pd.date_range(
        PRIMEIRO_MES_POSSIVEL.start_time - pd.Timedelta(days=1),
        FIM_DO_DESENVOLVIMENTO,
        freq="ME",
    ).append(pd.DatetimeIndex([FIM_DO_DESENVOLVIMENTO]))
    curvas = [ultima_curva_ate(pd.Timestamp(fim), arquivos) for fim in fins]
    return _serie_do_cupom(curvas)


def cupom_recente(arquivos: Arquivos, fim: pd.Timestamp) -> pd.Series:
    """O cupom de 30 dias de cada pregão de 10/10/2026 até a véspera de `fim`."""
    dias = pd.date_range(INICIO_DO_TRECHO_RECENTE, fim - pd.Timedelta(days=1), freq="D")
    curvas = [
        c
        for c in (curva_do_dia(pd.Timestamp(d), arquivos) for d in dias)
        if c is not None
    ]
    return _serie_do_cupom(curvas)


def _serie_do_cupom(curvas: list[Curva]) -> pd.Series:
    serie = pd.Series(
        [c.a_prazo() for c in curvas],
        index=pd.DatetimeIndex([c.data for c in curvas]),
        dtype=float,
    )
    return serie[~serie.index.duplicated(keep="last")].sort_index()


# --- CDI ----------------------------------------------------------------------------------------------


def carregar_cdi(inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.Series:
    """CDI diário (fração, dias úteis) do SGS 12, com o cache da P0-3."""
    conferir_fora_do_holdout(inicio, fim)
    return dados_p0_3.carregar_cdi(inicio, fim)


def hash_dos_arquivos(arquivos: Arquivos) -> str:
    """Impressão digital de tudo o que foi baixado (vai para a especificação da tentativa)."""
    texto = json.dumps(arquivos.hashes(), sort_keys=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
