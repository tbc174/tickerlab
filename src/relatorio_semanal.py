"""O relatório de setor da semana no site (ADR 0109, item 10; fila 210): um setor por semana, com um
cruzamento que tem data e fonte, e o que a base não tem dito com franqueza.

A semana 1 é a das elétricas. Os números vêm de um retrato das fichas da noite (`conteudo/relatorios_
semanais/eletricas.json`, feito por `montar_retrato`): o número de consumidores de cada grupo (ANEEL, ligado
pela tabela empresa ↔ série da base) e o auditor atual (FRE entregue à CVM). Daí saem, por conta aqui,
a participação de cada grupo, a das quatro maiores e o peso de cada auditor; o texto é escrito a partir
desses números, nunca à mão. Nada de nota, ordem por juízo ou previsão (ADR 0100, item 5; ADR 0103).

O retrato só leva companhias cuja ligação com a ANEEL a base sustenta; as que ficam de fora aparecem na
página com o motivo (`de_fora`).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src import dossie, relatorio_setor
from src.amostra_do_relatorio import conferir

PASTA = Path(__file__).resolve().parent.parent / "conteudo" / "relatorios_semanais"
CHAVE_DO_SETOR = "eletricas"
FONTE_DOS_CONSUMIDORES = (
    "ODbL (dados abertos da ANEEL, SAMP; citar a ANEEL), ligados a cada companhia pelo formulário "
    "de referência da CVM e pelo nome da distribuidora"
)
FONTE_DO_AUDITOR = (
    "ODbL (dados abertos da CVM; citar a fonte): Formulário de Referência"
)
QUATRO_MAIORES = 4
CASAS_DA_PARTICIPACAO = 1
AUDITORES = (  # trecho do nome em minúsculas → nome curto
    ("pricewaterhouse", "PwC"),
    ("deloitte", "Deloitte"),
    ("kpmg", "KPMG"),
    ("ernst", "EY"),
)
ANO_DA_TROCA_EM_DESTAQUE = "2022"
RODAPE = (
    "Nada aqui é recomendação de investimento. Os números descrevem o que as companhias e as agências "
    "entregaram, sem dizer o que vai acontecer."
)


@dataclass(frozen=True)
class Grupo:
    """Uma companhia do retrato, com o que a ficha da noite diz dela."""

    nome: str
    cnpj: str
    consumidores: int
    ano_base: str  # AAAA-MM do último dado da ANEEL
    auditor: str
    auditor_desde: str  # AAAA-MM-DD, como o FRE informa


def _auditor_curto(nome: str) -> str:
    minusculo = nome.lower()
    for trecho, curto in AUDITORES:
        if trecho in minusculo:
            return curto
    return nome


def _valor(secao: dossie.SecaoDaFicha, chave: str) -> str | int | float | None:
    return next(i.valor for i in secao.itens if i.chave == chave)


def grupo_da_ficha(ficha: dossie.Ficha) -> tuple[Grupo, float]:
    """O grupo e o total de consumidores do país no mesmo ano (consumidores ÷ participação)."""
    secoes = {s.chave: s for s in dossie.cortar(ficha).secoes}
    ultima = secoes["setor_regulado"].tabelas["aneel_consumidores"][0]
    auditoria = secoes["auditor_e_controladas"]
    grupo = Grupo(
        nome=ficha.empresa,
        cnpj=ficha.cnpj,
        consumidores=int(ultima["valor"]),
        ano_base=str(ultima["ultimo_mes"])[:7],
        auditor=_valor(auditoria, "auditor_atual"),
        auditor_desde=str(_valor(auditoria, "auditor_desde")),
    )
    return grupo, ultima["valor"] / ultima["participacao"]


def montar_retrato(
    pasta_das_fichas: Path, cnpjs: list[str], de_fora: list[dict[str, str]]
) -> dict[str, Any]:
    """O retrato que vai para `conteudo/relatorios_semanais/`: as fichas conferidas, só o que o relatório usa."""
    grupos, totais, datas = [], [], []
    for cnpj in cnpjs:
        ficha = dossie.ler_ficha(pasta_das_fichas / f"{cnpj}.json")
        if ficha is None:
            raise ValueError(f"a ficha {cnpj} não abre")
        conferir(dossie.cortar(ficha))
        grupo, total = grupo_da_ficha(ficha)
        grupos.append(grupo.__dict__)
        totais.append(round(total))
        datas.append(ficha.gerado_em.date().isoformat())
    if len(set(totais)) != 1:
        raise ValueError(
            f"o total de consumidores do país muda de ficha para ficha: {set(totais)}"
        )
    return {
        "setor": CHAVE_DO_SETOR,
        "dados_de": max(datas),
        "total_do_pais": totais[0],
        "grupos": grupos,
        "de_fora": de_fora,
    }


def ler_retrato(caminho: Path | None = None) -> dict[str, Any]:
    """O retrato guardado (a semana 1, por padrão)."""
    caminho = caminho or PASTA / f"{CHAVE_DO_SETOR}.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


# --- os números do cruzamento ----------------------------------------------------------------------


def _percentual(fracao: float) -> str:
    return f"{fracao * 100:.{CASAS_DA_PARTICIPACAO}f}".replace(".", ",") + "%"


def _milhoes(valor: float) -> str:
    return f"{valor / 1e6:.1f}".replace(".", ",") + " milhões"


def _milhares(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def _data_escrita(iso: str) -> str:
    ano, mes, dia = iso[:10].split("-")
    return f"{dia}/{mes}/{ano}"


def _mes_escrito(aaaa_mm: str) -> str:
    ano, mes = aaaa_mm.split("-")
    return f"{mes}/{ano}"


def _grupos_por_tamanho(retrato: dict[str, Any]) -> list[Grupo]:
    grupos = [Grupo(**g) for g in retrato["grupos"]]
    return sorted(grupos, key=lambda g: -g.consumidores)


def _com_data_possivel(grupos: list[Grupo], dados_de: str) -> list[Grupo]:
    """Sem as que informam o auditor atual "desde" uma data posterior à ficha (o formulário ainda não vale)."""
    return [g for g in grupos if g.auditor_desde <= dados_de]


def _peso_por_auditor(grupos: list[Grupo]) -> dict[str, tuple[int, int]]:
    """{auditor curto: (companhias, consumidores)}, do que mais pesa ao que menos."""
    pesos: dict[str, tuple[int, int]] = {}
    for g in grupos:
        n, soma = pesos.get(_auditor_curto(g.auditor), (0, 0))
        pesos[_auditor_curto(g.auditor)] = (n + 1, soma + g.consumidores)
    return dict(sorted(pesos.items(), key=lambda kv: -kv[1][1]))


def _nome_curto(nome: str) -> str:
    """Nome para o texto corrido: a razão social sem o 'S.A.' e sem o resto do cabeçalho."""
    curtos = {
        "NEOENERGIA S.A.": "Neoenergia",
        "EQUATORIAL S.A.": "Equatorial",
        "CPFL ENERGIA S.A.": "CPFL Energia",
        "CIA ENERGETICA DE MINAS GERAIS - CEMIG": "Cemig",
        "CIA PARANAENSE DE ENERGIA - COPEL": "Copel",
        "ENERGISA S.A.": "Energisa",
        "LIGHT S.A. - Em Recuperação Judicial": "Light",
        "REDE ENERGIA PARTICIPAÇÕES S.A.": "Rede Energia Participações",
        "CENTRAIS ELET DE SANTA CATARINA S.A.": "Celesc",
    }
    return curtos.get(nome, nome)


def _lista_em_texto(nomes: list[str]) -> str:
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _destaques(retrato: dict[str, Any], grupos: list[Grupo]) -> list[dict[str, str]]:
    total = retrato["total_do_pais"]
    soma = sum(g.consumidores for g in grupos)
    maiores = grupos[:QUATRO_MAIORES]
    base = _mes_escrito(grupos[0].ano_base)
    desde_2022 = [
        g for g in grupos if g.auditor_desde.startswith(ANO_DA_TROCA_EM_DESTAQUE)
    ]
    peso_2022 = sum(g.consumidores for g in desde_2022)
    dados_de = _data_escrita(retrato["dados_de"])
    return [
        {
            "titulo": f"{len(grupos)} companhias abertas atendem {_percentual(soma / total)} dos consumidores do país",
            "texto": (
                f"Em {base}, as distribuidoras do país atendiam {_milhoes(total)} de consumidores. As "
                f"{len(grupos)} companhias abertas desta página, com as distribuidoras que a base liga a "
                f"cada uma, somam {_milhoes(soma)}: {_percentual(soma / total)} do total."
            ),
            "fonte": FONTE_DOS_CONSUMIDORES,
            "data": f"{base} (ficha de {dados_de})",
        },
        {
            "titulo": f"As {QUATRO_MAIORES} maiores concentram {_percentual(sum(g.consumidores for g in maiores) / total)} do país",
            "texto": (
                f"{_lista_em_texto([_nome_curto(g.nome) for g in maiores])} atendem juntas "
                f"{_milhoes(sum(g.consumidores for g in maiores))} de consumidores, "
                f"{_percentual(sum(g.consumidores for g in maiores) / soma)} do que as {len(grupos)} somam."
            ),
            "fonte": FONTE_DOS_CONSUMIDORES,
            "data": f"{base} (ficha de {dados_de})",
        },
        {
            "titulo": (
                f"{len(desde_2022)} das {len(grupos)} informam o auditor atual desde {ANO_DA_TROCA_EM_DESTAQUE}"
            ),
            "texto": (
                f"{_lista_em_texto([_nome_curto(g.nome) for g in sorted(desde_2022, key=lambda g: -g.consumidores)])} "
                f"têm o auditor atual desde {ANO_DA_TROCA_EM_DESTAQUE}, segundo o formulário de referência. "
                f"Juntas, atendem {_percentual(peso_2022 / total)} dos consumidores do país."
            ),
            "fonte": FONTE_DO_AUDITOR,
            "data": f"ficha de {dados_de} (formulário mais recente)",
        },
    ]


def _tabela_dos_consumidores(
    retrato: dict[str, Any], grupos: list[Grupo]
) -> dict[str, Any]:
    total = retrato["total_do_pais"]
    return {
        "chave": "consumidores",
        "titulo": "Consumidores atendidos, por companhia aberta",
        "colunas": ["Companhia", "Consumidores", "Participação no país", "Dado de"],
        "linhas": [
            [
                _nome_curto(g.nome),
                _milhares(g.consumidores),
                _percentual(g.consumidores / total),
                _mes_escrito(g.ano_base),
            ]
            for g in grupos
        ],
    }


def _tabela_dos_auditores(grupos: list[Grupo], dados_de: str) -> dict[str, Any]:
    possiveis = {g.nome for g in _com_data_possivel(grupos, dados_de)}
    return {
        "chave": "auditor_de_cada",
        "titulo": "Auditor atual de cada companhia",
        "colunas": ["Companhia", "Auditor atual", "Desde"],
        "linhas": [
            [
                _nome_curto(g.nome),
                _auditor_curto(g.auditor),
                _data_escrita(g.auditor_desde)
                + ("" if g.nome in possiveis else " (data futura no formulário)"),
            ]
            for g in grupos
        ],
    }


def _tabela_do_peso_por_auditor(
    retrato: dict[str, Any], grupos: list[Grupo]
) -> dict[str, Any]:
    total = retrato["total_do_pais"]
    grupos = _com_data_possivel(grupos, retrato["dados_de"])
    return {
        "chave": "peso_por_auditor",
        "titulo": f"Quanto do país cada auditor acompanha ({len(grupos)} companhias com data possível)",
        "colunas": ["Auditor", "Companhias", "Consumidores", "Participação no país"],
        "linhas": [
            [auditor, str(n), _milhares(soma), _percentual(soma / total)]
            for auditor, (n, soma) in _peso_por_auditor(grupos).items()
        ],
    }


def _limites(retrato: dict[str, Any]) -> list[str]:
    de_fora = [f"{d['nome']}: {d['motivo']}" for d in retrato["de_fora"]]
    return [
        RODAPE,
        (
            "Esta página usa a ficha da noite (CVM e ANEEL). Resultado, dívida e caixa de cada companhia "
            "(DFP e ITR) ficam para o relatório completo do setor, no app."
        ),
        "A ligação entre a companhia e as distribuidoras da ANEEL vem do formulário de referência e do "
        "nome da distribuidora. Duas companhias ficaram de fora da tabela porque essa ligação ainda "
        "precisa de conferência, e uma por ter dado antigo: "
        + "; ".join(de_fora)
        + ".",
        (
            "A Energisa e a Rede Energia Participações são duas companhias na CVM. O formulário de "
            "referência da Energisa registra uma participação pequena na Rede Energia, então a base não "
            "soma as duas: se somasse, a tabela teria outra ordem."
        ),
        (
            "O auditor vem do campo “auditor atual” do formulário; a lista de trocas passadas ainda "
            "diverge dele em duas companhias, por isso o histórico de trocas não aparece aqui. A "
            "Neoenergia informa o auditor atual “desde” uma data futura: aparece na tabela com o aviso e "
            "fica fora da conta do peso de cada auditor."
        ),
        (
            "Companhia em recuperação judicial aparece com o nome registrado na CVM; a página não avalia "
            "a situação de nenhuma delas."
        ),
    ]


def _fonte_publica(fonte: str) -> str:
    """A fonte do "o que falta" sem o jargão de planejamento (série, mesa, nome de tabela)."""
    if "mesa Dados" in fonte:
        return "nenhuma coletada ainda"
    return re.sub(r" \(tabela [^)]*\)", "", fonte).replace(
        " da empresa (R)", " da empresa"
    )


def para_o_site(retrato: dict[str, Any] | None = None) -> dict[str, Any]:
    """O JSON da página `relatorio-de-setor-eletricas.html` (web/conteudo/relatorio_semanal_eletricas.json)."""
    retrato = retrato or ler_retrato()
    grupos = _grupos_por_tamanho(retrato)
    faltas = relatorio_setor.nao_temos(retrato["setor"])
    return {
        "setor": retrato["setor"],
        "titulo": "Elétricas: quem atende os consumidores do país e quem audita",
        "dados_de": _data_escrita(retrato["dados_de"]),
        "aviso": RODAPE,
        "destaques": _destaques(retrato, grupos),
        "tabelas": [
            _tabela_dos_consumidores(retrato, grupos),
            _tabela_dos_auditores(grupos, retrato["dados_de"]),
            _tabela_do_peso_por_auditor(retrato, grupos),
        ],
        "nao_temos": [
            {"kpi": f.kpi, "motivo": f.motivo, "fonte": _fonte_publica(f.fonte)}
            for f in faltas
        ],
        "limites": _limites(retrato),
    }
