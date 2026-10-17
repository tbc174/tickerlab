"""Exemplos e rótulo do modelo de atraso na entrega da DFP/ITR (modelo 8 do catálogo, ADR 0030).

Um **exemplo** é uma empresa, um documento (DFP ou ITR) e uma data-base. A pergunta do modelo é feita
na própria data-base (`data_da_previsao`): a empresa vai entregar depois do prazo da CVM?

Quem entra:
- todo documento entregue até `hoje` (a primeira versão vale: reapresentar depois do prazo não é
  atraso) **com a empresa registrada e ativa no cadastro da CVM na data do prazo**, a mesma regra
  das faltas abaixo: só é exemplo o que a empresa devia. Os que ficam de fora vão contados no
  manifesto (`fora_dos_exemplos`), por motivo (`MOTIVOS_FORA`):
  - `prazo_antes_do_primeiro_registro`: os ITRs e DFPs que a empresa manda de uma vez para pedir o
    registro, sem prazo a cumprir (eram 29% dos "atrasou"; conferência da data de entrega da CVM,
    15/10/2026);
  - `prazo_entre_dois_registros`: o mesmo, para pedir o registro de volta (todos "atrasou");
  - `prazo_depois_do_cancelamento`: a empresa já tinha saído (securitizadoras canceladas em 2022 que
    continuaram mandando ITR, por exemplo);
  - `empresa_fora_do_cadastro`: quase todas são emissores estrangeiros (GP Investments, Cosan Ltd.,
    Nu Holdings), que não estão no `cad_cia_aberta.csv`: não se sabe se deviam nem qual prazo valia.
  A pergunta do modelo vale, então, para quem continuar registrado até o prazo: um limite declarado
  no pré-registro (sair do registro antes do prazo é outra pergunta);
- o documento que a empresa **devia e não entregou**: entregou o mesmo documento um ano antes e estava
  registrada e ativa no cadastro da CVM na data do prazo (a mesma regra da R8). Só o primeiro ano
  sem entrega entra; empresa fora do cadastro nunca "deve" (não dá para saber). E só conta como
  falta uma data-base que outra empresa entregou: sem o arquivo do ano no índice (um download que
  falhou), ninguém "deixou de entregar"; e só no calendário da empresa (DFP no mês de fim do
  exercício, ITR nos outros fins de trimestre): uma DFP especial fora do exercício não se repete.
- documento sem entrega com o prazo ainda aberto fica de fora: a resposta ainda não existe.

O rótulo `atrasou` vale 1 com a entrega 1 dia útil ou mais depois do prazo (`src/prazos.py`, com a UF
da sede e o mês de fim do exercício), ou sem entrega com o prazo vencido. Medidos, sem decidir nada:
`dias_uteis_de_atraso`, `atraso_grave` (mais de 30 dias corridos ou não entregou) e `zona_cinzenta`
(1 ou 2 dias úteis: pode ser um feriado local).

`montar` lê os originais que o arquivista guardou (`cvm-hist-dfp`, `cvm-hist-itr` e o cadastro de
`cvm-cadastros`) e grava `<pasta>/rotulos_atraso/rotulos_atraso.parquet` com o manifesto (SHA-256 da
tabela e de cada original). O arquivista só baixa de novo o arquivo que mudou, sem anotar as
conferências: a data da coleta de cada arquivo anual é o que se sabe com certeza, e uma falta só conta
se o prazo venceu antes dela (`vistos_em`).

O rótulo não é coluna para prever: o mês de fim do exercício sai de todas as DFPs da empresa, e a UF,
do cadastro de hoje (ver `base/cadastro.py`).
"""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base.cadastro import FONTE_DO_CADASTRO, cadastro_do_acervo
from base.contas_cvm import ler_indice
from base.dias_uteis import dias_uteis
from base.historico import ano_do_arquivo
from base.parquet import gravar_tabela
from src import acervo
from src.banco.coletas import exigir_licenca, originais_mais_recentes
from src.prazos import ATRASO_GRAVE, prazo
from src.versao_do_codigo import versao_do_codigo

