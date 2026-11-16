"""Canal dos titulares do CNPJ: o que quem atende o privacidade@ roda no servidor de casa (ADR 0106, regra 3.8).

    python -m scripts.oposicao_do_titular pedido --base <pasta> --restrita <pasta> --cnpj <CNPJ> [--meio 982247] [--acervo-pessoa <pasta>]
    python -m scripts.oposicao_do_titular acesso --restrita <pasta> --cnpj <CNPJ> [--meio 982247]
    python -m scripts.oposicao_do_titular atender --base <pasta> --restrita <pasta> [--acervo-pessoa <pasta>]
    python -m scripts.oposicao_do_titular conferir --restrita <pasta>

O nome do titular, como a Receita publica, é lido da entrada (uma linha), nunca da linha de comando: assim ele
não fica no histórico do terminal. `pedido` registra a oposição (prazo de 15 dias) e já faz a lápide; `acesso`
mostra o que a base guarda sobre o papel da pessoa na empresa (art. 18, I e II) para a resposta; `conferir`
falha (saída 1, última linha `FALHAS:`) se alguma oposição passou do prazo sem lápide ou se uma carga que rodava
durante o pedido trouxe a pessoa de volta ao restrito; `atender` refaz a lápide de todas (sem pedir nome). Nada
do que se imprime traz nome, CPF ou id. Evite rodar `pedido` durante a carga mensal
(`scripts.carga_receita_retrato`); se rodou, o `conferir` acusa e o `atender` conserta.

Com `--acervo-pessoa` (a pasta `acervo_pessoa/` da tela da equipe, linha 829), `pedido` acha também o titular de
empresário individual ou MEI (que não está no quadro de sócios) pela raiz e pelo nome, e `pedido` e `atender`
tiram do acervo já montado o sócio, o titular e o contato da raiz dele: a oposição vale no dia, sem esperar a
montagem do mês seguinte.

Roda: cron de casa pelo oposicao-do-titular.sh (todo dia às 6h10 e 18h10).
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from base import oposicao_na_tela
from base.pessoas import oposicoes
from base.porta import pessoas as porta

FUSO = ZoneInfo(
    "America/Sao_Paulo"
)  # o prazo conta pelo dia no Brasil, não no relógio do servidor

PEDE_O_MEIO = (
    "{n} pessoas com esse nome nessa empresa: peça ao titular os 6 dígitos do meio do CPF, "
    "os que a Receita já publica (nunca o CPF inteiro), e rode de novo com --meio."
)
NINGUEM = (
    "Ninguém com esse nome no quadro dessa empresa: responda ao titular que a base não guarda "
    "dado dele nela (confira a grafia no cadastro da Receita)."
)


def _hoje() -> date:
    return datetime.now(FUSO).date()


def _ler_nome() -> str:
    print("Nome como a Receita publica: ", end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip()


def _achar(opcoes: argparse.Namespace) -> list[str] | None:
    """Os ids achados, ou None (com a mensagem impressa) quando não é exatamente uma pessoa."""
    nome = _ler_nome()
    ids = oposicoes.achar_titular(opcoes.restrita, opcoes.cnpj, nome, opcoes.meio)
    if not ids and getattr(opcoes, "acervo_pessoa", None) is not None:
        ids = oposicao_na_tela.achar_titular_individual(
            opcoes.acervo_pessoa, opcoes.cnpj, nome
        )
    if not ids:
        print(NINGUEM)
        return None
    if len(ids) > 1:
        print(PEDE_O_MEIO.format(n=len(ids)))
        return None
    return ids


def _lapide(resumo: oposicoes.Resumo, dia: date) -> str:
    return (
        f"lápide feita em {dia}: {resumo.pessoas_tiradas} linha(s) tirada(s) do restrito, "
        f"{resumo.arquivos_regravados} arquivo(s) do QSA regravado(s)"
    )


def _no_acervo_de_pessoa(opcoes: argparse.Namespace) -> None:
    if getattr(opcoes, "acervo_pessoa", None) is not None:
        ids = oposicoes.ids_opostos(opcoes.restrita)
        oposicao_na_tela.aplicar_no_acervo(opcoes.acervo_pessoa, ids)


def _pedido(opcoes: argparse.Namespace) -> int:
    ids = _achar(opcoes)
    if ids is None:
        return 1
    oposicoes.registrar(opcoes.restrita, ids, opcoes.pedido_em)
    resumo = oposicoes.atender(opcoes.base, opcoes.restrita, opcoes.hoje)
    _no_acervo_de_pessoa(opcoes)
    registro = oposicoes.ler(opcoes.restrita)
    linha = registro[registro["id_pessoa"] == ids[0]].iloc[0]
    print(
        f"Oposição registrada em {linha['pedido_em']}, prazo até {linha['prazo_ate']}; "
        f"{_lapide(resumo, opcoes.hoje)}. O nome já não sai."
    )
    return 0


def _atender(opcoes: argparse.Namespace) -> int:
    resumo = oposicoes.atender(opcoes.base, opcoes.restrita, opcoes.hoje)
    _no_acervo_de_pessoa(opcoes)
    print(f"Todas as oposições: {_lapide(resumo, opcoes.hoje)}.")
    return 0


def _acesso_ao_individual(opcoes: argparse.Namespace, ids: list[str]) -> None:
    """Empresário individual ou MEI: o titular e o contato do estabelecimento também estão na tela
    da equipe (art. 18, I e II); diz o que existe, sem imprimir nome, CPF nem id."""
    if getattr(opcoes, "acervo_pessoa", None) is None:
        return
    titular, contato = oposicao_na_tela.tem_na_tela(
        opcoes.acervo_pessoa, opcoes.cnpj, ids
    )
    if titular:
        print(
            "Como empresário individual, a tela da equipe mostra também o nome do titular "
            f"e o contato do estabelecimento ({contato} linha(s) de telefone, e-mail e endereço)."
        )


def _acesso(opcoes: argparse.Namespace) -> int:
    ids = _achar(opcoes)
    if ids is None:
        return 1
    pessoas = porta.pessoas_da_raiz(
        opcoes.restrita, oposicoes.raiz_do_cnpj(opcoes.cnpj)
    )
    papeis = pessoas[pessoas["id_pessoa"] == ids[0]]
    opostos = oposicoes.ids_opostos(opcoes.restrita)
    _acesso_ao_individual(opcoes, ids)
    print(
        "A base guarda, como a Receita publica (Fonte: Receita Federal, dados abertos do CNPJ): "
        "o nome e o CPF mascarado, mais:"
    )
    for _, papel in papeis.iterrows():
        desde = papel["data_entrada"]
        desde = desde.date().isoformat() if hasattr(desde, "date") else "sem data"
        print(f"- qualificação {papel['qualificacao']}, desde {desde}")
    print("Oposição registrada." if ids[0] in opostos else "Sem oposição registrada.")
    return 0


def _conferir(opcoes: argparse.Namespace) -> int:
    esperando = len(oposicoes.pendentes(opcoes.restrita))
    vencidas = oposicoes.vencidas(opcoes.restrita, opcoes.hoje)
    restos = oposicoes.restos(opcoes.restrita)
    print(
        f"Oposições sem lápide: {esperando}; vencidas: {vencidas}; "
        f"de volta ao restrito: {restos}."
    )
    falhas = []
    if getattr(opcoes, "acervo_pessoa", None) is not None:
        sobrou = oposicao_na_tela.restantes(
            opcoes.acervo_pessoa, oposicoes.ids_opostos(opcoes.restrita)
        )
        print(f"Linhas de quem se opôs ainda no acervo da tela: {sobrou}.")
        if sobrou:
            falhas.append(
                f"{sobrou} linha(s) de quem se opôs seguem no acervo da tela: "
                "rode `atender --acervo-pessoa`"
            )
    if vencidas:
        falhas.append(
            f"{vencidas} oposição(ões) do CNPJ passaram dos 15 dias sem lápide"
        )
    if restos:
        falhas.append(
            f"{restos} linha(s) de quem se opôs voltaram ao restrito "
            "(carga durante o pedido): rode `atender`"
        )
    if falhas:
        print("FALHAS: " + "; ".join(falhas))
        return 1
    return 0


def _analisador() -> argparse.ArgumentParser:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    acoes = analisador.add_subparsers(dest="acao", required=True)
    for nome, funcao in (
        ("pedido", _pedido),
        ("atender", _atender),
        ("acesso", _acesso),
        ("conferir", _conferir),
    ):
        acao = acoes.add_parser(nome)
        acao.set_defaults(funcao=funcao)
        acao.add_argument("--restrita", type=Path, required=True)
        acao.add_argument("--hoje", type=date.fromisoformat, default=_hoje())
        if nome in ("pedido", "atender"):
            acao.add_argument("--base", type=Path, required=True)
        acao.add_argument(
            "--acervo-pessoa",
            type=Path,
            default=None,
            help="o acervo_pessoa/ da tela da equipe (linha 829)",
        )
        if nome in ("pedido", "acesso"):
            acao.add_argument("--cnpj", required=True)
            acao.add_argument("--meio", default=None, help="6 dígitos do meio do CPF")
        if nome == "pedido":
            acao.add_argument("--pedido-em", type=date.fromisoformat, default=_hoje())
    return analisador


def main(argv: list[str] | None = None) -> int:
    opcoes = _analisador().parse_args(argv)
    try:
        if opcoes.acervo_pessoa is not None:  # antes de registrar qualquer coisa
            oposicao_na_tela.exigir_acervo(opcoes.acervo_pessoa)
        return opcoes.funcao(opcoes)
    except (
        oposicao_na_tela.SemAcervoError
    ) as erro:  # caminho errado não pode passar por aplicado
        print(f"ERRO: {erro}.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
