"""O aviso ao Tiago de cada rascunho do Raio-X (plano `2026-10-28-raio-x-todo-dia`, PR 6c, Tarefa 11).

    python -m scripts.avisar_raio_x --acervo <cópia do acervo> --esperando <pasta esperando/>

Em dia de evento o servidor de casa grava o rascunho do Raio-X em `<acervo>/pregao/raio-x/`
(`scripts/gerar_pregao_do_dia.py`), sem publicar. Este script roda no PC, sobre a cópia diária do acervo, e
escreve em `esperando/` uma nota para cada rascunho que ainda não tem nota: o que o dia teve, onde está o
rascunho e a recomendação. Publicar é texto novo (nível 1): só com o "pode" do Tiago. O início da sessão
(gancho do Claude, fora do repositório) chama este script e mostra a linha que ele imprime, para a sessão
pôr o pedido na Central.

A nota é o registro de que o aviso saiu: ela fica em `esperando/` depois de respondida, e o mesmo rascunho
nunca ganha outra. Rascunho sem o JSON (gravado por último) não saiu inteiro e não é avisado.
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base.intradiario_b3 import FUSO_DA_B3
from scripts.gerar_pregao_do_dia import (
    PASTA_DO_RAIO_X,
    PASTA_NO_ACERVO,
    caminho_do_rascunho,
    caminho_do_resumo,
)
from src.rascunho_do_raio_x import _percentual

MESA = "Produto"


def nome_da_nota(dia: date) -> str:
    return f"{MESA} · Raio-X de {dia:%d-%m-%Y} esperando o pode.md"


def rascunhos_sem_aviso(acervo: Path, esperando: Path) -> list[date]:
    """Os pregões com rascunho inteiro (o JSON existe) e sem nota em `esperando/`, do mais antigo ao mais novo."""
    pasta = acervo / PASTA_NO_ACERVO / PASTA_DO_RAIO_X
    if not pasta.is_dir():
        return []
    dias = sorted(date.fromisoformat(c.stem) for c in pasta.glob("*.json"))
    return [d for d in dias if not (esperando / nome_da_nota(d)).exists()]


def _motivo(evento: dict) -> str:
    partes = [e["evento"] for e in evento.get("calendario", [])]
    if evento.get("variacao_forte_do_ibovespa"):
        partes.append(
            f"variação do Ibovespa de {_percentual(evento['variacao_minima'])} ou mais"
        )
    return ", ".join(partes) or "dia de evento"


def _recomendacao(evento: dict) -> str:
    """Choque no índice merece o Raio-X publicado; dia de calendário sem choque, o pregão do dia já cobre."""
    if evento.get("variacao_forte_do_ibovespa"):
        return (
            "ler e publicar como estudo, como o Raio-X de 26/10: o índice teve um choque e o rascunho "
            "explica o que caiu mais e por quê."
        )
    return (
        "não publicar: dia de calendário sem choque no índice; a página do pregão do dia já mostra os "
        "números. O rascunho fica no acervo."
    )


def nota_de_espera(acervo: Path, dia: date, criado: date) -> str:
    """A nota de `esperando/` (tipo: espera), no formato das outras notas da pasta."""
    raio_x = json.loads(caminho_do_rascunho(acervo, dia, ".json").read_text("utf-8"))
    evento = (
        json.loads(caminho_do_resumo(acervo, dia).read_text("utf-8"))["evento"] or {}
    )
    queda = raio_x["queda"]
    return (
        f"---\ntipo: espera\nmesa: {MESA}\nde-quem: você\nsituacao: aberta\nprazo: \n"
        f"criado: {criado.isoformat()}\n---\n"
        f"Rascunho do Raio-X do pregão de {dia:%d/%m/%Y} ({_motivo(evento)}), gerado sozinho pelo servidor "
        f"de casa e não publicado. O Ibovespa variou {_percentual(raio_x['ibovespa']['variacao'])}; das "
        f"{queda['empresas']} empresas com giro de R$ 20 milhões ou mais, a mediana variou "
        f"{_percentual(queda['mediana'])} e {queda['quedas_fortes']} caíram 30% ou mais. Publicar é texto "
        f'novo: nível 1, só o seu "pode".\n\n'
        f"**Recomendação:** {_recomendacao(evento)}\n"
        f"Onde: `{caminho_do_rascunho(acervo, dia, '.html')}` (e o PDF ao lado); "
        "plano `planos/2026-10-28-raio-x-todo-dia.md`.\n"
    )


def avisar(acervo: Path, esperando: Path, hoje: date | None = None) -> list[Path]:
    """Escreve a nota de cada rascunho sem aviso e devolve as notas novas."""
    novas = []
    for dia in rascunhos_sem_aviso(acervo, esperando):
        esperando.mkdir(parents=True, exist_ok=True)
        nota = esperando / nome_da_nota(dia)
        nota.write_text(
            nota_de_espera(
                acervo, dia, hoje or datetime.now(ZoneInfo(FUSO_DA_B3)).date()
            ),
            "utf-8",
        )
        novas.append(nota)
    return novas


def main(argumentos: list[str] | None = None) -> int:
    leitor = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    leitor.add_argument("--acervo", type=Path, required=True)
    leitor.add_argument("--esperando", type=Path, required=True)
    opcoes = leitor.parse_args(argumentos)
    dias = rascunhos_sem_aviso(opcoes.acervo, opcoes.esperando)
    avisar(opcoes.acervo, opcoes.esperando)
    if dias:
        lista = ", ".join(f"{d:%d/%m/%Y}" for d in dias)
        print(
            f'Raio-X: rascunho(s) novo(s) esperando o "pode" do Tiago ({lista}); nota em esperando/ com a '
            "recomendação. Ponha o pedido na Central (pendência da mesa Produto)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
