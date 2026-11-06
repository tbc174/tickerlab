"""Os números do pregão do dia a partir do que o arquivista guardou (plano
`2026-10-28-raio-x-todo-dia`, PR 4b; linha 444 da fila).

    python -m scripts.gerar_pregao_do_dia                       (os pregões que faltam ou mudaram)
    python -m scripts.gerar_pregao_do_dia --pregao 2026-10-27   (refaz um)

Roda no servidor de casa depois do arquivista das 2h, que guarda o COTAHIST do dia
(`b3-cotahist-dia`), o boletim PR (`b3-boletim-pr`) e o Ibovespa (`b3-ibov-diario`). Acha os arquivos
pelo manifesto do acervo (a versão mais nova de cada um) e grava `<acervo>/pregao/AAAA-MM-DD.json`: o
`resumo_do_pregao`, o `evento` (por que o pregão é dia de evento, ou nada: `src/eventos_do_pregao.py`)
e a `origem` (o que entrou), que diz quando refazer. A B3 corrigir o dia refaz; o
arquivo do Ibovespa ganhar um dia novo não refaz os pregões de antes, porque a conta é sobre a série até
aquele dia.

Só números: o texto sai do molde aprovado (`src/texto_do_pregao.py`), e o script confere antes de gravar
que esse texto sai. Arquivo que falta, número que não sai ou molde fora do aprovado fazem a última linha
da saída ser `FALHAS: ...` e a saída 1 (o `rodar-tarefa.sh` leva ao Kuma). A véspera vem do calendário da
B3, nunca do último arquivo guardado: um dia sem arquivo não pode virar uma variação de dois dias.

Roda: cron de casa pelo gerar-pregao.sh (todo dia às 6h45); outro script (avisar_raio_x.py); citado
em estudos.py.
"""

import argparse
import gzip
import hashlib
import json
import sys
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from base import historico, indices_b3, porta
from base import intradiario_b3 as b3
from base.parquet import gravar_atomico
from scripts.barras_b3_do_dia import Guardado, versoes_mais_novas
from src import acervo, eventos_do_pregao, pregao_do_dia, raio_x
from src import demonstracoes as dm
from src import rascunho_do_raio_x as rascunho
from src import texto_do_pregao as tp
from src.calendario_b3 import eh_pregao
from src.versao_do_codigo import versao_do_codigo

FONTE_DO_COTAHIST = "b3-cotahist-dia"
FONTE_DO_PR = "b3-boletim-pr"
FONTE_DO_IBOVESPA = "b3-ibov-diario"
NOME_DA_TAREFA = "pregao-do-dia"
PASTA_NO_ACERVO = "pregao"
PASTA_DO_RAIO_X = "raio-x"
# Os DFP e ITR que o arquivista guarda, um arquivo por ano (`base/historico.py`).
FONTES_DOS_BALANCOS = {"DFP": "cvm-hist-dfp", "ITR": "cvm-hist-itr"}
# Anos de balanço lidos antes do da véspera: em janeiro, os 12 meses ainda usam o DFP de dois anos antes.
ANOS_DE_BALANCO_ANTES = 2
# Muda quando a conta muda: o resumo guardado com outra versão é refeito.
VERSAO_DA_REGRA = 2
# O pregão do molde aprovado. Antes dele, os papéis de hoje não dizem quem negociava na época.
PRIMEIRO_PREGAO = date(2026, 10, 27)
CAMINHO_DO_CATALOGO = (
    Path(__file__).resolve().parent.parent / "conteudo" / "catalogo_de_ativos.csv"
)
CAMINHO_DOS_NOMES = (
    Path(__file__).resolve().parent.parent / "conteudo" / "nomes_curtos_b3.csv"
)
# O que um arquivo ruim levanta ao ser lido; os outros pregões da rodada continuam.
ERROS_DE_LEITURA = (ValueError, KeyError, OSError, zipfile.BadZipFile)


