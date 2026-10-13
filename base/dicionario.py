"""Dicionário de dados da base de ML (série 1, PR 8; ADR 0027, exigência 8).

Um lugar só para dizer o que é cada tabela e cada coluna da base: descrição, unidade, de onde vem,
sob que licença, com que frequência muda e quanto atrasa em relação ao fato. O documento que o Tiago
revisa (`docs/dicionario-da-base.md`) é gerado daqui (`python -m base.dicionario`), e há teste que
reclama de coluna nova sem descrição e de documento desatualizado.
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.banco.coletas import licenca_da_fonte

ARQUIVO_DO_DOCUMENTO = "docs/dicionario-da-base.md"
TEXTO = "texto"
DATA = "data (dia)"
MOMENTO = "data e hora (UTC)"
REAIS = "reais (R$), já multiplicado pela escala informada"


@dataclass(frozen=True)
class Tabela:
    descricao: str
    fonte: str
    familia_da_fonte: (
        str  # a família em `src/banco/coletas.py::LICENCAS` (a licença vem de lá)
    )
    frequencia: str
    atraso: str
    onde: str
    colunas: dict[str, tuple[str, str]] = field(
        default_factory=dict
    )  # nome → (descrição, unidade)


_EMPRESA = {
    "cnpj": ("CNPJ da companhia, no formato 00.000.000/0000-00", TEXTO),
    "empresa": ("Nome da companhia como a fonte informa", TEXTO),
}
_DOCUMENTO = {
    "documento": ("DFP (demonstrações anuais) ou ITR (informações trimestrais)", TEXTO),
    "referencia": (
        "Data a que o documento se refere (fim do exercício ou do trimestre)",
        DATA,
    ),
}

TABELAS: dict[str, Tabela] = {
    "demonstracoes_como_era": Tabela(
        descricao=(
            "Uma linha por valor diferente que cada conta de cada período já teve (versão 1, "
            "reapresentações e o balanço seguinte refazendo o ano anterior), com o dia em que "
            "ficou público e o dia em que foi trocado. `como_era_em(base, data)` dá a foto."
        ),
        fonte=(
            "CVM: dados abertos de DFP e ITR (versão mais nova) e ENET (versões anteriores, "
            "XML de cada entrega)"
        ),
        familia_da_fonte="cvm",
        frequencia=(
            "Diária no servidor de casa (carga do ENET às 0h30); a base é remontada por ano"
        ),
        atraso=(
            "DFP: até 3 meses depois do fim do exercício; ITR: até 45 dias depois do trimestre "
            "(prazos da CVM, `src/prazos.py`); reapresentações a qualquer momento"
        ),
        onde="Parquet por ano em `<acervo>/base/demonstracoes/<ano>.parquet` (servidor de casa)",
        colunas={
            **_EMPRESA,
            "grupo": ("con (consolidado) ou ind (individual)", TEXTO),
            "demonstracao": (
                "BPA (ativo), BPP (passivo e patrimônio) ou DRE (resultado)",
                TEXTO,
            ),
            "conta": ("Código da conta no plano da CVM (1, 1.01, 3.01...)", TEXTO),
            "descricao": ("Nome da conta como a empresa informou", TEXTO),
            "inicio": (
                "Começo do período (vazio no balanço, que é um saldo numa data)",
                DATA,
            ),
            "fim": ("Fim do período ou data do saldo", DATA),
            "valor": ("Valor da conta; vazio quando a empresa deixou em branco", REAIS),
            **_DOCUMENTO,
            "versao": (
                "Versão do documento que publicou este valor (1, 2, 3...)",
                "número",
            ),
            "ordem": (
                "ultimo (período do próprio documento) ou penultimo (o ano anterior, refeito)",
                TEXTO,
            ),
            "origem": ("dados_abertos ou enet", TEXTO),
            "divulgado_em": (
                "Dia da entrega à CVM (vale a partir dele, inclusive; a CVM não informa a hora)",
                DATA,
            ),
            "ate": (
                "Dia em que outro valor tomou o lugar (vazio: vale até hoje)",
                DATA,
            ),
        },
    ),
    "achados_de_qualidade": Tabela(
        descricao=(
            'Os achados das regras fixas do selo "dado em conferência" (R1 a R11, '
            "`base/regras.py`): o número que chamou a atenção, o esperado e o porquê. Achado que "
            "some é fechado, nunca apagado."
        ),
        fonte="CVM: dados abertos de DFP e ITR, cadastro e eventos do IPE",
        familia_da_fonte="cvm",
        frequencia="Diária no VPS (tarefa `qualidade-cvm` às 8h15)",
        atraso="O do documento conferido; `valido_desde` diz desde quando o achado existe",
        onde="Tabela `achados_de_qualidade` do banco do app (VPS), migração 0026",
        colunas={
            "id": ("Identificador da linha", "UUID"),
            "regra": ("Regra que apontou (R1 a R11)", TEXTO),
            "cnpj": _EMPRESA["cnpj"],
            **_DOCUMENTO,
            "grupo": (
                "con, ind ou vazio (regras que olham o documento inteiro)",
                TEXTO,
            ),
            "conta": ("Conta apontada, ou vazio", TEXTO),
            "valor": ("O número publicado (na R8, os dias de atraso)", "reais ou dias"),
            "valor_esperado": ("O que a regra esperava encontrar", "reais ou dias"),
            "porque": ("Frase em português que o selo mostra", TEXTO),
            "versao_das_regras": ("Versão das regras que calculou", TEXTO),
            "valido_desde": (
                "Desde quando a informação existia (a entrega do documento)",
                MOMENTO,
            ),
            "calculado_em": ("Quando a tarefa gravou ou atualizou o achado", MOMENTO),
            "fechado_em": (
                "Quando o achado sumiu numa rodada nova (vazio: aberto)",
                MOMENTO,
            ),
        },
    ),
    "cadastro_das_companhias": Tabela(
        descricao=(
            "Cada registro de companhia aberta na CVM, inclusive as que saíram, com a data e o "
            "motivo (sem viés de sobrevivência, ADR 0027, exigência 4)"
        ),
        fonte="CVM: cadastro de companhias abertas (`cad_cia_aberta.csv`)",
        familia_da_fonte="cvm",
        frequencia="Diária (a CVM atualiza o arquivo todo dia útil)",
        atraso="Dias, entre o ato (registro ou cancelamento) e a publicação",
        onde="Lido do acervo quando preciso (`base/cadastro.py::ler_cadastro`)",
        colunas={
            **_EMPRESA,
            "registro": ("Data do registro na CVM", DATA),
            "cancelamento": ("Data do cancelamento (vazio: ativa)", DATA),
            "motivo_cancelamento": (
                "Motivo informado pela CVM (voluntário, de ofício...)",
                TEXTO,
            ),
            "situacao": ("Situação do registro (ATIVO, CANCELADA...)", TEXTO),
            "setor": ("Setor de atividade informado à CVM", TEXTO),
        },
    ),
    "tickers_no_tempo": Tabela(
        descricao=(
            "Cada código de ação da B3 (bolsa) com a empresa e o período em que existiu, juntando "
            "todos os anos do formulário cadastral (FCA): código que sumiu continua aqui"
        ),
        fonte="CVM: formulário cadastral (FCA), valores mobiliários",
        familia_da_fonte="cvm",
        frequencia="Anual (o FCA é entregue até 31/05) e a cada alteração",
        atraso="Até meses: a empresa atualiza o FCA quando muda algo",
        onde="Lido do acervo quando preciso (`base/cadastro.py::tickers_no_tempo`)",
        colunas={
            "codigo": ("Código de negociação na B3 (PETR4, TAEE11)", TEXTO),
            **_EMPRESA,
            "valor_mobiliario": (
                "Tipo do papel (ações ordinárias, preferenciais, units)",
                TEXTO,
            ),
            "primeiro_visto": ("Data do primeiro FCA em que o código apareceu", DATA),
            "ultimo_visto": ("Data do último FCA em que o código apareceu", DATA),
            "inicio_negociacao": ("Início da negociação informado pela empresa", DATA),
            "fim_negociacao": (
                "Fim da negociação informado (vazio: ainda negociado)",
                DATA,
            ),
        },
    ),
}


def _tabela_em_markdown(nome: str, tabela: Tabela) -> list[str]:
    linhas = [
        f"## `{nome}`",
        "",
        tabela.descricao,
        "",
        f"- **Fonte:** {tabela.fonte}",
        f"- **Licença:** {licenca_da_fonte(tabela.familia_da_fonte)}",
        f"- **Frequência:** {tabela.frequencia}",
        f"- **Atraso de divulgação:** {tabela.atraso}",
        f"- **Onde fica:** {tabela.onde}",
        "",
        "| Coluna | O que é | Unidade |",
        "|---|---|---|",
    ]
    linhas += [f"| `{c}` | {d} | {u} |" for c, (d, u) in tabela.colunas.items()]
    return [*linhas, ""]


def documento_em_markdown() -> str:
    linhas = [
        "# Dicionário de dados da base de ML",
        "",
        "Gerado por `python -m base.dicionario` a partir de `base/dicionario.py` (não edite à mão).",
        "Exigência 8 do critério de pronto da base (ADR 0027 do autor): para cada tabela, unidade,",
        "frequência, atraso de divulgação, fonte e licença.",
        "",
    ]
    for nome, tabela in TABELAS.items():
        linhas += _tabela_em_markdown(nome, tabela)
    return "\n".join(linhas).rstrip("\n") + "\n"


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent.parent / ARQUIVO_DO_DOCUMENTO
    # fim de linha LF também no Windows: o teste compara com o mesmo texto no Linux do CI
    destino.write_text(documento_em_markdown(), encoding="utf-8", newline="\n")
    print(f"dicionário gravado em {destino}")
