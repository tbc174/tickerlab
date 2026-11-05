"""Coleta e carga dos contratos e despesas por CNPJ de GO, MS e da capital de SP (linha 658, API dados C5).

    python -m scripts.carga_go_ms_sp --baixar <pasta nova e vazia> [--fontes go ms sp] [--anos 2023 2024 2025 2026]
    python -m scripts.carga_go_ms_sp --origem <pasta baixada>                (grava no acervo)
    python -m scripts.carga_go_ms_sp --origem <pasta> --pasta /tmp/base --forcar

Os leitores são os de `base/contratos_go_ms_sp.py` (só pessoa jurídica, sem nome, CPF, endereço nem texto livre).

`--baixar` lista os recursos CSV de cada portal CKAN (`package_search`) e baixa um arquivo por mês (GO e MS) ou
por ano (SP capital), com pausa entre os pedidos (o `robots.txt` do GO pede 10 s) e retomada de onde parou
(`baixados.jsonl`; a data do download vira o `disponivel_em`). O mês e o ano vêm do nome do recurso; recurso
sem período legível é pulado e anotado no log. Os portais:
- **GO**, licenças ambientais do Ipê (dadosabertos.go.gov.br, CC BY);
- **MS**, despesas por credor (www.dados.ms.gov.br, licença a confirmar);
- **SP capital**, extrato de contratos (dados.prefeitura.sp.gov.br, CC0).

`--origem` grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`), um Parquet por ano em
`<base>/<tabela>/<ano>.parquet`: `go_licencas_ipe`, `ms_despesas` e `sp_capital_contratos`. **Na primeira carga
do SP capital o mapa de cabeçalhos é conferido** (o CSV não foi amostrado): se o arquivo tem linhas e o
documento da contratada ou o número do contrato não é achado, a carga para e mostra o cabeçalho que veio, em
vez de gravar uma tabela vazia. Os arquivos baixados são dados de fora: ficam numa pasta nova, nunca no
repositório, e esta carga os lê com o Python em modo isolado (`python -I`).

Recusa rodar sem a versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando.
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from base import contratos_go_ms_sp
from base.contratos_go_ms_sp import _linhas_do_csv
from base.contratos_tces import Leitura, Linha
from base.parquet import GRAVADO, gravar_com_versoes
from scripts.carga_tce_rn import BAIXADOS, Baixador, Buscar, _ja_baixados
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_go_ms_sp")
TEMPO_LIMITE = 180
# o robots.txt do GO pede Crawl-delay de 10 s (lido em 04/11/2026); vale para as três fontes
PAUSA_PADRAO_EM_SEGUNDOS = 10.0
ANOS_PADRAO = (2023, 2024, 2025, 2026)
FONTES = ("go", "ms", "sp")
RECURSOS_POR_PAGINA = 100

# portal CKAN, consulta que acha o conjunto e a palavra que o nome do pacote precisa ter
PORTAIS = {
    "go": (
        "https://dadosabertos.go.gov.br",
        "licencas ambientais ipe",
        "licencas-ambientais-ipe",  # o pacote do SGA (outro sistema) repete os meses de 2026
    ),
    # o MS só atende em `www.` (o endereço sem `www` não resolve; conferido em 05/11/2026)
    "ms": ("https://www.dados.ms.gov.br", "despesas credor", "despesa"),
    "sp": (
        "https://dados.prefeitura.sp.gov.br",
        "contratos extrato",
        "compras-e-licitacoes",  # o pacote traz o extrato de contratos por ano
    ),
}
ANO_MES = re.compile(r"(20\d{2})[-_./ ]?(0[1-9]|1[0-2])(?!\d)")
MES_ANO = re.compile(r"(?<!\d)(0[1-9]|1[0-2])[-_./ ]?(20\d{2})")
SO_ANO = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

# tabela gravada: a chave que ordena e identifica a linha
CHAVES = {
    "go_licencas_ipe": ["numero_licenca", "versao", "cnpj", "tipo_licenca"],
    "ms_despesas": [
        "ano",
        "mes",
        "numero_documento",
        "cnpj",
        "orgao",
        "elemento_despesa",
        "empenhado",
        "liquidado",
        "pago",
    ],
    "sp_capital_contratos": [
        "numero_contrato",
        "numero_processo",
        "cnpj",
        "data_assinatura",
    ],
}
ORIGENS = {
    "go_licencas_ipe": ("go", PORTAIS["go"][0]),
    "ms_despesas": ("ms", PORTAIS["ms"][0]),
    "sp_capital_contratos": ("sp", PORTAIS["sp"][0]),
}
# campos do SP capital sem os quais a tabela não serve: se nenhum é achado, o mapa de cabeçalhos está errado
CAMPOS_OBRIGATORIOS_SP = ("numero_contrato",)

Porcao = tuple[str, str, Leitura]  # (tabela, ano, o que o leitor achou)


def _buscar(endereco: str) -> bytes:
    resposta = rede.get_com_agente(endereco, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    return resposta.content


# ------------------------------------------------------------------------------------ coleta


def periodo_do_recurso(
    nome: str, endereco: str, com_mes: bool
) -> tuple[int, int] | None:
    """`(ano, mês)` lido do nome do recurso (ou do endereço); mês 0 quando a fonte é anual.

    Devolve None quando não acha o período: o recurso é pulado, nunca adivinhado.
    """
    for texto in (nome, endereco.rsplit("/", 1)[-1]):
        if com_mes:
            if achado := ANO_MES.search(texto):
                return int(achado[1]), int(achado[2])
            if achado := MES_ANO.search(texto):
                return int(achado[2]), int(achado[1])
        elif achado := SO_ANO.search(texto):
            return int(achado[1]), 0
    return None


def recursos_csv(corpo: bytes, palavra: str) -> Iterator[tuple[str, str]]:
    """`(nome, endereço)` dos recursos CSV dos pacotes cujo nome tem `palavra`."""
    for pacote in json.loads(corpo)["result"]["results"]:
        if palavra not in str(pacote.get("name", "")).lower():
            continue
        for recurso in pacote.get("resources", []):
            endereco = str(recurso.get("url") or "")
            eh_csv = str(recurso.get("format", "")).lower() == "csv"
            if endereco and (eh_csv or endereco.lower().endswith(".csv")):
                yield str(recurso.get("name") or ""), endereco


def _baixar_fonte(baixador: Baixador, fonte: str, anos: Iterable[int]) -> None:
    portal, consulta, palavra = PORTAIS[fonte]
    corpo = baixador.pegar(
        f"{fonte}/indice.json",
        f"{portal}/api/3/action/package_search?q={quote(consulta)}&rows={RECURSOS_POR_PAGINA}",
    )
    anos = set(anos)
    for nome, endereco in recursos_csv(corpo, palavra):
        periodo = periodo_do_recurso(nome, endereco, com_mes=fonte != "sp")
        if periodo is None:
            log.warning("%s: recurso sem período no nome, pulado: %s", fonte, nome)
            continue
        ano, mes = periodo
        if ano not in anos:
            continue
        sufixo = f"{ano}-{mes:02d}" if mes else str(ano)
        baixador.pegar(f"{fonte}/{sufixo}.csv", endereco)


def baixar(
    destino: Path,
    fontes: Iterable[str] = FONTES,
    anos: Iterable[int] = ANOS_PADRAO,
    pausa: float = PAUSA_PADRAO_EM_SEGUNDOS,
    buscar: Buscar = _buscar,
    hoje: date | None = None,
) -> Baixador:
    """Baixa o que falta de cada fonte pedida; devolve o baixador (com `feitos`)."""
    if (
        destino.exists()
        and any(destino.iterdir())
        and not (destino / BAIXADOS).exists()
    ):
        raise SystemExit(f"{destino} não está vazia: baixe numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    baixador = Baixador(destino, buscar, pausa, hoje)
    anos = list(anos)
    for fonte in fontes:
        _baixar_fonte(baixador, fonte, anos)
    return baixador


# ------------------------------------------------------------------------------------ carga


def conferir_mapa_sp(corpo: bytes, leitura: Leitura, arquivo: str) -> None:
    """Para a carga se o CSV do SP capital tem linhas e o mapa de cabeçalhos não achou o que importa."""
    linhas = _linhas_do_csv(corpo)
    if not linhas:
        return
    cabecalho = ", ".join(linhas[0])
    if not leitura.linhas:
        raise SystemExit(
            f"SP capital {arquivo}: nenhum CNPJ achado em {len(linhas)} linhas; "
            f"confira DOCUMENTO_SP com o cabeçalho: {cabecalho}"
        )
    for campo in CAMPOS_OBRIGATORIOS_SP:
        if not any(linha.get(campo) for linha in leitura.linhas):
            raise SystemExit(
                f"SP capital {arquivo}: o campo {campo} não foi achado; "
                f"confira APELIDOS_SP com o cabeçalho: {cabecalho}"
            )
    for campo in (*contratos_go_ms_sp.DATAS_SP, "valor"):
        if not any(linha.get(campo) for linha in leitura.linhas):
            log.warning(
                "SP capital %s: o campo %s ficou vazio; cabeçalho: %s",
                arquivo,
                campo,
                cabecalho,
            )


def _quando(feitos: dict[str, str], arquivo: str) -> date:
    return date.fromisoformat(feitos[arquivo])


def _arquivos(feitos: dict[str, str], fonte: str) -> list[str]:
    return sorted(
        a for a in feitos if a.startswith(f"{fonte}/") and a != f"{fonte}/indice.json"
    )


def _do_go(origem: Path, feitos: dict[str, str]) -> list[Porcao]:
    return [
        (
            "go_licencas_ipe",
            Path(arquivo).stem[:4],
            contratos_go_ms_sp.ler_go_licencas(
                (origem / arquivo).read_bytes(), _quando(feitos, arquivo)
            ),
        )
        for arquivo in _arquivos(feitos, "go")
    ]


def _do_ms(origem: Path, feitos: dict[str, str]) -> list[Porcao]:
    porcoes = []
    for arquivo in _arquivos(feitos, "ms"):
        ano, mes = Path(arquivo).stem.split("-")
        leitura = contratos_go_ms_sp.ler_ms_despesas(
            (origem / arquivo).read_bytes(),
            int(ano),
            int(mes),
            _quando(feitos, arquivo),
        )
        porcoes.append(("ms_despesas", ano, leitura))
    return porcoes


def _do_sp(origem: Path, feitos: dict[str, str]) -> list[Porcao]:
    porcoes = []
    for arquivo in _arquivos(feitos, "sp"):
        corpo = (origem / arquivo).read_bytes()
        leitura = contratos_go_ms_sp.ler_sp_capital_contratos(
            corpo, _quando(feitos, arquivo)
        )
        conferir_mapa_sp(corpo, leitura, arquivo)
        porcoes.append(("sp_capital_contratos", Path(arquivo).stem, leitura))
    return porcoes


def montar(origem: Path) -> dict[tuple[str, str], pd.DataFrame]:
    """`(tabela, ano) -> linhas`, juntando os arquivos baixados de cada fonte."""
    feitos = _ja_baixados(origem)
    porcoes = [
        *_do_go(origem, feitos),
        *_do_ms(origem, feitos),
        *_do_sp(origem, feitos),
    ]
    juntas: dict[tuple[str, str], list[Linha]] = {}
    for tabela, ano, leitura in porcoes:
        juntas.setdefault((tabela, ano), []).extend(leitura.linhas)
    return {
        chave: _tabela(linhas, CHAVES[chave[0]])
        for chave, linhas in juntas.items()
        if linhas
    }


def _tabela(linhas: list[Linha], ordem: list[str]) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas)
    return tabela.sort_values(ordem, kind="stable").reset_index(drop=True)


def _origem(origem: Path, tabela: str, ano: str) -> dict[str, str]:
    """A origem do manifesto: o endereço do portal e o SHA-256 dos arquivos da tabela e do ano."""
    pasta, portal = ORIGENS[tabela]
    resumo = hashlib.sha256()
    for arquivo in sorted((origem / pasta).glob(f"{ano}*.csv")):
        resumo.update(arquivo.name.encode() + arquivo.read_bytes())
    return {"url": portal, "sha256": resumo.hexdigest()}


def carregar(origem: Path, saida: Path, forcar: bool = False) -> dict[str, str]:
    """Grava um Parquet por tabela e ano; devolve `tabela/ano -> gravado|igual`."""
    resultado: dict[str, str] = {}
    for (tabela, ano), linhas in montar(origem).items():
        resultado[f"{tabela}/{ano}"] = gravar_com_versoes(
            lambda t=linhas: t,
            saida / tabela / ano,
            [_origem(origem, tabela, ano)],
            CHAVES[tabela],
            forcar=forcar,
        )
    return resultado


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--baixar", type=Path, default=None)
    argumentos.add_argument("--origem", type=Path, default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--fontes", nargs="+", choices=FONTES, default=list(FONTES))
    argumentos.add_argument("--anos", type=int, nargs="+", default=list(ANOS_PADRAO))
    argumentos.add_argument("--pausa", type=float, default=PAUSA_PADRAO_EM_SEGUNDOS)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.baixar:
        baixar(opcoes.baixar, opcoes.fontes, opcoes.anos, opcoes.pausa)
        return 0
    if not opcoes.origem:
        argumentos.error("passe --baixar <pasta nova> ou --origem <pasta baixada>")
    if not (opcoes.origem / BAIXADOS).exists():
        log.error("falta %s em %s", BAIXADOS, opcoes.origem)
        return 1
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    resultado = carregar(opcoes.origem, saida, opcoes.forcar)
    log.info(
        "GO, MS e SP capital: %d tabelas/anos (%d gravados)",
        len(resultado),
        sum(r == GRAVADO for r in resultado.values()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
