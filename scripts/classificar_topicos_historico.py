"""Lote do histórico do leitor v2 (ADR 0069): o assunto dos fatos relevantes antigos, só pelo título.

    python -m scripts.classificar_topicos_historico --simular
    python -m scripts.classificar_topicos_historico --executar --autorizado-usd 1.50

Só os fatos que as regras do título deixaram em "Outros" vão ao modelo (Claude Haiku 5.5, Batches API,
50% mais barato). Como no leitor diário, o modelo escolhe numa lista fechada e devolve um trecho que
tem de existir no título; o resultado vai para `topico_modelo`, à parte, e a tela só o usa depois da
medição. `--simular` só conta tokens e estima o custo (não cria lote, não gasta). O lote real só roda
com `--executar` e `--autorizado-usd`: o valor que o Tiago aprovou; se a estimativa passa dele, para.
O lacre: só entregas até 31/03/2026 (o holdout da medição fica de fora); `--teto` limita a execução.
"""

import argparse
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date

import anthropic
import sqlalchemy as sa

from src import topicos, topicos_modelo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.leituras import TOPICO_MODELO, gravar_leitura, topicos_dos_fatos
from src.banco.leituras import lidos as lidos_no_banco
from src.banco.modelo import eventos
from src.configuracao import url_do_banco
from src.eventos import FONTE_IPE

log = logging.getLogger("tickerlab.lote_topicos")
CATEGORIA = "Fato Relevante"
LACRE = date(2026, 3, 31)
TETO_PADRAO = 2_000
AMOSTRA_DA_CONTAGEM = 50
# Claude Haiku 5.5 (prompts até 100 mil tokens), US$ por milhão de tokens; o lote cobra a metade
PRECO_ENTRADA, PRECO_SAIDA, DESCONTO_DO_LOTE = 0.10, 0.50, 0.5
SAIDA_ESTIMADA = 80  # tokens da resposta (JSON curto)
ESPERA_ENTRE_CONSULTAS = 60  # segundos

Pendente = tuple[str, str, date, str]  # (protocolo, cnpj, publicado em, título do IPE)


class SemAutorizacao(Exception):
    """O lote real só roda com o valor aprovado e acima da estimativa."""


@dataclass(frozen=True)
class Estimativa:
    documentos: int
    tokens_de_entrada: int
    custo_usd: float


def selecionar(
    conexao: sa.Connection, ate: date = LACRE, teto: int = TETO_PADRAO
) -> list[Pendente]:
    """Os fatos ainda em "Outros" que o modelo não leu, do mais novo, até o teto."""
    linhas = conexao.execute(
        sa.select(
            eventos.c.protocolo,
            eventos.c.cnpj,
            eventos.c.publicado_em,
            eventos.c.assunto,
        )
        .where(
            eventos.c.fonte == FONTE_IPE,
            eventos.c.categoria == CATEGORIA,
            eventos.c.publicado_em <= ate,
        )
        .order_by(eventos.c.publicado_em.desc(), eventos.c.protocolo)
    ).all()
    lidos = lidos_no_banco(
        conexao,
        FONTE_IPE,
        TOPICO_MODELO,
        [r.protocolo for r in linhas],
        versao=topicos.VERSAO,
    )
    candidatos = [r for r in linhas if r.protocolo not in lidos]
    achados = topicos_dos_fatos(
        conexao, FONTE_IPE, [(r.protocolo, r.assunto) for r in candidatos]
    )
    return [
        (r.protocolo, r.cnpj, r.publicado_em, r.assunto)
        for r in candidatos
        if achados[r.protocolo].principal == topicos.OUTROS
    ][:teto]


