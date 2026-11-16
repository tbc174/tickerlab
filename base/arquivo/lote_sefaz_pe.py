"""Benefícios fiscais de Pernambuco, do arquivista (linha 578 da fila; Ficha Clara, etapa 4b).

A SEFAZ-PE publica no portal de dados abertos do estado (`dados.pe.gov.br`, CKAN, licença CC BY lida em
03/11/2026) o conjunto `beneficios-fiscais`: um CSV por ano, de 2008 a 2025, com o programa (PRODEPE,
PEAP, "máquinas pesadas"...), o CNPJ, o CACEPE (cadastro estadual) e o prazo de cada benefício. Entra
como incentivo estadual nas conferências por CNPJ, ao lado do REIDI, da CDE e do RDE-IED
(`base/incentivos.py`). Este módulo não importa `fontes.py` (que importa este).

Escolhas (testes em `tests/test_base_arquivo_lote_sefaz_pe.py`):
- **Descoberta pela página, nunca pela API:** o `robots.txt` do portal fecha `/api/` e pede
  `Crawl-Delay: 10` (lido em 05/11/2026). A página do conjunto, que o robots deixa aberta, lista os
  links de download; a fonte leva a pausa de 10 segundos. Um CSV por ano: o JSON do mesmo ano e o
  arquivo de metadados ficam de fora;
- **Só do próprio portal:** link da página é dado, não ordem; baixa-se apenas de `https://dados.pe.gov.br/`
  (link relativo é resolvido, o de outro host ou esquema é ignorado), para a página não mandar o
  arquivista a um endereço interno ou alheio;
- **LGPD (ADR 0088): só pessoa jurídica.** Fica a linha cujo `cnpj` tem 14 caracteres, e a razão social
  (`empresa`) **sai de todas**: firma individual tem o nome da pessoa (o CSV de 2008 traz "JOAO ... CUNHA"),
  e o nome da empresa se lê na Receita pelo CNPJ. Linha com CPF no meio do texto também sai;
- **O formato mudou, a coleta falha:** sem a coluna `cnpj` no cabeçalho, nada é guardado (alguém lê o
  arquivo novo e decide), nunca um arquivo sem filtro. Nunca fica CSV pela metade;
- **O arquivo guardado** sai em UTF-8 com ";" e tudo entre aspas, como o das outras coletas; as datas
  seguem como a fonte escreve ("2010/08/04 00:00:00.000").
"""

import csv
import io
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import IO
from urllib.parse import urljoin

from base.arquivo.coleta import Alvo, Cliente, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import e_cnpj, tem_cpf_no_texto

PORTAL = "https://dados.pe.gov.br"
PACOTE = "beneficios-fiscais"
PAUSA_DO_ROBOTS_EM_SEGUNDOS = 10.0  # Crawl-Delay: 10 (05/11/2026)
MENSAL = "mensal"
SEPARADOR_DA_FONTE = ","
SEPARADOR_GUARDADO = ";"
CODIFICACAO = (
    "utf-8-sig"  # a fonte é UTF-8; o "-sig" tira a marca de ordem de bytes, se houver
)
LIMITE_DO_CAMPO = 1024**2
COLUNA_DO_DOCUMENTO = "cnpj"
COLUNAS_GUARDADAS = ("programa", "cnpj", "cacepe", "termo_inicial", "termo_final")
CSV_DO_ANO = re.compile(r'href="([^"]+/download/[^"/]*\.csv)"', re.IGNORECASE)


def filtrar_csv(origem: IO[bytes], destino: IO[bytes]) -> int:
    """Copia o CSV da fonte só com as `COLUNAS_GUARDADAS` e só com as linhas de CNPJ; devolve quantas.

    Sem a coluna do documento (ou com ela repetida) é erro. Linha com número de colunas diferente do
    cabeçalho sai (não dá para saber qual coluna é qual); linha com CPF em qualquer campo, inclusive
    na razão social, sai antes de a razão social ser descartada.
    """
    csv.field_size_limit(LIMITE_DO_CAMPO)
    leitor = csv.reader(
        io.TextIOWrapper(origem, encoding=CODIFICACAO, newline=""),
        delimiter=SEPARADOR_DA_FONTE,
    )
    saida = io.TextIOWrapper(destino, encoding="utf-8", newline="")
    escritor = csv.writer(
        saida,
        delimiter=SEPARADOR_GUARDADO,
        quoting=csv.QUOTE_ALL,
        lineterminator="\r\n",
    )
    cabecalho = next(leitor, None)
    if cabecalho is None:
        raise ValueError("CSV vazio")
    nomes = [coluna.strip().lower() for coluna in cabecalho]
    if nomes.count(COLUNA_DO_DOCUMENTO) != 1:
        raise ValueError(
            f"coluna {COLUNA_DO_DOCUMENTO!r} {nomes.count(COLUNA_DO_DOCUMENTO)} vezes no cabeçalho"
        )
    mantidas = [i for i, nome in enumerate(nomes) if nome in COLUNAS_GUARDADAS]
    documento = nomes.index(COLUNA_DO_DOCUMENTO)
    escritor.writerow([nomes[i] for i in mantidas])
    ficaram = 0
    for linha in leitor:
        if len(linha) != len(cabecalho):
            continue
        if not e_cnpj(linha[documento]) or tem_cpf_no_texto(linha):
            continue
        escritor.writerow([linha[i] for i in mantidas])
        ficaram += 1
    saida.flush()
    saida.detach()
    return ficaram


def alvo_do_csv(url: str) -> Alvo:
    """O CSV de um ano, baixado e gravado já filtrado (o original nunca fica no acervo)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with bruto.open("rb") as entrada, destino.open("wb") as saida:
                filtrar_csv(entrada, saida)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica CSV pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return Alvo(url, ".csv", obter)


def descobrir(cliente: Cliente, _agora: datetime) -> list[Alvo]:
    """Os CSVs do conjunto, na ordem da página (o ano mais novo primeiro), sem repetir.

    Link da página é dado, não ordem: só se baixa do próprio portal (https, mesmo host); link
    relativo é resolvido contra a página, e o de outro host ou esquema é ignorado.
    """
    endereco_da_pagina = f"{PORTAL}/dataset/{PACOTE}"
    pagina = cliente.ler(endereco_da_pagina).conteudo.decode("utf-8", errors="replace")
    resolvidos = (urljoin(endereco_da_pagina, h) for h in CSV_DO_ANO.findall(pagina))
    enderecos = list(dict.fromkeys(e for e in resolvidos if e.startswith(f"{PORTAL}/")))
    if not enderecos:
        raise ErroDeDescoberta(f"{PACOTE}: nenhum CSV na página do conjunto de dados")
    return [alvo_do_csv(e) for e in enderecos]


def fontes() -> list[Fonte]:
    """A fonte do lote para a lista `FONTES` (o id segue a família: `sefazpe-...`)."""
    return [
        Fonte(
            "sefazpe-beneficios",
            MENSAL,
            descobrir,
            pausa_minima=PAUSA_DO_ROBOTS_EM_SEGUNDOS,
        )
    ]
