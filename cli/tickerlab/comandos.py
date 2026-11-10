"""Os comandos da CLI `tickerlab` (v1, sobre as rotas da API externa que já existem; ADR 0127).

Cada comando de dado chama uma rota, imprime a resposta em tabela (padrão, para a pessoa) ou o envelope da
API inteiro com `--json` (para o agente) e sai com o código do tipo de problema (`cliente.Saida`).
"""

import json
import os
import re
from collections.abc import Callable
from datetime import datetime
from importlib import resources
from pathlib import Path

import click

from tickerlab import __version__, formato, planilha
from tickerlab.cliente import (
    SEM_CHAVE,
    AbrirHttp,
    ApiDoTickerlab,
    ErroDaCli,
    Saida,
    abrir_http,
)
from tickerlab.configuracao import (
    VARIAVEL_DA_CHAVE,
    ConfiguracaoInvalidaError,
    apagar_chave,
    chave_da_api,
    conferir_chave,
    endereco_da_api,
    gravar_chave,
)

# pontuação que o CNPJ costuma trazer; o resto (letras do CNPJ alfanumérico, números) fica
PONTUACAO_DO_CNPJ = re.compile(r"[.\-/\s]")
FORMATO_DO_CNPJ = re.compile(r"[0-9A-Z]{14}")
# a chave do setor como a API a dá (`tickerlab setor` lista); nada além disso chega ao endereço do pedido
FORMATO_DO_SETOR = re.compile(r"[a-z0-9_]{1,40}")
INSTRUCOES = {"agents": "AGENTS.md", "skill": "SKILL.md"}

Formatar = Callable[[dict], str]


def normalizar_cnpj(texto: str) -> str:
    """O CNPJ só com os 14 caracteres (com ou sem pontuação na entrada); quem confere o dígito é a API."""
    cnpj = PONTUACAO_DO_CNPJ.sub("", texto).upper()
    if not FORMATO_DO_CNPJ.fullmatch(cnpj):
        raise click.BadParameter(
            "o CNPJ tem 14 caracteres (com ou sem pontos, barra e traço), como 33.000.167/0001-01.",
            param_hint="CNPJ",
        )
    return cnpj


def _cnpj(_contexto: click.Context, _parametro: click.Parameter, valor: str) -> str:
    return normalizar_cnpj(valor)


def _setor(
    _contexto: click.Context, _parametro: click.Parameter, valor: str | None
) -> str | None:
    """A chave do setor em letras minúsculas, números e `_`; a lista certa sai de `tickerlab setor`."""
    if valor is not None and not FORMATO_DO_SETOR.fullmatch(valor):
        raise click.BadParameter(
            "a chave do setor é como `eletricas` ou `saude_suplementar`; veja a lista com `tickerlab setor`.",
            param_hint="CHAVE",
        )
    return valor


def _dia(valor: datetime | None) -> str | None:
    return None if valor is None else valor.date().isoformat()


def _api(contexto: click.Context) -> ApiDoTickerlab:
    """A API com a chave e o endereço do ambiente; erro claro se falta a chave ou o endereço é inseguro."""
    try:
        endereco = endereco_da_api(os.environ)
        chave = chave_da_api(os.environ)
    except ConfiguracaoInvalidaError as erro:
        raise ErroDaCli(str(erro), Saida.USO) from None
    if chave is None:
        raise ErroDaCli(SEM_CHAVE, Saida.CHAVE)
    abrir: AbrirHttp = contexto.find_root().obj or abrir_http
    return ApiDoTickerlab(abrir(endereco), chave, endereco)


def _mostrar(
    corpo: dict, como_json: bool, formatar: Formatar, destino: Path | None = None
) -> None:
    """Imprime a resposta (tabela ou JSON); com `destino`, grava a planilha e diz onde ela ficou."""
    if destino is not None:
        try:
            gravados = planilha.gravar(destino, corpo)
        except OSError as erro:
            raise ErroDaCli(
                f"não consegui gravar a planilha em {destino}: {erro.strerror or erro}",
                Saida.ERRO,
            ) from None
        if not como_json:
            click.echo(formato.planilha_gravada(gravados, corpo))
            return
    if como_json:
        click.echo(json.dumps(corpo, ensure_ascii=False, indent=2))
    else:
        click.echo(formatar(corpo))


def _extensao_da_planilha(
    _contexto: click.Context, _parametro: click.Parameter, valor: Path | None
) -> Path | None:
    if valor is not None and valor.suffix.lower() not in planilha.EXTENSOES:
        raise click.BadParameter(
            "a planilha termina em .xlsx (Excel, uma aba por tabela) ou .csv (um arquivo por tabela).",
            param_hint="--planilha",
        )
    return valor