def caminho_do_resumo(pasta: Path, dia: date) -> Path:
    return pasta / PASTA_NO_ACERVO / f"{dia.isoformat()}.json"


def pregao_anterior(dia: date) -> date:
    """O pregão de antes de `dia`, pelo calendário da B3."""
    anterior = dia - timedelta(days=1)
    while not eh_pregao(anterior):
        anterior -= timedelta(days=1)
    return anterior


def caminho_do_rascunho(pasta: Path, dia: date, extensao: str) -> Path:
    return pasta / PASTA_NO_ACERVO / PASTA_DO_RAIO_X / f"{dia.isoformat()}{extensao}"


def arquivos_no_acervo(pasta: Path) -> dict[str, dict]:
    """Por fonte, a versão mais nova guardada: COTAHIST e PR por pregão; o Ibovespa, o DFP e o ITR
    por ano."""
    return versoes_mais_novas(
        pasta,
        {
            FONTE_DO_COTAHIST: b3.pregao_do_endereco,
            FONTE_DO_PR: b3.pregao_do_endereco,
            FONTE_DO_IBOVESPA: indices_b3.ano_do_endereco,
            **dict.fromkeys(FONTES_DOS_BALANCOS.values(), historico.ano_do_arquivo),
        },
    )


def _guardado(arquivos: dict[str, dict], fonte: str, dia: date) -> Guardado:
    guardado = arquivos[fonte].get(dia)
    if guardado is None:
        raise pregao_do_dia.FaltaNoBoletimError(
            f"{fonte} de {dia.isoformat()} não está no acervo"
        )
    return guardado


def _ibovespa(arquivos: dict[str, dict]) -> pd.Series:
    """A série inteira, de todos os anos guardados (vazia se não houver nenhum)."""
    anos = arquivos[FONTE_DO_IBOVESPA]
    if not anos:
        return pd.Series(name="ibovespa", dtype="float64")
    return indices_b3.serie_dos_anos(
        {ano: _original(guardado.caminho) for ano, guardado in anos.items()}
    )


def _original(caminho: Path) -> bytes:
    """O arquivo como veio da fonte: o arquivista guarda o JSON em gzip (`.json.gz`)."""
    guardado = caminho.read_bytes()
    return gzip.decompress(guardado) if caminho.suffix == ".gz" else guardado


def _conferir_o_indice(
    arquivos: dict[str, dict], serie: pd.Series, dia: date, vespera: date
) -> None:
    """A conta da história compara com todos os anos: um ano sem arquivo mudaria o resultado sem
    avisar. E a véspera tem de estar na série, ou a variação do dia seria sobre dois pregões."""
    faltam = [
        str(ano)
        for ano in range(indices_b3.PRIMEIRO_ANO, dia.year + 1)
        if ano not in arquivos[FONTE_DO_IBOVESPA]
    ]
    if faltam:
        raise pregao_do_dia.FaltaNoBoletimError(
            f"{FONTE_DO_IBOVESPA}: faltam os anos {', '.join(faltam)}"
        )
    if pd.Timestamp(vespera) not in serie.index:
        raise pregao_do_dia.FaltaNoBoletimError(
            f"o Ibovespa de {vespera.isoformat()} não está na série"
        )


def _origem(
    arquivos: dict[str, dict],
    serie: pd.Series,
    calendario: list[eventos_do_pregao.EventoMarcado],
    dia: date,
    vespera: date,
) -> dict[str, object]:
    """O que entra no resumo do pregão. Levanta `FaltaNoBoletimError` se faltar alguma coisa.

    Do calendário, só as datas que caem no pregão: data nova de outro dia não refaz este."""
    _conferir_o_indice(arquivos, serie, dia, vespera)
    ate_o_dia = serie[serie.index <= pd.Timestamp(dia)].to_csv()
    marcados = eventos_do_pregao.eventos_do_pregao(dia, vespera, calendario)
    return {
        "versao_da_regra": VERSAO_DA_REGRA,
        "sha256_do_cotahist": _guardado(arquivos, FONTE_DO_COTAHIST, dia).sha256,
        "sha256_do_cotahist_da_vespera": _guardado(
            arquivos, FONTE_DO_COTAHIST, vespera
        ).sha256,
        "sha256_do_pr": _guardado(arquivos, FONTE_DO_PR, dia).sha256,
        "sha256_do_ibovespa_ate_o_dia": hashlib.sha256(ate_o_dia.encode()).hexdigest(),
        "eventos_marcados": [f"{e.data.isoformat()} {e.evento}" for e in marcados],
    }


