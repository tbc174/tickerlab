"""Conferência da leitura da DFP contra o ENET da CVM (exigência 6 de `demonstracoes_como_era`; linha 784).

A tabela lê a versão mais nova da DFP dos dados abertos da CVM. O ENET é o mesmo documento por outro canal
(o pacote que a empresa entregou). Este script sorteia uma amostra, baixa o ENET dela e grava as contas lidas
para o par `dfp_enet_x_nossa_leitura` (`base/cruzada.py`) comparar.

    python -m scripts.conferir_enet sortear --pasta <pasta nova fora do repositório>
    python -m scripts.conferir_enet baixar --pasta <a mesma pasta>

- **`sortear`** baixa o índice da DFP do ano e o cadastro de companhias abertas, e sorteia com **semente fixa**
  10 bancos, 5 seguradoras e 35 não financeiras. A lista é gravada em `base/conferidas/amostra_enet.csv` **antes**
  de qualquer pacote ser baixado: a amostra não se ajusta depois de ver o resultado.
- **`baixar`** baixa o pacote de cada linha da lista (um por vez, com pausa, em pasta nova) e grava as contas
  lidas em `<acervo>/placar/enet_amostra.csv.gz`.

Roda: manual, uma vez por rodada de prova da exigência 6 (a prova vale 90 dias).
"""

import argparse
import csv
import io
import random
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

from base.contas_cvm import ler_indice
from base.enet import DocumentoEnet, ler_xml_enet
from base.enet_coleta import Baixador, xml_do_pacote
from src import rede

SEMENTE = 20261110
ANO = 2024
QUANTAS = {"banco": 10, "seguradora": 5, "nao_financeira": 35}
RAIZ_DA_CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
INDICE_DA_DFP = f"{RAIZ_DA_CVM}/DOC/DFP/DADOS/dfp_cia_aberta_{ANO}.zip"
CADASTRO = f"{RAIZ_DA_CVM}/CAD/DADOS/cad_cia_aberta.csv"
AMOSTRA = (
    Path(__file__).resolve().parent.parent / "base" / "conferidas" / "amostra_enet.csv"
)
COLUNAS_DA_AMOSTRA = [
    "cnpj",
    "empresa",
    "grupo_da_amostra",
    "referencia",
    "versao",
    "link",
]
TEMPO_LIMITE = 120


def _baixar(url: str) -> bytes:
    resposta = rede.obter(url, timeout=TEMPO_LIMITE)
    resposta.raise_for_status()
    return resposta.content


def seguradoras_do_cadastro(cadastro: pd.DataFrame) -> set[str]:
    """Os CNPJs cujo setor de atividade no cadastro da CVM é de seguros."""
    setor = cadastro["SETOR_ATIV"].fillna("").str.lower()
    return set(cadastro.loc[setor.str.contains("segur"), "CNPJ_CIA"])


def sortear(
    indice: pd.DataFrame, bancos: set[str], seguradoras: set[str]
) -> pd.DataFrame:
    """A amostra: a versão mais nova da DFP de `ANO`, sorteada com `SEMENTE` em cada grupo."""
    do_ano = indice[indice["referencia"] == pd.Timestamp(ANO, 12, 31)]
    mais_nova = do_ano.sort_values("versao").drop_duplicates("cnpj", keep="last")
    mais_nova = mais_nova.sort_values("cnpj").reset_index(drop=True)
    grupo = mais_nova["cnpj"].map(
        lambda c: (
            "banco"
            if c in bancos
            else "seguradora"
            if c in seguradoras
            else "nao_financeira"
        )
    )
    sorteio = random.Random(SEMENTE)
    partes = []
    for nome, quantas in QUANTAS.items():
        candidatas = mais_nova[grupo == nome]
        indices = sorteio.sample(list(candidatas.index), min(quantas, len(candidatas)))
        partes.append(candidatas.loc[sorted(indices)].assign(grupo_da_amostra=nome))
    amostra = pd.concat(partes, ignore_index=True)
    amostra["referencia"] = amostra["referencia"].dt.date.astype(str)
    return amostra[COLUNAS_DA_AMOSTRA]


def _bancos_da_porta() -> set[str]:
    from base import porta

    with porta.abrir() as p:
        return set(p.ler("ligacao_dos_bancos")["cnpj"].dropna().unique())


def comando_sortear(pasta: Path) -> int:
    pasta.mkdir(
        parents=True, exist_ok=False
    )  # pasta nova: nada de misturar com outra rodada
    indice = ler_indice(_baixar(INDICE_DA_DFP), "DFP")
    cadastro = pd.read_csv(
        io.BytesIO(_baixar(CADASTRO)), sep=";", encoding="latin-1", dtype=str
    )
    amostra = sortear(indice, _bancos_da_porta(), seguradoras_do_cadastro(cadastro))
    amostra.to_csv(AMOSTRA, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    print(amostra["grupo_da_amostra"].value_counts().to_string())
    print(f"amostra gravada em {AMOSTRA}")
    return 0


TENTATIVAS = 3
PAUSA_ENTRE_TENTATIVAS = (
    60  # segundos: o ENET às vezes responde "serviço indisponível" no lugar do zip
)


def _documento_do_enet(
    baixador: Baixador, cnpj: str, link: str, pasta: Path
) -> DocumentoEnet | None:
    """Baixa o pacote do link e lê o XML; tenta de novo quando a CVM devolve erro no lugar do zip."""
    for tentativa in range(1, TENTATIVAS + 1):
        pacote = baixador.baixar(link)
        nome = cnpj.replace("/", "").replace(".", "").replace("-", "")
        (pasta / f"{nome}.zip").write_bytes(pacote)
        try:
            return ler_xml_enet(xml_do_pacote(pacote))
        except (zipfile.BadZipFile, ValueError) as erro:
            print(f"AVISO: {cnpj} não lido (tentativa {tentativa}): {erro}")
            if tentativa < TENTATIVAS:
                time.sleep(PAUSA_ENTRE_TENTATIVAS)
    return None


def contas_do_enet(amostra: pd.DataFrame, pasta: Path) -> pd.DataFrame:
    """Baixa cada pacote da amostra e junta as contas lidas do XML (última versão, no formato da tabela)."""
    baixador = Baixador()
    partes = []
    for linha in amostra.itertuples():
        documento = _documento_do_enet(baixador, linha.cnpj, linha.link, pasta)
        if documento is None:
            continue
        partes.append(documento.contas.assign(cnpj=linha.cnpj))
    return pd.concat(partes, ignore_index=True)


def comando_baixar(pasta: Path) -> int:
    from src import acervo

    amostra = pd.read_csv(AMOSTRA, dtype=str)
    contas = contas_do_enet(amostra, pasta)
    raiz = acervo.pasta_do_acervo()
    if raiz is None:
        raise SystemExit("o acervo está desligado: defina TICKERLAB_ACERVO")
    destino = raiz / "placar" / "enet_amostra.csv.gz"
    destino.parent.mkdir(parents=True, exist_ok=True)
    contas.to_csv(destino, index=False)
    print(f"{len(contas)} contas de {contas['cnpj'].nunique()} companhias em {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comando", choices=["sortear", "baixar"])
    parser.add_argument("--pasta", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.comando == "sortear":
        return comando_sortear(args.pasta)
    args.pasta.mkdir(parents=True, exist_ok=True)
    return comando_baixar(args.pasta)


if __name__ == "__main__":
    sys.exit(main())
