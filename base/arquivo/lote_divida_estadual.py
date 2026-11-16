"""Dívida ativa estadual do arquivista (linha 755 da fila; motor de risco cedente/sacado, linha 754).

Os estados que publicam a lista de devedores em arquivo, não só em tela. Entra primeiro o **Paraná**
(Sefa-PR, `listadevedores.sefa.pr.gov.br`): a aba "Arquivo" do Portal do Devedor oferece um ZIP gerado
todo dia com um CSV de todos os débitos inscritos (ICMS, IPVA, taxas...), de pessoa física e jurídica.
**Minas Gerais** (SEF-MG, `www.fazenda.mg.gov.br`, Resolução Conjunta SEF/AGE 5.625/2022) entra no mesmo
módulo: duas planilhas `.xlsb` de pessoa jurídica (as CDAs e os parcelamentos), em endereço fixo, lidas com
`python-calamine` (MIT; o `pyxlsb` é LGPL e não entra). Este módulo não importa `fontes.py` (que importa este).

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
- **Minas, a mesma regra:** a coluna `DEVEDOR PRINCIPAL` (o nome, que na firma individual é o da pessoa e
  às vezes traz o CPF) **nunca é guardada**; fica a linha cujo CNPJ tem a máscara e o dígito certos (o zero
  à esquerda vira espaço na máscara da planilha e é restaurado); a planilha com outra forma (aba a mais,
  coluna que sumiu) não guarda nada. A SEF-MG não tem `robots.txt` (404 em 06/11/2026) nem termos de uso
  escritos para a lista, só a base legal da divulgação (CTN, art. 198, §3º, II): licença **a confirmar**;
- **O arquivo guardado** sai em UTF-8 com ";" e tudo entre aspas, como o das outras coletas; datas e
  valores seguem como a fonte escreve ("18/06/1973", "1787.10" com ponto decimal).
"""

import csv
import io
import re
import unicodedata
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import IO
from urllib.parse import urljoin

from base import cnpj as cnpjs
from base.arquivo.coleta import Alvo, Cliente, ErroDeDescoberta, Fonte
from base.arquivo.lote_brasil2 import e_cnpj, tem_cpf_no_texto

