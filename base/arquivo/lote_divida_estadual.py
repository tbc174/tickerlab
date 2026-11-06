"""Dívida ativa estadual do arquivista (linha 755 da fila; motor de risco cedente/sacado, linha 754).

Os estados que publicam a lista de devedores em arquivo, não só em tela. Entra primeiro o **Paraná**
(Sefa-PR, `listadevedores.sefa.pr.gov.br`): a aba "Arquivo" do Portal do Devedor oferece um ZIP gerado
todo dia com um CSV de todos os débitos inscritos (ICMS, IPVA, taxas...), de pessoa física e jurídica.
Minas Gerais (SEF-MG, `.xlsb`) entra no mesmo módulo no PR seguinte. Este módulo não importa
`fontes.py` (que importa este).

Escolhas (testes em `tests/test_base_arquivo_lote_divida_estadual.py`):
- **LGPD (ADR 0075 e 0088): só pessoa jurídica.** Fica a linha cujo `CNPJ` tem 14 caracteres entre
  dígitos e `*`; CPF, linha sem documento e linha com CPF no meio do nome ou na coluna `CPF` saem. As
  colunas `CPF` e `Nome/razão social` **saem de todas as linhas** (firma individual e MEI têm o nome da
  pessoa na razão social; o nome de empresa se lê na Receita pelo CNPJ). O empresário individual que
  fica, sem CPF no nome, é marcado `trata_como_pessoa` na tabela (`base/divida_estadual.py`);
- **Descoberta pela página:** o ZIP muda de nome todo dia (`lista-devedores-pr_DD-MM-AAAA_HH_MM.zip`); o
  link está no HTML de `/portal-devedor/arquivo`. Link da página é dado, não ordem: só se baixa do
  próprio portal (https, mesmo host). O site não tem `robots.txt` (404 em 06/11/2026) nem termos de uso
  escritos para a lista: a licença fica **a confirmar** (ADR 0102, Emenda 2) e a fonte é citada;
- **O formato mudou, a coleta falha:** ZIP sem exatamente um CSV, ou CSV sem as colunas esperadas,
  guarda nada (alguém lê o arquivo novo e decide), nunca um arquivo sem filtro. Nunca fica CSV pela
  metade;
- **O arquivo guardado** sai em UTF-8 com ";" e tudo entre aspas, como o das outras coletas; datas e
  valores seguem como a fonte escreve ("18/06/1973", "1787.10" com ponto decimal).
"""

import csv
import io
import re
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import IO
from urllib.parse import urljoin

from base.arquivo.coleta import Alvo, Cliente, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import e_cnpj, tem_cpf_no_texto

SEMANAL = "semanal"
SEPARADOR_GUARDADO = ";"
CODIFICACAO = "utf-8-sig"  # o "-sig" tira a marca de ordem de bytes, se houver
LIMITE_DO_CAMPO = 1024**2

# ---- Paraná (Sefa-PR) ----
PORTAL_DO_PR = "https://listadevedores.sefa.pr.gov.br"
PAGINA_DO_PR = f"{PORTAL_DO_PR}/portal-devedor/arquivo"
ZIP_DO_PR = re.compile(r'href="([^"]+/download/csv/[^"/]*\.zip)"', re.IGNORECASE)
COLUNA_DO_CNPJ_NO_PR = "CNPJ"
COLUNAS_DE_PESSOA_NO_PR = ("CPF", "Nome/razão social")
# o que a coleta guarda, na ordem da fonte (as duas colunas de pessoa não entram)
COLUNAS_GUARDADAS_NO_PR = (
    "Dívida ativa",
    "Data da inscrição do débito",
    "Data da atualização",
    "Valor do imposto",
    "Valor da multa",
    "Valor dos juros",
    "Valor total",
    "Tipo do crédito",
    COLUNA_DO_CNPJ_NO_PR,
    "Suspensão de exigibilidade",
    "Indicativo de garantia",
    "Indicativo de parcelamento ativo",
)


