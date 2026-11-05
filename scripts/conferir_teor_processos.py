"""Conferência automática do teor dos processos (`base/conferencia_processos.py`; plano de
03/11/2026, PR 2): uma rodada por carga semanal, em dois passos.

    python -m scripts.conferir_teor_processos amostra [--dia AAAA-MM-DD] [--semente N]
    python -m scripts.conferir_teor_processos medir --respostas <arquivo.jsonl> [--dia AAAA-MM-DD]

- `amostra`: sorteia, com a semente (padrão: o dia, AAAAMMDD), as comunicações da
  `processos_comunicacoes` em que a regra preencheu cada campo e grava, na área restrita do acervo
  (`<acervo>/restrito/conferencias/processos-teor/<dia>/`), `amostra.json` (a semente, o que a regra
  leu, sem texto) e `pedidos.jsonl` (o pedido ao modelo do gabarito, com o teor mascarado).
- O gabarito: cada pedido respondido pelo modelo (`{"id", "tipo_de_ato", "resultado",
  "maior_valor"}`, uma linha por pedido), fora deste comando.
- `medir`: compara a regra com o gabarito e grava a conferência em
  `<acervo>/base/conferencias/processos-teor/<dia>.json` (só ids e contagens), que a próxima
  `carga_processos` aplica.

Lê só o acervo (não baixa nada nem chama a API). Saída 0 tudo certo; 1 algum campo abaixo do
critério (fica desligado: abre a ficha de falha); 2 sem a amostra do dia ou sem consulta guardada.
"""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base import conferencia_processos as cp
from base import processos, processos_teor
from base.processos_teor import Leitura
from src import acervo
from src.banco.conexao import obter_engine

log = logging.getLogger("tickerlab.conferir_teor_processos")
BRASILIA = ZoneInfo("America/Sao_Paulo")  # o dia da amostra é o do servidor de casa


def _trabalho(pasta: Path, dia: date) -> Path:
    return pasta.parent / acervo.PASTA_RESTRITA / cp.PASTA / dia.isoformat()


def amostra(pasta: Path, dia: date, semente: int) -> int:
    with obter_engine().connect() as conexao:
        itens = processos.comunicacoes_da_tabela(conexao)
    if not itens:
        log.error("nenhuma consulta do DJEN guardada no acervo")
        return 2
    leituras = {chave: processos_teor.ler(item) for chave, item in itens.items()}
    sorteadas = cp.sortear(leituras, semente)
    ids = sorted({i for lista in sorteadas.values() for i in lista})
    trabalho = _trabalho(pasta, dia)
    trabalho.mkdir(parents=True, exist_ok=True)
    (trabalho / "amostra.json").write_text(
        json.dumps(
            {
                "dia": dia.isoformat(),
                "semente": semente,
                "versao_da_regra": processos_teor.VERSAO_DA_REGRA,
                "modelo": cp.MODELO_DO_GABARITO,
                "cobre_ate": max(i["_visto_em"] for i in itens.values())
                .date()
                .isoformat(),
                "amostra": sorteadas,
                "leituras": {i: asdict(leituras[i]) for i in ids},
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    (trabalho / "pedidos.jsonl").write_text(
        "".join(
            json.dumps({"id": i, "pedido": cp.pedido(itens[i])}, ensure_ascii=False)
            + "\n"
            for i in ids
        ),
        encoding="utf-8",
    )
    log.info("amostra de %s: %s pedidos em %s", dia, len(ids), trabalho)
    return 0


def medir(pasta: Path, dia: date, respostas: Path) -> int:
    arquivo = _trabalho(pasta, dia) / "amostra.json"
    if not arquivo.exists():
        log.error("sem a amostra de %s (%s): rode o passo amostra antes", dia, arquivo)
        return 2
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    gabarito = {
        str(linha["id"]): linha
        for linha in map(json.loads, respostas.read_text(encoding="utf-8").splitlines())
    }
    leituras = {i: Leitura(**v) for i, v in dados["leituras"].items()}
    campos, discordantes = cp.medir(leituras, gabarito, dados["amostra"])
    conferencia = cp.Conferencia(
        feita_em=dia,
        versao_da_regra=dados["versao_da_regra"],
        modelo=dados["modelo"],
        semente=dados["semente"],
        cobre_ate=date.fromisoformat(dados["cobre_ate"]),
        campos=campos,
        discordantes=discordantes,
    )
    log.info("conferência gravada em %s", cp.gravar(conferencia, pasta))
    reprovados = [c for c, v in campos.items() if v.casos and not v.aprovado]
    for campo, valor in campos.items():
        log.info("%s: %s de %s (%s)", campo, valor.acertos, valor.casos, valor.precisao)
    if reprovados:
        log.error(
            "abaixo do critério de %s, desligados: %s",
            cp.CRITERIO,
            ", ".join(reprovados),
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("passo", choices=("amostra", "medir"))
    argumentos.add_argument("--pasta", type=Path, default=None)
    argumentos.add_argument(
        "--dia", type=date.fromisoformat, default=datetime.now(BRASILIA).date()
    )
    argumentos.add_argument("--semente", type=int, default=None)
    argumentos.add_argument("--respostas", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = (
        opcoes.pasta
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    if opcoes.passo == "amostra":
        semente = opcoes.semente or int(opcoes.dia.strftime("%Y%m%d"))
        return amostra(pasta, opcoes.dia, semente)
    if opcoes.respostas is None:
        argumentos.error("medir precisa de --respostas")
    return medir(pasta, opcoes.dia, opcoes.respostas)


if __name__ == "__main__":
    raise SystemExit(main())
