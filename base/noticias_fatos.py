"""Gatilhos das notas de dado: da base para `noticias_fatos` e `noticias_numeros` (ADR 0093).

Cada gatilho roda **uma vez por dia** sobre o que ficou público até o dia anterior e devolve só fatos que
valem uma nota. As regras são as do plano (`projeto-acoes/planos/2026-10-17-noticias-de-dado.md`, seção 2) e
ficam públicas na metodologia:

- **G1, resultado trimestral** (`fatos_de_resultado`): entrou um ITR ou DFP de companhia do universo e as
  quatro contas existem (receita, resultado operacional, lucro e dívida bruta). Versão 1 vira nota de
  resultado; versão 2 em diante só vira nota se uma das quatro contas mudou (reapresentação).
- **Universo** (`universo_em`): companhias com ticker na data, fora dos setores financeiros.
- **Janela:** o fato entra se ficou público até ontem e há no máximo 5 dias úteis (cobre a carga que
  falhou); mais velho que isso, não vira nota.
- **Trimestre isolado:** só o ITR traz o acumulado do ano e o 4º trimestre só existe na DFP. 1T = 3 meses;
  2T = 6M − 3M; 3T = 9M − 6M; 4T = exercício − 9M. **Cada parte vem "como era em `publico_em`"**
  (`como_era_em`): uma reapresentação de depois não muda o fato de antes. Se falta uma parte, o número
  daquela comparação não existe (nada é inventado).

O `id_fato` é o SHA-256 de `pauta` + a chave da linha de origem: remontar dá o mesmo id, e o fato que já
existe é ignorado por quem grava. O `hash_da_linha` cobre a linha e os números dela (sem o commit, para
não mudar a cada versão do código).
"""

import hashlib
import json
from collections.abc import Collection, Mapping
from datetime import date, datetime
from typing import Any

import pandas as pd

from base.dias_uteis import dias_uteis
from base.ponto_no_tempo import como_era_em
from src.demonstracoes import URL_DO_DFP, URL_DO_ITR, e_financeira
from src.versao_do_codigo import versao_do_codigo

JANELA_EM_DIAS_UTEIS = 5
PAUTA_RESULTADO = "resultado_trimestral"
VERSAO_DO_RESULTADO = "resultado-1.0"
TABELA_DAS_DEMONSTRACOES = "demonstracoes_como_era"
REAIS = "reais"

COLUNAS_DOS_FATOS = [
    "id_fato",
    "pauta",
    "versao_do_gatilho",
    "cnpj",
    "empresa",
    "tabela_de_origem",
    "chave_de_origem",
    "aconteceu_em",
    "publico_em",
    "coletado_em",
    "link",
    "topico",
    "metodo_do_topico",
    "versao_do_topico",
    "trecho",
    "reapresentacao",
    "fato_anterior",
    "marcas",
    "licenca",
    "hash_da_linha",
    "versao_do_codigo",
]
COLUNAS_DOS_NUMEROS = [
    "id_fato",
    "campo",
    "valor",
    "unidade",
    "periodo",
    "origem_conta",
    "origem_periodo",
    "origem_versao",
    "origem_divulgado_em",
    "calculo",
]
SEM_HASH = ("hash_da_linha", "versao_do_codigo")

CONTAS_DE_FLUXO = (
    ("receita", "3.01"),
    ("resultado_operacional", "3.05"),
    ("lucro", "3.11"),
)
CONTAS_DA_DIVIDA = (
    "2.01.04",
    "2.02.01",
)  # empréstimos e financiamentos: circulante + não circulante
FIM_DO_TRIMESTRE = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
TRIMESTRE_DO_MES = {3: 1, 6: 2, 9: 3, 12: 4}
MARCA_INDIVIDUAL = "individual"
MARCA_EM_CONFERENCIA = "dado_em_conferencia"


