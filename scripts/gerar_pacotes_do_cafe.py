"""Monta os pacotes do café (Painel e Mapa) a partir da base, para o servidor do app.

    python -m scripts.gerar_pacotes_do_cafe                   (a base do acervo; grava em <acervo>/cafe)
    python -m scripts.gerar_pacotes_do_cafe --pasta <base>    (outra pasta da base)
    python -m scripts.gerar_pacotes_do_cafe --saida <pasta>   (ensaio: grava fora do acervo)
    python -m scripts.gerar_pacotes_do_cafe --acervo <pasta>  (o acervo dos manifestos e da malha)

O servidor do app não tem a base (DuckDB); como as fichas do dossiê (`scripts/gerar_dossies.py`), o
que as telas do café mostram é montado aqui, no servidor de casa, e vai para lá como arquivo:

- `painel_do_cafe.json` (`src/commodities/cafe/pacote_do_painel.py`): as tabelas da CFTC, do Comex,
  do USDA, da CONAB e do clima como estavam hoje; o painel faz as contas no app.
- `mapa_do_cafe.json` (`src/commodities/cafe/pacote_do_mapa.py`): a PAM e o MapBiomas por município
  (`area_cafe_municipio`), o clima por região e a malha do IBGE (o original mais novo de cada UF no
  acervo, pelos manifestos do arquivista). A geada por estação ainda não é tabela da base: vai vazia
  e a tela diz "sem dado".
- `manifesto.json`: a versão do código, o hash de cada tabela lida (ADR 0078), as que faltaram e as
  falhas.

Lê a base só pela porta (`base.porta`, ADR 0077): o nome não é `montar_*` porque não grava a base,
então o `test_porta_unica` vigia. Cada arquivo é escrito ao lado e só troca de nome no fim: quem lê
nunca vê um pela metade. Um pacote que não dá para montar não apaga o da noite anterior.

Roda toda noite no servidor de casa: saída 0 tudo certo; 1 alguma falha (tabela que faltou, pacote
que não saiu), com a última linha `FALHAS: ...` (vai para o aviso do Kuma), como os dossiês.
"""

import argparse
import gzip
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base.commodities.area_municipio import COLUNAS_DA_PAM, COLUNAS_DO_MAPBIOMAS
from base.commodities.clima_regiao import COLUNAS_DIARIAS
from base.porta import Porta
from src import acervo
from src.commodities.cafe import pacote_do_mapa, pacote_do_painel, painel
from src.commodities.cafe.mapa import PROPRIEDADE_DO_CODIGO
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger(__name__)
FUSO = ZoneInfo("America/Sao_Paulo")  # o dia do pacote é o do Brasil, não o do servidor
TAMANHO_MAXIMO_DO_RESUMO = 300  # o resumo vai no endereço do push do Kuma
FONTE_DA_MALHA = (
    "ibge-malha-municipal"  # o id da fonte no arquivista (`base/arquivo/fontes.py`)
)
TABELA_DA_AREA = "area_cafe_municipio"
TABELA_DO_CLIMA = painel.TABELAS_DA_BASE["clima"]
VERSAO_DO_MANIFESTO = 1
ARQUIVO_DO_PAINEL = pacote_do_painel.ARQUIVO_PADRAO.name
ARQUIVO_DO_MAPA = pacote_do_mapa.ARQUIVO_PADRAO.name
ARQUIVO_DO_MANIFESTO = "manifesto.json"
# o diário do INMET por estação (a geada) ainda não é tabela da base: a geada sai "sem dado"
SEM_DIARIO = pd.DataFrame(columns=[*COLUNAS_DIARIAS, "regiao"])


@dataclass
class Leitor:
    """Lê as tabelas pela porta e anota o hash de cada arquivo lido e as tabelas que faltaram (vão no
    manifesto: dá para refazer a noite e conferir, ADR 0078). Como o de `scripts/gerar_dossies.py`:
    os scripts entram na imagem de casa pela entrada padrão, sem a pasta `scripts/`."""

    porta: Porta
    tabelas: dict[str, str | None] = field(default_factory=dict)
    faltando: list[str] = field(default_factory=list)

    def ler(
        self, tabela: str, filtros: dict[str, object] | None = None
    ) -> pd.DataFrame:
        """A tabela inteira (vazia e anotada, se não há arquivo nesta base)."""
        if tabela not in self.porta.tabelas:
            raise KeyError(f"tabela `{tabela}` não existe no dicionário da base")
        try:
            self.tabelas.update(self.porta.hashes(tabela))
        except KeyError:
            self.faltando.append(tabela)
            return pd.DataFrame()
        return self.porta.ler(tabela, filtros=filtros)


