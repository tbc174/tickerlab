"""Coleta e carga dos contratos e despesas por CNPJ dos TCEs de PE, SP, CE e RS (linha 652, API dados C1 a C4).

    python -m scripts.carga_tces --baixar <pasta nova e vazia> [--tribunais pe sp rs] [--anos 2023 2024 2025 2026]
    python -m scripts.carga_tces --origem <pasta baixada>                (grava no acervo)
    python -m scripts.carga_tces --origem <pasta> --pasta /tmp/base --forcar

Os leitores são os de `base/contratos_tces.py` (só pessoa jurídica, sem nome, CPF, endereço nem texto livre).

`--baixar`, uma pausa entre os pedidos e a retomada de onde parou (`baixados.jsonl`, a data do download vira o
`disponivel_em`):
- **PE**: `Contratos` e `TermoAditivo` do Dados Abertos, um pedido por ano (o teto da API é de 100 mil linhas por
  pedido: se a resposta chegar nele, a coleta para e avisa, em vez de gravar um ano cortado). As licitações
  ficam de fora: `LicitacoesDetalhes` tem outro formato e passa do teto (linha nova na fila).
- **SP**: despesas por município e mês, só fornecedor marcado como CNPJ (645 municípios x 12 meses por ano).
- **RS**: o `package_search` do CKAN lista os pacotes `contratos-<órgão>` e cada ZIP é baixado uma vez; só o
  `contrato.csv` é aberto.
- **CE**: sem coleta nesta carga (o endereço do SIM não foi confirmado); `--origem` já lê arquivos
  `ce/contratados_<município>_<ano>.json` e `ce/contratos_<município>_<ano>.json` postos à mão.

`--origem` grava, com manifesto e versões (`base/parquet.py::gravar_com_versoes`), uma tabela por assunto e
um Parquet por ano em `<base>/<tabela>/<ano>.parquet`: `tce_pe_contratos`, `tce_pe_aditivos`, `tce_sp_despesas`,
`tce_ce_contratos` e `tce_rs_contratos`. Os arquivos baixados são dados de fora: ficam numa pasta nova, nunca
no repositório, e esta carga os lê com o Python em modo isolado (`python -I`).

Licença a confirmar, só uso interno (ADR 0102, Emenda 2); nada é perguntado às fontes. Recusa rodar sem a
versão do código (exigência 13 da ADR 0055). Saída 0 tudo certo; 1 arquivo faltando.
"""

import argparse
import hashlib
import json
import logging
import sys
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from base import contratos_tces
from base.contratos_tces import Leitura, Linha
from base.parquet import GRAVADO, gravar_com_versoes
from scripts.carga_tce_rn import BAIXADOS, FUSO, Baixador, Buscar, _ja_baixados
from src import acervo, rede
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_tces")
PE = "https://sistemas.tce.pe.gov.br/DadosAbertos"
SP = "https://transparencia.tce.sp.gov.br/api/json"
RS = "https://dados.tce.rs.gov.br/api/3/action/package_search"
TEMPO_LIMITE = 180
PAUSA_PADRAO_EM_SEGUNDOS = 1.0
ANOS_PADRAO = (2023, 2024, 2025, 2026)
TRIBUNAIS = ("pe", "sp", "rs")
TETO_DO_PEDIDO_PE = 100_000
PACOTES_POR_PAGINA_RS = 100
MESES = range(1, 13)
SEM_ANO = "sem_ano"
# entidade da API do TCE-PE por tabela (o parâmetro de ano é `AnoContrato` nas duas)
ENTIDADES_PE = {"contratos": "Contratos", "aditivos": "TermoAditivo"}

# tabela gravada: (pasta de origem, chave que ordena e identifica a linha)
CHAVES = {
    "tce_pe_contratos": ["codigo_contrato", "cnpj"],
    "tce_pe_aditivos": ["codigo_contrato", "numero_aditivo", "ano_aditivo", "cnpj"],
    "tce_sp_despesas": [
        "municipio",
        "mes",
        "evento",
        "numero_empenho",
        "cnpj",
        "data_emissao",
        "valor",
    ],
    "tce_ce_contratos": [
        "codigo_municipio",
        "numero_contrato",
        "data_contrato",
        "cnpj",
    ],
    "tce_rs_contratos": [
        "codigo_orgao",
        "numero_licitacao",
        "ano_licitacao",
        "numero_contrato",
        "ano_contrato",
        "cnpj",
    ],
}

