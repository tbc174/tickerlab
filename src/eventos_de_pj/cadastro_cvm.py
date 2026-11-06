"""Os eventos de PJ do cadastro de companhias abertas da CVM (`cad_cia_aberta.csv`, `base/cadastro.py`).

O arquivista guarda uma versão do arquivo a cada dia em que ele muda. Cada versão é uma leitura
boa do dia em que foi baixada:

- **mudou:** um campo da companhia (situação, cancelamento e motivo, setor, UF, razão social) com
  outro valor que na versão anterior;
- **não observado:** a companhia que estava na versão anterior e saiu do arquivo;
- **fonte falhou:** o mês inteiro sem nenhuma tentativa boa de baixar o arquivo; o evento é do
  último dia do mês, quando o mês acabou sem leitura.

Os CNPJs repetidos (uma empresa com mais de um registro) ficam com o registro mais recente.
"""

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

import pandas as pd

from base.cadastro import FONTE_DO_CADASTRO
from src.eventos_de_pj.evento import (
    DescricaoDaFonte,
    EventoDePJ,
    Leitura,
    Tentativa,
    cnpj_do_objeto,
    eventos_das_leituras,
)

DESCRICAO = DescricaoDaFonte(
    fonte=FONTE_DO_CADASTRO,
    objeto_tipo="pj",
    documento="cadastro de companhias abertas (CVM, cad_cia_aberta.csv)",
    versao_do_calculo="eventos_cadastro_cvm 1",
    formula="mudança = o campo de uma versão do arquivo contra o da versão anterior",
)
CAMPOS = ("empresa", "situacao", "cancelamento", "motivo_cancelamento", "setor", "uf")
Versao = tuple[
    date, pd.DataFrame
]  # o dia da coleta e a tabela de `base.cadastro.ler_cadastro`


def _valor(valor: object) -> object:
    if isinstance(valor, pd.Timestamp):
        return valor.date().isoformat()
    if valor is None or pd.isna(valor):  # type: ignore[arg-type]
        return None
    return valor


def _objetos(tabela: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Por CNPJ, os campos do registro mais recente."""
    ordenada = tabela.sort_values("registro", kind="stable")
    objetos: dict[str, dict[str, object]] = {}
    for linha in ordenada.to_dict("records"):
        objetos[cnpj_do_objeto(str(linha["cnpj"]))] = {
            c: _valor(linha.get(c)) for c in CAMPOS
        }
    return objetos


def _fim_do_mes(dia: date) -> date:
    proximo = (dia.replace(day=1) + timedelta(days=32)).replace(day=1)
    return proximo - timedelta(days=1)


def _meses(primeiro: date, ultimo: date) -> list[date]:
    meses, mes = [], primeiro.replace(day=1)
    while mes <= ultimo:
        meses.append(mes)
        mes = _fim_do_mes(mes) + timedelta(days=1)
    return meses


def _falhas(dias_bons: set[date], dias: Sequence[date], ate: date) -> list[Leitura]:
    """Uma leitura que falhou para cada mês fechado até `ate` sem nenhum dia bom."""
    if not dias:
        return []
    meses_bons = {dia.replace(day=1) for dia in dias_bons}
    return [
        Leitura(periodo=mes, publico_em=_fim_do_mes(mes), ok=False, objetos={})
        for mes in _meses(min(dias), ate)
        if _fim_do_mes(mes) <= ate and mes not in meses_bons
    ]


def eventos_do_cadastro_cvm(
    versoes: Iterable[Versao],
    tentativas: Iterable[Tentativa],
    *,
    ate: date,
    cnpjs: Iterable[str] | None = None,
) -> list[EventoDePJ]:
    """Os eventos das companhias nos três estados, com o que se sabia no dia `ate`.

    `versoes` são as versões guardadas do arquivo; `tentativas`, as do registro de coletas (o
    `periodo` é o próprio dia). `cnpjs` limita às companhias pedidas.
    """
    versoes = [(dia, tabela) for dia, tabela in versoes if dia <= ate]
    tentativas = [t for t in tentativas if t.dia <= ate]
    pedidos = None if cnpjs is None else {cnpj_do_objeto(c) for c in cnpjs}
    lidas = []
    for dia, tabela in versoes:
        objetos = _objetos(tabela)
        if pedidos is not None:
            objetos = {
                cnpj: campos for cnpj, campos in objetos.items() if cnpj in pedidos
            }
        lidas.append(Leitura(periodo=dia, publico_em=dia, ok=True, objetos=objetos))
    dias_bons = {t.dia for t in tentativas if t.ok} | {dia for dia, _ in versoes}
    todos_os_dias = [t.dia for t in tentativas] + [dia for dia, _ in versoes]
    return eventos_das_leituras(
        [*lidas, *_falhas(dias_bons, todos_os_dias, ate)], DESCRICAO
    )