def _json(valor: object) -> str:
    return json.dumps(
        valor, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def id_do_fato(pauta: str, chave_de_origem: Mapping[str, object]) -> str:
    """SHA-256 de `pauta` + a chave da linha de origem em JSON canônico (estável entre montagens)."""
    return hashlib.sha256(f"{pauta}\n{_json(chave_de_origem)}".encode()).hexdigest()


def hash_da_linha(fato: Mapping[str, object], numeros: list[dict[str, object]]) -> str:
    """SHA-256 da linha do fato e dos números dela, sem o commit que montou."""
    corpo = {k: v for k, v in fato.items() if k not in SEM_HASH}
    ordenados = sorted(numeros, key=lambda n: str(n["campo"]))
    return hashlib.sha256(
        _json({"fato": corpo, "numeros": ordenados}).encode()
    ).hexdigest()


def _dia(dia: date | datetime | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(dia).normalize()


def no_prazo(publico_em: pd.Series, dia: date | pd.Timestamp) -> pd.Series:
    """Ficou público até ontem e há no máximo `JANELA_EM_DIAS_UTEIS` dias úteis (nada de futuro)."""
    hoje = _dia(dia)
    publico = pd.to_datetime(publico_em).reset_index(drop=True)
    if publico.empty:
        return pd.Series([], dtype=bool, index=publico_em.index)
    uteis = dias_uteis(publico, pd.Series([hoje] * len(publico)))
    dentro = (publico < hoje) & (uteis <= JANELA_EM_DIAS_UTEIS)
    return pd.Series(dentro.to_numpy(), index=publico_em.index)


def universo_em(
    tickers: pd.DataFrame, setores: pd.DataFrame, dia: date | pd.Timestamp
) -> set[str]:
    """CNPJ das companhias com ticker na data (`tickers_no_tempo`), fora dos setores financeiros.

    Bancos e seguradoras não têm "receita líquida" nem "dívida bruta" no plano de contas das empresas
    comuns (`src/demonstracoes.py::SETORES_FINANCEIROS`). Companhia sem setor no cadastro fica dentro.
    """
    hoje = _dia(dia)
    vale = (tickers["primeiro_visto"] <= hoje) & (
        tickers["valido_ate"].isna() | (tickers["valido_ate"] > hoje)
    )
    financeiras = {
        str(linha.cnpj)
        for linha in setores.itertuples()
        if e_financeira(str(linha.setor))
    }
    return {str(c) for c in tickers.loc[vale, "cnpj"]} - financeiras


def _vazio() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.DataFrame(columns=COLUNAS_DOS_FATOS), pd.DataFrame(
        columns=COLUNAS_DOS_NUMEROS
    )


def _montar(
    fatos: list[dict[str, Any]], numeros: dict[str, list[dict[str, Any]]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """DataFrames em ordem fixa (data, CNPJ, id), com o hash de cada linha já calculado."""
    if not fatos:
        return _vazio()
    for fato in fatos:
        fato["hash_da_linha"] = hash_da_linha(fato, numeros[fato["id_fato"]])
    tabela = pd.DataFrame(fatos).reindex(columns=COLUNAS_DOS_FATOS)
    tabela = tabela.sort_values(["publico_em", "cnpj", "id_fato"]).reset_index(
        drop=True
    )
    linhas = [n for i in tabela["id_fato"] for n in numeros[i]]
    return tabela, pd.DataFrame(linhas).reindex(columns=COLUNAS_DOS_NUMEROS)


# --- G1: resultado trimestral ---------------------------------------------------------------------

_Chave = tuple[str, str, "pd.Timestamp | None", pd.Timestamp]


class _Valores:
    """O que era público numa data, de uma companhia, para achar conta + período rápido."""

    def __init__(self, vistos: pd.DataFrame, grupo: str) -> None:
        self.valores: dict[_Chave, tuple[float, int, pd.Timestamp]] = {}
        uteis = vistos[(vistos["grupo"] == grupo) & vistos["valor"].notna()]
        for linha in uteis.itertuples():
            inicio = None if pd.isna(linha.inicio) else pd.Timestamp(linha.inicio)
            chave = (linha.demonstracao, linha.conta, inicio, pd.Timestamp(linha.fim))
            self.valores[chave] = (
                float(linha.valor),
                int(linha.versao),
                pd.Timestamp(linha.divulgado_em),
            )

    def acumulado(
        self, conta: str, ano: int, mes: int
    ) -> tuple[float, int, pd.Timestamp] | None:
        mes_fim, dia_fim = FIM_DO_TRIMESTRE[TRIMESTRE_DO_MES[mes]]
        chave = (
            "DRE",
            conta,
            pd.Timestamp(ano, 1, 1),
            pd.Timestamp(ano, mes_fim, dia_fim),
        )
        return self.valores.get(chave)

    def saldo(self, ano: int, mes: int) -> tuple[float, int, pd.Timestamp, str] | None:
        mes_fim, dia_fim = FIM_DO_TRIMESTRE[TRIMESTRE_DO_MES[mes]]
        achados = [
            (
                conta,
                self.valores.get(
                    ("BPP", conta, None, pd.Timestamp(ano, mes_fim, dia_fim))
                ),
            )
            for conta in CONTAS_DA_DIVIDA
        ]
        presentes = [(conta, v) for conta, v in achados if v is not None]
        if not presentes:
            return None
        return (
            sum(v[0] for _, v in presentes),
            max(v[1] for _, v in presentes),
            max(v[2] for _, v in presentes),
            " + ".join(conta for conta, _ in presentes),
        )


def _rotulo_da_parte(ano: int, mes: int) -> str:
    return f"{'exercício' if mes == 12 else 'acumulado'} {mes}M{ano % 100:02d}"


def _trimestre_isolado(
    valores: _Valores, conta: str, ano: int, trimestre: int
) -> dict[str, Any] | None:
    """O trimestre isolado de uma conta de fluxo, ou None se falta uma das partes."""
    mes = 3 * trimestre
    parte = valores.acumulado(conta, ano, mes)
    anterior = valores.acumulado(conta, ano, mes - 3) if trimestre > 1 else None
    if parte is None or (trimestre > 1 and anterior is None):
        return None
    valor = parte[0] - (anterior[0] if anterior else 0.0)
    versoes = [parte[1], *([anterior[1]] if anterior else [])]
    datas = [parte[2], *([anterior[2]] if anterior else [])]
    return {
        "valor": valor,
        "periodo": f"{trimestre}T{ano % 100:02d}",
        "origem_conta": conta,
        "origem_periodo": "exercicio" if mes == 12 else "acumulado",
        "origem_versao": max(versoes),
        "origem_divulgado_em": max(datas),
        "calculo": (
            f"{_rotulo_da_parte(ano, mes)} - {_rotulo_da_parte(ano, mes - 3)}"
            if anterior
            else ""
        ),
    }


def _divida(valores: _Valores, ano: int, trimestre: int) -> dict[str, Any] | None:
    achado = valores.saldo(ano, 3 * trimestre)
    if achado is None:
        return None
    valor, versao, divulgado, contas = achado
    mes_fim, dia_fim = FIM_DO_TRIMESTRE[trimestre]
    return {
        "valor": valor,
        "periodo": f"{dia_fim:02d}/{mes_fim:02d}/{ano}",
        "origem_conta": contas,
        "origem_periodo": "posicao",
        "origem_versao": versao,
        "origem_divulgado_em": divulgado,
        "calculo": contas,
    }


def _anterior(ano: int, trimestre: int) -> tuple[int, int]:
    return (ano - 1, 4) if trimestre == 1 else (ano, trimestre - 1)


def _numeros_do_trimestre(
    valores: _Valores, ano: int, trimestre: int
) -> dict[str, dict[str, Any]] | None:
    """Os números da nota, ou None se uma das quatro contas do trimestre não existe."""
    campos: dict[str, dict[str, Any]] = {}
    for nome, conta in CONTAS_DE_FLUXO:
        atual = _trimestre_isolado(valores, conta, ano, trimestre)
        if atual is None:
            return None
        campos[f"{nome}_trimestre"] = atual
        for sufixo, (a, t) in (
            ("mesmo_trimestre_ano_anterior", (ano - 1, trimestre)),
            ("trimestre_anterior", _anterior(ano, trimestre)),
        ):
            comparacao = _trimestre_isolado(valores, conta, a, t)
            if comparacao is not None:
                campos[f"{nome}_{sufixo}"] = comparacao
    divida = _divida(valores, ano, trimestre)
    if divida is None:
        return None
    campos["divida_bruta"] = divida
    anterior = _divida(valores, *_anterior(ano, trimestre))
    if anterior is not None:
        campos["divida_bruta_trimestre_anterior"] = anterior
    return campos


def _do_documento(
    vistos: pd.DataFrame, ano: int, trimestre: int
) -> tuple[dict[str, dict[str, Any]], bool] | None:
    """Os números pelo consolidado; sem ele, pelo individual (e diz que foi)."""
    for grupo in ("con", "ind"):
        numeros = _numeros_do_trimestre(_Valores(vistos, grupo), ano, trimestre)
        if numeros is not None:
            return numeros, grupo == "ind"
    return None


def _chaves_da_comparacao(numeros: dict[str, dict[str, Any]]) -> dict[str, float]:
    quatro = (
        "receita_trimestre",
        "resultado_operacional_trimestre",
        "lucro_trimestre",
        "divida_bruta",
    )
    return {campo: numeros[campo]["valor"] for campo in quatro}


def _documentos_novos(
    base: pd.DataFrame, universo: Collection[str], dia: date | pd.Timestamp
) -> pd.DataFrame:
    entregues = base[
        (base["ordem"] == "ultimo")
        & base["documento"].isin(["ITR", "DFP"])
        & base["cnpj"].isin(list(universo))
    ]
    documentos = entregues.groupby(
        ["cnpj", "documento", "referencia", "versao"], as_index=False
    ).agg(publico_em=("divulgado_em", "min"), empresa=("empresa", "first"))
    return documentos[no_prazo(documentos["publico_em"], dia)]


def fatos_de_resultado(
    base: pd.DataFrame,
    universo: Collection[str],
    dia: date | pd.Timestamp,
    *,
    coletado_em: datetime,
    em_conferencia: Collection[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """G1: os fatos de resultado trimestral que ficaram públicos na janela que termina ontem.

    `base`: `demonstracoes_como_era` inteira (com `ate`); `universo`: `universo_em`; `coletado_em`: quando a
    tabela de origem foi baixada (manifesto); `em_conferencia`: CNPJ com achado de qualidade aberto.
    """
    candidatos = _documentos_novos(base, universo, dia)
    if candidatos.empty:
        return _vazio()
    da_empresa = {
        cnpj: parte
        for cnpj, parte in base[base["cnpj"].isin(candidatos["cnpj"])].groupby("cnpj")
    }
    fatos: list[dict[str, Any]] = []
    numeros_dos_fatos: dict[str, list[dict[str, Any]]] = {}
    for doc in candidatos.itertuples():
        publico_em = pd.Timestamp(doc.publico_em)
        referencia = pd.Timestamp(doc.referencia)
        trimestre = TRIMESTRE_DO_MES.get(referencia.month)
        if (
            trimestre is None
        ):  # exercício social que não termina em março, junho, setembro ou dezembro
            continue
        parte = da_empresa[doc.cnpj]
        agora = _do_documento(
            como_era_em(parte, publico_em), referencia.year, trimestre
        )
        if agora is None:
            continue
        numeros, individual = agora
        versao = int(doc.versao)
        chave = {
            "cnpj": doc.cnpj,
            "documento": doc.documento,
            "referencia": referencia.date().isoformat(),
            "versao": versao,
        }
        anterior = None
        if versao > 1:
            anterior = _versao_anterior(parte, chave, publico_em, trimestre, numeros)
            if anterior is None:
                continue
        id_fato = id_do_fato(PAUTA_RESULTADO, chave)
        marcas = [
            m
            for m, ligada in (
                (MARCA_INDIVIDUAL, individual),
                (MARCA_EM_CONFERENCIA, doc.cnpj in em_conferencia),
            )
            if ligada
        ]
        fatos.append(
            {
                "id_fato": id_fato,
                "pauta": PAUTA_RESULTADO,
                "versao_do_gatilho": VERSAO_DO_RESULTADO,
                "cnpj": doc.cnpj,
                "empresa": doc.empresa,
                "tabela_de_origem": TABELA_DAS_DEMONSTRACOES,
                "chave_de_origem": _json(chave),
                "aconteceu_em": referencia,
                "publico_em": publico_em,
                "coletado_em": pd.Timestamp(coletado_em),
                "link": (URL_DO_DFP if doc.documento == "DFP" else URL_DO_ITR).format(
                    ano=referencia.year
                ),
                "topico": "",
                "metodo_do_topico": "",
                "versao_do_topico": "",
                "trecho": "",
                "reapresentacao": versao > 1,
                "fato_anterior": anterior or "",
                "marcas": marcas,
                "licenca": "cvm",
                "versao_do_codigo": versao_do_codigo(),
            }
        )
        numeros_dos_fatos[id_fato] = [
            {"id_fato": id_fato, "campo": campo, "unidade": REAIS, **n}
            for campo, n in numeros.items()
        ]
    return _montar(fatos, numeros_dos_fatos)


def _versao_anterior(
    parte: pd.DataFrame,
    chave: Mapping[str, object],
    publico_em: pd.Timestamp,
    trimestre: int,
    numeros: dict[str, dict[str, Any]],
) -> str | None:
    """`id_fato` da versão anterior, se uma das quatro contas mudou desde ela (senão None)."""
    referencia = pd.Timestamp(str(chave["referencia"]))
    versao = int(str(chave["versao"]))
    do_documento = parte[
        (parte["documento"] == chave["documento"])
        & (parte["referencia"] == referencia)
        & (parte["ordem"] == "ultimo")
        & (parte["versao"] < versao)
    ]
    if do_documento.empty:
        return None
    antes = _do_documento(
        como_era_em(parte, publico_em - pd.Timedelta(days=1)),
        referencia.year,
        trimestre,
    )
    if antes is not None and _chaves_da_comparacao(antes[0]) == _chaves_da_comparacao(
        numeros
    ):
        return None
    return id_do_fato(
        PAUTA_RESULTADO, {**chave, "versao": int(do_documento["versao"].max())}
    )
