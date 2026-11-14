"""Fontes novas da conferência de 14/11/2026 (meta das 300 tabelas pelo CNPJ, linha 904, PR 1).

O que o arquivista passa a guardar (as tabelas saem de `base/cadastros_conferidos.py`):

- **Receita, regime tributário pela ECF** (`rfb-renuncias-regime-*`): os quatro ZIPs de
  `Dados/Obrigacoes_Acessorias/ECF/` (lucro presumido, real, arbitrado, imunes e isentas). Só ano, CNPJ, CNPJ da
  SCP, forma de tributação e quantas escriturações: nenhuma coluna de pessoa, então o ZIP fica como veio. Os
  arquivos estão no compartilhamento público da Receita (o mesmo do CNPJ): baixa pelo WebDAV com o token do
  redirecionamento, mas o endereço guardado é o público (`arquivos.receitafederal.gov.br/Dados/...`), que dá a
  família `rfb-renuncias` da licença (`base/licenca.py`), a mesma da DIRBI e da ECF de renúncia. O endereço
  público responde 404 a um pedido direto: por isso a fonte não é "pesada" (que confere os cabeçalhos no
  endereço guardado) e a coleta compara o SHA-256;
- **MTE, PAT** (`mte-pat-*`): as relações de beneficiárias, facilitadoras e fornecedoras ativas no Programa de
  Alimentação do Trabalhador (XLSX com a data no nome). Chega ao acervo só um CSV com as colunas da lista (sem a
  razão social) e só a linha com CNPJ inteiro. **A relação de nutricionistas (pessoa física) nunca é baixada**;
- **ANM, TAH** (`anm-tah`): a Taxa Anual por Hectare. O documento mistura CPF mascarado e CNPJ, e há o nome do
  titular: chega ao acervo só a linha com CNPJ inteiro e sem a coluna do nome;
- **Anatel, PADOs** (`anatel-pados`): o CSV da gestão dos processos sancionadores, sem o nome da empresa e do
  grupo econômico, só a linha com CNPJ inteiro (o documento mistura CPF);
- **Anatel, produtos homologados** (`anatel-homologados`): sem o nome do solicitante e do fabricante, só a
  linha com CNPJ inteiro;
- **ANP, tancagem** (`anp-tancagem`): o CSV mais novo da página (o arquivo do mês que a ANP publicou por último).
  Os antigos ficam de fora: o layout muda de um ano para o outro (separador, codificação e nome das colunas) e
  são posições velhas do mesmo cadastro. A razão social fica no acervo; a tabela não a leva.

Escolhas (testes em `tests/test_base_arquivo_lote_conferidas_14_11.py`): o endereço que vem da página só vale se
for do próprio órgão (nada de baixar de outro host); arquivo sem a coluna do documento é erro, nunca "nada".
"""

import csv
import io
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from base.arquivo.coleta import Alvo, Cliente, Descobrir, ErroDeDescoberta, Fonte, Obter
from base.arquivo.obter import csv_so_com_colunas, tem_cnpj_inteiro
from base.retratos import nome_da_coluna

MENSAL = "mensal"

# --- Receita: regime tributário pela ECF -----------------------------------------------------------------
RAIZ_DA_RECEITA = "https://arquivos.receitafederal.gov.br/"
PASTA_DA_ECF = "Dados/Obrigacoes_Acessorias/ECF/"
DOWNLOAD_DA_RECEITA = RAIZ_DA_RECEITA + "public.php/dav/files/{token}/{caminho}"
TOKEN_DO_COMPARTILHAMENTO = re.compile(r"/s/([A-Za-z0-9]+)")
# o id da fonte → o ZIP da pasta da ECF (um regime por arquivo)
ZIPS_DA_ECF = {
    "rfb-renuncias-regime-presumido": "entidades-lucro-presumido.zip",
    "rfb-renuncias-regime-real": "entidades-lucro-real.zip",
    "rfb-renuncias-regime-arbitrado": "entidades-lucro-arbitrado.zip",
    "rfb-renuncias-regime-imunes": "entidades-imunes-e-isentas.zip",
}


def endereco_publico_da_ecf(nome: str) -> str:
    """O endereço público do ZIP (o que fica no registro e decide a licença)."""
    return RAIZ_DA_RECEITA + PASTA_DA_ECF + nome


def _token_da_receita(cliente: Cliente) -> str:
    final = cliente.ler(RAIZ_DA_RECEITA).url
    achado = TOKEN_DO_COMPARTILHAMENTO.search(final)
    if not achado:
        raise ErroDeDescoberta(f"Receita: sem o token do compartilhamento em {final}")
    return achado.group(1)