def filtrar_csv_do_pr(origem: IO[bytes], destino: IO[bytes]) -> int:
    """Copia o CSV do Paraná só com as `COLUNAS_GUARDADAS_NO_PR` e só com as linhas de CNPJ.

    Devolve quantas linhas ficaram. Falta de coluna esperada (a fonte mudou de formato), ou coluna
    repetida, é erro. Linha com número de colunas diferente do cabeçalho sai (não dá para saber qual
    coluna é qual); linha com CPF na coluna `CPF` ou no meio do nome sai antes de o nome ser descartado.
    """
    csv.field_size_limit(LIMITE_DO_CAMPO)
    leitor = csv.reader(io.TextIOWrapper(origem, encoding=CODIFICACAO, newline=""))
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
    nomes = [coluna.strip() for coluna in cabecalho]
    for esperada in (*COLUNAS_GUARDADAS_NO_PR, *COLUNAS_DE_PESSOA_NO_PR):
        if nomes.count(esperada) != 1:
            raise ValueError(
                f"coluna {esperada!r} {nomes.count(esperada)} vezes no cabeçalho"
            )
    mantidas = [nomes.index(coluna) for coluna in COLUNAS_GUARDADAS_NO_PR]
    documento = nomes.index(COLUNA_DO_CNPJ_NO_PR)
    de_pessoa = [nomes.index(coluna) for coluna in COLUNAS_DE_PESSOA_NO_PR]
    escritor.writerow(COLUNAS_GUARDADAS_NO_PR)
    ficaram = 0
    for linha in leitor:
        if len(linha) != len(cabecalho):
            continue
        if not e_cnpj(linha[documento]) or tem_cpf_no_texto(
            linha[i] for i in de_pessoa
        ):
            continue
        escritor.writerow([linha[i] for i in mantidas])
        ficaram += 1
    saida.flush()
    saida.detach()
    return ficaram


def _csv_do_zip(zip_: zipfile.ZipFile) -> zipfile.ZipInfo:
    """O único CSV do ZIP; qualquer outra forma é o formato que mudou."""
    csvs = [m for m in zip_.infolist() if m.filename.lower().endswith(".csv")]
    if len(csvs) != 1:
        raise ValueError(f"{len(csvs)} CSVs no ZIP do Paraná (esperado: 1)")
    return csvs[0]


def alvo_do_zip_do_pr(url: str) -> Alvo:
    """O ZIP do dia, baixado e gravado como CSV já filtrado (o original nunca fica no acervo)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with (
                zipfile.ZipFile(bruto) as arquivo,
                arquivo.open(_csv_do_zip(arquivo)) as entrada,
                destino.open("wb") as saida,
            ):
                filtrar_csv_do_pr(entrada, saida)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica CSV pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return Alvo(url, ".csv", obter)


def descobrir_o_pr(cliente: Cliente, _agora: datetime) -> list[Alvo]:
    """O ZIP do dia que a página do Portal do Devedor oferece, sem repetir.

    Link da página é dado, não ordem: só se baixa do próprio portal (https, mesmo host); link
    relativo é resolvido contra a página, e o de outro host ou esquema é ignorado.
    """
    pagina = cliente.ler(PAGINA_DO_PR).conteudo.decode("utf-8", errors="replace")
    resolvidos = (urljoin(PAGINA_DO_PR, h) for h in ZIP_DO_PR.findall(pagina))
    enderecos = list(
        dict.fromkeys(e for e in resolvidos if e.startswith(f"{PORTAL_DO_PR}/"))
    )
    if not enderecos:
        raise ErroDeDescoberta("sefapr: nenhum ZIP na página do Portal do Devedor")
    return [alvo_do_zip_do_pr(e) for e in enderecos]


def fontes() -> list[Fonte]:
    """As fontes do lote para a lista `FONTES` (o id segue a família: `sefapr-...`)."""
    return [Fonte("sefapr-divida-ativa", SEMANAL, descobrir_o_pr)]