def simular(
    cliente: anthropic.Anthropic,
    pendentes: list[Pendente],
    amostra: int = AMOSTRA_DA_CONTAGEM,
) -> Estimativa:
    """Conta os tokens (de uma amostra, se for grande; extrapola) e estima o custo. Não cria lote."""
    if not pendentes:
        return Estimativa(0, 0, 0.0)
    passo = max(1, len(pendentes) // amostra)
    contados = []
    for _, _, _, titulo in pendentes[::passo][:amostra]:
        pedido = topicos_modelo.pedido(titulo, "")
        contados.append(
            cliente.messages.count_tokens(
                model=pedido["model"],
                system=pedido["system"],
                messages=pedido["messages"],
            ).input_tokens
        )
    entrada = round(sum(contados) / len(contados) * len(pendentes))
    custo = (
        (entrada * PRECO_ENTRADA + SAIDA_ESTIMADA * len(pendentes) * PRECO_SAIDA)
        / 1e6
        * DESCONTO_DO_LOTE
    )
    return Estimativa(len(pendentes), entrada, custo)


def conferir_autorizacao(estimativa: Estimativa, autorizado_usd: float | None) -> None:
    if autorizado_usd is None:
        raise SemAutorizacao(
            "Sem --autorizado-usd: rode --simular e peça o pode do Tiago."
        )
    if estimativa.custo_usd > autorizado_usd:
        raise SemAutorizacao(
            f"A estimativa (US$ {estimativa.custo_usd:.4f}) passa do valor autorizado "
            f"(US$ {autorizado_usd:.4f})."
        )


def executar(
    cliente: anthropic.Anthropic,
    conexao: sa.Connection,
    pendentes: list[Pendente],
    espera: float = ESPERA_ENTRE_CONSULTAS,
) -> int:
    """Cria o lote, espera terminar e grava as respostas que respeitam a ADR 0069. Devolve quantas."""
    if not pendentes:
        return 0
    por_chave = {f"f{i}": p for i, p in enumerate(pendentes)}
    lote = cliente.messages.batches.create(
        requests=[
            {"custom_id": chave, "params": topicos_modelo.pedido(p[3], "")}
            for chave, p in por_chave.items()
        ]
    )
    log.info("Lote %s criado com %s fatos.", lote.id, len(por_chave))
    while cliente.messages.batches.retrieve(lote.id).processing_status != "ended":
        time.sleep(espera)
    gravados = 0
    for item in cliente.messages.batches.results(lote.id):
        if item.result.type != "succeeded" or item.custom_id not in por_chave:
            continue
        protocolo, cnpj, publicado, titulo = por_chave[item.custom_id]
        mensagem = item.result.message
        if mensagem.stop_reason != "end_turn":  # recusa ou resposta cortada
            continue
        texto = next((b.text for b in mensagem.content if b.type == "text"), "")
        leitura = topicos_modelo.interpretar(texto, titulo, "")
        if leitura is None:
            continue
        gravar_leitura(
            conexao, FONTE_IPE, protocolo, TOPICO_MODELO, cnpj, publicado,
            asdict(leitura), versao=topicos.VERSAO,
        )  # fmt: skip
        gravados += 1
    return gravados


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    modo = argumentos.add_mutually_exclusive_group(required=True)
    modo.add_argument("--simular", action="store_true", help="só conta tokens e custo")
    modo.add_argument("--executar", action="store_true", help="cria o lote (gasta)")
    argumentos.add_argument("--autorizado-usd", type=float, help="o valor aprovado")
    argumentos.add_argument("--teto", type=int, default=TETO_PADRAO)
    argumentos.add_argument("--ate", type=date.fromisoformat, default=LACRE)
    opcoes = argumentos.parse_args(argv)
    if opcoes.ate > LACRE:
        argumentos.error(f"--ate não pode passar do lacre ({LACRE}).")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cliente = topicos_modelo.cliente_da_chave()
    if cliente is None:
        log.error("Sem %s no ambiente.", topicos_modelo.VARIAVEL_DA_CHAVE)
        return 1
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            pendentes = selecionar(conexao, opcoes.ate, opcoes.teto)
        estimativa = simular(cliente, pendentes)
        print(
            f"{estimativa.documentos} fatos · {estimativa.tokens_de_entrada} tokens de entrada · "
            f"custo estimado no lote: US$ {estimativa.custo_usd:.4f} ({topicos_modelo.MODELO})"
        )
        if opcoes.simular:
            return 0
        conferir_autorizacao(estimativa, opcoes.autorizado_usd)
        with motor.begin() as conexao:
            print(f"Gravados: {executar(cliente, conexao, pendentes)}")
    except SemAutorizacao as erro:
        log.error("%s", erro)
        return 2
    except (anthropic.APIError, sa.exc.SQLAlchemyError) as erro:
        log.error("Lote interrompido: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
