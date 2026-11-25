"""A cola dos eventos de PJ com o acervo e o registro de coletas (linha 414, sobra da linha 115).

Os adaptadores de `fidc.py` e `cadastro_cvm.py` recebem prontas as versões e as tentativas de
download; aqui elas são lidas de onde estão guardadas:

- **versões:** cada conteúdo diferente de um arquivo, guardado pelo arquivista com o dia em que foi
  baixado (`src.banco.coletas.versoes_guardadas`);
- **tentativas:** cada download do endereço no registro de coletas (`registro.tentativas_da_url`).

**Sem olhar o futuro:** um evento existe a partir do dia em que a versão foi guardada (o dia em que a
base viu), nunca do dia do fato. Com `como_em`/`ate`, só valem as versões e as tentativas daquele dia
para trás: uma regravação posterior não reescreve o que se via antes.

Limites honestos: `versoes_guardadas` guarda cada conteúdo uma vez, então um arquivo que volta a um
conteúdo antigo (A, depois B, depois A) não mostra a volta; a primeira versão de cada informe de
FIDC não diz quando o fundo entrou (vale o prazo da CVM, `base.publicacao`); e o mês do informe cuja
versão sumiu do acervo fica de fora (melhor sem o mês do que com data inventada).
"""

from datetime import date, timedelta

import pandas as pd
import sqlalchemy as sa

from base import fidc, publicacao
from base.arquivo.fontes import FIDC_DO_MES
from base.cadastro import ler_cadastro
from src import acervo
from src.banco.coletas import versoes_guardadas
from src.demonstracoes import URL_DO_CADASTRO
from src.eventos_de_pj import cadastro_cvm, registro
from src.eventos_de_pj import fidc as eventos_fidc
from src.eventos_de_pj.evento import EventoDePJ, Tentativa
from src.securitizacao import monitoramento

CHAVE_DO_INFORME = ["competencia", "cnpj_fundo"]  # um informe por fundo e mês
DIAS_DE_FOLGA_PARA_O_PROXIMO_MES = 32  # de qualquer dia do mês, cai no mês seguinte


def fim_do_mes(mes: date) -> date:
    """O último dia do mês de `mes`: a competência do informe de FIDC."""
    primeiro = mes.replace(day=1)
    proximo = (primeiro + timedelta(days=DIAS_DE_FOLGA_PARA_O_PROXIMO_MES)).replace(
        day=1
    )
    return proximo - timedelta(days=1)


def meses_ate(hoje: date, quantos: int) -> list[date]:
    """As competências (fim de mês) dos `quantos` meses já fechados antes de `hoje`, da mais antiga à
    mais nova. Peça um mês a mais do que se quer ver: o evento é a comparação com o mês anterior."""
    meses: list[date] = []
    mes = hoje.replace(day=1)
    for _ in range(quantos):
        mes = (mes - timedelta(days=1)).replace(day=1)
        meses.append(fim_do_mes(mes))
    return meses[::-1]


def _dia_ate(dia: date, limite: date | None) -> bool:
    return limite is None or dia <= limite


# ---------------------------------------------------------------- informe mensal de FIDC


def endereco_do_informe(competencia: date) -> str:
    """O endereço do arquivo do informe de um mês, o mesmo que o arquivista baixa."""
    return FIDC_DO_MES.format(aaaamm=f"{competencia:%Y%m}")


def _leituras_vazias() -> pd.DataFrame:
    colunas = {c: pd.Series(dtype="object") for c in monitoramento.COLUNAS}
    for coluna in ("competencia", "disponivel_em"):
        colunas[coluna] = pd.Series(dtype="datetime64[ns]")
    return pd.DataFrame(colunas)


def _versoes_do_informe(
    conexao: sa.Connection, endereco: str, como_em: date | None
) -> list[publicacao.Versao]:
    """As versões guardadas do arquivo, da mais antiga à mais nova, vistas até `como_em`."""
    todas = publicacao.todas_as_versoes(conexao, [(endereco, b"")])
    return [
        v
        for v in todas
        if v.dia is not None and v.caminho and _dia_ate(v.dia.date(), como_em)
    ]


