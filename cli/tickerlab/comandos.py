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
from pathlib import Path

import click

from tickerlab import __version__, formato, origem, planilha
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
from tickerlab.consultas import (
    compilado,
    faixa_inteira,
    faixa_real,
    maximo,
    traducao,
    valores,
)
from tickerlab.instrucoes_montadas import ARQUIVOS, montar

# pontuação que o CNPJ costuma trazer; o resto (letras do CNPJ alfanumérico, números) fica
PONTUACAO_DO_CNPJ = re.compile(r"[.\-/\s]")
FORMATO_DO_CNPJ = re.compile(r"[0-9A-Z]{14}")
# a chave do setor como a API a dá (`tickerlab setor` lista), o mesmo formato do conector; nada além disso chega
# ao endereço do pedido
FORMATO_DO_SETOR = compilado("chave_do_setor")
# o nome que a API sugere para o deck; qualquer outro (ou com pasta dentro) é ignorado
NOME_DO_DECK = re.compile(
    rf'filename="(tickerlab-(?:empresa-\d{{14}}|setor-{FORMATO_DO_SETOR.pattern})\.pptx)"'
)
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
SITUACOES = valores("prospectar", "--situacao")
VALORES_MAXIMOS = 50  # por filtro, o mesmo limite da API
# Os mapas do português (o que o analista escreve) para a API e as faixas das opções vêm da lista única das
# portas (`consultas.json`), os mesmos do conector.
PORTES = traducao("portes")  # o porte como a Receita o escreve
POR_PAGINA_MAXIMO = maximo("prospectar", "--por-pagina")
TIPOS_DA_ANVISA = traducao(
    "tipos_da_anvisa"
)  # "todos" é a soma dos tipos que a API serve
REGISTROS_MAXIMOS = maximo(
    "prospectar", "--anvisa-ativos-min"
)  # o teto da API para o mínimo de registros
ORDENS_DA_BUSCA = traducao(
    "ordens_da_busca"
)  # só a de registros na Anvisa, do que tem mais para o que tem menos
TIPOS_DE_EVENTO = traducao("tipos_de_evento")
TIPOS_DE_VINCULO = traducao("tipos_de_vinculo")

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
    """A chave do setor em letras minúsculas, números e `_` (o hífen vira `_`, como no conector); a lista certa sai
    de `tickerlab setor`."""
    if valor is None:
        return None
    chave = valor.replace("-", "_")
    if not FORMATO_DO_SETOR.fullmatch(chave):
        raise click.BadParameter(
            "a chave do setor é como `eletricas` ou `saude_suplementar`; veja a lista com `tickerlab setor`.",
            param_hint="CHAVE",
        )
    return chave


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
    anvisa_tipo: str | None = None
    anvisa_ativos_min: int | None = None
    anvisa_total_min: int | None = None
    ordenar_por: str | None = None

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
            "anvisa_active_min": _inteiro(self.anvisa_ativos_min),
            "anvisa_total_min": _inteiro(self.anvisa_total_min),
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
        if self.anvisa_tipo:  # o tipo só escolhe qual contagem: sozinho não filtra (a API também o recusa)
            filtros["anvisa_type"] = TIPOS_DA_ANVISA[self.anvisa_tipo]
        if self.ordenar_por:  # a ordem não filtra: não conta como filtro
            filtros["sort"] = ORDENS_DA_BUSCA[self.ordenar_por]
        return filtros


def _dia(valor: datetime | None) -> str | None:
    return None if valor is None else valor.date().isoformat()


def _inteiro(valor: int | None) -> str | None:
    return None if valor is None else str(valor)


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
        texto = formato.com_aviso_de_nao_disponivel(formatar(corpo), corpo)
        click.echo(formato.com_aviso_de_piloto(texto, corpo))


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