COLUNAS = (
    "cnpj",
    "empresa",
    "documento",
    "referencia",
    "data_da_previsao",
    "prazo",
    "primeira_entrega",
    "dias_uteis_de_atraso",
    "atrasou",
    "atraso_grave",
    "zona_cinzenta",
    "uf",
    "mes_fim_do_exercicio",
)
DOCUMENTO = ["cnpj", "documento", "referencia"]
TABELA = "rotulos_atraso"
FONTES_DO_INDICE = {"DFP": "cvm-hist-dfp", "ITR": "cvm-hist-itr"}
VistosEm = Mapping[tuple[str, int], pd.Timestamp]
ZONA_CINZENTA = 2  # dias úteis
BRASILIA = "America/Sao_Paulo"
ANTES_DO_REGISTRO = "prazo_antes_do_primeiro_registro"
ENTRE_REGISTROS = "prazo_entre_dois_registros"
DEPOIS_DO_CANCELAMENTO = "prazo_depois_do_cancelamento"
FORA_DO_CADASTRO = "empresa_fora_do_cadastro"
MOTIVOS_FORA = (
    ANTES_DO_REGISTRO,
    ENTRE_REGISTROS,
    DEPOIS_DO_CANCELAMENTO,
    FORA_DO_CADASTRO,
)


