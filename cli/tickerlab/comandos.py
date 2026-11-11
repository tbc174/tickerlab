"""Os comandos da CLI `tickerlab` (v1, sobre as rotas da API externa que já existem; ADR 0127).

Cada comando de dado chama uma rota, imprime a resposta em tabela (padrão, para a pessoa) ou o envelope da
API inteiro com `--json` (para o agente) e sai com o código do tipo de problema (`cliente.Saida`).
"""

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
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
# os filtros da busca (`prospectar`): o formato de cada um, conferido antes de gastar um pedido
# o CNAE: a subclasse inteira (7 dígitos) ou um prefixo (divisão, grupo, classe)
FORMATO_DO_CNAE = re.compile(r"\d{2,7}")
FORMATO_DA_UF = re.compile(r"[A-Z]{2}")
# o município: o código da Receita (até 4 dígitos, não o do IBGE) ou o nome, que a API procura
FORMATO_DO_CODIGO_DO_MUNICIPIO = re.compile(r"\d{1,4}")
TAMANHO_MAXIMO_DO_NOME = 60
FORMATO_DA_NATUREZA = re.compile(
    r"\d{1,4}"
)  # a natureza da Receita (2054) ou o começo dela (2)
PONTUACAO_DE_CODIGO = re.compile(r"[.\-/\s]")
SITUACOES = ("ativa", "baixada", "inapta", "suspensa", "nula")
VALORES_MAXIMOS = 50  # por filtro, o mesmo limite da API
# o porte como a Receita o escreve, em português na CLI e em inglês na API
PORTES = {
    "micro": "micro",
    "pequena": "small",
    "demais": "other",
    "nao_informado": "not_informed",
}
POR_PAGINA_MAXIMO = 100
# os tipos de evento como a CLI os recebe e como a API os chama
TIPOS_DE_EVENTO = {"documento": "ipe_filing", "auditor": "auditor_change"}

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


def _codigos(
    formato_: re.Pattern[str], explicacao: str
) -> Callable[[click.Context, click.Parameter, object], object]:
    """Um conferidor de código (CNAE, UF, município, natureza) que tira a pontuação e recusa o resto."""

    def conferir(
        _contexto: click.Context, parametro: click.Parameter, valores: tuple[str, ...]
    ) -> tuple[str, ...]:
        _no_maximo(valores, parametro)
        limpos = []
        for texto in valores:
            codigo = PONTUACAO_DE_CODIGO.sub("", texto).upper()
            if not formato_.fullmatch(codigo):
                raise click.BadParameter(explicacao, param_hint=f"--{parametro.name}")
            limpos.append(codigo)
        return tuple(limpos)

    return conferir


def _no_maximo(valores: tuple[str, ...], parametro: click.Parameter) -> None:
    if len(valores) > VALORES_MAXIMOS:
        raise click.BadParameter(
            f"no máximo {VALORES_MAXIMOS} valores por filtro.",
            param_hint=f"--{parametro.name}",
        )


def _municipios(
    _contexto: click.Context, parametro: click.Parameter, valores: tuple[str, ...]
) -> tuple[str, ...]:
    """O código da Receita (até 4 dígitos) ou o nome do município; quem procura o nome é a API."""
    _no_maximo(valores, parametro)
    limpos = []
    for texto in valores:
        valor = texto.strip()
        e_codigo = FORMATO_DO_CODIGO_DO_MUNICIPIO.fullmatch(valor)
        if not e_codigo and (
            valor.isdigit() or not valor or len(valor) > TAMANHO_MAXIMO_DO_NOME
        ):
            raise click.BadParameter(
                "o município é o nome (Campinas) ou o código da Receita, de até 4 dígitos (7107 é São "
                "Paulo); o código do IBGE, de 7 dígitos, não vale aqui.",
                param_hint="--municipio",
            )
        limpos.append(valor)
    return tuple(limpos)


