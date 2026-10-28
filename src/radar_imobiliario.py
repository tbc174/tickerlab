"""Radar de ITBI: pacote agregado validado, sem consulta externa por pedido."""

import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.configuracao import PASTA_RAIZ

Cidade = Literal["SP", "RIO"]
Recorte = Literal["todos", "residencial"]
Mes = Annotated[str, Field(pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")]
Valor = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Quantidade = Annotated[int, Field(ge=0, strict=True)]
MAX_BYTES = 5_000_000
VARIAVEL_DO_ARQUIVO = "TICKERLAB_RADAR_IMOBILIARIO"
ARQUIVO_PADRAO = PASTA_RAIZ / "dados_locais" / "radar_imobiliario.json"
FONTES = {
    "SP": "https://prefeitura.sp.gov.br/fazenda/w/acesso_a_informacao/31501",
    "RIO": "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Fazenda/ITBI/MapServer/5",
}
FONTE_GEOGRAFICA = "https://geoinfo-smdu.github.io/tutorial-GeoSampa/"
ATRIBUICOES = {
    "SP": "Fontes: Prefeitura de São Paulo, Secretaria Municipal da Fazenda e GeoSampa. Cruzamentos e agregação: TickerLab.",
    "RIO": "ITBI — Prefeitura do Rio de Janeiro, Secretaria Municipal de Fazenda, elaborado pelo Instituto Pereira Passos. Recortes e agregação: TickerLab.",
}
DEFINICOES = {
    "SP": "DTIs pagas de compra e venda, no mês do pagamento; não são imóveis únicos.",
    "RIO": "Operações agregadas de compra e promessa de compra e venda, no mês informado pela fonte.",
}
AVISOS = [
    "Valores declarados nominais; incluem transmissões parciais e mudanças de composição. Não são índice de valorização nem avaliação de imóvel.",
    "Dados retrospectivos da apuração, sujeitos a revisões. A data do ITBI não equivale à data de registro em cartório.",
]


class Agregado(BaseModel):
    """Campos permitidos: rejeita identificadores e endereços por imóvel."""

    model_config = ConfigDict(extra="forbid")
    cidade: Cidade
    recorte: Recorte
    mes: Mes
    quantidade: Quantidade
    valor_medio: Valor | None


class Regiao(Agregado):
    """Quantidade e média por região; SP usa distrito, Rio usa bairro."""

    tipo: Literal["distrito", "bairro"]
    nome: Annotated[str, Field(min_length=1, max_length=100)]


class Pacote(BaseModel):
    """Retrato datado da coleta, fora do repositório e sem dados unitários."""

    model_config = ConfigDict(extra="forbid")
    versao: Literal[1]
    apurado_em: date
    mensais: Annotated[list[Agregado], Field(min_length=1, max_length=2400)]
    regioes: Annotated[list[Regiao], Field(max_length=30000)]

    @model_validator(mode="after")
    def conferir_totais(self) -> Self:
        """Rejeita repetição, período futuro e regiões sem total municipal compatível."""
        totais = {(p.cidade, p.recorte, p.mes): p.quantidade for p in self.mensais}
        if len(totais) != len(self.mensais):
            raise ValueError("Mês municipal repetido.")
        if any(p.mes > self.apurado_em.strftime("%Y-%m") for p in self.mensais):
            raise ValueError("Competência posterior à apuração.")
        vistos = set()
        somas: dict[tuple[str, str, str], int] = defaultdict(int)
        for regiao in self.regioes:
            chave = (regiao.cidade, regiao.recorte, regiao.mes)
            identificacao = (*chave, regiao.nome)
            esperado = "distrito" if regiao.cidade == "SP" else "bairro"
            if regiao.tipo != esperado or identificacao in vistos:
                raise ValueError("Tipo de região incorreto ou região repetida.")
            vistos.add(identificacao)
            somas[chave] += regiao.quantidade
        if any(chave not in totais or n > totais[chave] for chave, n in somas.items()):
            raise ValueError("Regiões sem total municipal compatível.")
        return self


class Ponto(Agregado):
    """Uma competência, com cobertura territorial e comparação anual disponível."""

    localizadas: Quantidade
    variacao_anual_pct: float | None


class RadarImobiliarioV1(BaseModel):
    """Resposta da página do radar, só com o recorte solicitado."""

    apurado_em: date
    cidade: Cidade
    recorte: Recorte
    definicao: str
    tipo_regiao: Literal["distrito", "bairro"]
    fonte: str
    fonte_geografica: str | None
    atribuicao: str
    licenca: str | None
    serie: list[Ponto]
    regioes: list[Regiao]
    avisos: list[str]


def validar_pacote(dados: object) -> Pacote:
    """Valida a estrutura e reconcilia as contagens regionais com as municipais."""
    return Pacote.model_validate(dados)


def caminho_do_pacote() -> Path:
    """Caminho fixado pelo operador, nunca por um parâmetro da requisição."""
    return Path(os.environ.get(VARIAVEL_DO_ARQUIVO) or ARQUIVO_PADRAO)


def ler_pacote() -> Pacote | None:
    """Lê no máximo 5 MB; pacote ausente ou inválido equivale a indisponível."""
    try:
        with caminho_do_pacote().open("rb") as arquivo:
            corpo = arquivo.read(MAX_BYTES + 1)
        if len(corpo) > MAX_BYTES:
            return None
        return Pacote.model_validate_json(corpo)
    except (OSError, ValueError):
        return None


def montar_vista(
    pacote: Pacote, cidade: Cidade, recorte: Recorte
) -> RadarImobiliarioV1:
    """Filtra a cidade e o uso; lacunas permanecem ausentes e nunca viram zero."""
    meses = sorted(
        (p for p in pacote.mensais if p.cidade == cidade and p.recorte == recorte),
        key=lambda p: p.mes,
    )
    regioes = [r for r in pacote.regioes if r.cidade == cidade and r.recorte == recorte]
    totais = {p.mes: p.quantidade for p in meses}
    localizadas: dict[str, int] = defaultdict(int)
    for regiao in regioes:
        localizadas[regiao.mes] += regiao.quantidade
    pontos = []
    for mes in meses:
        anterior = totais.get(f"{int(mes.mes[:4]) - 1}{mes.mes[4:]}")
        variacao = (mes.quantidade / anterior - 1) * 100 if anterior else None
        pontos.append(
            Ponto(
                **mes.model_dump(),
                localizadas=localizadas[mes.mes],
                variacao_anual_pct=variacao,
            )
        )
    avisos = list(AVISOS)
    if cidade == "SP":
        avisos.append(
            "Distrito oficial não é bairro informado. Localização pela quadra fiscal inteiramente contida em um único distrito do GeoSampa, com malha da apuração. Quadras ambíguas ficam sem localização; não há reconstrução de limites históricos."
        )
        avisos.append(
            "Repetições exatas da fonte foram mantidas: não existe identificador público único da DTI. Dez linhas com estrutura inconsistente foram separadas no piloto."
        )
    else:
        avisos.append(
            "O recorte do Rio usa a tabela 5, de imóveis residenciais e não residenciais. Imóveis territoriais da tabela 6 não estão incluídos. A média municipal é ponderada pela quantidade de operações de cada grupo."
        )
    return RadarImobiliarioV1(
        apurado_em=pacote.apurado_em,
        cidade=cidade,
        recorte=recorte,
        definicao=DEFINICOES[cidade],
        tipo_regiao="distrito" if cidade == "SP" else "bairro",
        fonte=FONTES[cidade],
        fonte_geografica=FONTE_GEOGRAFICA if cidade == "SP" else None,
        atribuicao=ATRIBUICOES[cidade],
        licenca="https://creativecommons.org/licenses/by/4.0/"
        if cidade == "RIO"
        else None,
        serie=pontos,
        regioes=regioes,
        avisos=avisos,
    )
