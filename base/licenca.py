"""A marca de licença de cada tabela da base (ADR 0008, Emenda 1; pedido "Trava das licenças no código").

Cada tabela ganha no manifesto o campo `licenca`: as fontes de onde veio, cada uma com a sua marca
(`src/banco/coletas.py::REVENDA`), e a marca da tabela, que é a **mais restrita** delas. As fontes saem
das `origens` que o manifesto já guarda:

- original coletado: a fonte pelo endereço (`FAMILIA_DO_ENDERECO`; o SGS 189 é o IGP-M da FGV);
- tabela da base (`cda/2025.parquet`): as fontes dela, pelo manifesto dela, até os originais;
- tabela conferida à mão (`base/conferidas/`): as fontes da coluna `fonte`, quando ela diz a fonte do
  arquivista (`comexstat`, `antt-siade`); texto livre ("cadastro de companhias da CVM") não conta;
- base de cripto, que grava sem origens: a fonte pela pasta (`PASTAS_DA_CRIPTO`).

Endereço que não casa com nenhuma fonte, tabela de entrada que sumiu ou tabela sem nenhuma origem entra
em `sem_fonte` e vale como "a confirmar". O manifesto gravado antes desta trava não tem o campo: a marca é calculada na hora.

`exigir_licenca_das_tabelas` e `exigir_licenca_das_origens` dão **erro** ao treinar, rotular ou
exportar com fonte "não comercial" ou "a confirmar" (`coletas.exigir_licenca`).
"""

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.banco.coletas import (
    REVENDA,
    Marca,
    exigir_licenca,
    marca_da_fonte,
    marca_mais_restrita,
)

PROFUNDIDADE_MAXIMA = (
    8  # tabelas derivadas encadeadas (a linhagem aceita 5; folga para a rede)
)
RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parent.parent
TABELAS_CONFERIDAS = "base/conferidas/"
SEM_ORIGENS = "(sem origens)"  # tabela sem nenhuma fonte: a confirmar, e a trava barra
# o começo do endereço (sem o "https://") → a família da fonte em `coletas.REVENDA`; vale o mais longo
FAMILIA_DO_ENDERECO = {
    "dados.cvm.gov.br/": "cvm",
    "www.rad.cvm.gov.br/": "cvm",
    "cvm.gov.br/": "cvm",
    "www.sec.gov/": "sec",
    "data.sec.gov/": "sec",
    "api.bcb.gov.br/dados/serie/bcdata.sgs.189/": "bcb-sgs-189",  # IGP-M da FGV
    "api.bcb.gov.br/": "bcb",
    "olinda.bcb.gov.br/": "bcb",
    "dadosabertos.bcb.gov.br/": "bcb",
    "www.bcb.gov.br/": "bcb",
    "home.treasury.gov/": "tesouro",
    "www.tesourotransparente.gov.br/": "tesouro-br",
    "iextrading.com/": "iex",
    "arquivos.receitafederal.gov.br/": "rfb-cnpj",
    "www.gov.br/receitafederal/": "rfb",
    "dadosabertos.pgfn.gov.br/": "pgfn",
    "portaldatransparencia.gov.br/": "cgu",
    "dadosabertos.ibama.gov.br/": "ibama",
    "www.gov.br/trabalho-e-emprego/": "mte",
    "api.gleif.org/": "gleif",
    "dadosabertos.ccee.org.br/": "ccee",
    "dados.antt.gov.br/": "antt",
    "www.gov.br/anp/": "anp",
    "sistemas.anac.gov.br/": "anac",
    "dadosabertos.ans.gov.br/": "ans",
    "dados.ons.org.br/": "ons",
    "ons-aws-prod-opendata.s3.amazonaws.com/": "ons",  # os arquivos do ONS ficam na AWS
    "www.anatel.gov.br/": "anatel",
    "dadosabertos.aneel.gov.br/": "aneel",
    "dados.susep.gov.br/": "susep",
    "www2.susep.gov.br/": "susep",
    "balanca.mdic.gov.br/": "comexstat",
    "www.b3.com.br/": "b3",
    "arquivos.b3.com.br/": "b3",
    "bvmf.bmfbovespa.com.br/": "b3",
    "www.igcp.com.br/": "assessoria",
    "web.archive.org/": "wayback",
    "www.cftc.gov/": "cftc",
    "wikimedia.org/": "wiki",
    "api.gdeltproject.org/": "gdelt",
    "api.kraken.com/": "kraken",
    "assets.kraken.com/": "kraken",
    "api.mercadobitcoin.net/": "mb",
    "pit.tce.pr.gov.br/": "tce-pr",
    "dados.tce.rs.gov.br/dados/municipal/empenhos/": "tce-rs-empenhos",
    "dados.tce.rs.gov.br/": "tce-rs",
    "www.gov.br/conab/": "conab",
}
# a base de cripto (`<acervo>/cripto/<pasta>/...`, `base/cripto/coleta.py`) grava sem origens
PASTAS_DA_CRIPTO = {
    ("precos", "kraken"): "kraken",
    ("precos", "mb"): "mb",
    ("cftc",): "cftc",
    ("wikipedia",): "wiki",
    ("gdelt",): "gdelt",
    ("receita",): "rfb",
    ("no",): "btc",
    ("rede_diaria",): "btc",
}