@dataclass(frozen=True)
class FiltrosDaBusca:
    """Os filtros do `prospectar` como a CLI os recebe (cada um pode ter vários valores)."""

    cnae: tuple[str, ...] = ()
    uf: tuple[str, ...] = ()
    municipio: tuple[str, ...] = ()
    porte: tuple[str, ...] = ()
    natureza: tuple[str, ...] = ()
    situacao: tuple[str, ...] = ()
    aberta_depois: datetime | None = None
    aberta_antes: datetime | None = None
    so_matriz: bool = False

    def para_a_api(self) -> dict[str, str | list[str]]:
        """Os filtros com os nomes da API; erro de uso se não há nenhum além da situação."""
        listas = {
            "cnae": list(self.cnae),
            "state": list(self.uf),
            "municipality": list(self.municipio),
            "size": [PORTES[porte] for porte in self.porte],
            "legal_nature": list(self.natureza),
        }
        unicos = {
            "opened_after": _dia(self.aberta_depois),
            "opened_before": _dia(self.aberta_antes),
            "head_office": "true" if self.so_matriz else None,
        }
        filtros: dict[str, str | list[str]] = {
            **{nome: valores for nome, valores in listas.items() if valores},
            **{nome: valor for nome, valor in unicos.items() if valor},
        }
        if not filtros:
            raise click.UsageError(
                "diga pelo menos um filtro além da situação, como `tickerlab prospectar --cnae 3511 "
                "--uf SP`: a busca sem filtro devolveria a base inteira."
            )
        if self.situacao:
            filtros["registration_status"] = list(self.situacao)
        return filtros


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
@click.option(
    "--so-cadastro",
    is_flag=True,
    help="Só o cadastro na Receita (a rota /companies/{cnpj}), sem as entregas à CVM; serve à chave que "
    "tem só o conjunto `companies`.",
)
@opcao_planilha
@opcao_json
@click.pass_context
def empresa(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    so_cadastro: bool,
    como_json: bool,
    destino: Path | None,
) -> None:
    """O perfil da empresa: cadastro na Receita e, da companhia aberta, cada DFP e ITR com o prazo da CVM.

    O cadastro traz a situação (com data e motivo), matriz ou filial, razão social, natureza jurídica e
    Simples. As entregas dizem, de cada DFP e ITR devida até o dia, o prazo, quando saiu a primeira
    versão, os dias úteis de atraso e a situação (on_time, gray_zone, late, severely_late, not_filed).
    """
    api = _api(contexto)
    dia = _dia(como_era)
    corpo = api.empresa(cnpj, dia) if so_cadastro else api.perfil(cnpj, dia)
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def comparaveis(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Os comparáveis da companhia aberta: as do mesmo grupo de setores, com os números do último DFP.

    Cada par traz receita, EBITDA, lucro, patrimônio, dívida líquida e as razões (margem EBITDA, margem
    líquida, retorno sobre o patrimônio, dívida líquida/EBITDA); `peer_medians` é a mediana de cada razão
    entre os pares. O setor é o do FCA entregue até o dia: com --como-era, os pares de então. Leia os
    `limits` antes de usar o número.
    """
    corpo = _api(contexto).comparaveis(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@click.option(
    "--tipo",
    "tipos",
    multiple=True,
    type=click.Choice(sorted(TIPOS_DE_EVENTO)),
    help="Só um tipo (pode repetir): documento (o que a companhia entregou à CVM pelo IPE: fato "
    "relevante, comunicado, assembleia...) ou auditor (troca de auditor, pelo FCA). Sem ela, todos.",
)
@click.option(
    "--todas",
    is_flag=True,
    help="Segue as páginas até o fim e junta tudo numa resposta (cada página é um pedido da quota).",
)
@opcao_planilha
@opcao_json
@click.pass_context
def eventos(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    tipos: tuple[str, ...],
    todas: bool,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Os eventos da empresa, do mais novo ao mais velho: documentos à CVM e trocas de auditor.

    O documento traz o protocolo, a categoria e o tipo da CVM, a data de referência e o endereço dele (o
    assunto escrito pela companhia não sai). A troca de auditor traz o dia, o anterior, o novo e os anos
    com o anterior. Com --como-era, só o que já era público no dia. Leia os `limits`.
    """
    corpo = _api(contexto).eventos(
        cnpj, _dia(como_era), [TIPOS_DE_EVENTO[tipo] for tipo in tipos], todas
    )
    _mostrar(corpo, como_json, formato.eventos, destino)


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
@click.option(
    "--cnae",
    multiple=True,
    callback=_codigos(
        FORMATO_DO_CNAE,
        "o CNAE tem de 2 a 7 dígitos (com ou sem pontuação): 35 é a divisão, 3511501 a subclasse.",
    ),
    help="Atividade principal (CNAE fiscal), inteira ou só o começo: 35, 351, 3511501. Pode repetir.",
)
@click.option(
    "--uf",
    multiple=True,
    callback=_codigos(FORMATO_DA_UF, "a UF tem 2 letras, como SP."),
    help="Estado do estabelecimento (2 letras). Pode repetir.",
)
@click.option(
    "--municipio",
    multiple=True,
    callback=_municipios,
    help="Município: o nome (Campinas; junte --uf se o nome existe em mais de um estado) ou o código "
    "da Receita (até 4 dígitos; 7107 é São Paulo). Não é o código do IBGE. Pode repetir.",
)
@click.option(
    "--porte",
    multiple=True,
    type=click.Choice(list(PORTES)),
    help="Porte declarado à Receita: micro, pequena, demais ou nao_informado. Pode repetir.",
)
@click.option(
    "--natureza",
    multiple=True,
    callback=_codigos(
        FORMATO_DA_NATUREZA,
        "a natureza jurídica tem até 4 dígitos, como 2054 (S.A. fechada) ou só o começo, como 2.",
    ),
    help="Natureza jurídica da Receita, inteira ou o começo (2054 é S.A. fechada, 2062 é limitada). "
    "Pode repetir.",
)
@click.option(
    "--situacao",
    multiple=True,
    type=click.Choice(SITUACOES),
    help="Situação cadastral na Receita; sem ela, só as ativas. Não conta como filtro. Pode repetir.",
)
@click.option(
    "--aberta-depois",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Só as abertas a partir deste dia (AAAA-MM-DD).",
)
@click.option(
    "--aberta-antes",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Só as abertas antes deste dia (AAAA-MM-DD); para empresas com mais de 10 anos, 10 anos atrás.",
)
@click.option(
    "--so-matriz", is_flag=True, help="Só a matriz de cada empresa, sem as filiais."
)
@click.option(
    "--por-pagina",
    type=click.IntRange(1, POR_PAGINA_MAXIMO),
    help=f"Empresas por página (até {POR_PAGINA_MAXIMO}; sem ela, o padrão da API).",
)
@click.option(
    "--todas",
    is_flag=True,
    help="Busca todas as páginas, uma atrás da outra (cada página é um pedido da quota).",
)
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def prospectar(
    contexto: click.Context,
    por_pagina: int | None,
    todas: bool,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
    **filtros_da_cli: object,
) -> None:
    """Empresas por atividade, lugar, porte e idade, do cadastro da Receita (só empresa, nunca pessoa).

    Pelo menos um filtro além da situação. A resposta vem em páginas, por ordem de CNPJ: sem --todas, só a
    primeira (e o aviso de que há mais). Com --planilha lista.xlsx, a lista vai para o Excel, com a fonte e
    a data de cada linha. Não traz sócio, contato nem endereço: para a ficha de uma empresa,
    `tickerlab empresa`.
    """
    filtros = FiltrosDaBusca(**filtros_da_cli).para_a_api()  # type: ignore[arg-type]
    if por_pagina is not None:
        filtros["limit"] = str(por_pagina)
    if como_era is not None:
        filtros["known_at"] = como_era.date().isoformat()
    corpo = _api(contexto).buscar_empresas(filtros, todas)
    _mostrar(corpo, como_json, formato.prospeccao, destino)


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