def _cnpj_opcional(
    contexto: click.Context, parametro: click.Parameter, valor: str | None
) -> str | None:
    """O CNPJ de `deck`, que também aceita --setor no lugar dele."""
    return None if valor is None else _cnpj(contexto, parametro, valor)


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
def dossie(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """O dossiê do CNPJ numa saída só: perfil, eventos, vínculos e comparáveis, com fonte e data.

    Gasta 4 pedidos da quota. O perfil é obrigatório; uma seção que a chave não cobre, ou sem dado, aparece em
    `gaps` com o motivo (não achado não quer dizer que não existe). Só pessoa jurídica.
    """
    corpo = _api(contexto).dossie(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.dossie, destino)


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
    """O perfil da empresa: o cadastro na Receita e, da companhia aberta, cada DFP e ITR com o prazo da CVM.

    Em `registration`, a situação cadastral na Receita Federal (com data e motivo), matriz ou filial, mês do
    retrato, razão social, natureza jurídica e opção pelo Simples, cada um na versão que valia no dia. Em
    `periodic_filings`, de companhia aberta, cada DFP e ITR devida até o dia, com o prazo da CVM, a primeira
    entrega, os dias úteis de atraso e a situação (`on_time`, `gray_zone`, `late`, `severely_late`, `not_filed`).
    Em `limits`, o que a leitura não cobre. --so-cadastro traz só o cadastro (para a chave sem o conjunto
    `profiles`).
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
def analise(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """A análise completa da empresa numa resposta: cada bloco que a chave pode ver, com fonte e data.

    Em `blocks`: o cadastro, os sócios e as participadas pessoa jurídica, os vínculos e o auditor, os eventos, a
    ficha de crédito, os ativos, os comparáveis de companhia aberta, os indicadores das agências reguladoras
    (ANEEL e ANS), o balanço no Banco Central (IF.data) e o registro de administradora de fundo imobiliário na
    CVM; com o conjunto de integridade no contrato, também as sanções da CGU (CEIS, CNEP, CEPIM e acordos de
    leniência), os termos de embargo do IBAMA e o Cadastro de Empregadores do MTE, só da pessoa jurídica; com o
    conjunto `extended_sources`, os registros adicionais (Anatel, títulos da ANM, tancagem da ANP e o PAT do MTE).
    Bloco que a chave não vê não aparece.

    `summary` é a frase do topo (fato), `timeline` os marcos datados, `inferences` as leituras (dedução, com os
    blocos de onde vieram: diga que é dedução), `not_found` o que o bloco consultou e não achou, `timed_out` o
    bloco que não respondeu a tempo (não é falta de dado: peça esse bloco pelo comando próprio) e `not_included`
    as bases que a análise não consulta (a ausência delas não quer dizer nada sobre a empresa). Cada lista vem
    cortada (`truncated`): o comando do bloco traz o resto. Cada bloco conta um pedido na quota
    (`requests_used`).
    """
    corpo = _api(contexto).analise(cnpj, _dia(como_era))
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

    O grupo de setores (`sector_group`) é o do FCA entregue até o dia: com --como-era, os pares de então. A
    empresa pedida e cada par trazem receita, EBITDA, lucro, patrimônio, dívida líquida e as razões (margem
    EBITDA, margem líquida, retorno sobre o patrimônio, dívida líquida/EBITDA); `peer_medians` é a mediana de
    cada razão entre os pares. Leia os `limits` antes de usar o número. Pede o conjunto `comparables` no
    contrato; empresa sem FCA no dia sai com o código 5.
    """
    corpo = _api(contexto).comparaveis(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


def _um_codigo(
    formato_: re.Pattern[str], explicacao: str
) -> Callable[[click.Context, click.Parameter, str | None], str | None]:
    """Um conferidor de um código só (sem repetir) que tira a pontuação e recusa o resto."""

    def conferir(
        _contexto: click.Context, parametro: click.Parameter, valor: str | None
    ) -> str | None:
        if valor is None:
            return None
        codigo = PONTUACAO_DE_CODIGO.sub("", valor).upper()
        if not formato_.fullmatch(codigo):
            raise click.BadParameter(explicacao, param_hint=f"--{parametro.name}")
        return codigo

    return conferir


@principal.command()
@click.option(
    "--cnae",
    required=True,
    metavar="<5 ou 7 dígitos>",
    callback=_um_codigo(
        re.compile(r"\d{5}|\d{7}"),
        "o CNAE tem 5 dígitos (a classe) ou 7 (a subclasse), com ou sem pontuação.",
    ),
    help="Atividade do setor (CNAE fiscal): 5 dígitos (a classe, como 35115) ou 7 (a subclasse).",
)
@click.option(
    "--uf",
    metavar="UF",
    callback=_um_codigo(FORMATO_DA_UF, "a UF tem 2 letras, como SP."),
    help="Estado do estabelecimento (2 letras). Sem ela, o país todo.",
)
@click.option(
    "--anos",
    type=faixa_inteira("compradores", "--anos"),
    default=3,
    show_default=True,
    help="Quantos anos para trás olhar os movimentos (1 a 10).",
)
@click.option(
    "--limite",
    type=faixa_inteira("compradores", "--limite"),
    default=20,
    show_default=True,
    help="Quantos compradores trazer (1 a 50; o plano pode cortar antes).",
)
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def compradores(
    contexto: click.Context,
    cnae: str,
    uf: str | None,
    anos: int,
    limite: int,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Quem comprou ou entrou como sócio no setor nos últimos anos: candidatos a comprador.

    Só pessoa jurídica. Cada comprador traz os sinais (entrou como sócio, fundo sócio, controla empresa do setor)
    e as evidências, com exemplos da empresa do setor, a UF e a data. Movimento passado não é intenção de compra:
    leia os `limits`.
    """
    corpo = _api(contexto).compradores(cnae, uf, anos, limite, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@click.option(
    "--dias",
    type=faixa_inteira("novidades", "--dias"),
    default=7,
    show_default=True,
    help="Quantos dias para trás olhar (1 a 30).",
)
@opcao_json
@click.pass_context
def novidades(contexto: click.Context, dias: int, como_json: bool) -> None:
    """As fontes que a pesquisa provou na semana: órgão, data, trecho literal e hash do original.

    De cada uma, `agency` (o órgão público), `date`, `excerpt` (o trecho literal, até 300 caracteres),
    `excerpt_cut` (vazio = sem corte em relação ao trecho que o bot guardou, não o original completo; `inicio`,
    `fim` ou `ambos` quando é só um pedaço: cite como recorte, sem completar nem pôr reticências), `source_url`
    e `original_sha256` (o hash do original, que prova que o trecho está lá). Só fonte pública de órgão e só o
    que tem prova gravada; sem nada novo, a lista vem vazia: "nenhuma fonte nova provada na semana". Não é
    opinião nem recomendação: é citação conferida.
    """
    corpo = _api(contexto).novidades(dias)
    _mostrar(corpo, como_json, formato.novidades)


@principal.command()
@argumento_cnpj
@opcao_como_era
@click.option(
    "--profundidade",
    type=faixa_inteira("vinculos", "--profundidade"),
    default=1,
    show_default=True,
    help="Quantos saltos a partir da empresa (1 a 3): os vínculos dos vínculos.",
)
@click.option(
    "--tipo",
    "tipos",
    multiple=True,
    type=click.Choice(sorted(TIPOS_DE_VINCULO)),
    help="Só um tipo (pode repetir): controlada, coligada, participada (a sociedade e a participação no capital, "
    "pelo FRE) ou auditor (a firma que auditava a companhia, pelo FCA). Sem ela, todos.",
)
@opcao_planilha
@opcao_json
@click.pass_context
def vinculos(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    profundidade: int,
    tipos: tuple[str, ...],
    como_json: bool,
    destino: Path | None,
) -> None:
    """Os vínculos da empresa como eram no dia: controladas, coligadas, participadas e o auditor.

    De 1 a 3 saltos: de quem era controlada (`subsidiary_of`), coligada (`affiliate_of`) ou participada
    (`investee_of`) e quem ela controlava, com a participação no capital (`ownership_pct`, pelo FRE), e a firma
    que a auditava (`audits`, pelo FCA). Cada ponta (`from`, `to`) traz o id na rede (`entity_id`), a raiz do
    CNPJ (`cnpj_root`) e a razão social do dia. Pede o conjunto `links` no contrato; `truncated: true` é lista
    cortada. Só companhia aberta informa controle e coligação, uma vez por ano: leia os `limits`. Pessoa física
    não sai.
    """
    corpo = _api(contexto).vinculos(
        cnpj,
        _dia(como_era),
        profundidade,
        [TIPOS_DE_VINCULO[tipo] for tipo in tipos],
    )
    if not como_json:
        corpo = formato.vinculos_em_linhas(corpo)
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
    help="Segue as páginas até o fim e junta tudo numa resposta (cada página é um pedido da quota). Sem ela, "
    "só os 50 eventos mais novos.",
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
    """Os eventos da empresa, do mais novo ao mais velho: documentos entregues à CVM e trocas de auditor.

    O documento (`ipe_filing`, pelo IPE) traz o protocolo, a categoria e o tipo da CVM, a data de referência e o
    endereço dele (`document_url`); o assunto escrito pela companhia não sai. A troca de auditor
    (`auditor_change`, pelo FCA) traz o dia (`effective_on`), o anterior (`previous`), o novo (`new`) e os anos
    com o anterior (`years_with_previous`). --tipo pode repetir. Com --como-era, só o que já era público no dia.
    `next_cursor` preenchido: há mais páginas; --todas junta todas (um pedido por página). Pede o conjunto `events` no contrato. Sem evento não quer dizer que nada aconteceu:
    leia os `limits`.
    """
    corpo = _api(contexto).eventos(
        cnpj, _dia(como_era), [TIPOS_DE_EVENTO[tipo] for tipo in tipos], todas
    )
    _mostrar(corpo, como_json, formato.eventos, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def ativos(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Os ativos físicos da empresa como eram no dia, um bloco por base de agência, com fonte e data.

    Os contratos de exploração e produção de petróleo e gás da ANP em que a empresa é sócia
    (`oil_gas_contracts`: rodada, fase, campo ou bloco, bacia, terra ou mar, participação e se opera) e, quando a
    chave os vê, as barragens (SIGBM) e os royalties de mineração (CFEM) da ANM. Bloco sem dado vem com `found`
    falso e o que a base não cobre vem em `not_covered`: não achado não quer dizer que a empresa não tem o ativo
    (leia os `limits`). Só pessoa jurídica.
    """
    corpo = _api(contexto).ativos(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def registros(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Os registros da empresa nas agências reguladoras como eram no dia, cada valor com a fonte e a data.

    Em `blocks`: os indicadores comerciais da distribuidora na ANEEL e o IDSS da operadora de saúde na ANS
    (`regulated_activities`) e, com o conjunto `extended_sources`, os processos e os produtos homologados na
    Anatel, a taxa anual por hectare na ANM, a tancagem na ANP e o PAT no MTE (`additional_records`). Bloco que a
    chave não vê não aparece; `not_found` é o bloco consultado que não achou a empresa, e isso não quer dizer que
    ela não tem registro na agência. Não abre o resto da análise: cada conjunto aberto conta um pedido na quota
    (`requests_used`). Sem nenhum dos dois conjuntos, a CLI sai com o código 5. Só pessoa jurídica.
    """
    corpo = _api(contexto).registros(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def compras(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """As compras públicas da empresa como eram no dia, cada valor com a fonte e a data.

    Só com o conjunto `public_procurement` no contrato da organização. Em `blocks`: o cadastro de fornecedor no
    SICAF (se está ativo e habilitado a licitar, com a atividade, a natureza jurídica, o porte e o município) e,
    quando a chave as vê, as compras de medicamentos e produtos de saúde do BPS em que ela é a fornecedora
    (`public_procurement`). `not_found` é o bloco consultado que não achou a empresa e a lista que não aparece não
    foi lida; isso não quer dizer que ela não vende ao governo.
    Não abre o resto da análise: conta um pedido na quota (`requests_used`). Sem o conjunto, a CLI sai com o
    código 5. Só pessoa jurídica.
    """
    corpo = _api(contexto).compras(cnpj, _dia(como_era))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@opcao_planilha
@opcao_json
@click.pass_context
def credito(
    contexto: click.Context,
    cnpj: str,
    como_era: datetime | None,
    como_json: bool,
    destino: Path | None,
) -> None:
    """Os fatos de crédito da empresa como eram no dia, cada um com a fonte e o dia em que ficou público.

    A situação na Receita, os fatos relevantes dos últimos 12 meses e a cessão de recebíveis a FIDC. Não é rating,
    nota nem elegibilidade, e não traz o SCR individual do Banco Central. Só para a chave com o conjunto de
    crédito; sem ele, a CLI sai com o código 5. Só pessoa jurídica.
    """
    corpo = _api(contexto).credito(cnpj, _dia(como_era))
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
    """DFP e ITR da companhia aberta (CVM): cada conta com o documento, a versão e a data de entrega.

    Uma linha por conta e período, do mais novo ao mais velho, com o documento, a data de referência, a versão
    (reapresentação) e a data de entrega. Empresa fechada não tem: a CLI sai com o código 5 e diz que a base não
    tem faturamento de empresa fechada; ela não o estima, e o número não deve ser inventado.
    """
    corpo = _api(contexto).demonstracoes(cnpj, _dia(como_era), _dia(periodo))
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


@principal.command()
@argumento_cnpj
@opcao_como_era
@click.option(
    "--retorno-suposto",
    type=faixa_real("fundo", "--retorno-suposto"),
    metavar="0.12",
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
    """Cadastro, taxas e carteira do fundo (CVM); com --retorno-suposto, o custo da taxa em prazos.

    A carteira é a declarada à CVM (CDA). Com --retorno-suposto, a conta de quanto a taxa de administração leva
    em alguns prazos, sobre um capital de exemplo.
    """
    corpo = _api(contexto).fundo(cnpj, _dia(como_era), retorno_suposto)
    _mostrar(corpo, como_json, formato.resposta_de_dado, destino)


def _nome_do_deck(cabecalho: str | None, padrao: str) -> str:
    """O nome sugerido pela API no cabeçalho, só se tiver o formato esperado; senão o padrão local."""
    achado = NOME_DO_DECK.search(cabecalho or "")
    return achado.group(1) if achado else padrao


@principal.command()
@click.argument("cnpj", required=False, callback=_cnpj_opcional)
@click.option(
    "--setor",
    "chave_do_setor",
    metavar="<chave>",
    callback=_setor,
    help="O deck do setor (a chave que `tickerlab setor` lista) em vez do de uma empresa.",
)
@opcao_como_era
@click.option(
    "--saida",
    "saida",
    type=click.Path(path_type=Path, dir_okay=False),
    metavar="arq.pptx",
    help="Onde gravar o .pptx. Sem isto, grava aqui mesmo com o nome que a API sugere.",
)
@click.option(
    "--substituir",
    is_flag=True,
    help="Troca o arquivo se ele já existir (sem isto a CLI recusa, para não apagar nada).",
)
@click.pass_context
def deck(
    contexto: click.Context,
    cnpj: str | None,
    chave_do_setor: str | None,
    como_era: datetime | None,
    saida: Path | None,
    substituir: bool,
) -> None:
    """Grava o deck (.pptx) da empresa (CNPJ) ou do setor (--setor), com a fonte e a data de cada tabela.

    Um dos dois: `tickerlab deck 11222333000181` ou `tickerlab deck --setor eletricas`. Gasta um pedido da
    quota, como o JSON da mesma rota. Não imprime os dados: diz onde o arquivo ficou. Recusa trocar um arquivo
    que já existe (--substituir troca; use só se a pessoa pediu).
    """
    if (cnpj is None) == (chave_do_setor is None):
        raise click.UsageError(
            "peça o deck de uma empresa (CNPJ) ou de um setor (--setor), um dos dois."
        )
    api = _api(contexto)
    if cnpj is not None:
        conteudo, cabecalho = api.deck_da_empresa(cnpj, _dia(como_era))
        padrao = f"tickerlab-empresa-{cnpj}.pptx"
    else:
        conteudo, cabecalho = api.deck_do_setor(chave_do_setor or "", _dia(como_era))
        padrao = f"tickerlab-setor-{chave_do_setor}.pptx"
    destino = saida or Path(_nome_do_deck(cabecalho, padrao))
    if destino.suffix.lower() != ".pptx":
        raise click.UsageError("--saida termina em .pptx.")
    if destino.exists() and not substituir:
        raise ErroDaCli(
            f"{destino} já existe: use outro --saida ou --substituir para trocar o arquivo.",
            Saida.PEDIDO_INVALIDO,
        )
    try:
        destino.write_bytes(conteudo)
    except OSError as erro:
        raise ErroDaCli(
            f"não consegui gravar o deck em {destino}: {erro.strerror or erro}",
            Saida.ERRO,
        ) from None
    click.echo(
        f"Deck gravado em {destino} (cada tabela com a fonte e a data). {formato.AVISO}"
    )


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

    Sem a chave, a lista dos setores (`eletricas`, `bancos`...) com o dia da ficha, sem gastar a quota. Com a
    chave, o mercado por série da agência (tamanho, CR4, HHI e a faixa de concentração do CADE, por ano), a
    fatia de cada companhia aberta, quem são elas e as notas de método (`notes`): leia-as antes de concluir. O
    setor sai como a ficha da última noite o deixou: --como-era antes dela dá o código 5.
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
    metavar="<2 a 7 dígitos>",
    callback=_codigos(
        FORMATO_DO_CNAE,
        "o CNAE tem de 2 a 7 dígitos (com ou sem pontuação): 35 é a divisão, 3511501 a subclasse.",
    ),
    help="Atividade principal (CNAE fiscal), inteira ou só o começo: 35, 351, 3511501. Pode repetir.",
)
@click.option(
    "--uf",
    multiple=True,
    metavar="UF",
    callback=_codigos(FORMATO_DA_UF, "a UF tem 2 letras, como SP."),
    help="Estado do estabelecimento (2 letras). Pode repetir.",
)
@click.option(
    "--municipio",
    multiple=True,
    metavar="<nome ou código da Receita>",
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
    metavar="<até 4 dígitos>",
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
    "--anvisa-tipo",
    type=click.Choice(list(TIPOS_DA_ANVISA)),
    help="Tipo de registro na Anvisa que as opções abaixo contam: cosmeticos, saneantes, produtos_saude ou "
    "todos (a soma dos três; é o que vale se você der só o mínimo).",
)
@click.option(
    "--anvisa-ativos-min",
    type=faixa_inteira("prospectar", "--anvisa-ativos-min"),
    help="Só empresas com pelo menos este número de registros ativos na Anvisa. É sinal de porte, não faturamento.",
)
@click.option(
    "--anvisa-total-min",
    type=faixa_inteira("prospectar", "--anvisa-total-min"),
    help="Só empresas com pelo menos este número de registros na Anvisa, ativos ou não.",
)
@click.option(
    "--ordenar-por",
    type=click.Choice(list(ORDENS_DA_BUSCA)),
    help="Ordena em vez de por CNPJ: anvisa põe primeiro quem tem mais registros ativos na Anvisa.",
)
@click.option(
    "--por-pagina",
    type=faixa_inteira("prospectar", "--por-pagina"),
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

    Pelo menos um filtro além da situação; os de lista podem repetir (até 50 valores). Cada empresa traz o CNPJ
    e, cada um com fonte e data, razão social, natureza, porte, situação, abertura, CNAE, UF, município e
    matriz. O município é o nome ou o código da Receita (não o do IBGE). A lista é o que o cadastro diz (CNAE e
    porte declarados pela própria empresa), não uma triagem. Pede o conjunto `prospecting` no contrato.

    Os registros na Anvisa (cosméticos, saneantes e produtos para saúde) entram como sinal de porte de empresa
    fechada: com --anvisa-ativos-min, --anvisa-total-min, --anvisa-tipo ou --ordenar-por anvisa, cada empresa
    traz a contagem, com a fonte e o dia do retrato (o tipo e a ordem sozinhos não bastam como filtro). Não é
    faturamento, e empresa sem registro vale 0.

    A resposta vem em páginas, por ordem de CNPJ (ou de registros, com --ordenar-por anvisa): sem --todas, só a
    primeira, e `next_cursor` preenchido quer dizer que há mais; --todas busca todas (cada página é um pedido da
    quota). Não traz sócio, contato nem endereço: para a ficha de uma empresa, `tickerlab empresa`.
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


@principal.command(name="de-onde-vem")
@click.argument("sobre")
@opcao_json
@click.pass_context
def de_onde_vem(contexto: click.Context, sobre: str, como_json: bool) -> None:
    """De onde vem um conjunto ou um campo que a sua chave vê: fonte, licença e piloto. Não gasta a quota.

    Para cada campo, a fonte, a licença e a frase de atribuição dessa fonte, a finalidade do conjunto e se o
    campo é de piloto. SOBRE é o nome de um conjunto (como `credit`) ou de um campo (como `legal_name`), da lista de `tickerlab
    catalogo`; de um campo, sai cada conjunto que o tem. Serve para saber de onde veio um número antes de
    citá-lo e o que pode ser dito dele. Não traz dado de empresa, o significado de cada campo, o dia do retrato
    nem conjunto ou campo que a sua chave não vê; nome que ela não vê sai com o código 5.
    """
    try:
        nome = origem.pergunta(sobre)
    except origem.NomeInvalido as erro:
        raise ErroDaCli(str(erro), Saida.USO) from None
    try:
        corpo = origem.explicacao(_api(contexto).catalogo(), nome)
    except origem.NadaComEsseNome as erro:
        raise ErroDaCli(str(erro), Saida.SEM_DADO) from None
    _mostrar(corpo, como_json, formato.de_onde_vem)


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
    "qual", type=click.Choice(sorted(ARQUIVOS)), default="agents", required=False
)
def instrucoes(qual: str) -> None:
    """Imprime as instruções para o agente de IA: `agents` (AGENTS.md) ou `skill` (SKILL.md do Claude Code).

    Ex.: `tickerlab instrucoes > AGENTS.md` na pasta do seu projeto. Os comandos saem da ajuda de cada um
    (a mesma do --help), montada na hora.
    """
    click.echo(montar(qual, principal), nl=False)
