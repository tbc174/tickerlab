"""O pacote do Mapa do café: o que a tela mostra, num JSON só (plano do café, PR 10).

Os dados do mapa (PAM e MapBiomas por município, clima por região e a malha do IBGE) moram na base,
no servidor de casa. Como as fichas do dossiê (`src/dossie.py`), o pacote é montado lá
(`montar_pacote`, funções puras) e chega ao app como um arquivo JSON (`ler_pacote`). A rota
`GET /v1/commodities/cafe/mapa` lê o arquivo e monta a vista de um tipo de café (`montar_vista`).
Um arquivo que não abre ou de versão desconhecida não é mostrado (`None`): melhor "sem dado" do que
um mapa errado.

**Sem olhar o futuro:** o pacote de um dia só usa o que estava publicado naquele dia (a PAM de um
ano sai em 31/10 do ano seguinte; o clima de cada mês tem `disponivel_em`). **Sem dado não vira
zero:** município ou região sem número fica vazio, com o motivo escrito. Os índices de clima são
contexto datado (`indices_de_clima.py`), não previsão de safra nem de preço.
"""

import json
import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from base.commodities.area_municipio import MES_E_DIA_EM_QUE_A_PAM_SAI
from base.commodities.clima_regiao import (
    DIAS_ATE_PUBLICAR,
    FIM_DA_NORMAL,
    FONTE_CHIRPS,
    FONTE_INMET,
    INICIO_DA_NORMAL,
    MINIMO_DE_ESTACOES,
)
from src.commodities.cafe import calendario
from src.commodities.cafe.indices_de_clima import (
    LIMIAR_DE_GEADA_C,
    MESES_DA_GEADA,
    IndiceClimatico,
    chuva_acumulada,
    dias_de_geada,
)
from src.commodities.cafe.mapa import (
    DadosDoMapa,
    MunicipioNoMapa,
    montar_dados_do_mapa,
    simplificar_malha,
)
from src.commodities.cafe.regioes import ARABICA, CONILON, POR_ID, REGIOES, Regiao
from src.configuracao import PASTA_RAIZ

log = logging.getLogger(__name__)

VERSAO_DO_PACOTE = 1  # muda quando o app precisa ler o pacote de outro jeito
TIPOS_DO_MAPA = (
    ARABICA,
    CONILON,
)  # o mapa separa os dois cafés; "total" misturaria (risco 4)
VARIAVEL_DO_ARQUIVO = "TICKERLAB_MAPA_DO_CAFE"
ARQUIVO_PADRAO = PASTA_RAIZ / "dados_locais" / "commodities" / "mapa_do_cafe.json"
MESES_DA_CHUVA = 3  # "os últimos 90 dias" em meses fechados: o clima da base é mensal
PORCENTAGEM = 100.0

PRODUCAO, AREA, CHUVA, GEADA = "producao", "area", "chuva", "geada"
CAMADAS = (PRODUCAO, AREA, CHUVA, GEADA)
NOME_DO_TIPO = {ARABICA: "arábica", CONILON: "conilon"}
NOME_DA_FONTE_DO_CLIMA = {
    FONTE_CHIRPS: "CHIRPS v2.0 (satélite e pluviômetros, UCSB; Funk et al. 2015)",
    FONTE_INMET: "estações automáticas do INMET (BDMEP)",
}
FONTE_DA_PAM = "IBGE, Produção Agrícola Municipal (PAM), tabela 1613 do SIDRA"
FONTE_DO_MAPBIOMAS = "MapBiomas, Coleção 11 (CC BY 4.0; Souza et al. 2020)"
FONTE_DA_GEADA = (
    "estações automáticas do INMET (BDMEP), média ponderada pela área de café da PAM"
)
FONTE_DA_MALHA = "IBGE, malha municipal (API de malhas), simplificada para o navegador"
FONTE_DO_CALENDARIO = (
    "Camargo & Camargo (2001), fases do cafeeiro em dois anos; épocas de colheita da CONAB e da "
    "Embrapa Café"
)
AVISO = (
    "Contexto datado, não previsão: o mapa mostra o que foi publicado até a data do pacote. Não diz "
    "como será a safra nem para onde vai o preço, e nada aqui é recomendação de investimento."
)
NOME_DO_MES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro",
)  # fmt: skip
NOME_DA_FASE = {  # com o artigo: "a safra em curso está na florada"
    "florada": "na florada",
    "enchimento": "no enchimento do grão",
    "maturacao": "na maturação",
    "repouso": "no repouso dos ramos",
    "vegetacao": "na vegetação (formação dos ramos)",
    "inducao": "na indução das gemas florais",
}