def _em_dia(caminho: Path, origem: dict[str, object]) -> bool:
    if not caminho.exists():
        return False
    return json.loads(caminho.read_text("utf-8")).get("origem") == origem


def _papeis(pasta: Path, vespera: date) -> pd.DataFrame:
    nomes = pd.read_csv(CAMINHO_DOS_NOMES, comment="#")
    with porta.abrir(pasta / "base") as base:
        tickers = base.ler(
            "tickers_no_tempo",
            colunas=["codigo", "cnpj", "inicio_negociacao", "fim_negociacao"],
        )
        cadastro = base.ler("fca_geral", colunas=["cnpj", "setor", "conhecido_em"])
    return pregao_do_dia.tabela_de_papeis(
        catalogo=pd.read_csv(CAMINHO_DO_CATALOGO, comment="#"),
        tickers=tickers,
        cadastro=cadastro,
        nomes_curtos=dict(zip(nomes["simbolo"], nomes["empresa"], strict=True)),
        ate=vespera,
    )


def _empresas(
    dia: date, vespera: date, arquivos: dict[str, dict], pasta: Path
) -> pd.DataFrame:
    """A tabela do pregão (`pregao_do_dia.variacoes_das_empresas`) dos COTAHIST da véspera e do dia."""
    cotahist_da_vespera = b3.ler_cotahist(
        _guardado(arquivos, FONTE_DO_COTAHIST, vespera).caminho
    )
    cotahist = b3.ler_cotahist(_guardado(arquivos, FONTE_DO_COTAHIST, dia).caminho)
    return pregao_do_dia.variacoes_das_empresas(
        cotahist_da_vespera,
        cotahist,
        _papeis(pasta, vespera),
        pregao_do_dia.codigos_com_evento(cotahist_da_vespera, cotahist),
    )


def montar_resumo(
    dia: date,
    vespera: date,
    empresas: pd.DataFrame,
    arquivos: dict[str, dict],
    serie: pd.Series,
    calendario: list[eventos_do_pregao.EventoMarcado],
) -> dict:
    """O resumo do pregão e o motivo do dia de evento, sem gravar. Confere que o texto aprovado sai
    destes números."""
    resumo: dict[str, Any] = pregao_do_dia.resumo_do_pregao(
        pregao_do_dia.EntradasDoPregao(
            dia=dia,
            vespera=vespera,
            empresas=empresas,
            ibovespa=serie,
            contratos=b3.ler_contratos_do_pr(
                _guardado(arquivos, FONTE_DO_PR, dia).caminho
            ),
        )
    )
    tp.texto_do_pregao(resumo, tp.ler_molde())
    resumo["evento"] = eventos_do_pregao.motivo_do_evento(
        dia, vespera, resumo["ibovespa"]["variacao"], calendario
    )
    return resumo


def _gravar(caminho: Path, resumo: dict, origem: dict[str, object]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        **resumo,
        "origem": origem,
        "processado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "versao_do_codigo": versao_do_codigo(),
    }
    texto = json.dumps(registro, ensure_ascii=False, indent=1)
    gravar_atomico(caminho, lambda p: p.write_text(texto, "utf-8"))