@dataclass
class Resumo:
    pacotes: list[str] = field(default_factory=list)  # os arquivos gravados nesta noite
    falhas: list[str] = field(default_factory=list)


# --- o painel ---------------------------------------------------------------------------------------
def pacote_do_dia(leitor: Leitor, dia: date) -> pacote_do_painel.PacoteDoPainel:
    """As tabelas do painel lidas pela porta e recortadas em `dia`; a que faltou vira motivo."""
    tabelas: dict[str, pd.DataFrame] = {}
    motivos: dict[str, str] = {}
    for nome, tabela in painel.TABELAS_DA_BASE.items():
        lida = leitor.ler(tabela, filtros=painel.FILTROS_DA_BASE.get(nome))
        if tabela in leitor.faltando:
            motivos[nome] = painel.motivo_sem_tabela(tabela)
        else:
            tabelas[nome] = lida
    return pacote_do_painel.montar_pacote(
        tabelas, motivos, dia, painel.MESES_DAS_EXPORTACOES
    )


# --- o mapa -----------------------------------------------------------------------------------------
def _registros_da_malha(raiz: Path) -> dict[str, dict]:
    """O registro mais novo de cada endereço da malha nos manifestos do arquivista (um por UF)."""
    mais_novo: dict[str, dict] = {}
    for manifesto in sorted((raiz / "manifesto").glob("*.jsonl")):
        for linha in manifesto.read_text(encoding="utf-8").splitlines():
            registro = json.loads(linha)
            if registro.get("fonte") == FONTE_DA_MALHA and registro.get("caminho"):
                anterior = mais_novo.get(registro["url"])
                if anterior is None or registro["hora"] >= anterior["hora"]:
                    mais_novo[registro["url"]] = registro
    return mais_novo


def malha_do_acervo(raiz: Path) -> dict | None:
    """A malha municipal das UFs com café, juntando o original mais novo de cada UF (None: nenhum)."""
    feicoes = []
    for url, registro in sorted(_registros_da_malha(raiz).items()):
        caminho = raiz / registro["caminho"]
        conteudo = caminho.read_bytes()
        if caminho.suffix == ".gz":
            conteudo = gzip.decompress(conteudo)
        malha = json.loads(conteudo)
        feicoes += [
            f
            for f in malha.get("features", [])
            if PROPRIEDADE_DO_CODIGO in f.get("properties", {})
        ]
        log.info("malha: %s (%d municípios)", url, len(malha.get("features", [])))
    return {"type": "FeatureCollection", "features": feicoes} if feicoes else None


def fonte_do_clima(mensal: pd.DataFrame) -> str:
    """O CHIRPS (cobre todos os municípios) quando a base tem a chuva dele; senão, as estações."""
    tem_chirps = mensal[
        (mensal["fonte"] == pacote_do_mapa.FONTE_CHIRPS) & mensal["chuva_mm"].notna()
    ]
    return (
        pacote_do_mapa.FONTE_CHIRPS
        if not tem_chirps.empty
        else pacote_do_mapa.FONTE_INMET
    )


def mapa_do_dia(
    leitor: Leitor, raiz: Path, dia: date
) -> tuple[pacote_do_mapa.PacoteDoMapa | None, list[str]]:
    """O pacote do mapa de `dia`, ou None e o que faltou para montá-lo."""
    area = leitor.ler(TABELA_DA_AREA)
    mensal = leitor.ler(TABELA_DO_CLIMA)
    malha = malha_do_acervo(raiz)
    faltou = [t for t in (TABELA_DA_AREA, TABELA_DO_CLIMA) if t in leitor.faltando]
    if malha is None:
        faltou.append(f"{FONTE_DA_MALHA} no acervo")
    if faltou:
        return None, faltou
    # a tabela da base tem as duas fontes lado a lado; o mapa as recebe separadas (`ler_pam`, `ler_mapbiomas`)
    valores_da_pam = list(COLUNAS_DA_PAM[4:])
    pam = area[list(COLUNAS_DA_PAM)].dropna(subset=valores_da_pam, how="all")
    mapbiomas = area[list(COLUNAS_DO_MAPBIOMAS)].dropna(subset=["area_mapbiomas_ha"])
    pacote = pacote_do_mapa.montar_pacote(
        pam, mapbiomas, mensal, SEM_DIARIO, malha, dia,
        fonte_do_clima=fonte_do_clima(mensal),
    )  # fmt: skip
    return pacote, []