def zip_da_receita(nome: str) -> Obter:
    """Baixa o ZIP pelo compartilhamento (WebDAV com o token), guardado sob o endereço público."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        token = _token_da_receita(cliente)
        url = DOWNLOAD_DA_RECEITA.format(token=token, caminho=PASTA_DA_ECF + nome)
        return cliente.baixar(url, destino)

    return obter


def _da_ecf(nome: str) -> Descobrir:
    return lambda cliente, agora: [
        Alvo(endereco_publico_da_ecf(nome), ".zip", zip_da_receita(nome))
    ]


# --- MTE: PAT --------------------------------------------------------------------------------------------
PAGINA_DO_PAT = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/servicos/empregador/programa-de-alimentacao-do-trabalhador-pat/"
    "relacao-de-empresas-beneficiarias-ativas-no-pat"
)
PASTA_DO_PAT = (
    "https://www.gov.br/trabalho-e-emprego/pt-br/servicos/empregador/programa-de-alimentacao-do-trabalhador-pat/"
    "arquivos-e-imagens/"
)
XLSX_NA_PAGINA = re.compile(rb'href="([^"]+\.xlsx)"', re.IGNORECASE)
# o id da fonte → o começo do nome da planilha; a de nutricionistas (pessoa física) nunca entra aqui
RELACOES_DO_PAT = {
    "mte-pat-beneficiarias": "beneficiarias",
    "mte-pat-facilitadoras": "facilitadoras",
    "mte-pat-fornecedoras": "fornecedoras",
}
PESSOA_FISICA_DO_PAT = "nutricionistas"
# as colunas que chegam ao acervo, pelo nome sem acento (o MTE põe hífen invisível no meio da palavra)
COLUNAS_DO_PAT = (
    "CNPJ",
    "MATRIZOUFILIAL",
    "MUNICIPIO",
    "UF",
    "NOREGISTRO",
    "DATACADASTRO",
    "ATE5SALARIOSMINIMOS",
    "ACIMADE5SALARIOSMINIMOS",
    "TOTALTRABALHADORESATENDIDOS",
    "SITUACAO",
)
DOCUMENTO_DO_PAT = "CNPJ"


def planilha_do_pat(conteudo: bytes, endereco: str) -> list[dict[str, str]]:
    """As linhas da 1ª aba com as colunas da lista (nome sem acento) e CNPJ inteiro; CPF e CNPJ errado saem."""
    from openpyxl import load_workbook

    livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    try:
        linhas = livro.worksheets[0].iter_rows(values_only=True)
        cabecalho = [nome_da_coluna(str(c or "")) for c in next(linhas, ())]
        faltam = sorted(set(COLUNAS_DO_PAT) - set(cabecalho))
        if faltam:
            raise ValueError(f"{endereco}: faltam as colunas {', '.join(faltam)}")
        posicoes = {c: cabecalho.index(c) for c in COLUNAS_DO_PAT}
        return [
            registro
            for linha in linhas
            if (registro := _registro(linha, posicoes))
            and tem_cnpj_inteiro(registro[DOCUMENTO_DO_PAT])
        ]
    finally:
        livro.close()


def _registro(linha: tuple[object, ...], posicoes: dict[str, int]) -> dict[str, str]:
    def texto(valor: object) -> str:
        if isinstance(valor, datetime):
            return valor.date().isoformat()
        return "" if valor is None else str(valor).strip()

    return {c: texto(linha[p]) if p < len(linha) else "" for c, p in posicoes.items()}


def xlsx_do_pat(url: str) -> Obter:
    """Baixa a planilha e grava em `destino` um CSV (";", UTF-8) só com as colunas da lista e CNPJ inteiro."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            registros = planilha_do_pat(bruto.read_bytes(), url)
        finally:
            bruto.unlink(missing_ok=True)
        with destino.open("w", encoding="utf-8", newline="") as saida:
            escritor = csv.DictWriter(saida, COLUNAS_DO_PAT, delimiter=";")
            escritor.writeheader()
            escritor.writerows(registros)
        return cabecalhos

    return obter


def _do_pat(comeco: str) -> Descobrir:
    def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        links = dict.fromkeys(
            m.decode()
            for m in XLSX_NA_PAGINA.findall(cliente.ler(PAGINA_DO_PAT).conteudo)
        )
        achados = [
            link
            for link in links
            if link.startswith(PASTA_DO_PAT)
            and link.rsplit("/", 1)[-1].lower().startswith(comeco)
        ]
        if not achados:
            raise ErroDeDescoberta(
                f"PAT: sem a planilha de {comeco} em {PAGINA_DO_PAT}"
            )
        return [Alvo(achados[0], ".csv", xlsx_do_pat(achados[0]))]

    return descobrir


