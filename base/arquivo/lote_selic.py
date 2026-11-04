"""Meta da Selic (SGS 432) e Focus Selic anual do Banco Central, guardados pelo arquivista (linha 225).

A tabela `bcb_selic_focus` (`base/bcb_selic_focus.py`) nasceu de uma exportação do banco de produção;
o servidor de casa não tem esse banco. Estas duas fontes guardam, como vieram, o que a tabela precisa,
direto do BCB (família já licenciada, ODbL citando o BC):

- `bcb-sgs-selic-meta`: SGS 432 desde 2000, em janelas de até 10 anos (acima disso o SGS responde 406);
  a última janela termina em 31/12 do ano, para o endereço não mudar a cada dia;
- `bcb-focus-selic-anual`: Focus (Olinda, `ExpectativasMercadoAnuais`), Selic, só a conta que o boletim
  divulga (`baseCalculo` 0), um pedido por ano da pesquisa.

O Olinda responde `value: []` para o que ainda não saiu: isso é `SemArquivo`, nunca "ok".
"""

from datetime import date, datetime
from urllib.parse import quote

from base.arquivo.coleta import Alvo, Cliente, Fonte
from base.arquivo.lote_acervos import janelas
from base.arquivo.lote_bcb import olinda_com_dados

SEMANAL = "semanal"
PRIMEIRO_DIA_DA_META = date(2000, 1, 1)
PRIMEIRO_ANO_DO_FOCUS = 2001  # a primeira pesquisa do Focus com a Selic anual
CODIGO_DA_META = 432
SGS = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial={inicio:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}"
)
FOCUS = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoAnuais"
)
PEDIDOS_DO_FOCUS_POR_ANO = (
    20000  # uma pesquisa por dia útil, uns cinco anos de referência cada
)


def descobrir_meta(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um pedido por janela de 10 anos, de 2000 até 31/12 do ano de `agora`."""
    fim = date(agora.year, 12, 31)
    return [
        Alvo(SGS.format(codigo=CODIGO_DA_META, inicio=inicio, fim=ate), ".json")
        for inicio, ate in janelas(PRIMEIRO_DIA_DA_META, fim)
    ]


def endereco_do_focus(ano: int) -> str:
    """As pesquisas do Focus de `ano` para a Selic (o Olinda só aceita `%20`, nunca o `+`)."""
    filtro = (
        f"Indicador eq 'Selic' and baseCalculo eq 0 "
        f"and Data ge '{ano}-01-01' and Data le '{ano}-12-31'"
    )
    consulta = f"$filter={quote(filtro, safe="$'")}&$top={PEDIDOS_DO_FOCUS_POR_ANO}&$format=json"
    return f"{FOCUS}?{consulta}"


def descobrir_focus(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um pedido por ano da pesquisa, de 2001 até o ano de `agora`."""
    return [
        Alvo(endereco_do_focus(ano), ".json", olinda_com_dados(endereco_do_focus(ano)))
        for ano in range(PRIMEIRO_ANO_DO_FOCUS, agora.year + 1)
    ]


def fontes() -> list[Fonte]:
    """As duas fontes do lote, para o `FONTES` do arquivista."""
    return [
        Fonte("bcb-sgs-selic-meta", SEMANAL, descobrir_meta, "json"),
        Fonte("bcb-focus-selic-anual", SEMANAL, descobrir_focus, "json"),
    ]