# --- gravar -----------------------------------------------------------------------------------------
def _trocar(destino: Path, gravar: Callable[[Path], None]) -> None:
    """Grava ao lado e troca de nome no fim (quem lê nunca vê o arquivo pela metade)."""
    montando = destino.with_name(f".{destino.name}.montando")
    gravar(montando)
    montando.replace(destino)


def montar(
    pasta: Path, raiz: Path, saida: Path, agora: datetime, versao: str
) -> Resumo:
    """Grava os pacotes e o manifesto em `saida`; devolve o que saiu e o que falhou."""
    resumo = Resumo()
    dia = agora.date()
    saida.mkdir(parents=True, exist_ok=True)
    with Porta(pasta) as porta:
        leitor = Leitor(porta)
        do_painel = pacote_do_dia(leitor, dia)
        do_mapa, faltou_no_mapa = mapa_do_dia(leitor, raiz, dia)
    if do_painel.tabelas:
        _trocar(
            saida / ARQUIVO_DO_PAINEL,
            lambda c: pacote_do_painel.gravar_pacote(do_painel, c),
        )
        resumo.pacotes.append(ARQUIVO_DO_PAINEL)
    else:
        resumo.falhas.append("painel: nenhuma tabela do café na base")
    if do_mapa is not None:
        _trocar(
            saida / ARQUIVO_DO_MAPA, lambda c: pacote_do_mapa.gravar_pacote(do_mapa, c)
        )
        resumo.pacotes.append(ARQUIVO_DO_MAPA)
    else:
        resumo.falhas.append("mapa: sem " + ", ".join(faltou_no_mapa))
    faltando = sorted(set(leitor.faltando))
    if faltando:
        resumo.falhas.append("faltam na base: " + ", ".join(faltando))
    manifesto = {
        "versao": VERSAO_DO_MANIFESTO,
        "gerado_em": agora.isoformat(),
        "versao_do_codigo": versao,
        "pacotes": resumo.pacotes,
        "tabelas": dict(sorted(leitor.tabelas.items())),
        "faltando": faltando,
        "falhas": resumo.falhas,
    }
    texto = json.dumps(manifesto, ensure_ascii=False, indent=1)
    _trocar(
        saida / ARQUIVO_DO_MANIFESTO, lambda c: c.write_text(texto, encoding="utf-8")
    )
    return resumo


def _avisar(problemas: list[str]) -> int:
    linha = "FALHAS: café: " + "; ".join(problemas)
    print(linha[:TAMANHO_MAXIMO_DO_RESUMO])
    return 1


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None, help="pasta da base")
    argumentos.add_argument(
        "--saida", type=Path, default=None, help="onde gravar os pacotes"
    )
    argumentos.add_argument(
        "--acervo", type=Path, default=None, help="o acervo (manifestos e a malha)"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    raiz = opcoes.acervo or acervo.pasta_do_acervo() or Path("dados_locais/acervo")
    pasta = opcoes.pasta or raiz / "base"
    saida = opcoes.saida or raiz / "cafe"
    versao = exigir_versao_do_codigo()
    log.info("Versão do código: %s", versao)
    try:
        resumo = montar(pasta, raiz, saida, datetime.now(FUSO), versao)
    except Exception as erro:  # a noite não para em silêncio: o Kuma recebe o motivo
        log.exception("a montagem dos pacotes do café falhou")
        return _avisar([f"{type(erro).__name__}: {erro}"])
    log.info("pacotes do café: %s", ", ".join(resumo.pacotes) or "nenhum")
    return _avisar(resumo.falhas) if resumo.falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
