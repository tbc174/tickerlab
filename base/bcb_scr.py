"""SCR.data do Banco Central: carteira de crédito, atraso e inadimplência por UF, segmento, tipo de
cliente, CNAE (PJ) ou ocupação (PF), porte, modalidade, origem e indexador, por mês (série 3 da base
de ML, PR 7).

- **Versão 2** (`https://www.bcb.gov.br/pda/desig/scrdata_<ano>.zip`), licença ODbL, de jul/2012 em
  diante, um CSV por mês. A versão 1 (`planilha_<ano>.zip`) parou em jun/2025 e fica fora.
- **Formato** (inventário de 14/10/2026): UTF-8 com BOM, `;`, tudo entre aspas (há CNAE com `;` no
  nome), vírgula decimal, 24 colunas iguais em 2012 e 2026; ~210 mil linhas por mês em 2012, ~310 mil
  em 2026. Valores em reais. `numero_de_operacoes` = -1 quando o BC não informa: vira vazio.
- **Agregado:** não há pessoa nem instituição identificada.
- **"Como era na data":** o BC publica 30 dias depois do fim do mês, no último dia útil (ago/2026 já
  estava no arquivo em 09/10); a base usa data-base + 60 dias. O BC regrava anos passados (o de 2025
  em set/2026): cada baixada do arquivista é uma coleta e a tabela guarda uma linha por **valor
  diferente** de cada chave (`base/setoriais/revisoes.py`). O primeiro valor vale desde o prazo; a
  revisão vale só desde o dia em que foi vista (`visto_em`), nunca antes (ADR 0027, exigência 3). Limite:
  o que o BC revisou antes da 1ª coleta guardada não aparece. A tabela anterior fica guardada como
  `<ano>.v<N>`.
"""

import io
import zipfile
from collections.abc import Callable, Iterator, Sequence

import numpy as np
import pandas as pd

from base.setoriais import revisoes

ENDERECO = "https://www.bcb.gov.br/pda/desig/scrdata_{ano}.zip"
PRIMEIRO_ANO = 2012
DIAS_ATE_FICAR_PUBLICO = 60
SEM_NUMERO = -1
COLUNAS_DE_TEXTO = (
    "data_base",
    "uf",
    "segmento",
    "cliente",
    "cnae_ocupacao",
    "porte",
    "modalidade",
    "submodalidade",
    "origem",
    "indexador",
)


def endereco_do_ano(ano: int) -> str:
    return ENDERECO.format(ano=ano)