SEMANAL = "semanal"
SEPARADOR_GUARDADO = ";"
CODIFICACAO = "utf-8-sig"  # o "-sig" tira a marca de ordem de bytes, se houver
LIMITE_DO_CAMPO = 1024**2
# a coluna do documento só tem o CNPJ (dígitos, "*" e pontuação), nunca "CNPJ - razão social"
SO_O_DOCUMENTO = re.compile(r"[0-9*./\-]{14,18}")

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
        if (
            not SO_O_DOCUMENTO.fullmatch(linha[documento].strip())
            or not e_cnpj(linha[documento])
            or tem_cpf_no_texto(linha[i] for i in de_pessoa)
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
        bruto.unlink(
            missing_ok=True
        )  # sobra de uma rodada morta à força: tem CPF e nome
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


# ---- Minas Gerais (SEF-MG) ----
PORTAL_DE_MG = "https://www.fazenda.mg.gov.br"
PASTA_DE_MG = f"{PORTAL_DE_MG}/transparencia/Divida-Ativa/divida-ativa-arquivos"
ARQUIVO_DAS_CDAS_DE_MG = "Resolucao_5625_22_PTA_PJ.xlsb"
ARQUIVO_DOS_PARCELAMENTOS_DE_MG = "Resolucao_5625_22_PARCELAMENTO_PJ.xlsb"
# "DD.DDDDDD/DDDD-DD": a planilha aplica a máscara no número e escreve o zero à esquerda. Linha que começa
# com espaço (" 0.015381/1600-46") é inscrição estadual de 13 dígitos, devedor sem CNPJ, ou CPF: não é CNPJ
MASCARA_DO_CNPJ_DE_MG = re.compile(r"[0-9]{2}\.[0-9]{6}/[0-9]{4}-[0-9]{2}")
# 11 dígitos seguidos no nome, com ou sem pontuação: CPF escrito sem pontos escapa do `tem_cpf_no_texto`
ONZE_DIGITOS_NO_NOME = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
# nome na planilha -> nome guardado (o nome do devedor sai: firma individual leva o nome da pessoa)
COLUNAS_DAS_CDAS_DE_MG = {
    "CNPJ": "CNPJ",
    "NCDA": "CDA",
    "DATAINSCRICAO": "Data da inscrição",
    "ESPECIE": "Espécie",
    "SALDOCDAR": "Saldo da CDA",
    "SALDONUCLEOR": "Saldo do núcleo",
}
COLUNAS_DOS_PARCELAMENTOS_DE_MG = {
    "IDENTIFICACAO": "CNPJ",
    "NPARCELAMENTO": "Parcelamento",
    "ESPECIE": "Espécie",
    "DATAPARCELAMENTO": "Data do parcelamento",
    "QTDEPARCELAS": "Parcelas",
    "DEBITOR": "Débito",
}
COLUNA_DE_PESSOA_DE_MG = "DEVEDORPRINCIPAL"
Planilha = Iterator[Sequence[object]]


def _chave_da_coluna(titulo: object) -> str:
    """ "Nº CDA" e "N° CDA" viram "NCDA": sem acento, sem símbolo, só letras e números, maiúsculo."""
    decomposto = unicodedata.normalize(
        "NFKD", str(titulo).replace("º", "").replace("°", "")
    )
    sem_marca = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", sem_marca.upper())


def _cnpj_da_mascara(valor: object) -> str | None:
    """O CNPJ de 14 caracteres da célula mascarada de MG, ou None se não tem a forma nem o dígito certo."""
    texto = str(valor).rstrip()
    if not MASCARA_DO_CNPJ_DE_MG.fullmatch(texto):
        return None
    cnpj = re.sub(r"[./-]", "", texto)
    return cnpjs.formatar(cnpj) if cnpjs.dv_confere(cnpj) else None


def _texto_da_celula(valor: object) -> str:
    """Data em ISO, número com ponto e o resto como texto; célula vazia é texto vazio."""
    if valor is None:
        return ""
    if isinstance(valor, datetime | date):
        return valor.isoformat()[:10]
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _linhas_da_planilha(arquivo: IO[bytes]) -> Planilha:
    """As linhas da única aba do arquivo (o formato é reconhecido pelo conteúdo: .xlsb, .xlsx...)."""
    from python_calamine import (
        CalamineWorkbook,
    )  # só a coleta de MG precisa; import tardio

    planilha = CalamineWorkbook.from_filelike(arquivo)
    if len(planilha.sheet_names) != 1:
        raise ValueError(
            f"{len(planilha.sheet_names)} abas no arquivo de MG (esperado: 1)"
        )
    return planilha.get_sheet_by_index(0).iter_rows()


def filtrar_planilha_de_mg(
    linhas: Planilha, colunas: Mapping[str, str], destino: IO[bytes]
) -> int:
    """Grava em CSV só as `colunas` das linhas de CNPJ com dígito certo, sem o nome do devedor.

    Devolve quantas linhas ficaram. Coluna esperada ausente ou repetida (a fonte mudou de formato),
    ou ainda a coluna do nome sumir, é erro: não dá para garantir o que se está guardando.
    Linha com CPF no meio do nome sai.
    """
    saida = io.TextIOWrapper(destino, encoding="utf-8", newline="")
    escritor = csv.writer(
        saida,
        delimiter=SEPARADOR_GUARDADO,
        quoting=csv.QUOTE_ALL,
        lineterminator="\r\n",
    )
    cabecalho = next(linhas, None)
    if cabecalho is None:
        raise ValueError("planilha vazia")
    nomes = [_chave_da_coluna(c) for c in cabecalho]
    for esperada in (*colunas, COLUNA_DE_PESSOA_DE_MG):
        if nomes.count(esperada) != 1:
            raise ValueError(
                f"coluna {esperada!r} {nomes.count(esperada)} vezes no cabeçalho"
            )
    mantidas = [nomes.index(c) for c in colunas]
    nome = nomes.index(COLUNA_DE_PESSOA_DE_MG)
    escritor.writerow(colunas.values())
    ficaram = 0
    for linha in linhas:
        if len(linha) != len(cabecalho):
            continue
        cnpj = _cnpj_da_mascara(linha[mantidas[0]])
        nome_do_devedor = _texto_da_celula(linha[nome])
        if (
            cnpj is None
            or tem_cpf_no_texto([nome_do_devedor])
            or ONZE_DIGITOS_NO_NOME.search(nome_do_devedor)
        ):
            continue
        escritor.writerow([cnpj, *(_texto_da_celula(linha[i]) for i in mantidas[1:])])
        ficaram += 1
    saida.flush()
    saida.detach()
    return ficaram


def alvo_da_planilha_de_mg(url: str, colunas: Mapping[str, str]) -> Alvo:
    """A planilha de MG baixada e gravada como CSV já filtrado (o original nunca fica no acervo)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        bruto.unlink(
            missing_ok=True
        )  # sobra de uma rodada morta à força: tem o nome dos devedores
        try:
            cabecalhos = cliente.baixar(url, bruto)
            with bruto.open("rb") as entrada, destino.open("wb") as saida:
                filtrar_planilha_de_mg(_linhas_da_planilha(entrada), colunas, saida)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica CSV pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return Alvo(url, ".csv", obter)


def descobrir_o_mg(_cliente: Cliente, _agora: datetime) -> list[Alvo]:
    """As duas planilhas de PJ da SEF-MG, em endereço fixo (a página não lista os arquivos em HTML)."""
    return [
        alvo_da_planilha_de_mg(
            f"{PASTA_DE_MG}/{ARQUIVO_DAS_CDAS_DE_MG}", COLUNAS_DAS_CDAS_DE_MG
        ),
        alvo_da_planilha_de_mg(
            f"{PASTA_DE_MG}/{ARQUIVO_DOS_PARCELAMENTOS_DE_MG}",
            COLUNAS_DOS_PARCELAMENTOS_DE_MG,
        ),
    ]


def fontes() -> list[Fonte]:
    """As fontes do lote para a lista `FONTES` (o id segue a família: `sefapr-...`)."""
    return [
        Fonte("sefapr-divida-ativa", SEMANAL, descobrir_o_pr),
        Fonte("sefmg-divida-ativa", SEMANAL, descobrir_o_mg),
    ]