def balancos_do_acervo(
    arquivos: dict[str, dict], empresas: pd.DataFrame, vespera: date
) -> pd.DataFrame | None:
    """Dívida líquida e EBITDA das empresas do pregão, dos DFP e ITR guardados, só o que era público
    na véspera (`raio_x.balancos_na_vespera`). None sem nenhum arquivo: o rascunho diz que ficou sem
    a conta da dívida. O ano que falta (o DFP do ano corrente ainda não existe) só fica de fora."""
    cnpjs = set(empresas["cnpj"].dropna())
    contas, documentos = [], []
    for documento, fonte in FONTES_DOS_BALANCOS.items():
        for ano in range(vespera.year - ANOS_DE_BALANCO_ANTES, vespera.year + 1):
            guardado = arquivos[fonte].get(ano)
            if guardado is None:
                continue
            do_ano, indice = dm.ler_demonstracoes(
                _original(guardado.caminho), documento
            )
            contas.append(do_ano[do_ano["cnpj"].isin(cnpjs)])
            documentos.append(indice[indice["cnpj"].isin(cnpjs)])
    if not contas:
        return None
    return raio_x.balancos_na_vespera(
        pd.concat(contas, ignore_index=True),
        pd.concat(documentos, ignore_index=True),
        vespera,
    )


def gravar_rascunho_do_raio_x(
    dia: date,
    vespera: date,
    empresas: pd.DataFrame,
    serie: pd.Series,
    arquivos: dict[str, dict],
    pasta: Path,
) -> None:
    """O Raio-X do dia de evento em JSON, HTML e PDF, no acervo. Não publica: espera o "pode"."""
    saida = raio_x.raio_x_do_pregao(
        dia, vespera, empresas, serie, balancos_do_acervo(arquivos, empresas, vespera)
    )
    texto = json.dumps(saida, ensure_ascii=False, indent=1, allow_nan=False)
    pagina = rascunho.em_html(saida)
    pdf = rascunho.em_pdf(saida, datetime.now(ZoneInfo(b3.FUSO_DA_B3)))
    caminho = caminho_do_rascunho(pasta, dia, ".json")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    gravar_atomico(
        caminho.with_suffix(".html"), lambda p: p.write_text(pagina, "utf-8")
    )
    gravar_atomico(caminho.with_suffix(".pdf"), lambda p: p.write_bytes(pdf))
    # o JSON por último: é ele que diz que o rascunho saiu inteiro
    gravar_atomico(caminho, lambda p: p.write_text(texto, "utf-8"))
    print(
        f"{dia}: rascunho do Raio-X em {PASTA_NO_ACERVO}/{PASTA_DO_RAIO_X}/{dia.isoformat()}, "
        'esperando o "pode"',
        flush=True,
    )


def _falta_o_rascunho(caminho_do_resumo: Path, pasta: Path, dia: date) -> bool:
    """Dia de evento cujo rascunho não saiu (a rodada anterior falhou nele): refaz."""
    evento = json.loads(caminho_do_resumo.read_text("utf-8")).get("evento")
    return evento is not None and not caminho_do_rascunho(pasta, dia, ".json").exists()


def gerar_pregao(
    dia: date,
    arquivos: dict[str, dict],
    serie: pd.Series,
    calendario: list[eventos_do_pregao.EventoMarcado],
    pasta: Path,
    forcar: bool = False,
) -> bool:
    """Grava o resumo de `dia` se ele falta ou mudou. True se gravou."""
    vespera = pregao_anterior(dia)
    origem = _origem(arquivos, serie, calendario, dia, vespera)
    caminho = caminho_do_resumo(pasta, dia)
    if (
        not forcar
        and _em_dia(caminho, origem)
        and not _falta_o_rascunho(caminho, pasta, dia)
    ):
        return False
    empresas = _empresas(dia, vespera, arquivos, pasta)
    resumo = montar_resumo(dia, vespera, empresas, arquivos, serie, calendario)
    _gravar(caminho, resumo, origem)
    print(
        f"{dia}: Ibovespa {resumo['ibovespa']['variacao']:+.2%}, "
        f"{sum(resumo['amplitude'][k] for k in ('subiram', 'cairam', 'estaveis'))} empresas, "
        f"{len(resumo['a_conferir'])} a conferir"
        + (", dia de evento" if resumo["evento"] else ""),
        flush=True,
    )
    if resumo["evento"]:
        gravar_rascunho_do_raio_x(dia, vespera, empresas, serie, arquivos, pasta)
    return True


