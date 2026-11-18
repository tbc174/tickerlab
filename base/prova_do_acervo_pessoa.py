"""Prova por máquina, só com contagens, de que `socios_pf/`, `individuais/` e o `manifesto.json` do
`acervo_pessoa/` não levam CPF, menor de idade, endereço, telefone nem e-mail (ADR 0128, Emenda 4).

É a conferência que acompanha a pasta antes de ela sair da VM de casa (`scripts/montar_acervo_pessoa.py
--conferir`). Lê um arquivo por vez e devolve só números: nenhum nome, valor ou linha sai daqui.

O que se conta, por tabela:
- colunas fora das que a montagem grava (uma coluna de CPF ou de endereço que aparecesse);
- onze dígitos, juntos ou separados por pontuação, no nome (CPF em qualquer forma, válido ou não);
- CPF formatado ou mascarado, CPF válido só com dígitos, e e-mail no nome (`src/pessoa_no_texto.py`);
- telefone e CEP no nome;
- qualificação de menor, de incapaz ou de quem representa (`base/receita_pessoa.py`): a faixa etária não é
  gravada, então o "zero menor" se prova pela qualificação aqui e pelos descartes do manifesto;
- raiz que não tem 8 dígitos e `id_pessoa` que não é o pseudônimo de 32 letras hexadecimais.

No manifesto: texto com cara de pessoa (CPF, e-mail ou telefone) em qualquer chave ou valor, origem que não
seja um `*.zip` com o SHA-256 dele, a falta da marca do corte do contato e um corte obrigatório que veio vazio
(um corte zerado num mês real é sinal de que o layout da Receita mudou sem a montagem perceber).
"""

import json
import re
from pathlib import Path

import pandas as pd

from base import receita_individuais, receita_pessoa
from base.pessoas.chave import TAMANHO_DO_ID
from base.receita_contato import CONTATO_DE_PESSOA, ONZE_DIGITOS_SEPARADOS
from src.pessoa_no_texto import telefone_no_texto, texto_de_pessoa

MES = "mes_do_retrato"
SOCIOS = "socios_pf"
INDIVIDUAIS = "individuais"
MANIFESTO = "manifesto.json"
CORTES = "cortes_do_contato"
# num mês real há milhões de MEI e de sociedades de um sócio só: zero aqui é defeito, não dado. A EIRELI fica de
# fora: foi extinta pela Lei 14.195/2021 (art. 41), e zero pode ser verdade.
CORTES_OBRIGATORIOS = ("mei_do_simples", "quadro_de_um_socio")
COLUNAS = {
    SOCIOS: frozenset({*receita_pessoa.COLUNAS_COM_ID, MES}),
    INDIVIDUAIS: frozenset({*receita_individuais.COLUNAS, MES}),
}
COLUNA_DO_NOME = {SOCIOS: "nome_socio", INDIVIDUAIS: "titular"}
QUALIFICACOES_PROIBIDAS = (
    receita_pessoa.QUALIFICACOES_DE_MENOR_OU_INCAPAZ
    | receita_pessoa.QUALIFICACOES_DE_QUEM_REPRESENTA
)
CEP = r"(?<!\d)\d{5}-?\d{3}(?!\d)"
RAIZ = r"\d{8}"
ID_PESSOA = rf"[0-9a-f]{{{TAMANHO_DO_ID}}}"
ORIGEM = re.compile(r"[A-Za-z]+\d*\.zip")
SHA256 = re.compile(r"[0-9a-f]{64}")
ACHADOS = (
    "colunas_fora_do_esperado",
    "onze_digitos",
    "cpf_ou_email",
    "telefone",
    "cep",
    "menor_ou_representante",
    "cnpj_basico_fora_do_formato",
    "id_pessoa_fora_do_formato",
)
ACHADOS_DO_MANIFESTO = (
    "textos_com_cara_de_pessoa",
    "origens_fora_do_formato",
    "sem_a_marca_do_corte",
    "corte_do_contato_vazio",
)


def _texto(coluna: pd.Series) -> pd.Series:
    return coluna.fillna("").astype(str)


def _contar_no_nome(nome: pd.Series) -> dict[str, int]:
    """Só o nome que tem dígito ou arroba passa pelas buscas lentas: nome de gente quase nunca tem."""
    suspeito = nome[nome.str.contains(r"[\d@]", regex=True)]
    return {
        "onze_digitos": int(
            suspeito.str.contains(ONZE_DIGITOS_SEPARADOS, regex=True).sum()
        ),
        "cpf_ou_email": sum(map(texto_de_pessoa, suspeito)),
        "telefone": sum(map(telefone_no_texto, suspeito)),
        "cep": int(suspeito.str.contains(CEP, regex=True).sum()),
    }