SEM_PAM = "a PAM não registra café {tipo} neste município em {ano}"
FORA_DAS_REGIOES = "fora das regiões produtoras do cadastro: sem índice de clima"
SEM_CHUVA = "sem dado de chuva suficiente na região no período"
SEM_NORMAL = "sem a normal de 1991–2020 para comparar"
SEM_GEADA = (
    f"sem temperatura de {MINIMO_DE_ESTACOES} estações do INMET com dias bastantes na região "
    "no inverno"
)


@dataclass(frozen=True)
class ClimaDaRegiao:
    """Os dois índices do mapa numa região: a chuva dos últimos meses publicados e a geada do
    último inverno publicado."""

    regiao: str
    chuva: IndiceClimatico
    geada: IndiceClimatico


@dataclass(frozen=True)
class PacoteDoMapa:
    gerado_em: date  # o dia do "como era": nada publicado depois entrou
    fonte_do_clima: str  # de onde vem a chuva (`FONTE_CHIRPS` ou `FONTE_INMET`)
    por_tipo: Mapping[str, DadosDoMapa]  # um por tipo de `TIPOS_DO_MAPA`
    clima: tuple[ClimaDaRegiao, ...]
    malha: dict  # FeatureCollection simplificada (`simplificar_malha`), propriedade `codarea`


# --- montar (no servidor de casa) --------------------------------------------------------------------
def ultimo_ano_da_pam(hoje: date) -> int:
    """O ano mais recente da PAM já publicado em `hoje` (o ano Y sai em 31/10 de Y + 1)."""
    mes, dia = MES_E_DIA_EM_QUE_A_PAM_SAI
    return hoje.year - 1 if hoje >= date(hoje.year, mes, dia) else hoje.year - 2


def ultimo_inverno_publicado(hoje: date) -> int:
    """O ano do último inverno (junho a agosto) já fechado e publicado pelo INMET em `hoje`."""
    fim = date(hoje.year, MESES_DA_GEADA[-1], 31)
    publicado = fim + timedelta(days=DIAS_ATE_PUBLICAR[FONTE_INMET])
    return hoje.year if hoje >= publicado else hoje.year - 1


def _publicado_ate(tabela: pd.DataFrame, hoje: date) -> pd.DataFrame:
    if tabela.empty or "disponivel_em" not in tabela:
        return tabela
    return tabela[pd.to_datetime(tabela["disponivel_em"]) <= pd.Timestamp(hoje)]


def _ultimo_mes_com_chuva(mensal: pd.DataFrame, fonte: str) -> pd.Timestamp | None:
    da_fonte = mensal[(mensal["fonte"] == fonte) & mensal["chuva_mm"].notna()]
    if da_fonte.empty:
        return None
    return pd.Timestamp(da_fonte["competencia"].max())


def _meses_ate(ultimo: pd.Timestamp) -> tuple[int, ...]:
    """Os `MESES_DA_CHUVA` meses que terminam em `ultimo`, na ordem (podem virar o ano)."""
    return tuple(
        (ultimo - pd.DateOffset(months=n)).month
        for n in reversed(range(MESES_DA_CHUVA))
    )


def _clima_da_regiao(
    regiao: Regiao,
    mensal: pd.DataFrame,
    diario: pd.DataFrame,
    ultimo_mes: pd.Timestamp | None,
    inverno: int,
    fonte: str,
    hoje: date,
) -> ClimaDaRegiao:
    if (
        ultimo_mes is None
    ):  # nenhum mês publicado da fonte: a janela fica no dia do pacote
        chuva = IndiceClimatico(None, None, None, 0, (hoje, hoje))
    else:
        chuva = chuva_acumulada(
            mensal, regiao.id, ultimo_mes.year, _meses_ate(ultimo_mes), fonte
        )
    inicio = date(inverno, MESES_DA_GEADA[0], 1)
    fim = date(inverno, MESES_DA_GEADA[-1], 31)
    geada = (
        IndiceClimatico(None, None, None, 0, (inicio, fim))
        if diario.empty
        else dias_de_geada(diario, regiao.id, inverno)
    )
    return ClimaDaRegiao(regiao.id, chuva, geada)