def pregoes_da_rodada(arquivos: dict[str, dict]) -> list[date]:
    """Os pregões com COTAHIST guardado, do primeiro aprovado em diante (arquivo em feriado não entra)."""
    return [
        dia
        for dia in sorted(arquivos[FONTE_DO_COTAHIST])
        if dia >= PRIMEIRO_PREGAO and eh_pregao(dia)
    ]


def falta_o_ultimo_pregao(arquivos: dict[str, dict], hoje: date) -> list[str]:
    """Sem o COTAHIST do último pregão fechado, a rodada não teria nada a dizer e não avisaria."""
    ultimo = pregao_anterior(hoje)
    if ultimo < PRIMEIRO_PREGAO or ultimo in arquivos[FONTE_DO_COTAHIST]:
        return []
    return [
        f"{NOME_DA_TAREFA} {ultimo}: {FONTE_DO_COTAHIST} de {ultimo} não está no acervo"
    ]


def _molde_fora_do_aprovado() -> list[str]:
    impressao = tp.impressao_digital(tp.ler_molde())
    if impressao == tp.IMPRESSAO_DO_MOLDE_APROVADO:
        return []
    return [f"{NOME_DA_TAREFA}: o molde do texto não é o aprovado; nada foi gerado"]


def gerar_os_pregoes(
    dias: list[date], arquivos: dict[str, dict], pasta: Path, forcar: bool = False
) -> list[str]:
    """Gera os pregões e devolve os motivos dos que não saíram. Um não impede o outro."""
    try:
        serie = _ibovespa(arquivos)
    except ERROS_DE_LEITURA as erro:
        return [f"{NOME_DA_TAREFA}: o Ibovespa guardado não abriu ({erro})"]
    try:
        calendario = eventos_do_pregao.ler_calendario()
    except ERROS_DE_LEITURA as erro:
        return [f"{NOME_DA_TAREFA}: o calendário de eventos não abriu ({erro})"]
    falhas = []
    for dia in dias:
        try:
            gerar_pregao(dia, arquivos, serie, calendario, pasta, forcar)
        except ERROS_DE_LEITURA as erro:
            falhas.append(f"{NOME_DA_TAREFA} {dia}: {erro}")
    return falhas


def _opcoes(argumentos: list[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    leitor.add_argument("--pregao", type=date.fromisoformat, default=None)
    leitor.add_argument(
        "--hoje", type=date.fromisoformat, default=None, help="para testes"
    )
    return leitor.parse_args(argumentos)


def main(argumentos: list[str] | None = None) -> int:
    """0 = tudo certo (inclusive nada a fazer ou dia sem pregão); 1 = algum pregão não saiu."""
    opcoes = _opcoes(argumentos)
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        print("Acervo desligado: nada a gerar.")
        return 0
    if opcoes.pregao is not None and not eh_pregao(opcoes.pregao):
        print(f"{opcoes.pregao}: não houve pregão, nada a gerar.")
        return 0
    hoje = opcoes.hoje or datetime.now(ZoneInfo(b3.FUSO_DA_B3)).date()
    arquivos = arquivos_no_acervo(pasta)
    dias = [opcoes.pregao] if opcoes.pregao else pregoes_da_rodada(arquivos)
    falhas = _molde_fora_do_aprovado()
    if not falhas:
        falhas = gerar_os_pregoes(dias, arquivos, pasta, forcar=bool(opcoes.pregao))
        falhas += falta_o_ultimo_pregao(arquivos, hoje)
    if falhas:
        print("FALHAS: " + "; ".join(falhas))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