def _entregues(indice: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """Cada documento com a data da primeira entrega até `hoje` e o nome mais recente da empresa."""
    ate_hoje = indice.dropna(subset=["referencia", "recebido_em"])
    ate_hoje = ate_hoje[ate_hoje["recebido_em"] <= hoje].sort_values("recebido_em")
    return ate_hoje.groupby(DOCUMENTO, as_index=False).agg(
        empresa=("empresa", "last"), primeira_entrega=("recebido_em", "min")
    )


def _mes_fim_do_exercicio(indice: pd.DataFrame) -> pd.Series:
    """Por CNPJ, o mês das data-bases da DFP que mais aparece (12 quando não há DFP)."""
    dfp = indice[indice["documento"] == "DFP"].dropna(subset=["referencia"])
    dfp = dfp.drop_duplicates(DOCUMENTO)
    meses = dfp["referencia"].dt.month
    return meses.groupby(dfp["cnpj"]).agg(lambda m: int(m.mode().max()))


def _ativa_no_prazo(candidatos: pd.DataFrame, cadastro: pd.DataFrame) -> pd.Series:
    """Para cada candidato, se algum registro da empresa estava ativo na data do prazo."""
    juntos = candidatos[["cnpj", "prazo"]].reset_index().merge(cadastro, on="cnpj")
    ativa = (juntos["registro"].isna() | (juntos["registro"] <= juntos["prazo"])) & (
        juntos["cancelamento"].isna() | (juntos["cancelamento"] > juntos["prazo"])
    )
    return (
        ativa.groupby(juntos["index"]).any().reindex(candidatos.index, fill_value=False)
    )


def _motivo_fora(exemplos: pd.DataFrame, cadastro: pd.DataFrame) -> pd.Series:
    """Por que a entrega não é exemplo (um de `MOTIVOS_FORA`), ou "" quando a empresa devia."""
    primeiro_registro = exemplos["cnpj"].map(cadastro.groupby("cnpj")["registro"].min())
    juntos = exemplos[["cnpj", "prazo"]].reset_index().merge(cadastro, on="cnpj")
    volta_depois = (
        (juntos["registro"] > juntos["prazo"]).groupby(juntos["index"]).any()
    ).reindex(exemplos.index, fill_value=False)
    motivo = pd.Series("", index=exemplos.index)
    motivo[~_ativa_no_prazo(exemplos, cadastro)] = DEPOIS_DO_CANCELAMENTO
    motivo[(motivo != "") & volta_depois] = ENTRE_REGISTROS
    motivo[exemplos["prazo"] < primeiro_registro] = ANTES_DO_REGISTRO
    motivo[~exemplos["cnpj"].isin(set(cadastro["cnpj"]))] = FORA_DO_CADASTRO
    return motivo


def _com_prazo(
    exemplos: pd.DataFrame, ufs: pd.Series, meses: pd.Series
) -> pd.DataFrame:
    exemplos = exemplos.assign(
        uf=exemplos["cnpj"].map(ufs).fillna(""),
        mes_fim_do_exercicio=exemplos["cnpj"].map(meses).fillna(12).astype(int),
    )
    prazos = [
        prazo(d, r.date(), mes_fim_do_exercicio=m, uf=u)
        for d, r, m, u in zip(
            exemplos["documento"],
            exemplos["referencia"],
            exemplos["mes_fim_do_exercicio"],
            exemplos["uf"],
            strict=True,
        )
    ]
    return exemplos.assign(
        prazo=pd.to_datetime(pd.Series(prazos, index=exemplos.index))
    )


def _esta_em(
    tabela: pd.DataFrame, outra: pd.DataFrame, colunas: list[str]
) -> pd.Series:
    chaves = pd.MultiIndex.from_frame(outra[colunas])
    return pd.Series(
        pd.MultiIndex.from_frame(tabela[colunas]).isin(chaves), index=tabela.index
    )


def _no_calendario_da_empresa(exemplos: pd.DataFrame) -> pd.Series:
    """DFP no mês de fim do exercício; ITR nos outros fins de trimestre do exercício."""
    distancia = (
        exemplos["referencia"].dt.month - exemplos["mes_fim_do_exercicio"]
    ) % 12
    dfp = exemplos["documento"] == "DFP"
    return (dfp & (distancia == 0)) | (~dfp & (distancia != 0) & (distancia % 3 == 0))


def _devidos_sem_entrega(
    entregues: pd.DataFrame,
    cadastro: pd.DataFrame,
    ufs: pd.Series,
    meses: pd.Series,
    hoje: pd.Timestamp,
    vistos_em: VistosEm | None,
) -> pd.DataFrame:
    """Os documentos de um ano depois de cada entrega que não chegaram e já venceram.

    Só data-bases do calendário da empresa (uma DFP especial fora do exercício não se repete) e que
    outra empresa entregou (o arquivo do ano está no índice).
    """
    seguinte = entregues["referencia"] + pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
    candidatos = entregues.assign(referencia=seguinte).drop(columns="primeira_entrega")
    candidatos = candidatos[
        ~_esta_em(candidatos, entregues, DOCUMENTO)
        & _esta_em(candidatos, entregues, ["documento", "referencia"])
    ]
    candidatos = _com_prazo(candidatos.reset_index(drop=True), ufs, meses)
    vencidos = candidatos[
        (candidatos["prazo"] < hoje) & _no_calendario_da_empresa(candidatos)
    ]
    if vistos_em is not None:
        visto = pd.Series(
            [
                vistos_em.get((d, r.year), pd.NaT)
                for d, r in zip(
                    vencidos["documento"], vencidos["referencia"], strict=True
                )
            ],
            index=vencidos.index,
            dtype="datetime64[ns]",
        )
        vencidos = vencidos[vencidos["prazo"] < visto]
    return vencidos[_ativa_no_prazo(vencidos, cadastro)].assign(primeira_entrega=pd.NaT)


def montar_exemplos(
    indice: pd.DataFrame,
    cadastro: pd.DataFrame,
    hoje: pd.Timestamp,
    *,
    vistos_em: VistosEm | None = None,
) -> pd.DataFrame:
    """Os exemplos com o rótulo, como se sabia em `hoje`.

    `indice`: as entregas de DFP e ITR de todos os anos (`base/contas_cvm.ler_indice`, juntos);
    `cadastro`: `base/cadastro.ler_cadastro` (`cnpj`, `registro`, `cancelamento`, `uf`);
    `vistos_em`: (documento, ano do arquivo) → dia em que o arquivo foi coletado; com ele, uma falta
    só conta se o prazo venceu antes da coleta.
    """
    return montar_exemplos_e_fora(indice, cadastro, hoje, vistos_em=vistos_em)[0]


def montar_exemplos_e_fora(
    indice: pd.DataFrame,
    cadastro: pd.DataFrame,
    hoje: pd.Timestamp,
    *,
    vistos_em: VistosEm | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Os exemplos (`montar_exemplos`) e quantas entregas ficaram de fora, por motivo.

    O que fica de fora: `{motivo: {"exemplos": n, "atrasou": k}}` para cada um de `MOTIVOS_FORA`
    (`atrasou`: quantas seriam "atrasou" se entrassem).
    """
    fora = {motivo: {"exemplos": 0, "atrasou": 0} for motivo in MOTIVOS_FORA}
    if indice.empty:
        return pd.DataFrame(columns=list(COLUNAS)), fora
    entregues = _entregues(indice, hoje)
    if entregues.empty:
        return pd.DataFrame(columns=list(COLUNAS)), fora
    ufs = (
        cadastro[cadastro["uf"].ne("")].drop_duplicates("cnpj").set_index("cnpj")["uf"]
    )
    meses = _mes_fim_do_exercicio(indice)
    com_prazo = _com_prazo(entregues, ufs, meses)
    motivo = _motivo_fora(com_prazo, cadastro)
    atrasados = com_prazo["primeira_entrega"] > com_prazo["prazo"]
    for nome in MOTIVOS_FORA:
        deste = motivo == nome
        fora[nome] = {
            "exemplos": int(deste.sum()),
            "atrasou": int((deste & atrasados).sum()),
        }
    exemplos = pd.concat(
        [
            com_prazo[motivo == ""],
            _devidos_sem_entrega(entregues, cadastro, ufs, meses, hoje, vistos_em),
        ],
        ignore_index=True,
    )
    entregue = exemplos["primeira_entrega"].notna()
    fim = exemplos["primeira_entrega"].where(entregue, hoje)
    dias = np.maximum(dias_uteis(exemplos["prazo"], fim), 0)
    corridos = (fim - exemplos["prazo"]).dt.days
    atrasou = ~entregue | (exemplos["primeira_entrega"] > exemplos["prazo"])
    exemplos = exemplos.assign(
        data_da_previsao=exemplos["referencia"],
        dias_uteis_de_atraso=dias,
        atrasou=atrasou,
        atraso_grave=~entregue | (corridos > ATRASO_GRAVE),
        zona_cinzenta=entregue & atrasou & (dias <= ZONA_CINZENTA),
    )
    exemplos = (
        exemplos[list(COLUNAS)]
        .sort_values(["referencia", "documento", "cnpj"])
        .reset_index(drop=True)
    )
    return exemplos, fora


def _dia(momento: object) -> pd.Timestamp:
    """O dia (sem hora nem fuso) de um momento, no horário de Brasília."""
    dia = pd.Timestamp(momento)  # type: ignore[arg-type]
    if dia.tzinfo is not None:
        dia = dia.tz_convert(BRASILIA).tz_localize(None)
    return dia.normalize()


def _cadastro(
    conexao: sa.Connection, origens: list[dict[str, str]]
) -> pd.DataFrame | None:
    achado = cadastro_do_acervo(conexao)
    if achado is None:
        return None
    origens.append(achado[1])
    return achado[0]


def montar(conexao: sa.Connection, pasta: Path, agora: datetime) -> int:
    """`<pasta>/rotulos_atraso/rotulos_atraso.parquet` dos originais do acervo; devolve as linhas.

    Nada é gravado (0) sem índice da DFP/ITR ou sem o cadastro. Fonte que não pode rotular (ADR 0008,
    Emenda 1) é erro, antes de ler qualquer original.
    """
    exigir_licenca(
        "rotular", [*FONTES_DO_INDICE.values(), FONTE_DO_CADASTRO], onde=TABELA
    )
    partes: list[pd.DataFrame] = []
    vistos_em: dict[tuple[str, int], pd.Timestamp] = {}
    origens: list[dict[str, str]] = []
    for documento, fonte in FONTES_DO_INDICE.items():
        for original in originais_mais_recentes(conexao, fonte):
            ano = ano_do_arquivo(original.url)
            conteudo = acervo.ler_original(original.caminho_do_original)
            if ano is None or conteudo is None:
                continue
            partes.append(ler_indice(conteudo, documento))
            vistos_em[(documento, ano)] = _dia(original.baixado_em)
            origens.append({"url": original.url, "sha256": original.sha256})
    cadastro = _cadastro(conexao, origens)
    if not partes or cadastro is None:
        return 0
    indice = pd.concat(partes, ignore_index=True)
    exemplos, fora = montar_exemplos_e_fora(
        indice, cadastro, _dia(agora), vistos_em=vistos_em
    )
    # o dia, e não a hora: mesmos originais e mesmo dia dão a mesma tabela (exigência 9)
    tabela = exemplos.assign(
        montado_em=_dia(agora).tz_localize(BRASILIA).isoformat(),
        versao_do_codigo=versao_do_codigo(),
    )
    gravar_tabela(
        tabela,
        pasta / TABELA / TABELA,
        origens,
        ["documento", "referencia", "cnpj"],
        extras={"fora_dos_exemplos": fora},
    )
    return len(tabela)
