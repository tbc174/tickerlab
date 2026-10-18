"""Regiões produtoras de café do Brasil, município a município (plano do café, PR 8, tarefa 8.1).

Uma região é um conjunto de municípios (código IBGE de 7 dígitos) com um tipo predominante
(arábica ou conilon). O clima por região (`base/commodities/clima_regiao.py`) e o mapa
(`src/commodities/cafe/mapa.py`) usam esta lista; nada aqui depende do Streamlit.

**De onde vem a divisão.** As regiões são as que o mercado e os produtores usam: as dos
levantamentos da CONAB (Sul de Minas, Cerrado Mineiro, Matas de Minas, Norte/Jequitinhonha/Mucuri;
Mogiana e Alta Paulista; Norte Pioneiro do Paraná; Planalto, Oeste e Atlântico da Bahia; montanhas
e norte do Espírito Santo; Rondônia), que coincidem com as indicações geográficas reconhecidas
pelo INPI (Cerrado Mineiro, Mantiqueira de Minas e Região de Pinhal no Sul de Minas, Matas de Minas,
Alta Mogiana, Norte Pioneiro do Paraná, Oeste da Bahia, Montanhas do Espírito Santo, Caparaó) e com
as regiões da Embrapa Café. Para que a divisão seja reproduzível, cada região é definida por
**mesorregiões e microrregiões do IBGE** (`DEFINICOES`), e entram nela os municípios dessas áreas
com área colhida de café na PAM (tabela 1613, variável 216) de pelo menos `AREA_MINIMA_HA` no ano
mais recente: é isso que `scripts/regioes_do_cafe.py` grava em `municipios.csv`, ao lado deste
arquivo, com a área de arábica e de conilon de cada município. O tipo predominante da região é o
que tem mais área colhida na soma dos municípios dela.

Limites conhecidos: município fica inteiro numa região (o Caparaó, que a CONAB divide entre MG e
ES, fica nas Matas de Minas e nas montanhas do ES conforme a UF); Goiás, Mato Grosso, Rio de
Janeiro, Pernambuco e Ceará produzem pouco e ficam fora; a lista segue a PAM do ano em
`municipios.csv` (coluna `ano_pam`), não o cadastro de produtores.
"""

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ARABICA, CONILON = "arabica", "conilon"
# Área colhida de café na PAM abaixo disso não faz o município entrar numa região.
AREA_MINIMA_HA = 50
ARQUIVO_DOS_MUNICIPIOS = Path(__file__).with_name("municipios.csv")
TAMANHO_DO_CODIGO = 7  # código IBGE de município: UF (2) + município (5)


@dataclass(frozen=True)
class DefinicaoDaRegiao:
    """Uma região produtora descrita por áreas do IBGE (o que o script usa para montar a lista)."""

    id: str
    nome: str
    ufs: tuple[str, ...]
    mesorregioes: tuple[int, ...] = ()  # códigos de 4 dígitos do IBGE
    microrregioes: tuple[int, ...] = ()  # códigos de 5 dígitos do IBGE
    descricao: str = ""


