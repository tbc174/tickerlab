"""Coleta e carga do TCE-RN (API de dados abertos) para a base: unidades, licitações e participantes (linha 662).

    python -m scripts.carga_tce_rn --baixar <pasta nova e vazia> [--anos 2023 2024 2025 2026] [--pausa 1.0]
    python -m scripts.carga_tce_rn --origem <pasta baixada>                (grava no acervo)
    python -m scripts.carga_tce_rn --origem <pasta> --pasta /tmp/base --forcar

`--baixar`, nesta ordem: o cadastro de unidades (923; 586 com CNPJ), as licitações de cada unidade em cada ano
e, para cada lote com id, os participantes (`ParticipantesDeLicitacao`, um pedido por lote, com pausa entre
os pedidos). A API não traz a data em que cada linha ficou pública: `baixados.jsonl` guarda a data do download
de cada arquivo e ela vira o `disponivel_em`. A coleta retoma de onde parou (o que já está em `baixados.jsonl`
não é pedido de novo). Os arquivos baixados são dados de fora: ficam numa pasta nova, nunca no repositório, e
esta carga os lê com o Python em modo isolado (`python -I`).

`--origem` grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`):
- `tce_rn/unidades.parquet`: o cadastro de unidades (CNPJ só nas que têm um válido);
- `tce_rn/licitacoes/<ano>.parquet`: uma linha por lote;
- `tce_rn/participantes/<ano>.parquet`: todos os participantes com CNPJ válido, com a classificação
  (`ordem_classificacao` 1 é o vencedor); o ano é o da licitação do lote.

Licença a confirmar, só uso interno (ADR 0102, Emenda 2); nada é perguntado à fonte. Recusa rodar sem a
versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando.

Roda: outro script (carga_go_ms_sp.py, carga_tces.py).
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import tce_rn
from base.contratos_tces import Linha
from base.parquet import GRAVADO, gravar_com_versoes
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_tce_rn")
FUSO = ZoneInfo("America/Sao_Paulo")
API = "https://apidadosabertos.tce.rn.gov.br/api"
ENDERECO_UNIDADES = f"{API}/InformacoesBasicasApi/JurisdicionadosTCE/json"
ENDERECO_LICITACOES = f"{API}/ProcedimentosLicitatoriosApi/LicitacaoPublica/json"
ENDERECO_PARTICIPANTES = (
    f"{API}/ProcedimentosLicitatoriosApi/ParticipantesDeLicitacao/json"
)
UNIDADES = "unidades.json"
PASTA_LICITACOES = "licitacoes"
PASTA_PARTICIPANTES = "participantes"
BAIXADOS = "baixados.jsonl"
ORDEM_DAS_UNIDADES = ["id_unidade"]
ORDEM_DAS_LICITACOES = ["id_unidade", "numero_licitacao", "numero_lote", "id_lote"]
ORDEM_DOS_PARTICIPANTES = ["id_lote", "cnpj", "ordem_classificacao"]
TEMPO_LIMITE = 120
PAUSA_PADRAO_EM_SEGUNDOS = 1.0
ANOS_PADRAO = (2023, 2024, 2025, 2026)

Buscar = Callable[[str], bytes]


def _buscar(endereco: str) -> bytes:
    resposta = rede.get_com_agente(endereco, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    return resposta.content


def _ja_baixados(destino: Path) -> dict[str, str]:
    """`arquivo -> data do download` do que já foi baixado (a coleta retoma daqui)."""
    registro = destino / BAIXADOS
    if not registro.exists():
        return {}
    linhas = [
        json.loads(t) for t in registro.read_text(encoding="utf-8").splitlines() if t
    ]
    return {item["arquivo"]: item["baixado_em"] for item in linhas}


class Baixador:
    """Baixa cada arquivo uma vez, com pausa entre os pedidos, e anota a data em `baixados.jsonl`."""

    def __init__(
        self, destino: Path, buscar: Buscar, pausa: float, hoje: date | None = None
    ) -> None:
        self.destino, self.buscar, self.pausa = destino, buscar, pausa
        self.hoje = hoje or datetime.now(FUSO).date()
        self.feitos = _ja_baixados(destino)

    def pegar(self, arquivo: str, endereco: str) -> bytes:
        caminho = self.destino / arquivo
        if arquivo in self.feitos:
            return caminho.read_bytes()
        corpo = self.buscar(endereco)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(corpo)
        registro = {"arquivo": arquivo, "baixado_em": self.hoje.isoformat()}
        with open(self.destino / BAIXADOS, "a", encoding="utf-8") as saida:
            saida.write(json.dumps(registro) + "\n")
        self.feitos[arquivo] = self.hoje.isoformat()
        time.sleep(self.pausa)
        return corpo


def baixar(
    destino: Path,
    anos: Iterable[int] = ANOS_PADRAO,
    pausa: float = PAUSA_PADRAO_EM_SEGUNDOS,
    buscar: Buscar = _buscar,
    limite_de_unidades: int | None = None,
    hoje: date | None = None,
) -> Baixador:
    """Cadastro, licitações por unidade e ano, participantes por lote; devolve o baixador (com `feitos`)."""
    if (
        destino.exists()
        and any(destino.iterdir())
        and not (destino / BAIXADOS).exists()
    ):
        raise SystemExit(f"{destino} não está vazia: baixe numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    baixador = Baixador(destino, buscar, pausa, hoje)
    corpo = baixador.pegar(UNIDADES, ENDERECO_UNIDADES)
    unidades = tce_rn.ler_unidades(corpo, baixador.hoje).linhas
    ids = [str(u["id_unidade"]) for u in unidades][:limite_de_unidades]
    for ano in anos:
        for id_unidade in ids:
            corpo = baixador.pegar(
                f"{PASTA_LICITACOES}/{id_unidade}_{ano}.json",
                f"{ENDERECO_LICITACOES}/{id_unidade}/{ano}-01-01/{ano}-12-31",
            )
            for linha in tce_rn.ler_licitacoes(
                corpo, int(id_unidade), baixador.hoje
            ).linhas:
                if linha["id_lote"]:
                    baixador.pegar(
                        f"{PASTA_PARTICIPANTES}/{linha['id_lote']}.json",
                        f"{ENDERECO_PARTICIPANTES}/{linha['id_lote']}",
                    )
        log.info("ano %s: %d arquivos baixados até aqui", ano, len(baixador.feitos))
    return baixador


def _tabela(linhas: list[Linha], ordem: list[str]) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas)
    if tabela.empty:
        return tabela
    return tabela.sort_values(ordem, kind="stable").reset_index(drop=True)


def montar_licitacoes(origem: Path) -> dict[str, pd.DataFrame]:
    """`ano -> tabela de licitações` lendo `licitacoes/<unidade>_<ano>.json` da pasta baixada."""
    feitos = _ja_baixados(origem)
    por_ano: dict[str, list[Linha]] = {}
    for arquivo in sorted(a for a in feitos if a.startswith(f"{PASTA_LICITACOES}/")):
        unidade, ano = Path(arquivo).stem.split("_")
        leitura = tce_rn.ler_licitacoes(
            (origem / arquivo).read_bytes(),
            int(unidade),
            date.fromisoformat(feitos[arquivo]),
        )
        por_ano.setdefault(ano, []).extend(leitura.linhas)
    return {ano: _tabela(l, ORDEM_DAS_LICITACOES) for ano, l in por_ano.items()}


def montar_participantes(
    origem: Path, licitacoes: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """`ano -> participantes`: o ano é o da licitação que citou o lote (lote repetido fica no 1º ano)."""
    feitos = _ja_baixados(origem)
    por_ano: dict[str, list[Linha]] = {}
    vistos: set[str] = set()
    for ano, tabela in sorted(licitacoes.items()):
        for id_lote in tabela["id_lote"].dropna().unique():
            arquivo = f"{PASTA_PARTICIPANTES}/{id_lote}.json"
            if id_lote in vistos or arquivo not in feitos:
                continue
            vistos.add(id_lote)
            leitura = tce_rn.ler_participantes(
                (origem / arquivo).read_bytes(),
                id_lote,
                date.fromisoformat(feitos[arquivo]),
            )
            por_ano.setdefault(ano, []).extend(leitura.linhas)
    return {ano: _tabela(l, ORDEM_DOS_PARTICIPANTES) for ano, l in por_ano.items()}


def _origem(arquivos: list[Path]) -> dict[str, str]:
    """A origem do manifesto: o endereço da API e o SHA-256 do que foi lido."""
    resumo = hashlib.sha256()
    for arquivo in arquivos:
        resumo.update(arquivo.name.encode() + arquivo.read_bytes())
    return {"url": API, "sha256": resumo.hexdigest()}


def carregar(origem: Path, saida: Path, forcar: bool = False) -> dict[str, str]:
    """Grava unidades, licitações e participantes; devolve `tabela -> gravado|igual`."""
    feitos = _ja_baixados(origem)
    de_licitacoes = sorted((origem / PASTA_LICITACOES).glob("*.json"))
    de_participantes = sorted((origem / PASTA_PARTICIPANTES).glob("*.json"))
    resultado: dict[str, str] = {}

    def gravar(
        nome: str,
        montar: Callable[[], pd.DataFrame],
        ordem: list[str],
        arquivos: list[Path],
    ) -> None:
        resultado[nome] = gravar_com_versoes(
            montar,
            saida / "tce_rn" / nome,
            [_origem(arquivos)],
            ordem,
            forcar=forcar,
        )

    def unidades() -> pd.DataFrame:
        leitura = tce_rn.ler_unidades(
            (origem / UNIDADES).read_bytes(), date.fromisoformat(feitos[UNIDADES])
        )
        return _tabela(leitura.linhas, ORDEM_DAS_UNIDADES)

    gravar("unidades", unidades, ORDEM_DAS_UNIDADES, [origem / UNIDADES])
    licitacoes = montar_licitacoes(origem)
    for ano, tabela in licitacoes.items():
        gravar(
            f"licitacoes/{ano}",
            lambda t=tabela: t,
            ORDEM_DAS_LICITACOES,
            [a for a in de_licitacoes if a.stem.endswith(f"_{ano}")],
        )
    for ano, tabela in montar_participantes(origem, licitacoes).items():
        gravar(
            f"participantes/{ano}",
            lambda t=tabela: t,
            ORDEM_DOS_PARTICIPANTES,
            de_participantes,
        )
    return resultado


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--baixar", type=Path, default=None)
    argumentos.add_argument("--origem", type=Path, default=None)
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument("--anos", type=int, nargs="+", default=list(ANOS_PADRAO))
    argumentos.add_argument("--pausa", type=float, default=PAUSA_PADRAO_EM_SEGUNDOS)
    argumentos.add_argument("--limite-de-unidades", type=int, default=None)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.baixar:
        baixar(
            opcoes.baixar,
            opcoes.anos,
            opcoes.pausa,
            limite_de_unidades=opcoes.limite_de_unidades,
        )
        return 0
    if not opcoes.origem:
        argumentos.error("passe --baixar <pasta nova> ou --origem <pasta baixada>")
    if (
        not (opcoes.origem / UNIDADES).exists()
        or not (opcoes.origem / BAIXADOS).exists()
    ):
        log.error("faltam %s e %s em %s", UNIDADES, BAIXADOS, opcoes.origem)
        return 1
    saida = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    resultado = carregar(opcoes.origem, saida, opcoes.forcar)
    log.info(
        "TCE-RN: %d tabelas (%d gravadas)",
        len(resultado),
        sum(r == GRAVADO for r in resultado.values()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
