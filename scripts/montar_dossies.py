"""Monta as fichas do dossiê da empresa a partir da base (plano de 17/10/2026, PR 1).

    python -m scripts.montar_dossies                   (a base do acervo; grava em <acervo>/dossies)
    python -m scripts.montar_dossies --pasta <base>    (outra pasta da base)
    python -m scripts.montar_dossies --saida <pasta>   (ensaio: grava fora do acervo)

Lê só o que a base já tem (nenhuma coleta nova) e grava `<saida>/<AAAA-MM-DD>/<cnpj>.json`, uma ficha
por companhia com ticker que vale hoje e tem alguma seção, e o `manifesto.json`: a versão do esquema e do
código, o hash de cada tabela lida (ADR 0078: dá para refazer e conferir) e as tabelas que faltaram. A
pasta do dia é montada ao lado e só troca de nome no fim: quem lê nunca vê uma pasta pela metade. As
regras do que pode entrar ficam em `base/dossie.py`.

Uma seção que quebra numa empresa não derruba as outras nem a noite; uma ficha com pessoa não é gravada.
Roda toda noite no servidor de casa, depois da rede: saída 0 tudo certo; 1 alguma falha, com a última
linha `FALHAS: ...` (vai para o aviso do Kuma), como `scripts/montar_rede.py`.
"""

import argparse
import json
import logging
import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

from base import dossie
from base.parquet import arquivos_atuais
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger(__name__)
FUSO = ZoneInfo("America/Sao_Paulo")  # o dia da pasta é o do Brasil, não o do servidor
TAMANHO_MAXIMO_DO_RESUMO = 300  # o resumo vai no endereço do push do Kuma
VAZIA = pd.DataFrame()
Filtro = list[tuple[str, str, str]]


@dataclass
class Leitor:
    """Lê as tabelas da base e anota o hash de cada uma e as que faltaram (vão no manifesto)."""

    pasta: Path
    tabelas: dict[str, str | None] = field(default_factory=dict)
    faltando: list[str] = field(default_factory=list)

    def _anotar(self, arquivo: Path) -> None:
        nome = arquivo.relative_to(self.pasta).with_suffix("").as_posix()
        manifesto = arquivo.with_suffix(".json")
        self.tabelas[nome] = (
            json.loads(manifesto.read_text(encoding="utf-8")).get("sha256_da_tabela")
            if manifesto.exists()
            else None
        )

    def _ler(
        self, arquivo: Path, colunas: list[str] | None, filtro: Filtro | None
    ) -> pd.DataFrame:
        existentes = pq.read_schema(arquivo).names
        escolhidas = (
            None if colunas is None else [c for c in colunas if c in existentes]
        )
        self._anotar(arquivo)
        return pq.read_table(
            arquivo, columns=escolhidas, filters=filtro or None
        ).to_pandas()

    def arquivo(self, relativo: str, colunas: list[str] | None = None) -> pd.DataFrame:
        """Um Parquet da base (vazio e anotado como faltando, se não existe)."""
        arquivo = self.pasta / f"{relativo}.parquet"
        if not arquivo.exists():
            self.faltando.append(relativo)
            return VAZIA
        return self._ler(arquivo, colunas, None)

    def arquivos(
        self,
        relativo: str,
        colunas: list[str] | None = None,
        filtro: Filtro | None = None,
        pular: str = "",
    ) -> list[pd.DataFrame]:
        """Cada Parquet atual de uma pasta da base, sem as versões guardadas (vazia → faltando)."""
        arquivos = [
            a
            for a in arquivos_atuais(self.pasta / relativo)
            if not (pular and pular in a.name)
        ]
        if not arquivos:
            self.faltando.append(relativo)
        return [self._ler(a, colunas, filtro) for a in arquivos]

    def pasta_inteira(
        self, relativo: str, colunas: list[str] | None = None
    ) -> pd.DataFrame:
        partes = [p for p in self.arquivos(relativo, colunas) if not p.empty]
        return pd.concat(partes, ignore_index=True) if partes else VAZIA


@dataclass(frozen=True)
class Entradas:
    """As tabelas da base que o dossiê usa, de todas as empresas."""

    empresas: pd.DataFrame  # cnpj (só dígitos), empresa
    auditores: pd.DataFrame
    trocas: pd.DataFrame
    controladas: pd.DataFrame
    controladoras: pd.DataFrame
    ofertas_160: pd.DataFrame
    ofertas_antigas: pd.DataFrame
    painel: pd.DataFrame
    empresa_serie: pd.DataFrame
    eventos: pd.DataFrame
    series: dict[str, pd.DataFrame]
    pessoas: set[str]


def _empresas(tickers: pd.DataFrame) -> pd.DataFrame:
    """As companhias com algum ticker que vale hoje (o FCA mais recente ainda o mostra)."""
    if tickers.empty:
        return pd.DataFrame(columns=["cnpj", "empresa"])
    valendo = tickers[tickers["valido_ate"].isna()]
    tabela = pd.DataFrame(
        {"cnpj": dossie.digitos(valendo["cnpj"]), "empresa": valendo["empresa"]}
    )
    return tabela.drop_duplicates("cnpj").reset_index(drop=True)