# fmt: off
DEFINICOES: tuple[DefinicaoDaRegiao, ...] = (
    DefinicaoDaRegiao(
        "sul-de-minas", "Sul de Minas", ("MG",),
        mesorregioes=(3110,),  # Sul/Sudoeste de Minas
        microrregioes=(31057, 31042, 31044, 31045, 31046),  # Lavras; Piuí, Formiga, Campo Belo, Oliveira
        descricao="Varginha, Guaxupé, Alfenas, Três Pontas, Poços de Caldas, a Mantiqueira e o Campo das Vertentes; a maior região de arábica do país",
    ),
    DefinicaoDaRegiao(
        "cerrado-mineiro", "Cerrado Mineiro", ("MG",),
        mesorregioes=(3105, 3101),  # Triângulo Mineiro/Alto Paranaíba; Noroeste de Minas
        descricao="Patrocínio, Araguari, Monte Carmelo, Carmo do Paranaíba e Unaí; a indicação geográfica Cerrado Mineiro, café irrigado e mecanizado",
    ),
    DefinicaoDaRegiao(
        "matas-de-minas", "Matas de Minas", ("MG",),
        mesorregioes=(3112, 3108),  # Zona da Mata; Vale do Rio Doce
        descricao="Manhuaçu, Caratinga, Muriaé, Viçosa e o Caparaó mineiro; montanha e pequena propriedade",
    ),
    DefinicaoDaRegiao(
        "chapada-de-minas", "Chapada de Minas", ("MG",),
        mesorregioes=(3103, 3104, 3102),  # Jequitinhonha; Vale do Mucuri; Norte de Minas
        descricao="Capelinha, Turmalina, Minas Novas e o norte do estado; planalto, café irrigado e de sequeiro",
    ),
    DefinicaoDaRegiao(
        "mogiana", "Mogiana", ("SP",),
        mesorregioes=(3502, 3507),  # Ribeirão Preto (Franca, Batatais); Campinas (São João da Boa Vista, Amparo)
        descricao="Franca, Pedregulho, Espírito Santo do Pinhal e São João da Boa Vista; a Alta Mogiana e a Média Mogiana",
    ),
    DefinicaoDaRegiao(
        "alta-paulista", "Alta Paulista", ("SP",),
        mesorregioes=(3509, 3510, 3504, 3508),  # Marília; Assis; Bauru; Presidente Prudente
        descricao="Garça, Marília, Ourinhos e o centro-oeste paulista (Alta Paulista e Média Sorocabana)",
    ),
    DefinicaoDaRegiao(
        "norte-do-parana", "Norte do Paraná", ("PR",),
        mesorregioes=(4104, 4103, 4101),  # Norte Pioneiro; Norte Central; Noroeste
        descricao="Norte Pioneiro (Carlópolis, Tomazina), Londrina e o noroeste; arábica em zona de geada",
    ),
    DefinicaoDaRegiao(
        "oeste-da-bahia", "Oeste da Bahia", ("BA",),
        mesorregioes=(2901,),  # Extremo Oeste Baiano
        descricao="Barreiras, Luís Eduardo Magalhães e São Desidério; arábica irrigado por pivô no cerrado",
    ),
    DefinicaoDaRegiao(
        "planalto-da-bahia", "Planalto da Bahia", ("BA",),
        mesorregioes=(2906, 2903),  # Centro Sul Baiano (Vitória da Conquista, Chapada Diamantina); Centro Norte
        descricao="Vitória da Conquista, Barra do Choça, Piatã e a Chapada Diamantina; arábica de altitude",
    ),
    DefinicaoDaRegiao(
        "es-montanhas", "Espírito Santo, montanhas", ("ES",),
        mesorregioes=(3204, 3203),  # Sul e Central Espírito-santense
        descricao="Venda Nova do Imigrante, Afonso Cláudio, Brejetuba, Iúna e o Caparaó capixaba; arábica de montanha (há conilon nas baixadas)",
    ),
    DefinicaoDaRegiao(
        "es-norte", "Espírito Santo, norte", ("ES",),
        mesorregioes=(3201, 3202),  # Noroeste e Litoral Norte Espírito-santense
        descricao="Linhares, São Mateus, Jaguaré, Nova Venécia, Vila Valério e Colatina; a maior região de conilon do país",
    ),
    DefinicaoDaRegiao(
        "rondonia", "Rondônia", ("RO",),
        mesorregioes=(1101, 1102),  # o estado inteiro
        descricao="Cacoal, Alta Floresta d'Oeste, Rolim de Moura e São Miguel do Guaporé; conilon (robusta amazônico)",
    ),
    DefinicaoDaRegiao(
        "bahia-atlantico", "Bahia, Atlântico", ("BA",),
        mesorregioes=(2907,),  # Sul Baiano
        descricao="Itabela, Eunápolis, Itamaraju e o extremo sul; conilon de baixada",
    ),
)
# fmt: on


@dataclass(frozen=True)
class Municipio:
    codigo: str  # IBGE, 7 dígitos
    nome: str
    uf: str
    area_arabica_ha: float
    area_conilon_ha: float

    @property
    def area_ha(self) -> float:
        return self.area_arabica_ha + self.area_conilon_ha