opcao_json = click.option(
    "--json",
    "como_json",
    is_flag=True,
    help="Imprime a resposta inteira da API em JSON (para o agente), com fonte e data de cada campo.",
)
opcao_como_era = click.option(
    "--como-era",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Mostra o dado como era público neste dia (AAAA-MM-DD); sem ela, hoje.",
)
opcao_planilha = click.option(
    "--planilha",
    "destino",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    callback=_extensao_da_planilha,
    help="Grava a resposta numa planilha para o Excel: .xlsx (uma aba por tabela, mais a aba das fontes) "
    "ou .csv (separado por ponto e vírgula, um arquivo por tabela). Cada linha leva a fonte e a data.",
)
argumento_cnpj = click.argument("cnpj", callback=_cnpj)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="tickerlab")
def principal() -> None:
    """TickerLab: dados de empresas e fundos do Brasil, com fonte e data em cada número.

    A chave vem de TICKERLAB_API_KEY ou de `tickerlab login`. Nada aqui é recomendação de investimento.
    """


@principal.command()
@argumento_cnpj
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def empresa(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Situação cadastral, razão social, natureza jurídica e Simples do CNPJ, na Receita Federal."""
    corpo = _api(contexto).empresa(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@click.option(
    "--periodo",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Só o período que termina neste dia (AAAA-MM-DD), como 2025-12-31.",
)
@opcao_planilha
@opcao_json
@click.pass_context
def demonstracoes(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    periodo: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """DFP e ITR da companhia aberta (CVM): cada conta com o documento, a versão e a data de entrega."""
    corpo = _api(contexto).demonstracoes(cnpj, _dia(como_era), _dia(periodo))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@click.option(
    "--retorno-suposto",
    type=float,
    help="Retorno bruto ao ano que você supõe, em fração (0.12 = 12%), para a conta do custo da taxa.",
)
@opcao_planilha
@opcao_json
@click.pass_context
def fundo(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    retorno_suposto: float | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Cadastro, taxas e carteira do fundo (CVM); com --retorno-suposto, o custo da taxa em prazos."""
    corpo = _api(contexto).fundo(cnpj, _dia(como_era), retorno_suposto)
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@click.argument("chave", required=False, callback=_setor)
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def setor(
    contexto: click.Context,
    chave: str | None,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """O mercado do setor (tamanho, CR4 e HHI por ano), a fatia de cada companhia aberta e quem são.

    Sem CHAVE, lista os setores disponíveis, sem gastar a quota. O setor sai como a ficha da última noite
    o deixou: --como-era antes dela não tem resposta.
    """
    api = _api(contexto)
    if chave is None:
        _mostrar(api.setores(), como_json, formato.setores, destino)
        return
    _mostrar(
        api.setor(chave, _dia(como_era)), como_json, formato.resposta_de_dado, destino
    )


@principal.command()
@opcao_json
@click.pass_context
def catalogo(contexto: click.Context, como_json: bool) -> None:
    """O que a sua chave pode pedir hoje: conjuntos, campos, fontes e licenças. Não gasta a quota."""
    _mostrar(_api(contexto).catalogo(), como_json, formato.catalogo)


@principal.command()
@opcao_json
@click.pass_context
def consumo(contexto: click.Context, como_json: bool) -> None:
    """Os pedidos do mês da sua organização, os limites do plano e o que ainda cabe. Não gasta a quota."""
    _mostrar(_api(contexto).consumo(), como_json, formato.consumo)


@principal.command()
@click.option(
    "--sem-conferir",
    is_flag=True,
    help="Grava sem perguntar à API se a chave vale (para configurar sem internet).",
)
@click.pass_context
def login(contexto: click.Context, sem_conferir: bool) -> None:
    """Grava a chave da API no seu usuário (pergunta sem mostrar; nunca passe a chave como argumento)."""
    digitada = click.prompt(
        "Chave da API (não aparece enquanto você digita)", hide_input=True
    )
    try:
        chave = conferir_chave(digitada)
    except ConfiguracaoInvalidaError as erro:
        raise ErroDaCli(str(erro), Saida.USO) from None
    if not sem_conferir:
        try:
            endereco = endereco_da_api(os.environ)
        except ConfiguracaoInvalidaError as erro:
            raise ErroDaCli(str(erro), Saida.USO) from None
        abrir: AbrirHttp = contexto.find_root().obj or abrir_http
        ApiDoTickerlab(abrir(endereco), chave, endereco).consumo()  # 401 não grava
    arquivo = gravar_chave(chave, os.environ)
    click.echo(f"Chave gravada em {arquivo} (só o seu usuário lê).")
    if os.environ.get(VARIAVEL_DA_CHAVE, "").strip():
        click.echo(
            f"Atenção: {VARIAVEL_DA_CHAVE} está definida e vale mais que o arquivo.",
            err=True,
        )


@principal.command()
def logout() -> None:
    """Apaga a chave gravada pelo `tickerlab login` (a variável de ambiente, se houver, fica)."""
    if apagar_chave(os.environ):
        click.echo("Chave apagada deste usuário.")
    else:
        click.echo("Não havia chave gravada.")


@principal.command()
@click.argument(
    "qual", type=click.Choice(sorted(INSTRUCOES)), default="agents", required=False
)
def instrucoes(qual: str) -> None:
    """Imprime as instruções para o agente de IA: `agents` (AGENTS.md) ou `skill` (SKILL.md do Claude Code).

    Ex.: `tickerlab instrucoes > AGENTS.md` na pasta do seu projeto.
    """
    arquivo = resources.files("tickerlab") / "instrucoes" / INSTRUCOES[qual]
    click.echo(arquivo.read_text(encoding="utf-8"), nl=False)
