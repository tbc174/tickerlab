"""Exigência 7 da prontidão: qualidade automática de cada tabela (ADR 0027; ADR 0108, Emenda 1, D10).

Cada tabela que a API serve tem uma `Regra` escrita à mão: a chave natural da linha, o que pode ficar
vazio nela e por quê, a coluna de data e a de valor. `avaliar` compara as medidas que a porta tira
(`Porta.perfil`) com a regra. O que não bate e não tem explicação escrita deixa a tabela **vermelha**:
sem a prova da 7, sem prontidão. As regras só apontam, nunca corrigem.

- **linhas repetidas** na chave (além do aceito, com o motivo);
- **vazio** numa coluna da chave que não é opcional;
- **ano faltando** entre o primeiro e o último;
- **salto** de linhas entre anos seguidos (mais que o dobro, ou menos que a metade);
- **escala**: a mediana do valor de um ano ≥ 10 vezes a do ano anterior, ou o inverso.

O ano em curso só tem parte dos dados: salto e escala não o comparam (o ano faltando e a chave contam).

Quem mede e grava o resultado do dia é `scripts/conferir_qualidade.py`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")
FATOR_DE_SALTO = 2.0
FATOR_DE_ESCALA = 10.0


@dataclass(frozen=True)
class Regra:
    chave: tuple[str, ...]
    periodo: str | None = None
    valor: str | None = None
    opcionais: Mapping[str, str] = field(
        default_factory=dict
    )  # coluna da chave -> por que pode faltar
    repetidas_aceitas: int = 0
    porque_repetidas: str = ""
    saltos_explicados: Mapping[int, str] = field(
        default_factory=dict
    )  # ano -> o que houve


@dataclass(frozen=True)
class Achado:
    texto: str
    explicacao: str = ""


def _por_ano(perfil: Mapping[str, object]) -> dict[int, tuple[int, float | None]]:
    return dict(perfil["por_ano"])  # type: ignore[arg-type]


def _faltando(anos: list[int]) -> list[int]:
    return sorted(set(range(min(anos), max(anos) + 1)) - set(anos)) if anos else []


def _salto(antes: int, agora: int) -> bool:
    return antes > 0 and (
        agora > antes * FATOR_DE_SALTO or agora < antes / FATOR_DE_SALTO
    )


def _da_chave(regra: Regra, perfil: Mapping[str, object]) -> list[Achado]:
    achados = []
    repetidas = int(perfil["repetidas"])  # type: ignore[call-overload]
    if repetidas > regra.repetidas_aceitas:
        achados.append(
            Achado(
                f"{repetidas} linhas repetidas na chave (aceitas: {regra.repetidas_aceitas})"
            )
        )
    elif repetidas:
        achados.append(
            Achado(f"{repetidas} linhas repetidas na chave", regra.porque_repetidas)
        )
    vazios: Mapping[str, int] = perfil["vazios_na_chave"]  # type: ignore[assignment]
    for coluna, n in vazios.items():
        if n and coluna not in regra.opcionais:
            achados.append(Achado(f"{n} linhas com `{coluna}` vazia na chave"))
        elif n:
            achados.append(
                Achado(
                    f"{n} linhas com `{coluna}` vazia na chave", regra.opcionais[coluna]
                )
            )
    return achados


def _dos_anos(
    regra: Regra, perfil: Mapping[str, object], ano_em_curso: int
) -> list[Achado]:
    por_ano = _por_ano(perfil)
    if not por_ano:
        return []
    achados = [Achado(f"ano faltando: {ano}") for ano in _faltando(list(por_ano))]
    anos = sorted(por_ano)
    for antes, ano in pairwise(anos):
        if ano >= ano_em_curso:
            continue
        (linhas_antes, escala_antes), (linhas, escala) = por_ano[antes], por_ano[ano]
        if _salto(linhas_antes, linhas):
            texto = f"{ano}: {linhas_antes} -> {linhas} linhas em relação a {antes}"
            achados.append(Achado(texto, regra.saltos_explicados.get(ano, "")))
        if (
            escala
            and escala_antes
            and max(escala / escala_antes, escala_antes / escala) >= FATOR_DE_ESCALA
        ):
            achados.append(
                Achado(
                    f"{ano}: a mediana do valor mudou de escala em relação a {antes}",
                    regra.saltos_explicados.get(ano, ""),
                )
            )
    return achados


def avaliar(
    regra: Regra, perfil: Mapping[str, object], ano_em_curso: int | None = None
) -> list[Achado]:
    """Tudo o que a regra aponta na tabela, com a explicação escrita quando há."""
    return [
        *_da_chave(regra, perfil),
        *_dos_anos(regra, perfil, ano_em_curso or datetime.now(BRASILIA).year),
    ]


def sem_explicacao(achados: list[Achado]) -> list[Achado]:
    return [a for a in achados if not a.explicacao]


REGRAS: dict[str, Regra] = {
    "demonstracoes_como_era": Regra(
        chave=(
            "cnpj",
            "documento",
            "referencia",
            "versao",
            "origem",
            "ordem",
            "grupo",
            "demonstracao",
            "conta",
            "inicio",
            "fim",
        ),
        periodo="referencia",
        valor="valor",
        opcionais={
            "inicio": "balanço patrimonial é uma foto do dia: não tem data de início"
        },
        saltos_explicados={
            2011: "2010 só tem a DFP; o ITR entra a partir de 2011",
            2021: "a partir de 2021 a tabela guarda também as versões lidas do ENET (origem `enet`), além dos dados abertos",
        },
    ),
    "cadastro_de_fundos": Regra(
        # o cadastro repete o fundo uma vez por gestor, auditor, custodiante, administrador e controlador
        chave=(
            "TP_FUNDO",
            "CNPJ_FUNDO",
            "CD_CVM",
            "CPF_CNPJ_GESTOR",
            "CNPJ_AUDITOR",
            "CNPJ_CUSTODIANTE",
            "CNPJ_ADMIN",
            "CNPJ_CONTROLADOR",
        ),
        opcionais={
            "CD_CVM": "fundo ainda em análise na CVM, sem código",
            "CPF_CNPJ_GESTOR": "quase todos são fundos cancelados, que a CVM deixa sem gestor",
            "CNPJ_AUDITOR": "fundo sem auditor informado (os cancelados, em geral)",
            "CNPJ_CUSTODIANTE": "fundo sem custodiante informado",
            "CNPJ_ADMIN": "fundo sem administrador informado (os cancelados, em geral)",
            "CNPJ_CONTROLADOR": "fundo sem controlador informado",
        },
        repetidas_aceitas=1,
        porque_repetidas="uma linha idêntica em todas as colunas (FIC-FITVM, mesmo CNPJ), duplicada no arquivo da CVM; a base não corrige",
    ),
    "carteiras_dos_fundos": Regra(
        chave=(
            "competencia",
            "cnpj_fundo",
            "tipo_do_fundo",
            "tipo",
            "codigo",
            "descricao",
            "quantidade",
            "valor",
            "compras",
            "vendas",
        ),
        periodo="competencia",
        valor="valor",
        opcionais={
            c: "posição sem esse campo no arquivo da CVM"
            for c in ("codigo", "quantidade", "valor", "compras", "vendas")
        },
        repetidas_aceitas=100,
        porque_repetidas="linhas idênticas em todas as colunas, duplicadas no arquivo da CVM (cerca de 0,0005% da tabela); a base não corrige",
    ),
    # retrato mensal da Receita: um único mês por vez, sem série por ano para comparar; vale a chave única
    # (um estabelecimento por CNPJ de 14 dígitos) e nenhuma coluna de cadastro vazia
    "cnpj_estabelecimentos_pj": Regra(
        chave=(
            "cnpj",
            "cnpj_basico",
            "matriz",
            "situacao_cadastral",
            "uf",
            "municipio",
            "cnae_principal",
            "data_inicio_atividade",
        ),
    ),
    "cnpj_empresas_pj": Regra(
        chave=("cnpj_basico", "razao_social", "natureza_juridica", "porte"),
    ),
}