def _pessoas(entidades: pd.DataFrame) -> set[str]:
    if entidades.empty:
        return set()
    pessoas = entidades[entidades["trata_como_pessoa"].fillna(False).astype(bool)]
    return {n for n in pessoas["nome"].dropna().map(dossie.normalizar_nome) if n}


def _filtro(serie: dossie.SerieDaAgencia) -> Filtro:
    return [(coluna, "=", valor) for coluna, valor in serie.filtros]


def ler_serie(leitor: Leitor, serie: dossie.SerieDaAgencia) -> pd.DataFrame:
    """(ano, chave, valor) de todo o mercado de uma agência, já no modo da série."""
    colunas = ["competencia", serie.chave, serie.valor]
    mensais = []
    for parte in leitor.arquivos(
        serie.pasta, colunas, _filtro(serie), serie.pular_arquivos
    ):
        if parte.empty:
            continue
        chave = parte[serie.chave].astype(str).str.strip()
        parte = pd.DataFrame(
            {
                "competencia": parte["competencia"],
                "chave": dossie.digitos(chave) if serie.chave_em_digitos else chave,
                "valor": pd.to_numeric(parte[serie.valor], errors="coerce"),
            }
        )
        mensais.append(
            parte.groupby(["competencia", "chave"], as_index=False)["valor"].sum()
        )
    if not mensais:
        return VAZIA
    juntas = pd.concat(mensais, ignore_index=True)
    juntas = juntas.groupby(["competencia", "chave"], as_index=False)["valor"].sum()
    return dossie.serie_anual(juntas, serie.modo)


def _controladoras(leitor: Leitor) -> tuple[pd.DataFrame, set[str]]:
    entidades = leitor.arquivo(
        "rede/entidades", ["id_entidade", "nome", "trata_como_pessoa"]
    )
    ligacoes = leitor.arquivo(
        "rede/ligacoes", ["de", "para", "tipo", "situacao", "fonte", "participacao"]
    )
    identificadores = leitor.arquivo(
        "rede/identificadores", ["id_entidade", "sistema", "valor", "ate"]
    )
    pessoas = _pessoas(entidades)
    if ligacoes.empty or entidades.empty or identificadores.empty:
        return VAZIA, pessoas
    return dossie.controladoras(ligacoes, entidades, identificadores), pessoas


def ler_entradas(leitor: Leitor) -> Entradas:
    """Tudo o que o dossiê lê da base, uma vez, para todas as empresas."""
    controladoras, pessoas = _controladoras(leitor)
    return Entradas(
        empresas=_empresas(
            leitor.arquivo("fca/tickers", ["cnpj", "empresa", "valido_ate"])
        ),
        auditores=leitor.pasta_inteira("auditores"),
        trocas=leitor.arquivo("trocas_de_auditor/trocas"),
        controladas=leitor.pasta_inteira("controladas"),
        controladoras=controladoras,
        ofertas_160=leitor.arquivo("ofertas/resolucao_160"),
        ofertas_antigas=leitor.arquivo("ofertas/antigas"),
        painel=leitor.pasta_inteira("fundos/painel_empresa"),
        empresa_serie=leitor.arquivo("empresa_serie/empresa_serie"),
        eventos=leitor.pasta_inteira(
            "eventos", ["cnpj", "rotulo", "assunto", "publicado_em", "link"]
        ),
        series={s.nome: ler_serie(leitor, s) for s in dossie.SERIES_DAS_AGENCIAS},
        pessoas=pessoas,
    )


def _por_cnpj(tabela: pd.DataFrame, coluna: str) -> dict[str, pd.DataFrame]:
    """A tabela separada por CNPJ (só dígitos), para cada empresa ler só as linhas dela."""
    if tabela.empty or coluna not in tabela.columns:
        return {}
    return {str(c): g for c, g in tabela.groupby(dossie.digitos(tabela[coluna]))}


Secao = Callable[[str], dict | None]


def _secoes(entradas: Entradas) -> dict[str, Secao]:
    """Cada seção como uma função do CNPJ, com as tabelas já separadas por empresa."""
    auditores = _por_cnpj(entradas.auditores, "cnpj")
    trocas = _por_cnpj(entradas.trocas, "cnpj")
    controladas = _por_cnpj(entradas.controladas, "cnpj_companhia")
    controladoras = _por_cnpj(entradas.controladoras, "cnpj")
    ofertas_160 = _por_cnpj(entradas.ofertas_160, "cnpj_emissor")
    ofertas_antigas = _por_cnpj(entradas.ofertas_antigas, "cnpj_emissor")
    painel = _por_cnpj(entradas.painel, "cnpj")
    empresa_serie = _por_cnpj(entradas.empresa_serie, "cnpj_companhia")
    eventos = _por_cnpj(entradas.eventos, "cnpj")
    return {
        "auditor_e_controladas": lambda c: dossie.secao_auditor_e_controladas(
            auditores.get(c, VAZIA),
            trocas.get(c, VAZIA),
            controladas.get(c, VAZIA),
            controladoras.get(c, VAZIA),
            entradas.pessoas,
        ),
        "ofertas_e_fundos": lambda c: dossie.secao_ofertas_e_fundos(
            ofertas_160.get(c, VAZIA),
            ofertas_antigas.get(c, VAZIA),
            painel.get(c, VAZIA),
        ),
        "setor_regulado": lambda c: dossie.secao_setor_regulado(
            empresa_serie.get(c, VAZIA), entradas.series
        ),
        "negocios": lambda c: dossie.secao_negocios(eventos.get(c, VAZIA)),
    }


