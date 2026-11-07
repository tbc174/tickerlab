"""Ordem cronológica de pagamentos de Pernambuco e do Espírito Santo, do arquivista (linha 755 da fila).

Os dois estados publicam, em CKAN de dados abertos com licença CC BY (lida em 06/11/2026), a lista
dos pagamentos a fornecedores com o CNPJ do credor, a data em que a despesa foi liquidada (o estado
reconheceu a dívida) e a data em que pagou. O intervalo entre as duas é o prazo real de pagamento do
governo: o sinal que o motor de risco de cedente e sacado (linha 754) usa para duplicata de órgão
público. Pernambuco: `dados.pe.gov.br`, um CSV do ano, com o nome do dia (`..._2026_06112026.csv`);
Espírito Santo: `dados.es.gov.br`, um CSV por ano (`ordemcronologicapagamentos-2025.csv`, 80 a 200 MB).

Escolhas (testes em `tests/test_base_arquivo_lote_ordem_cronologica.py`):
- **Descoberta pela página, nunca pela API:** os `robots.txt` dos dois portais fecham `/api/` e pedem
  `Crawl-Delay: 10` (lidos em 06/11/2026); a página do conjunto, que o robots deixa aberta, lista os
  links de download, e a fonte leva a pausa de 10 segundos. O JSON do mesmo ano e os metadados ficam de
  fora (só o CSV);
- **Só do próprio portal:** link da página é dado, não ordem; baixa-se apenas do host do portal (link
  relativo é resolvido, o de outro host ou esquema é ignorado). O de ES responde com um redirecionamento
  para o armazenamento do estado, que o cliente segue;
- **LGPD (ADR 0075 e 0088): só pessoa jurídica.** Fica a linha cujo documento do credor é um CNPJ, e
  **saem de todas** o nome do credor (firma individual leva o nome da pessoa), a descrição do empenho, o
  objeto do contrato e as justificativas (texto livre). Linha com CPF em qualquer campo, inclusive no
  texto livre, sai inteira antes de o texto ser descartado;
- **O formato mudou, a coleta falha:** sem a coluna do documento (ou com ela repetida) no cabeçalho,
  nada é guardado (alguém lê o arquivo novo e decide), nunca um arquivo sem filtro. Nunca fica CSV pela
  metade, e o original (200 MB) nunca fica no acervo, só o filtrado (alguns MB);
- **O arquivo guardado** sai em UTF-8 com ";" e tudo entre aspas, como o das outras coletas; datas e
  valores seguem como a fonte escreve (a leitura, em `base/ordem_cronologica.py`, os converte).
"""

import csv
import io
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO
from urllib.parse import urljoin

from base.arquivo.coleta import Alvo, Cliente, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import tem_cpf_no_texto
from base.arquivo.obter import tem_cnpj_inteiro

MENSAL = "mensal"
PAUSA_DO_ROBOTS_EM_SEGUNDOS = 10.0  # Crawl-Delay: 10 nos dois portais (06/11/2026)
SEPARADOR_DA_FONTE = ";"
SEPARADOR_GUARDADO = ";"
CODIFICACAO = "utf-8-sig"  # as fontes são UTF-8; o "-sig" tira a marca de ordem de bytes, se houver
LIMITE_DO_CAMPO = 1024**2
CSV_DO_PORTAL = re.compile(r'href="([^"]+/download/[^"/]*\.csv)"', re.IGNORECASE)


@dataclass(frozen=True)
class Formato:
    """Onde está o conjunto de dados de um estado e quais colunas dele ficam no acervo."""

    id: str  # id da fonte no registro de coletas ("família-detalhe")
    portal: str
    pacote: str
    documento: str  # a coluna do CNPJ do credor (nome em minúsculas)
    guardadas: tuple[
        str, ...
    ]  # colunas que ficam (em minúsculas); o nome do credor nunca