@dataclass(frozen=True)
class Regiao:
    id: str
    nome: str
    ufs: tuple[str, ...]
    tipo_predominante: str  # `ARABICA` ou `CONILON`
    municipios: tuple[Municipio, ...]
    descricao: str = ""

    @property
    def codigos(self) -> frozenset[str]:
        return frozenset(m.codigo for m in self.municipios)

    @property
    def area_ha(self) -> float:
        return sum(m.area_ha for m in self.municipios)


def ler_municipios(
    arquivo: Path = ARQUIVO_DOS_MUNICIPIOS,
) -> dict[str, list[Municipio]]:
    """Os municípios do CSV, por id de região (o CSV já diz a região de cada um).

    Sem o arquivo (só acontece enquanto `scripts/regioes_do_cafe.py` o gera pela primeira vez,
    pois o script importa este módulo), as regiões ficam vazias.
    """
    por_regiao: dict[str, list[Municipio]] = {}
    if not arquivo.exists():
        return por_regiao
    with arquivo.open(encoding="utf-8", newline="") as aberto:
        for linha in csv.DictReader(aberto):
            municipio = Municipio(
                linha["codigo"],
                linha["nome"],
                linha["uf"],
                float(linha["area_arabica_ha"]),
                float(linha["area_conilon_ha"]),
            )
            por_regiao.setdefault(linha["regiao"], []).append(municipio)
    return por_regiao


def tipo_predominante(municipios: Iterable[Municipio]) -> str:
    """Arábica ou conilon, pelo que tem mais área colhida na soma dos municípios."""
    lista = list(municipios)
    arabica = sum(m.area_arabica_ha for m in lista)
    conilon = sum(m.area_conilon_ha for m in lista)
    return CONILON if conilon > arabica else ARABICA


def montar_regioes(
    definicoes: Iterable[DefinicaoDaRegiao] = DEFINICOES,
    municipios_por_regiao: dict[str, list[Municipio]] | None = None,
) -> tuple[Regiao, ...]:
    """As regiões, com os municípios do CSV (ou os dados; serve aos testes) em cada uma."""
    if municipios_por_regiao is None:
        municipios_por_regiao = ler_municipios()
    regioes = []
    for definicao in definicoes:
        municipios = tuple(
            sorted(municipios_por_regiao.get(definicao.id, []), key=lambda m: m.codigo)
        )
        regioes.append(
            Regiao(
                definicao.id,
                definicao.nome,
                definicao.ufs,
                tipo_predominante(municipios),
                municipios,
                definicao.descricao,
            )
        )
    return tuple(regioes)


REGIOES: tuple[Regiao, ...] = montar_regioes()
POR_ID: dict[str, Regiao] = {r.id: r for r in REGIOES}
_REGIAO_DO_MUNICIPIO: dict[str, Regiao] = {
    m.codigo: regiao for regiao in REGIOES for m in regiao.municipios
}


def normalizar_codigo(codigo: str | int) -> str:
    """Código IBGE como texto de 7 dígitos: aceita int, texto ou os 6 dígitos sem o verificador."""
    texto = str(codigo).strip()
    if len(texto) == TAMANHO_DO_CODIGO - 1 and texto.isdigit():
        return texto + _digito_verificador(texto)
    return texto.zfill(TAMANHO_DO_CODIGO)


def _digito_verificador(seis_digitos: str) -> str:
    """O 7º dígito do código IBGE de município (módulo 10 com pesos 1, 2, 1, 2, 1, 2)."""
    soma = 0
    for posicao, caractere in enumerate(seis_digitos):
        produto = int(caractere) * (1 if posicao % 2 == 0 else 2)
        soma += produto // 10 + produto % 10
    return str((10 - soma % 10) % 10)


def regiao_do_municipio(codigo: str | int) -> Regiao | None:
    """A região produtora de um município (código IBGE), ou None se ele não está em nenhuma."""
    return _REGIAO_DO_MUNICIPIO.get(normalizar_codigo(codigo))
