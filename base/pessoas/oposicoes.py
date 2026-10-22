"""Oposição do titular (LGPD, art. 18, § 2º; ADR 0106, regra 3.8; ADR 0077, item 2): pedido → lápide → o nome some.

O pedido chega pelo canal de privacidade, como a política promete: o titular diz qual empresa e não precisa
mandar documento. Quem atende acha a pessoa pelo CNPJ da empresa e pelo nome como a Receita publica (a prova
mínima); com homônimo na mesma empresa, pelos 6 dígitos do meio do CPF, os que a Receita já publica. O CPF
inteiro nunca é pedido nem guardado: se vier, só o meio é usado.

Registrar conta o prazo de 15 dias (`prazo_ate`). Daí em diante:
1. a saída já não mostra o nome (`consulta.socios_da_empresa` lê as oposições);
2. `atender` faz a lápide: tira a pessoa de `pessoas` (restrito), troca o `id_pessoa` por vazio no QSA vigente
   e nas mudanças (`base.parquet.regravar_por_lapide`, que anota o dia no manifesto) e marca `atendida_em`;
3. a carga do mês seguinte lê `pessoas_oposicoes` e não traz a pessoa de volta (`ids_opostos`). Uma carga que
   já rodava quando o pedido chegou leu as oposições antes dele e traz a pessoa de volta: `restos` conta esses
   casos (o `conferir` do script acusa) e rodar `atender` de novo limpa.

A tabela de oposições guarda só o id e as datas (prova do atendimento, 5 anos no RIPD) e sobrevive às cargas.
Log só com contagens e o dia: nunca nome, CPF ou id. Não rode `atender` durante a carga mensal.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from base.parquet import VERSAO_GUARDADA, gravar_atomico, regravar_por_lapide
from base.pessoas import chave as chaves
from base.pessoas.tabelas import COLUNAS_DE_OPOSICOES, sem_opostos

log = logging.getLogger(__name__)

COLUNAS = COLUNAS_DE_OPOSICOES
PRAZO = timedelta(days=15)  # política de privacidade e LIA: o nome sai em até 15 dias
ARQUIVO = "pessoas_oposicoes.parquet"
PASTA_DAS_PESSOAS = "pessoas"
TABELAS_COM_PESSOA = ("qsa",)  # onde o `id_pessoa` aparece fora do restrito
TAMANHO_DA_RAIZ = 8
PREFIXO = 2  # a carga reparte pelos 2 primeiros caracteres da raiz
MEIO = re.compile(r"^\d{6}$")


@dataclass(frozen=True)
class Resumo:
    """O que uma rodada de `atender` fez (só contagens)."""

    atendidas: int
    pessoas_tiradas: int
    arquivos_regravados: int


def raiz_do_cnpj(cnpj: str) -> str:
    """Os 8 primeiros caracteres do CNPJ (aceita pontuado, só a raiz e o alfanumérico de 2026)."""
    limpo = re.sub(r"[^0-9A-Za-z]", "", cnpj).upper()
    if len(limpo) < TAMANHO_DA_RAIZ:
        raise ValueError("CNPJ curto demais: precisa ao menos da raiz (8 posições)")
    return limpo[:TAMANHO_DA_RAIZ]


def meio_do_cpf(valor: str) -> str:
    """Os 6 dígitos do meio, de `982247`, `***982247**` ou do CPF inteiro (que não é guardado)."""
    texto = valor.strip()
    if MEIO.match(texto):
        return texto
    return chaves.mascarar_cpf(texto)[3:9]


def pessoas_da_raiz(restrita: Path, raiz: str) -> pd.DataFrame:
    pasta = restrita / PASTA_DAS_PESSOAS / raiz[:PREFIXO]
    arquivos = sorted(pasta.glob("*.parquet")) if pasta.is_dir() else []
    if not arquivos:
        return pd.DataFrame(
            columns=["id_pessoa", "cnpj_basico", "nome", "cpf_mascarado"]
        )
    tabela = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    return tabela[tabela["cnpj_basico"] == raiz]


def achar_titular(restrita: Path, cnpj: str, nome: str, meio: str | None) -> list[str]:
    """Os `id_pessoa` de quem tem esse nome no quadro dessa empresa (com `meio`, só quem tem esse CPF)."""
    pessoas = pessoas_da_raiz(restrita, raiz_do_cnpj(cnpj))
    alvo = chaves.normalizar_nome(nome)
    achados = pessoas[pessoas["nome"].map(chaves.normalizar_nome) == alvo]
    if meio is not None:
        achados = achados[achados["cpf_mascarado"].str[3:9] == meio_do_cpf(meio)]
    return sorted(set(achados["id_pessoa"]))


def ler(restrita: Path) -> pd.DataFrame:
    """A tabela de oposições (vazia, com as colunas, antes do primeiro pedido)."""
    arquivo = restrita / ARQUIVO
    if not arquivo.is_file():
        return pd.DataFrame(columns=list(COLUNAS))
    return pd.read_parquet(arquivo)


def _gravar(restrita: Path, tabela: pd.DataFrame) -> None:
    restrita.mkdir(parents=True, exist_ok=True)
    gravar_atomico(
        restrita / ARQUIVO,
        lambda caminho: tabela.astype(object).to_parquet(caminho, index=False),
    )


def ids_opostos(restrita: Path) -> set[str]:
    """Todo id com oposição registrada, atendida ou não: entrada da carga e da saída."""
    return set(ler(restrita)["id_pessoa"])


def registrar(restrita: Path, ids: list[str], pedido_em: date) -> int:
    """Registra o pedido com o prazo de 15 dias; pedido repetido não reabre o prazo. Devolve os novos."""
    registro = ler(restrita)
    novos = [i for i in ids if i not in set(registro["id_pessoa"])]
    if novos:
        linhas = pd.DataFrame(
            {
                "id_pessoa": novos,
                "pedido_em": [pedido_em] * len(novos),
                "prazo_ate": [pedido_em + PRAZO] * len(novos),
                "atendida_em": [None] * len(novos),
            }
        )
        registro = pd.concat([registro.astype(object), linhas], ignore_index=True)
        _gravar(restrita, registro)
    log.info("oposição: %d pedido(s) novo(s) em %s", len(novos), pedido_em)
    return len(novos)


def pendentes(restrita: Path) -> pd.DataFrame:
    registro = ler(restrita)
    return registro[registro["atendida_em"].isna()]


def vencidas(restrita: Path, hoje: date) -> int:
    """Quantas oposições ainda sem lápide passaram do prazo (a LIA manda rever a base se houver uma)."""
    return int((pendentes(restrita)["prazo_ate"] < hoje).sum())


def restos(restrita: Path) -> int:
    """Linhas no restrito de quem já teve a lápide: a carga que rodava durante o pedido trouxe de volta."""
    registro = ler(restrita)
    atendidos = set(registro.loc[registro["atendida_em"].notna(), "id_pessoa"])
    pasta = restrita / PASTA_DAS_PESSOAS
    arquivos = sorted(pasta.rglob("*.parquet")) if atendidos and pasta.is_dir() else []
    return sum(
        int(
            pd.read_parquet(a, columns=["id_pessoa"])["id_pessoa"].isin(atendidos).sum()
        )
        for a in arquivos
    )


def _tirar_do_restrito(restrita: Path, ids: set[str]) -> int:
    tiradas = 0
    for arquivo in sorted((restrita / PASTA_DAS_PESSOAS).rglob("*.parquet")):
        tabela = pd.read_parquet(arquivo)
        restante = sem_opostos(tabela, ids)
        if len(restante) == len(tabela):
            continue
        tiradas += len(tabela) - len(restante)
        gravar_atomico(
            arquivo, lambda caminho, t=restante: t.to_parquet(caminho, index=False)
        )
    return tiradas


def _regravar_tabelas(pasta: Path, ids: set[str], dia: date) -> int:
    regravados = 0
    for tabela in TABELAS_COM_PESSOA:
        for parte in ("vigente", "mudancas"):
            for arquivo in sorted((pasta / parte / tabela).glob("*.parquet")):
                if VERSAO_GUARDADA.search(arquivo.stem):
                    continue  # a versão guardada é regravada junto com a vigente dela
                regravados += len(regravar_por_lapide(arquivo, ids, dia.isoformat()))
    return regravados


def atender(pasta: Path, restrita: Path, dia: date) -> Resumo:
    """A lápide de todas as oposições (idempotente) e o dia do atendimento nas que esperavam."""
    registro = ler(restrita)
    ids = set(registro["id_pessoa"])
    tiradas = _tirar_do_restrito(restrita, ids) if ids else 0
    regravados = _regravar_tabelas(pasta, ids, dia) if ids else 0
    esperando = registro["atendida_em"].isna()
    if esperando.any():
        registro = registro.astype(object)
        registro.loc[esperando, "atendida_em"] = dia
        _gravar(restrita, registro)
    resumo = Resumo(int(esperando.sum()), tiradas, regravados)
    log.info(
        "lápide de %s: %d atendida(s), %d pessoa(s) tirada(s), %d arquivo(s) regravado(s)",
        dia,
        resumo.atendidas,
        resumo.pessoas_tiradas,
        resumo.arquivos_regravados,
    )
    return resumo
