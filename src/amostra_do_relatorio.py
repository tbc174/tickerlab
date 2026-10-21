"""A amostra aberta do relatório da base no site: a CPFL Energia (plano do relatório-modelo, 17/10/2026,
PR 1, tarefas 4 e 5).

A ficha da CPFL montada no servidor de casa fica congelada em `dados_de_exemplo/dossie/`. Daqui saem o
JSON da página do site (`scripts/exportar_conteudo.py`) e o PDF (`scripts/gerar_site.py`), do mesmo
`Relatorio`: os números são os mesmos nos dois.

Antes de sair, a ficha passa de novo pelas regras do dossiê (só fonte vendável, nada da lista de crise,
nenhuma pessoa): a página é aberta a qualquer um.
"""

from dataclasses import dataclass
from datetime import datetime

from base import dossie as dossie_da_base
from src import destaques as destaques_da_base
from src import dossie
from src.relatorio_empresa import Relatorio, Secao
from src.relatorio_empresa_pdf import LISTA, relatorio_da_empresa

NOME = "CPFL Energia"
TICKER = "CPFE3"
SETOR = "Energia elétrica"
CAMINHO_DO_PDF = f"/relatorio/exemplo-{TICKER}.pdf"
TITULO_DOS_DESTAQUES = "O que a base mostra"
RODAPE = (
    "Nada aqui é recomendação de investimento. Dados entregues à CVM e às agências reguladoras, "
    "reunidos pela base do TickerLab; podem ser reapresentados."
)
TITULO_DOS_LIMITES = "Limites e cuidados"
AVISO = (
    "Amostra aberta do relatório da base do TickerLab. Nada aqui é recomendação de investimento: os "
    "números descrevem o que a empresa e as agências entregaram, sem dizer o que vai acontecer."
)


def _limites(ficha: dossie.Ficha) -> list[str]:
    return [
        (
            "Nada aqui é recomendação de investimento. Os destaques descrevem o que a companhia, "
            "os fundos e as agências entregaram; não dizem se é bom ou ruim nem o que vai acontecer."
        ),
        *dossie.limites_da_ficha(ficha),
    ]


@dataclass(frozen=True)
class Amostra:
    ficha: dossie.Ficha
    destaques: list[destaques_da_base.Destaque]
    relatorio: Relatorio


def conferir(ficha: dossie.Ficha) -> None:
    """Levanta erro se a ficha tem seção fora do registro, tabela que não pode ser mostrada ou pessoa."""
    registro = {secao.chave: secao for secao in dossie_da_base.SECOES}
    for secao in ficha.secoes:
        if secao.chave not in registro:
            raise dossie_da_base.TabelaProibidaError(
                f"seção fora do registro do dossiê: {secao.chave}"
            )
        dossie_da_base.exigir_que_pode_mostrar(registro[secao.chave].tabelas)
    # os nomes das entidades-pessoa ficam no servidor de casa; aqui valem o CPF e as colunas
    dossie_da_base.conferir_sem_pessoas(ficha.model_dump(mode="json"), set())


def _cnpj_escrito(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _secao_dos_destaques(destaques: list[destaques_da_base.Destaque]) -> Secao:
    lista = [
        {
            "titulo": d.titulo,
            "texto": d.texto,
            "nota": f"Fonte: {d.fonte}; dado de {d.data}.",
            "link": d.link,
        }
        for d in destaques
    ]
    return Secao("destaques", TITULO_DOS_DESTAQUES, tabelas={LISTA: lista})


def montar(ficha: dossie.Ficha | None = None) -> Amostra:
    """A amostra da ficha (a da CPFL, por padrão), já conferida."""
    lida = ficha or dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    if lida is None:
        raise ValueError("a ficha de exemplo não abre")
    cortada = dossie.cortar(lida)
    conferir(cortada)
    destaques = destaques_da_base.destaques_da_ficha(cortada)
    secoes = [
        _secao_dos_destaques(destaques),
        *dossie.secoes_da_ficha(cortada),
        Secao("limites", TITULO_DOS_LIMITES, paragrafos=_limites(cortada)),
    ]
    fontes = tuple(dict.fromkeys(f for s in cortada.secoes for f in s.fontes))
    relatorio = Relatorio(
        empresa=NOME,
        cnpj=_cnpj_escrito(cortada.cnpj),
        ticker=TICKER,
        setor=SETOR,
        grupo=SETOR,
        secoes=secoes,
        fontes=fontes,
        aviso_das_notas=AVISO,
        em_conferencia=False,
    )
    return Amostra(cortada, destaques, relatorio)


def _tabelas_para_o_site(ficha: dossie.Ficha, secao: Secao) -> list[dict[str, object]]:
    tabelas = []
    for chave, linhas in secao.tabelas.items():
        colunas = list(linhas[0]) if linhas else []
        links = dossie.links_da_tabela(ficha, secao.chave, chave)
        tabelas.append(
            {
                "chave": chave,
                "titulo": dossie.titulo_da_tabela(chave),
                "colunas": colunas,
                "linhas": [[linha[c] for c in colunas] for linha in linhas],
                "links": links if any(links) else [],
            }
        )
    return tabelas


def para_o_site(amostra: Amostra | None = None) -> dict[str, object]:
    """O JSON da página `relatorio-de-exemplo.html` (web/conteudo/amostra_relatorio.json)."""
    amostra = amostra or montar()
    relatorio = amostra.relatorio
    da_ficha = [s for s in relatorio.secoes if s.chave not in ("destaques", "limites")]
    return {
        "empresa": relatorio.empresa,
        "razao_social": amostra.ficha.empresa,
        "cnpj": relatorio.cnpj,
        "ticker": relatorio.ticker,
        "setor": relatorio.setor,
        "dados_de": f"{amostra.ficha.gerado_em:%d/%m/%Y}",
        "pdf": CAMINHO_DO_PDF,
        "aviso": AVISO,
        "destaques": [
            {
                "chave": d.chave,
                "titulo": d.titulo,
                "texto": d.texto,
                "fonte": d.fonte,
                "data": d.data,
                "secao": d.secao,
                "link": d.link,
            }
            for d in amostra.destaques
        ],
        "secoes": [
            {
                "chave": s.chave,
                "titulo": s.titulo,
                "itens": [
                    {"nome": i.nome, "texto": i.texto, "base": i.base} for i in s.itens
                ],
                "paragrafos": s.paragrafos,
                "tabelas": _tabelas_para_o_site(amostra.ficha, s),
            }
            for s in da_ficha
        ],
        "limites": relatorio.secao("limites").paragrafos,
        "fontes": list(relatorio.fontes),
    }


def pdf(amostra: Amostra | None = None) -> bytes:
    """O PDF da amostra, com a data da ficha (o arquivo não muda a cada geração)."""
    amostra = amostra or montar()
    gerado_em: datetime = amostra.ficha.gerado_em
    # com o anexo "como cada número foi calculado": texto público, com o "pode" do Tiago (21/10)
    return relatorio_da_empresa(amostra.relatorio, gerado_em, aviso=RODAPE)