def montar_pacote(
    pam: pd.DataFrame,
    area: pd.DataFrame,
    mensal: pd.DataFrame,
    diario: pd.DataFrame,
    malha: dict,
    hoje: date,
    regioes: Sequence[Regiao] = REGIOES,
    fonte_do_clima: str = FONTE_CHIRPS,
) -> PacoteDoMapa:
    """O pacote "como era em `hoje`": a PAM (`ler_pam`) e o MapBiomas (`ler_mapbiomas`) do último
    ano publicado, o clima mensal por região (`clima_regiao_cafe`) até o último mês publicado, a
    geada do último inverno pelo diário do INMET por estação (com `regiao`) e a malha só dos
    municípios do mapa."""
    ano = ultimo_ano_da_pam(hoje)
    pam, area = pam[pam["ano"] <= ano], area[area["ano"] <= ano]
    mensal = _publicado_ate(mensal, hoje)
    ultimo_mes = _ultimo_mes_com_chuva(mensal, fonte_do_clima)
    competencia = ultimo_mes.date() if ultimo_mes is not None else None
    por_tipo = {
        tipo: montar_dados_do_mapa(
            pam, area, mensal, regioes, tipo, None, competencia, fonte_do_clima
        )
        for tipo in TIPOS_DO_MAPA
    }
    inverno = ultimo_inverno_publicado(hoje)
    clima = tuple(
        _clima_da_regiao(r, mensal, diario, ultimo_mes, inverno, fonte_do_clima, hoje)
        for r in regioes
    )
    codigos = {m.codigo for d in por_tipo.values() for m in d.municipios}
    return PacoteDoMapa(
        hoje, fonte_do_clima, por_tipo, clima, simplificar_malha(malha, codigos)
    )


# --- gravar e ler ------------------------------------------------------------------------------------
def _indice_em_dicionario(indice: IndiceClimatico) -> dict[str, object]:
    return {
        "valor": indice.valor,
        "normal": indice.normal,
        "anomalia": indice.anomalia,
        "n_estacoes": indice.n_estacoes,
        "inicio": indice.periodo[0].isoformat(),
        "fim": indice.periodo[1].isoformat(),
    }


def _indice_do_dicionario(dados: Mapping) -> IndiceClimatico:
    periodo = (date.fromisoformat(dados["inicio"]), date.fromisoformat(dados["fim"]))
    return IndiceClimatico(
        dados["valor"],
        dados["normal"],
        dados["anomalia"],
        int(dados["n_estacoes"]),
        periodo,
    )


def em_dicionario(pacote: PacoteDoMapa) -> dict[str, object]:
    """O pacote em tipos simples (é o JSON gravado)."""
    return {
        "versao": VERSAO_DO_PACOTE,
        "gerado_em": pacote.gerado_em.isoformat(),
        "fonte_do_clima": pacote.fonte_do_clima,
        "por_tipo": {t: d.em_dicionario() for t, d in pacote.por_tipo.items()},
        "clima": [
            {
                "regiao": c.regiao,
                "chuva": _indice_em_dicionario(c.chuva),
                "geada": _indice_em_dicionario(c.geada),
            }
            for c in pacote.clima
        ],
        "malha": pacote.malha,
    }


def _dados_do_dicionario(dados: Mapping) -> DadosDoMapa:
    return DadosDoMapa(
        ano=int(dados["ano"]),
        tipo=str(dados["tipo"]),
        competencia=dados["competencia"],
        municipios=tuple(MunicipioNoMapa(**m) for m in dados["municipios"]),
    )