def leituras_do_informe(
    conexao: sa.Connection, competencia: date, *, como_em: date | None = None
) -> pd.DataFrame | None:
    """Os fundos do informe de um mês como `monitoramento.leituras_dos_informes`, com o conteúdo da
    versão mais nova guardada até `como_em` e `disponivel_em = max(prazo, dia em que foi visto)`.

    None se nenhuma versão está no acervo (ou nenhuma até `como_em`)."""
    versoes = _versoes_do_informe(conexao, endereco_do_informe(competencia), como_em)
    conteudo = acervo.ler_original(versoes[-1].caminho or "") if versoes else None
    if conteudo is None:
        return None
    tabelas = fidc.ler_informe(conteudo)
    if monitoramento.INFORME_I not in tabelas:
        return None
    try:
        vistos = publicacao.vistos_nas_versoes(
            versoes, fidc.chaves_do_informe, CHAVE_DO_INFORME
        )
    except FileNotFoundError:  # uma versão antiga sumiu do acervo: sem data de visto
        return None
    quadro_i = publicacao.com_visto_em(
        tabelas[monitoramento.INFORME_I].assign(disponivel_em=fidc.disponivel_em),
        vistos,
        CHAVE_DO_INFORME,
    )
    # nada existe antes do dia em que a base guardou a primeira versão (o prazo é só o piso)
    primeira = pd.Timestamp(versoes[0].dia)  # type: ignore[arg-type]
    quadro_i["disponivel_em"] = quadro_i["disponivel_em"].clip(lower=primeira)
    tabelas[monitoramento.INFORME_I] = quadro_i
    return monitoramento.leituras_dos_informes(tabelas)


def tentativas_do_fidc(
    conexao: sa.Connection, competencias: list[date]
) -> list[Tentativa]:
    """Cada download do arquivo de cada mês, como tentativa de ler a competência dele."""
    return [
        tentativa
        for competencia in competencias
        for tentativa in registro.tentativas_da_url(
            conexao, endereco_do_informe(competencia), periodo=competencia
        )
    ]


def eventos_do_fidc_do_acervo(
    conexao: sa.Connection,
    competencias: list[date],
    *,
    como_em: date | None = None,
    cnpjs: list[str] | None = None,
) -> list[EventoDePJ]:
    """Os eventos dos fundos nos três estados, lidos do acervo, com o que se sabia em `como_em`.

    `competencias` são os fins de mês a ler (`meses_ate`); o evento de um mês é a comparação com o
    anterior, então o primeiro mês da lista só serve de base."""
    partes = [
        leituras
        for competencia in competencias
        if (leituras := leituras_do_informe(conexao, competencia, como_em=como_em))
        is not None
    ]
    leituras = pd.concat(partes, ignore_index=True) if partes else _leituras_vazias()
    return eventos_fidc.eventos_do_fidc(
        leituras,
        tentativas_do_fidc(conexao, competencias),
        como_em=como_em,
        cnpjs=cnpjs,
    )


# ---------------------------------------------------------------- cadastro de companhias abertas


def versoes_do_cadastro_cvm(
    conexao: sa.Connection, *, ate: date | None = None
) -> list[cadastro_cvm.Versao]:
    """Cada versão guardada do `cad_cia_aberta.csv` (dia em que foi baixada, tabela de
    `ler_cadastro`), da mais antiga à mais nova. Versão que sumiu do acervo é pulada; no mesmo dia
    vale a última."""
    por_dia: dict[date, pd.DataFrame] = {}
    for versao in versoes_guardadas(conexao, URL_DO_CADASTRO):
        dia = publicacao.dia_da_coleta(versao.baixado_em).date()
        if not _dia_ate(dia, ate):
            continue
        conteudo = acervo.ler_original(versao.caminho)
        if conteudo is not None:
            por_dia[dia] = ler_cadastro(conteudo)
    return sorted(por_dia.items(), key=lambda par: par[0])


def tentativas_do_cadastro_cvm(
    conexao: sa.Connection, *, ate: date | None = None
) -> list[Tentativa]:
    """Cada download do `cad_cia_aberta.csv`, com o próprio dia como período."""
    return [
        t
        for t in registro.tentativas_da_url(conexao, URL_DO_CADASTRO)
        if _dia_ate(t.dia, ate)
    ]


def eventos_do_cadastro_cvm_do_acervo(
    conexao: sa.Connection, *, ate: date, cnpjs: list[str] | None = None
) -> list[EventoDePJ]:
    """Os eventos das companhias nos três estados, lidos do acervo, com o que se sabia no dia `ate`."""
    return cadastro_cvm.eventos_do_cadastro_cvm(
        versoes_do_cadastro_cvm(conexao, ate=ate),
        tentativas_do_cadastro_cvm(conexao, ate=ate),
        ate=ate,
        cnpjs=cnpjs,
    )