def _ler_mes(arquivo: zipfile.ZipFile, nome: str) -> pd.DataFrame:
    bruto = pd.read_csv(
        arquivo.open(nome),
        sep=";",
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    mes = pd.DataFrame({"data_base": pd.to_datetime(bruto["data_base"])})
    for coluna in COLUNAS_DE_TEXTO[1:]:
        mes[coluna] = bruto[coluna].replace("", None).astype("category")
    for coluna in bruto.columns.difference(COLUNAS_DE_TEXTO, sort=False):
        mes[coluna] = pd.to_numeric(bruto[coluna].str.replace(",", ".", regex=False))
    mes["numero_de_operacoes"] = (
        mes["numero_de_operacoes"].astype("Int64").mask(lambda n: n == SEM_NUMERO)
    )
    return mes


def ler_ano(conteudo_do_zip: bytes) -> pd.DataFrame:
    """Os meses do arquivo de um ano, um embaixo do outro, com os tipos certos."""
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        meses = [_ler_mes(arquivo, nome) for nome in sorted(arquivo.namelist())]
    ano = pd.concat(meses, ignore_index=True)
    for coluna in COLUNAS_DE_TEXTO[1:]:
        ano[coluna] = ano[coluna].astype(str).replace("None", None).astype("category")
    return ano


def disponivel_em(tabela: pd.DataFrame) -> pd.Series:
    """Desde quando o mês era público: data-base + 60 dias (o BC publica em ~30 a 40)."""
    return tabela["data_base"] + pd.Timedelta(days=DIAS_ATE_FICAR_PUBLICO)


def _com_a_ordem_na_chave(tabela: pd.DataFrame) -> pd.DataFrame:
    """O BC publica mais de uma linha para a mesma chave (a seção do CNAE junta atividades; a base soma
    todas), às vezes até iguais. `ocorrencia` numera as linhas de uma chave dentro da coleta (0, 1...), para que
    nem a repetição nem a revisão de uma apague a outra; entra na chave da tabela."""
    chave = tabela[list(COLUNAS_DE_TEXTO)].astype(object)
    return tabela.assign(
        ocorrencia=chave.groupby(list(COLUNAS_DE_TEXTO), dropna=False).cumcount()
    )


def _com_prazo(tabela: pd.DataFrame) -> pd.DataFrame:
    return _com_a_ordem_na_chave(tabela).assign(disponivel_em=disponivel_em(tabela))


CHAVE = [*COLUNAS_DE_TEXTO, "ocorrencia"]
# a posição de cada linha no jeito de juntar de antes (a coleta, a linha dentro dela): fora da comparação dos
# valores (`carimbos`), servem só para devolver as linhas na mesma ordem de `revisoes.juntar_coletas`
_COLETA, _LINHA = "_coleta", "_linha"
Meses = Callable[[], Iterator[pd.DataFrame]]


class MesForaDoFormatoError(ValueError):
    """Um CSV do arquivo do ano não é de um mês só, ou repete o mês de outro CSV: a leitura mês a mês não vale."""


def ano_com_revisoes(
    coletas: Sequence[tuple[pd.Timestamp, pd.DataFrame]],
) -> pd.DataFrame:
    """As coletas de um ano (dia da baixada, `ler_ano`) numa tabela com as revisões do BC.

    Sem o dia (acervo desligado) a coleta entra com `visto_em` vazio: o valor vale desde o prazo."""
    return _juntar_mes_a_mes(
        [
            (dia, lambda tabela=tabela: _meses_da_tabela(tabela))
            for dia, tabela in coletas
        ]
    )


def ano_com_revisoes_dos_arquivos(
    coletas: Sequence[tuple[pd.Timestamp, Callable[[], bytes]]],
) -> pd.DataFrame:
    """O mesmo que `ano_com_revisoes` com as coletas lidas por `ler_ano`, linha por linha, sem abrir todas
    (linha 1076): cada arquivo (dia da baixada, função que traz o zip) é lido só na sua vez, um mês por vez.

    O ano corrente guarda uma versão por mês e, com todas abertas, a carga caía sem memória (o SCR de 2026
    caiu com 4 GB em 25/11/2026). Dá para juntar mês a mês porque a data-base está na chave e nos valores:
    revisão e repetição nunca cruzam dois meses. A memória fica nas linhas diferentes já vistas de cada mês
    mais um mês de um arquivo."""
    return _juntar_mes_a_mes(
        [(dia, lambda ler=ler: _meses_do_arquivo(ler())) for dia, ler in coletas]
    )


def _meses_da_tabela(tabela: pd.DataFrame) -> Iterator[pd.DataFrame]:
    com_prazo = _com_prazo(tabela)
    com_prazo[_LINHA] = np.arange(len(com_prazo))
    for _, mes in com_prazo.groupby("data_base", sort=False):
        yield mes


def _meses_do_arquivo(conteudo_do_zip: bytes) -> Iterator[pd.DataFrame]:
    """Os meses do arquivo como `ler_ano` + `_com_prazo` os dariam, um CSV por vez (a `ocorrencia` conta dentro
    da chave, que tem a data-base: com um mês por CSV, contar no CSV é o mesmo que contar no ano)."""
    vistos: set[pd.Timestamp] = set()
    inicio = 0
    with zipfile.ZipFile(io.BytesIO(conteudo_do_zip)) as arquivo:
        for nome in sorted(arquivo.namelist()):
            mes = _ler_mes(arquivo, nome)
            datas = set(mes["data_base"].unique())
            if len(datas) != 1 or datas & vistos:
                raise MesForaDoFormatoError(nome)
            vistos |= datas
            com_prazo = _com_prazo(mes)
            com_prazo[_LINHA] = np.arange(inicio, inicio + len(mes))
            inicio += len(mes)
            yield com_prazo


def _juntar_mes_a_mes(coletas: Sequence[tuple[pd.Timestamp, Meses]]) -> pd.DataFrame:
    """`revisoes.juntar_coletas` de cada mês, uma coleta por vez, com as linhas na ordem de lá."""
    if not coletas:
        raise ValueError("nenhuma coleta para juntar")
    por_mes: dict[pd.Timestamp, pd.DataFrame] = {}
    em_ordem = sorted(coletas, key=revisoes.ordem_da_coleta)
    for posicao, (dia, meses) in enumerate(em_ordem):
        for mes in meses():
            mes[_COLETA] = posicao
            data_base = mes["data_base"].iat[0]
            por_mes[data_base] = revisoes.acrescentar_coleta(
                por_mes.get(data_base), dia, mes, CHAVE, carimbos=(_COLETA, _LINHA)
            )
    partes = list(por_mes.values())
    por_mes.clear()
    juntas = revisoes.concatenar(partes)
    del partes
    ordem = np.lexsort((juntas[_LINHA].to_numpy(), juntas[_COLETA].to_numpy()))
    juntas = juntas.take(ordem).drop(columns=[_COLETA, _LINHA]).reset_index(drop=True)
    for coluna in COLUNAS_DE_TEXTO[1:]:
        # as categorias de `astype("category")` sobre o texto: só as usadas, em ordem
        usadas = juntas[coluna].astype("category").cat.remove_unused_categories()
        juntas[coluna] = usadas.cat.reorder_categories(sorted(usadas.cat.categories))
    return juntas