def do_dicionario(dados: Mapping) -> PacoteDoMapa:
    """O pacote de volta do JSON; erro (`ValueError`, `KeyError`, `TypeError`) se não for um."""
    if dados.get("versao") != VERSAO_DO_PACOTE:
        raise ValueError(
            f"versão do pacote {dados.get('versao')!r}: esperava {VERSAO_DO_PACOTE}"
        )
    por_tipo = {t: _dados_do_dicionario(d) for t, d in dados["por_tipo"].items()}
    if set(por_tipo) != set(TIPOS_DO_MAPA):
        raise ValueError(
            f"tipos do pacote {sorted(por_tipo)}: esperava {TIPOS_DO_MAPA}"
        )
    clima = tuple(
        ClimaDaRegiao(
            str(c["regiao"]),
            _indice_do_dicionario(c["chuva"]),
            _indice_do_dicionario(c["geada"]),
        )
        for c in dados["clima"]
    )
    if dados["malha"].get("type") != "FeatureCollection":
        raise ValueError("a malha do pacote não é um FeatureCollection")
    return PacoteDoMapa(
        date.fromisoformat(dados["gerado_em"]),
        str(dados["fonte_do_clima"]),
        por_tipo,
        clima,
        dados["malha"],
    )


def gravar_pacote(pacote: PacoteDoMapa, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(em_dicionario(pacote), ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(texto, encoding="utf-8")


def arquivo_do_pacote() -> Path:
    return Path(os.environ.get(VARIAVEL_DO_ARQUIVO) or ARQUIVO_PADRAO)


def ler_pacote(caminho: Path | None = None) -> PacoteDoMapa | None:
    """O pacote gravado, ou `None` se ainda não há arquivo ou se ele não abre (o erro vai ao log)."""
    caminho = caminho or arquivo_do_pacote()
    if not caminho.exists():
        return None
    try:
        return do_dicionario(json.loads(caminho.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        log.exception("Pacote do mapa do café inválido: %s", caminho.name)
        return None


# --- a vista de um tipo (o que a rota devolve) -------------------------------------------------------
@dataclass(frozen=True)
class Camada:
    """Uma camada do mapa: o que pinta os municípios, com o "o que é isto" e a fonte."""

    chave: str
    titulo: str
    unidade: str
    o_que_e: str
    fonte: str
    escala: str  # "sequencial" (mais é mais) ou "divergente" (em torno de `referencia`)
    referencia: float | None


@dataclass(frozen=True)
class MunicipioDaVista:
    codigo: str
    nome: str
    uf: str
    regiao: str | None
    valores: dict[str, float | None]  # por camada
    sem_dado: dict[str, str]  # por camada sem valor: o motivo (o mapa pinta de cinza)
    area_mapbiomas_ha: float | None


@dataclass(frozen=True)
class IndiceDaVista:
    valor: float | None
    normal: float | None
    n_estacoes: int
    inicio: date
    fim: date
    texto: str  # a frase pronta, com o período e de onde veio


@dataclass(frozen=True)
class ItemDoMes:
    titulo: str
    texto: str


@dataclass(frozen=True)
class RegiaoDaVista:
    id: str
    nome: str
    tipo_predominante: str
    chuva: IndiceDaVista
    geada: IndiceDaVista
    fase: str  # a frase da fase do calendário no mês
    o_que_o_mercado_olha: tuple[ItemDoMes, ...]


@dataclass(frozen=True)
class VistaDoMapa:
    tipo: str
    ano: int
    gerado_em: date
    mes: int
    camadas: tuple[Camada, ...]
    municipios: tuple[MunicipioDaVista, ...]
    regioes: tuple[RegiaoDaVista, ...]
    malha: dict
    fontes: tuple[str, ...]
    aviso: str = AVISO


def _numero_br(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _periodo_br(inicio: date, fim: date) -> str:
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def _camadas(pacote: PacoteDoMapa, tipo: str, ano: int) -> tuple[Camada, ...]:
    nome = NOME_DO_TIPO[tipo]
    fonte_do_clima = NOME_DA_FONTE_DO_CLIMA.get(
        pacote.fonte_do_clima, pacote.fonte_do_clima
    )
    return (
        Camada(
            PRODUCAO,
            f"Produção de café {nome}",
            "t",
            f"Quanto café {nome} o município colheu no ano, em toneladas de café beneficiado, como "
            "o IBGE publicou.",
            f"{FONTE_DA_PAM}, ano {ano}",
            "sequencial",
            None,
        ),
        Camada(
            AREA,
            f"Área colhida de café {nome}",
            "ha",
            f"Os hectares de café {nome} colhidos no ano. Não é a área plantada: lavoura nova ou "
            "podada ainda não colhe.",
            f"{FONTE_DA_PAM}, ano {ano}",
            "sequencial",
            None,
        ),
        Camada(
            CHUVA,
            f"Chuva dos últimos {MESES_DA_CHUVA} meses contra a normal",
            "% da normal",
            "A chuva somada da região nos últimos meses publicados, em porcentagem da normal de "
            f"{INICIO_DA_NORMAL}–{FIM_DA_NORMAL} dos mesmos meses: 100% é a chuva de sempre. O "
            "índice é da região produtora, não do município.",
            f"{fonte_do_clima}; normal {INICIO_DA_NORMAL}–{FIM_DA_NORMAL}",
            "divergente",
            PORCENTAGEM,
        ),
        Camada(
            GEADA,
            "Dias de geada no último inverno",
            "dias",
            f"Dias de junho a agosto com temperatura mínima abaixo de "
            f"{_numero_br(LIMIAR_DE_GEADA_C, 1)} °C no abrigo das estações da região. A geada "
            "não tira a safra do ano: tira a do ano seguinte.",
            FONTE_DA_GEADA,
            "sequencial",
            None,
        ),
    )


def _porcentagem_da_normal(indice: IndiceClimatico) -> float | None:
    razao = indice.razao_da_normal
    return None if razao is None else round(razao * PORCENTAGEM, 1)


def _motivo_do_clima(indice: IndiceClimatico, camada: str) -> str:
    if indice.valor is None:
        return SEM_CHUVA if camada == CHUVA else SEM_GEADA
    return SEM_NORMAL


def _municipio_da_vista(
    m: MunicipioNoMapa, clima: Mapping[str, ClimaDaRegiao], tipo: str, ano: int
) -> MunicipioDaVista:
    valores: dict[str, float | None] = {PRODUCAO: m.producao_t, AREA: m.area_pam_ha}
    sem_dado = {
        c: SEM_PAM.format(tipo=NOME_DO_TIPO[tipo], ano=ano)
        for c in (PRODUCAO, AREA)
        if not valores[
            c
        ]  # zero na PAM é "não produz este café": cinza, não a cor do mínimo
    }
    valores.update({c: None for c in sem_dado})
    da_regiao = clima.get(m.regiao) if m.regiao else None
    if da_regiao is None:
        valores.update({CHUVA: None, GEADA: None})
        sem_dado.update({CHUVA: FORA_DAS_REGIOES, GEADA: FORA_DAS_REGIOES})
    else:
        valores[CHUVA] = _porcentagem_da_normal(da_regiao.chuva)
        valores[GEADA] = da_regiao.geada.valor
        for camada, indice in ((CHUVA, da_regiao.chuva), (GEADA, da_regiao.geada)):
            if valores[camada] is None:
                sem_dado[camada] = _motivo_do_clima(indice, camada)
    return MunicipioDaVista(
        m.codigo, m.nome, m.uf, m.regiao, valores, sem_dado, m.area_mapbiomas_ha
    )


def texto_da_chuva(indice: IndiceClimatico, fonte_do_clima: str) -> str:
    """'Chuva de X mm contra a normal de Y mm (1991–2020), N estações, de D1 a D2.'"""
    periodo = _periodo_br(*indice.periodo)
    if indice.valor is None:
        return f"Sem dado de chuva bastante na região de {periodo}."
    de_onde = (
        f"{indice.n_estacoes} estações do INMET"
        if fonte_do_clima == FONTE_INMET
        else NOME_DA_FONTE_DO_CLIMA.get(fonte_do_clima, fonte_do_clima)
    )
    normal = (
        f"contra a normal de {_numero_br(indice.normal)} mm ({INICIO_DA_NORMAL}–{FIM_DA_NORMAL})"
        if indice.normal is not None
        else f"sem a normal de {INICIO_DA_NORMAL}–{FIM_DA_NORMAL} para comparar"
    )
    return f"Chuva de {_numero_br(indice.valor)} mm {normal}, {de_onde}, de {periodo}."


def texto_da_geada(indice: IndiceClimatico) -> str:
    """'N dias de geada (normal: M), K estações do INMET, de 01/06 a 31/08.'"""
    periodo = _periodo_br(*indice.periodo)
    if indice.valor is None:
        return f"Sem dado de temperatura bastante na região de {periodo} ({SEM_GEADA})."
    normal = (
        f"normal de {_numero_br(indice.normal, 1)} dias ({INICIO_DA_NORMAL}–{FIM_DA_NORMAL})"
        if indice.normal is not None
        else "sem normal para comparar"
    )
    return (
        f"{_numero_br(indice.valor, 1)} dias com mínima abaixo de "
        f"{_numero_br(LIMIAR_DE_GEADA_C, 1)} °C ({normal}), {indice.n_estacoes} estações do "
        f"INMET, de {periodo}."
    )


def _indice_da_vista(indice: IndiceClimatico, texto: str) -> IndiceDaVista:
    return IndiceDaVista(
        indice.valor, indice.normal, indice.n_estacoes, *indice.periodo, texto
    )


def texto_da_fase(fase: calendario.Fase) -> str:
    """A fase do mês em uma frase: as duas safras que andam juntas, a colheita e a geada."""
    partes = [
        (
            f"Em {NOME_DO_MES[fase.mes - 1]}, a safra em curso está "
            f"{NOME_DA_FASE[fase.safra_em_curso]}, e a seguinte, "
            f"{NOME_DA_FASE[fase.safra_seguinte]}"
        )
    ]
    if fase.em_colheita:
        partes.append("é época de colheita")
    if fase.na_janela_de_geada:
        partes.append("é a janela de geada")
    return "; ".join(partes) + "."


def _regiao_da_vista(
    regiao: Regiao, clima: ClimaDaRegiao, mes: int, fonte_do_clima: str
) -> RegiaoDaVista:
    olha = calendario.o_que_o_mercado_olha(mes, regiao)
    return RegiaoDaVista(
        regiao.id,
        regiao.nome,
        regiao.tipo_predominante,
        _indice_da_vista(clima.chuva, texto_da_chuva(clima.chuva, fonte_do_clima)),
        _indice_da_vista(clima.geada, texto_da_geada(clima.geada)),
        texto_da_fase(olha.fase),
        tuple(
            ItemDoMes(calendario.TITULO_DO_TEXTO[i.tema], i.texto) for i in olha.itens
        ),
    )


def _fontes(pacote: PacoteDoMapa, ano: int) -> tuple[str, ...]:
    return (
        f"{FONTE_DA_PAM}, ano {ano}",
        f"{FONTE_DO_MAPBIOMAS}, ano {ano}",
        NOME_DA_FONTE_DO_CLIMA.get(pacote.fonte_do_clima, pacote.fonte_do_clima),
        FONTE_DA_GEADA,
        FONTE_DA_MALHA,
        FONTE_DO_CALENDARIO,
    )


def montar_vista(
    pacote: PacoteDoMapa, tipo: str, mes: int, regioes: Iterable[Regiao] | None = None
) -> VistaDoMapa:
    """O mapa de um tipo de café (`TIPOS_DO_MAPA`) no `mes` do calendário (1 a 12): as camadas,
    os municípios com o valor (ou o motivo de não ter) de cada camada e as regiões com os índices
    de clima e a fase do calendário."""
    if tipo not in TIPOS_DO_MAPA:
        raise ValueError(f"tipo {tipo!r}: use um de {TIPOS_DO_MAPA}")
    dados = pacote.por_tipo[tipo]
    clima = {c.regiao: c for c in pacote.clima}
    por_id = POR_ID if regioes is None else {r.id: r for r in regioes}
    return VistaDoMapa(
        tipo=tipo,
        ano=dados.ano,
        gerado_em=pacote.gerado_em,
        mes=mes,
        camadas=_camadas(pacote, tipo, dados.ano),
        municipios=tuple(
            _municipio_da_vista(m, clima, tipo, dados.ano) for m in dados.municipios
        ),
        regioes=tuple(
            _regiao_da_vista(por_id[c.regiao], c, mes, pacote.fonte_do_clima)
            for c in pacote.clima
            if c.regiao in por_id
        ),
        malha=pacote.malha,
        fontes=_fontes(pacote, dados.ano),
    )


def vista_em_dicionario(vista: VistaDoMapa) -> dict[str, object]:
    """A vista em tipos simples (datas em AAAA-MM-DD)."""
    dados = asdict(vista)
    dados["gerado_em"] = vista.gerado_em.isoformat()
    for regiao in dados["regioes"]:
        for indice in (regiao["chuva"], regiao["geada"]):
            indice["inicio"] = indice["inicio"].isoformat()
            indice["fim"] = indice["fim"].isoformat()
    return dados