def _fora_do_formato(linhas: pd.DataFrame, coluna: str, formato: str) -> int:
    if coluna not in linhas:
        return len(linhas)
    return int((~_texto(linhas[coluna]).str.fullmatch(formato)).sum())


def contar_arquivo(linhas: pd.DataFrame, tabela: str) -> dict[str, int]:
    """Os achados de um arquivo de `socios_pf` ou `individuais`, só em números."""
    contagem = dict.fromkeys(ACHADOS, 0)
    contagem["colunas_fora_do_esperado"] = len(set(linhas.columns) - COLUNAS[tabela])
    contagem |= _contar_no_nome(
        _texto(linhas.get(COLUNA_DO_NOME[tabela], pd.Series(dtype=str)))
    )
    if "qualificacao" in linhas:
        qualificacao = _texto(linhas["qualificacao"]).str.strip().str.zfill(2)
        contagem["menor_ou_representante"] = int(
            qualificacao.isin(QUALIFICACOES_PROIBIDAS).sum()
        )
    contagem["cnpj_basico_fora_do_formato"] = _fora_do_formato(
        linhas, "cnpj_basico", RAIZ
    )
    contagem["id_pessoa_fora_do_formato"] = _fora_do_formato(
        linhas, "id_pessoa", ID_PESSOA
    )
    return contagem


def contar_tabela(pasta: Path) -> dict[str, int]:
    """Soma os achados de todos os arquivos da tabela, lendo um por vez; `arquivos` 0 é pasta ausente."""
    total = {"arquivos": 0, "linhas": 0, **dict.fromkeys(ACHADOS, 0)}
    for arquivo in sorted(pasta.glob("*.parquet")) if pasta.is_dir() else ():
        linhas = pd.read_parquet(arquivo)
        total["arquivos"] += 1
        total["linhas"] += len(linhas)
        for achado, quantos in contar_arquivo(linhas, pasta.name).items():
            total[achado] += quantos
    return total


def _textos(valor: object) -> list[str]:
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        return [
            t for chave, item in valor.items() for t in (str(chave), *_textos(item))
        ]
    if isinstance(valor, list):
        return [t for item in valor for t in _textos(item)]
    return []


def contar_manifesto(caminho: Path) -> dict[str, int] | None:
    """Os achados do `manifesto.json` (None se ele não existe). As origens são conferidas pelo formato
    (nome do ZIP e SHA-256) e ficam fora da busca de texto, porque um SHA-256 pode ter 11 dígitos seguidos."""
    if not caminho.is_file():
        return None
    manifesto = json.loads(caminho.read_text(encoding="utf-8"))
    origens = manifesto.get("origens", {})
    resto = {chave: valor for chave, valor in manifesto.items() if chave != "origens"}
    textos = [*_textos(resto), *(str(nome) for nome in origens)]
    return {
        "textos_com_cara_de_pessoa": sum(
            texto_de_pessoa(t) or telefone_no_texto(t) for t in textos
        ),
        "origens_fora_do_formato": sum(
            not (ORIGEM.fullmatch(str(nome)) and SHA256.fullmatch(str(sha)))
            for nome, sha in origens.items()
        ),
        "sem_a_marca_do_corte": int(
            CONTATO_DE_PESSOA not in manifesto.get("descartes", {})
        ),
        "corte_do_contato_vazio": _cortes_vazios(manifesto.get(CORTES)),
    }


def _cortes_vazios(cortes: object) -> int:
    """Quantos cortes obrigatórios faltam ou vieram com zero raiz (todos, se o manifesto não tem a chave)."""
    if not isinstance(cortes, dict):
        return len(CORTES_OBRIGATORIOS)
    return sum(
        not (isinstance(cortes.get(nome), int) and cortes[nome] > 0)
        for nome in CORTES_OBRIGATORIOS
    )


def conferir(acervo_pessoa: Path) -> tuple[dict, list[str]]:
    """A prova inteira (só números) e a lista de falhas, cada uma `tabela.achado`; lista vazia é aprovado."""
    prova: dict = {
        tabela: contar_tabela(acervo_pessoa / tabela)
        for tabela in (SOCIOS, INDIVIDUAIS)
    }
    falhas = [
        f"{tabela}.{achado}"
        for tabela in (SOCIOS, INDIVIDUAIS)
        for achado in ACHADOS
        if prova[tabela][achado]
    ]
    falhas += [
        f"{tabela}.ausente"
        for tabela in (SOCIOS, INDIVIDUAIS)
        if not prova[tabela]["arquivos"]
    ]
    do_manifesto = contar_manifesto(acervo_pessoa / MANIFESTO)
    if do_manifesto is None:
        falhas.append(f"{MANIFESTO}.ausente")
    else:
        prova[MANIFESTO] = do_manifesto
        falhas += [
            f"{MANIFESTO}.{achado}"
            for achado, quantos in do_manifesto.items()
            if quantos
        ]
    return prova, falhas