@dataclass
class Resumo:
    empresas: int = 0
    fichas: int = 0
    falhas: list[str] = field(default_factory=list)


def _ficha(
    cnpj: str, empresa: str, secoes: dict[str, Secao], gerado_em: str, quebras: Counter
) -> dict | None:
    """A ficha de uma empresa (None: nenhuma seção); a seção que quebra fica de fora e é contada."""
    feitas = []
    for chave, montar_secao in secoes.items():
        try:
            feitas.append(montar_secao(cnpj))
        except Exception as erro:  # noqa: BLE001 (uma seção não derruba a ficha nem a noite)
            quebras[f"{chave}: {type(erro).__name__}: {erro}"] += 1
    ficha = dossie.montar_ficha(cnpj, empresa, feitas, gerado_em)
    return ficha if ficha["secoes"] else None


def _gravar_json(destino: Path, conteudo: dict) -> None:
    destino.write_text(
        json.dumps(conteudo, ensure_ascii=False, allow_nan=False, indent=None),
        encoding="utf-8",
    )


def _gravar_fichas(
    entradas: Entradas, pasta: Path, gerado_em: str, resumo: Resumo
) -> None:
    secoes = _secoes(entradas)
    quebras: Counter = Counter()
    for linha in entradas.empresas.itertuples(index=False):
        ficha = _ficha(str(linha.cnpj), str(linha.empresa), secoes, gerado_em, quebras)
        if ficha is None:
            continue
        try:
            dossie.conferir_sem_pessoas(ficha, entradas.pessoas)
            _gravar_json(pasta / f"{linha.cnpj}.json", ficha)
        except (dossie.PessoaNaFichaError, ValueError) as erro:
            resumo.falhas.append(f"{linha.cnpj}: {type(erro).__name__}")
            continue
        resumo.fichas += 1
    resumo.falhas += [f"{quebra} ({n} empresas)" for quebra, n in quebras.items()]


def _trocar_pasta(montando: Path, destino: Path) -> None:
    """A pasta do dia aparece inteira de uma vez; a de antes, do mesmo dia, sai."""
    if destino.exists():
        shutil.rmtree(destino)
    montando.rename(destino)


def montar(
    pasta: Path, saida: Path, agora: pd.Timestamp, versao_do_codigo: str
) -> Resumo:
    """Grava as fichas e o manifesto em `<saida>/<dia>`; devolve quantas e o que falhou."""
    leitor = Leitor(pasta)
    entradas = ler_entradas(leitor)
    resumo = Resumo(empresas=len(entradas.empresas))
    if entradas.empresas.empty:
        resumo.falhas.append("fca/tickers: sem o universo das empresas")
        return resumo
    dia = agora.strftime("%Y-%m-%d")
    montando = saida / f".{dia}.montando"
    shutil.rmtree(montando, ignore_errors=True)
    montando.mkdir(parents=True)
    _gravar_fichas(entradas, montando, agora.isoformat(), resumo)
    _gravar_json(
        montando / "manifesto.json",
        {
            "versao_do_esquema": dossie.VERSAO_DO_ESQUEMA,
            "gerado_em": agora.isoformat(),
            "versao_do_codigo": versao_do_codigo,
            "empresas": resumo.empresas,
            "fichas": resumo.fichas,
            "tabelas": dict(sorted(leitor.tabelas.items())),
            "faltando": sorted(set(leitor.faltando)),
            "falhas": resumo.falhas,
        },
    )
    _trocar_pasta(montando, saida / dia)
    return resumo


def _avisar(problemas: list[str]) -> int:
    linha = "FALHAS: dossiês: " + "; ".join(problemas)
    print(linha[:TAMANHO_MAXIMO_DO_RESUMO])
    return 1


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--pasta", type=Path, default=None, help="pasta da base")
    argumentos.add_argument(
        "--saida", type=Path, default=None, help="onde gravar as fichas"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    raiz = acervo.pasta_do_acervo() or Path("dados_locais/acervo")
    pasta = opcoes.pasta or raiz / "base"
    saida = opcoes.saida or raiz / "dossies"
    versao = exigir_versao_do_codigo()
    log.info("Versão do código: %s", versao)
    try:
        resumo = montar(pasta, saida, pd.Timestamp(datetime.now(FUSO)), versao)
    except Exception as erro:  # a noite não para em silêncio: o Kuma recebe o motivo
        log.exception("a montagem dos dossiês falhou")
        return _avisar([f"{type(erro).__name__}: {erro}"])
    log.info("dossiês: %d fichas de %d empresas", resumo.fichas, resumo.empresas)
    return _avisar(resumo.falhas) if resumo.falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