Porcao = tuple[str, str, Leitura]  # (tabela, ano, o que o leitor achou)


def _buscar(endereco: str) -> bytes:
    resposta = rede.get_com_agente(endereco, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    return resposta.content


# ------------------------------------------------------------------------------------ coleta


def _baixar_pe(baixador: Baixador, anos: Iterable[int]) -> None:
    for ano in anos:
        for tabela, entidade in ENTIDADES_PE.items():
            corpo = baixador.pegar(
                f"pe/{tabela}_{ano}.json",
                f"{PE}/{entidade}!json?AnoContrato={ano}",
            )
            _recusar_corte_pe(corpo, tabela, ano)


def _recusar_corte_pe(corpo: bytes, tabela: str, ano: int) -> None:
    """A API corta em 100 mil linhas sem avisar: ano cortado não vale, e o arquivo é apagado do registro."""
    resposta = json.loads(corpo.decode(contratos_tces.CODIFICACAO_PE))["resposta"]
    if int(resposta.get("tamanhoResultado") or 0) >= TETO_DO_PEDIDO_PE:
        raise SystemExit(
            f"TCE-PE {tabela} {ano}: a resposta chegou ao teto de {TETO_DO_PEDIDO_PE} linhas; "
            "apague o arquivo e a linha dele em baixados.jsonl e divida o pedido (linha nova)"
        )


def _baixar_sp(baixador: Baixador, anos: Iterable[int]) -> None:
    municipios = [
        item["municipio"]
        for item in json.loads(baixador.pegar("sp/municipios.json", f"{SP}/municipios"))
    ]
    for ano in anos:
        for municipio in municipios:
            for mes in MESES:
                baixador.pegar(
                    f"sp/{municipio}_{ano}_{mes:02d}.json",
                    f"{SP}/despesas/{quote(municipio)}/{ano}/{mes}",
                )
        log.info("SP %s: %d arquivos até aqui", ano, len(baixador.feitos))


def _baixar_rs(baixador: Baixador) -> None:
    pacotes: list[tuple[str, str]] = []
    inicio = 0
    while True:
        corpo = baixador.pegar(
            f"rs/indice_{inicio}.json",
            f"{RS}?q=name:contratos-*&rows={PACOTES_POR_PAGINA_RS}&start={inicio}",
        )
        pagina = contratos_tces.pacotes_de_contratos(corpo)
        total = json.loads(corpo)["result"]["results"]
        pacotes.extend(pagina)
        if len(total) < PACOTES_POR_PAGINA_RS:
            break
        inicio += PACOTES_POR_PAGINA_RS
    for nome in contratos_tces.pendentes(
        (n for n, _ in pacotes), (Path(a).stem for a in baixador.feitos)
    ):
        endereco = dict(pacotes)[nome]
        baixador.pegar(f"rs/{nome}.zip", endereco)


def baixar(
    destino: Path,
    tribunais: Iterable[str] = TRIBUNAIS,
    anos: Iterable[int] = ANOS_PADRAO,
    pausa: float = PAUSA_PADRAO_EM_SEGUNDOS,
    buscar: Buscar = _buscar,
    hoje: date | None = None,
) -> Baixador:
    """Baixa o que falta de cada tribunal pedido; devolve o baixador (com `feitos`)."""
    if (
        destino.exists()
        and any(destino.iterdir())
        and not (destino / BAIXADOS).exists()
    ):
        raise SystemExit(f"{destino} não está vazia: baixe numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    baixador = Baixador(destino, buscar, pausa, hoje)
    anos = list(anos)
    if "pe" in tribunais:
        _baixar_pe(baixador, anos)
    if "sp" in tribunais:
        _baixar_sp(baixador, anos)
    if "rs" in tribunais:
        _baixar_rs(baixador)
    return baixador


# ------------------------------------------------------------------------------------ carga


def _quando(feitos: dict[str, str], arquivo: str) -> date:
    return date.fromisoformat(feitos[arquivo])


def _do_pe(origem: Path, feitos: dict[str, str]) -> list[Porcao]:
    porcoes = []
    for arquivo in sorted(a for a in feitos if a.startswith("pe/") and "_" in a):
        tabela, ano = Path(arquivo).stem.split("_")
        leitura = contratos_tces.ler_pe(
            (origem / arquivo).read_bytes(), tabela, _quando(feitos, arquivo)
        )
        porcoes.append((f"tce_pe_{tabela}", ano, leitura))
    return porcoes


def _do_sp(origem: Path, feitos: dict[str, str]) -> list[Porcao]:
    porcoes = []
    for arquivo in sorted(
        a for a in feitos if a.startswith("sp/") and a != "sp/municipios.json"
    ):
        *municipio, ano, _ = Path(arquivo).stem.split("_")
        leitura = contratos_tces.ler_sp(
            (origem / arquivo).read_bytes(), int(ano), _quando(feitos, arquivo)
        )
        for linha in leitura.linhas:
            linha["municipio"] = "_".join(municipio)
        porcoes.append(("tce_sp_despesas", ano, leitura))
    return porcoes


def _do_rs(origem: Path, feitos: dict[str, str]) -> list[Porcao]:
    porcoes = []
    for arquivo in sorted(
        a for a in feitos if a.startswith("rs/") and a.endswith(".zip")
    ):
        leitura = contratos_tces.ler_rs(
            (origem / arquivo).read_bytes(), _quando(feitos, arquivo)
        )
        por_ano: dict[str, Leitura] = {}
        for linha in leitura.linhas:
            ano = str(linha.get("ano_contrato") or SEM_ANO)
            por_ano.setdefault(ano, Leitura()).linhas.append(linha)
        porcoes.extend(
            ("tce_rs_contratos", ano, parte) for ano, parte in por_ano.items()
        )
    return porcoes


def _do_ce(origem: Path) -> list[Porcao]:
    """Pares `contratados_<município>_<ano>.json` + `contratos_<município>_<ano>.json` postos em `ce/`."""
    porcoes = []
    for contratados in sorted((origem / "ce").glob("contratados_*.json")):
        sufixo = contratados.name.removeprefix("contratados_")
        contratos = contratados.with_name(f"contratos_{sufixo}")
        ano = contratados.stem.rsplit("_", 1)[-1]
        coletado = datetime.fromtimestamp(contratados.stat().st_mtime, FUSO).date()
        leitura = contratos_tces.ler_ce(
            contratados.read_bytes(),
            contratos.read_bytes() if contratos.exists() else b'{"elements": []}',
            coletado,
        )
        porcoes.append(("tce_ce_contratos", ano, leitura))
    return porcoes


def montar(origem: Path) -> dict[tuple[str, str], pd.DataFrame]:
    """`(tabela, ano) -> linhas`, juntando os arquivos baixados de cada tribunal."""
    feitos = _ja_baixados(origem)
    porcoes = [
        *_do_pe(origem, feitos),
        *_do_sp(origem, feitos),
        *_do_rs(origem, feitos),
        *_do_ce(origem),
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
    """A origem do manifesto: o endereço do tribunal e o SHA-256 dos arquivos da tabela e do ano."""
    resumo = hashlib.sha256()
    pasta = {"pe": PE, "sp": SP, "rs": RS, "ce": "dadosabertos.tce.ce.gov.br"}[
        tabela.split("_")[1]
    ]
    for arquivo in sorted(origem.glob(f"{tabela.split('_')[1]}/*")):
        if ano in arquivo.name or tabela.endswith("_rs_contratos"):
            resumo.update(arquivo.name.encode() + arquivo.read_bytes())
    return {"url": pasta, "sha256": resumo.hexdigest()}


def carregar(origem: Path, saida: Path, forcar: bool = False) -> dict[str, str]:
    """Grava uma tabela por assunto e um Parquet por ano; devolve `tabela/ano -> gravado|igual`."""
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
    argumentos.add_argument(
        "--tribunais", nargs="+", choices=TRIBUNAIS, default=list(TRIBUNAIS)
    )
    argumentos.add_argument("--anos", type=int, nargs="+", default=list(ANOS_PADRAO))
    argumentos.add_argument("--pausa", type=float, default=PAUSA_PADRAO_EM_SEGUNDOS)
    argumentos.add_argument("--forcar", action="store_true")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if opcoes.baixar:
        baixar(opcoes.baixar, opcoes.tribunais, opcoes.anos, opcoes.pausa)
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
        "TCEs: %d tabelas/anos (%d gravados)",
        len(resultado),
        sum(r == GRAVADO for r in resultado.values()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