@dataclass(frozen=True)
class Licenca:
    fontes: dict[str, Marca] = field(default_factory=dict)  # família → marca
    sem_fonte: tuple[
        str, ...
    ] = ()  # endereços sem fonte conhecida: contam como "a confirmar"

    @property
    def marca(self) -> Marca:
        marcas = [
            *self.fontes.values(),
            *([Marca.A_CONFIRMAR] if self.sem_fonte else []),
        ]
        return marca_mais_restrita(marcas)

    def junta(self, outra: "Licenca") -> "Licenca":
        return Licenca(
            {**self.fontes, **outra.fontes},
            tuple(dict.fromkeys([*self.sem_fonte, *outra.sem_fonte])),
        )

    def para_o_manifesto(self) -> dict[str, object]:
        campo: dict[str, object] = {
            "marca": self.marca.value,
            "fontes": {f: m.value for f, m in sorted(self.fontes.items())},
        }
        if self.sem_fonte:
            campo["sem_fonte"] = list(self.sem_fonte)
        return campo


def familia_do_endereco(url: str) -> str | None:
    """A família da fonte de um original pelo endereço; None se não é de nenhuma fonte conhecida."""
    sem_esquema = url.split("://", 1)[-1]
    if "/" not in sem_esquema:
        sem_esquema += "/"
    casam = [p for p in FAMILIA_DO_ENDERECO if sem_esquema.startswith(p)]
    return FAMILIA_DO_ENDERECO[max(casam, key=len)] if casam else None


def _familia_da_pasta_de_cripto(arquivo: Path) -> str | None:
    partes = arquivo.parts
    if "cripto" not in partes:
        return None
    depois = partes[len(partes) - partes[::-1].index("cripto") : -1]
    for pasta, familia in PASTAS_DA_CRIPTO.items():
        if tuple(depois[: len(pasta)]) == pasta:
            return familia
    return None


def _familia_conhecida(valor: str) -> str | None:
    """A família de um valor da coluna `fonte` ("antt-siade" → "antt"); texto livre → None."""
    if valor in REVENDA:
        return valor
    familia = valor.split("-", 1)[0]
    return familia if familia in REVENDA else None


def _da_conferida(arquivo: Path) -> Licenca:
    if not arquivo.is_file():
        return Licenca()
    with arquivo.open(encoding="utf-8", newline="") as texto:
        linhas = csv.DictReader(texto, delimiter=";")
        valores = {linha.get("fonte") or "" for linha in linhas}
    familias = {f for f in map(_familia_conhecida, valores) if f}
    return Licenca({f: marca_da_fonte(f) for f in familias})