# --- ANM: TAH --------------------------------------------------------------------------------------------
TAH_DA_ANM = "https://dadosabertos.anm.gov.br/TAH/Tah.csv"
COLUNAS_DA_TAH = (
    "NRProcesso",
    "NRAnoProcesso",
    "NRCpfCnpj",
    "DSFaseProcesso",
    "NMSuperintendencia",
    "NRHectares",
    "DTQuitacao",
    "VLPago",
    "VLTotal",
)  # sem `NMPessoa`, o nome do titular

# --- Anatel: PADOs e produtos homologados ------------------------------------------------------------------
PADOS_DA_ANATEL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acompanhamento_e_controle/gestao_de_pados.zip"
MEMBRO_DOS_PADOS = "CSV_GESTAO_DE_PADOS.csv"
COLUNAS_DOS_PADOS = (
    "Processo",
    "Anexação",
    "Tema",
    "CPF/CNPJ",
    "Serviço",
    "Status do Processo",
    "Fase",
    "Multa Aplicada no Processo",
    "Situação do Pagamento",
)  # sem `Empresa` e `Grupo Econômico`
HOMOLOGADOS_DA_ANATEL = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/certificacao_de_produtos/produtos_certificados.zip"
COLUNAS_DOS_HOMOLOGADOS = (
    "Data da Homologação",
    "Número de Homologação",
    "CNPJ do Solicitante",
    "Certificado de Conformidade Técnica",
    "Data do Certificado de Conformidade Técnica",
    "Data de Validade do Certificado",
    "Situação do Certificado",
    "Situação do Requerimento",
    "Modelo",
    "Nome Comercial",
    "Categoria do Produto",
    "Tipo do Produto",
    "País do Fabricante",
)  # sem o nome do solicitante e o do fabricante

# --- ANP: tancagem -----------------------------------------------------------------------------------------
PAGINA_DA_TANCAGEM = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
    "tancagem-do-abastecimento-nacional-de-combustiveis"
)
PASTA_DA_TANCAGEM = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/"
    "arquivos-tancagem-do-abastecimento-nacional-de-combustiveis/dados-abertos/"
)
CSV_DA_TANCAGEM = re.compile(
    rb'href="(' + re.escape(PASTA_DA_TANCAGEM.encode()) + rb'(\d{4})/[^"/]+\.csv)"',
    re.IGNORECASE,
)


def descobrir_tancagem(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """O CSV mais novo: o último link do ano mais alto (a página lista os meses do ano em ordem)."""
    achados = CSV_DA_TANCAGEM.findall(cliente.ler(PAGINA_DA_TANCAGEM).conteudo)
    if not achados:
        raise ErroDeDescoberta(f"ANP: nenhum CSV da tancagem em {PAGINA_DA_TANCAGEM}")
    ano_mais_alto = max(int(ano) for _, ano in achados)
    do_ano = [link.decode() for link, ano in achados if int(ano) == ano_mais_alto]
    return [Alvo(do_ano[-1])]


def _filtrado(url: str, obter: Obter) -> Descobrir:
    return lambda cliente, agora: [Alvo(url, ".csv", obter)]


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família da licença)."""
    return [
        *(Fonte(id_, MENSAL, _da_ecf(nome)) for id_, nome in ZIPS_DA_ECF.items()),
        *(
            Fonte(id_, MENSAL, _do_pat(comeco))
            for id_, comeco in RELACOES_DO_PAT.items()
        ),
        Fonte(
            "anm-tah",
            MENSAL,
            _filtrado(
                TAH_DA_ANM,
                csv_so_com_colunas(
                    TAH_DA_ANM,
                    COLUNAS_DA_TAH,
                    "latin-1",
                    separador=",",
                    so_com_cnpj_em="NRCpfCnpj",
                ),
            ),
            pesada=True,
        ),
        Fonte(
            "anatel-pados",
            MENSAL,
            _filtrado(
                PADOS_DA_ANATEL,
                csv_so_com_colunas(
                    PADOS_DA_ANATEL,
                    COLUNAS_DOS_PADOS,
                    "utf-8-sig",
                    so_com_cnpj_em="CPF/CNPJ",
                    dentro_do_zip=True,
                    membro=MEMBRO_DOS_PADOS,
                ),
            ),
        ),
        Fonte(
            "anatel-homologados",
            MENSAL,
            _filtrado(
                HOMOLOGADOS_DA_ANATEL,
                csv_so_com_colunas(
                    HOMOLOGADOS_DA_ANATEL,
                    COLUNAS_DOS_HOMOLOGADOS,
                    "utf-8-sig",
                    so_com_cnpj_em="CNPJ do Solicitante",
                    dentro_do_zip=True,
                ),
            ),
            pesada=True,
        ),
        Fonte("anp-tancagem", MENSAL, descobrir_tancagem),
    ]