# Pernambuco: `cnpj` e `cpf` são colunas separadas (a de CPF fica vazia nas linhas de empresa); o nome
# do credor, a justificativa de priorização e de suspensão e a observação são texto livre e não ficam.
PERNAMBUCO = Formato(
    id="sefazpe-ordem-cronologica",
    portal="https://dados.pe.gov.br",
    pacote="cronograma-de-pagamentos",
    documento="cnpj",
    guardadas=(
        "descicao_unidade_gestora",
        "codigo_ug",
        "cnpj",
        "numero_empenho",
        "numero_documento",
        "categoria_contrato",
        "numero_ordem_bancaria",
        "data_liquidacao",
        "data_ordem_bancaria",
        "data_pagamento",
        "valor_documento",
        "valor_liquido_pagamento",
    ),
)
# Espírito Santo: `Credor` é o documento (14 dígitos, sem máscara, para empresa); o nome do credor, a
# descrição do empenho, o nome e o objeto do contrato são texto livre e não ficam.
ESPIRITO_SANTO = Formato(
    id="esdados-ordem-cronologica",
    portal="https://dados.es.gov.br",
    pacote="portal-da-transparencia-contratos-ordem-cronologica-de-pagamentos",
    documento="credor",
    guardadas=(
        "codigoug",
        "unidadegestora",
        "nomecategoriacontrato",
        "datacronologica",
        "credor",
        "codigone",
        "codigonl",
        "dataemissaonl",
        "dataemissaoob",
        "codigoob",
        "valorob",
    ),
)
FORMATOS = (PERNAMBUCO, ESPIRITO_SANTO)


def filtrar_csv(origem: IO[bytes], destino: IO[bytes], formato: Formato) -> int:
    """Copia o CSV da fonte só com as colunas do `formato` e só com as linhas de CNPJ; devolve quantas.

    Sem a coluna do documento (ou com ela repetida) é erro. Linha com número de colunas diferente do
    cabeçalho sai (não dá para saber qual coluna é qual); linha com CPF em qualquer campo, inclusive
    no texto livre, sai antes de o texto ser descartado.
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
    if nomes.count(formato.documento) != 1:
        raise ValueError(
            f"coluna {formato.documento!r} {nomes.count(formato.documento)} vezes no cabeçalho"
        )
    mantidas = [i for i, nome in enumerate(nomes) if nome in formato.guardadas]
    documento = nomes.index(formato.documento)
    escritor.writerow([nomes[i] for i in mantidas])
    ficaram = 0
    for linha in leitor:
        if len(linha) != len(cabecalho):
            continue
        if not tem_cnpj_inteiro(linha[documento].strip()) or tem_cpf_no_texto(linha):
            continue
        escritor.writerow([linha[i] for i in mantidas])
        ficaram += 1
    saida.flush()
    saida.detach()
    return ficaram


def alvo_do_csv(url: str, formato: Formato) -> Alvo:
    """O CSV de um estado, baixado e gravado já filtrado (o original nunca fica no acervo)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with bruto.open("rb") as entrada, destino.open("wb") as saida:
                filtrar_csv(entrada, saida, formato)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica CSV pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return Alvo(url, ".csv", obter)


def descobrir_em(cliente: Cliente, formato: Formato) -> list[Alvo]:
    """Os CSVs do conjunto, na ordem da página, sem repetir.

    Link da página é dado, não ordem: só se baixa do próprio portal (https, mesmo host); link
    relativo é resolvido contra a página, e o de outro host ou esquema é ignorado.
    """
    endereco_da_pagina = f"{formato.portal}/dataset/{formato.pacote}"
    pagina = cliente.ler(endereco_da_pagina).conteudo.decode("utf-8", errors="replace")
    resolvidos = (urljoin(endereco_da_pagina, h) for h in CSV_DO_PORTAL.findall(pagina))
    enderecos = list(
        dict.fromkeys(e for e in resolvidos if e.startswith(f"{formato.portal}/"))
    )
    if not enderecos:
        raise ErroDeDescoberta(f"{formato.pacote}: nenhum CSV na página do conjunto")
    return [alvo_do_csv(e, formato) for e in enderecos]


def descobrir_o_pe(cliente: Cliente, _agora: datetime) -> list[Alvo]:
    return descobrir_em(cliente, PERNAMBUCO)


def descobrir_o_es(cliente: Cliente, _agora: datetime) -> list[Alvo]:
    return descobrir_em(cliente, ESPIRITO_SANTO)


def fontes() -> list[Fonte]:
    """As fontes do lote para a lista `FONTES` (o id segue a família: `sefazpe-...`, `esdados-...`)."""
    return [
        Fonte(
            PERNAMBUCO.id,
            MENSAL,
            descobrir_o_pe,
            pausa_minima=PAUSA_DO_ROBOTS_EM_SEGUNDOS,
        ),
        Fonte(
            ESPIRITO_SANTO.id,
            MENSAL,
            descobrir_o_es,
            pausa_minima=PAUSA_DO_ROBOTS_EM_SEGUNDOS,
        ),
    ]