def _achar_tabela(url: str, onde: Path) -> Path | None:
    """A tabela de entrada (`cda/2025.parquet`), procurada da pasta de `onde` para cima."""
    return next((p / url for p in onde.parents if (p / url).is_file()), None)


def _licenca(
    arquivo: Path, origens: Sequence[Mapping[str, str]], vistas: set[Path]
) -> Licenca:
    licenca = Licenca()
    familia_da_pasta = _familia_da_pasta_de_cripto(arquivo)
    if familia_da_pasta:
        licenca = licenca.junta(
            Licenca({familia_da_pasta: marca_da_fonte(familia_da_pasta)})
        )
    for origem in origens:
        url = origem["url"]
        if url.startswith(TABELAS_CONFERIDAS):
            licenca = licenca.junta(_da_conferida(RAIZ_DO_REPOSITORIO / url))
            continue
        if url.endswith(".parquet") and "://" not in url:
            entrada = _achar_tabela(url, arquivo)
            if (
                entrada is None
                or len(vistas) >= PROFUNDIDADE_MAXIMA
                or entrada in vistas
            ):
                licenca = licenca.junta(Licenca(sem_fonte=(url,)))
            else:
                licenca = licenca.junta(_da_tabela(entrada, vistas | {entrada}))
            continue
        familia = familia_do_endereco(url)
        if familia is None:
            licenca = licenca.junta(Licenca(sem_fonte=(url,)))
        else:
            licenca = licenca.junta(Licenca({familia: marca_da_fonte(familia)}))
    if not licenca.fontes and not licenca.sem_fonte:
        return Licenca(sem_fonte=(SEM_ORIGENS,))
    return licenca


def _da_tabela(arquivo: Path, vistas: set[Path]) -> Licenca:
    manifesto = arquivo.with_suffix(".json")
    if not manifesto.exists():
        return Licenca(sem_fonte=(arquivo.name,))
    anotado = json.loads(manifesto.read_text(encoding="utf-8"))
    gravada = anotado.get("licenca")
    if (
        gravada is not None
    ):  # as marcas de hoje: uma fonte que ganhou resposta muda a tabela antiga
        return Licenca(
            {f: marca_da_fonte(f) for f in gravada.get("fontes", {})},
            tuple(gravada.get("sem_fonte", ())),
        )
    return _licenca(arquivo, anotado.get("origens") or [], vistas)


def licenca_para_gravar(
    arquivo: Path, origens: Sequence[Mapping[str, str]]
) -> dict[str, object]:
    """O campo `licenca` do manifesto de `arquivo`, gravado com estas `origens`."""
    return _licenca(arquivo, origens, {arquivo}).para_o_manifesto()


def licenca_da_tabela(arquivo: Path) -> Licenca:
    """A licença de uma tabela já gravada: a do manifesto ou, se ele é anterior à trava, calculada."""
    return _da_tabela(arquivo, {arquivo})


def _exigir(uso: str, licenca: Licenca, modelo: str | None, onde: str) -> None:
    exigir_licenca(uso, [*licenca.fontes, *licenca.sem_fonte], modelo=modelo, onde=onde)


def exigir_licenca_das_tabelas(
    uso: str, arquivos: Iterable[Path], modelo: str | None = None
) -> None:
    """Erro se alguma tabela tem fonte que não pode `uso` (a mensagem diz a tabela e a fonte)."""
    for arquivo in arquivos:
        _exigir(uso, licenca_da_tabela(arquivo), modelo, arquivo.as_posix())


def exigir_licenca_das_origens(
    uso: str,
    origens: Sequence[Mapping[str, str]],
    destino: Path,
    modelo: str | None = None,
) -> None:
    """Erro antes de montar `destino` (ex.: a amostra de treino) com origens que não podem `uso`."""
    _exigir(uso, _licenca(destino, origens, {destino}), modelo, destino.as_posix())
