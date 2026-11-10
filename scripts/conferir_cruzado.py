"""Conferência cruzada do dia (exigência 6 da ADR 0027; plano do placar de confiança, PR 1).

    python -m scripts.conferir_cruzado [--dia AAAA-MM-DD]

Lê a base **só pela porta** (`base.porta`), compara cada par de `base/cruzada.py::PARES`, grava
`<acervo>/placar/<dia>/cruzada.json` e imprime uma linha por par. Divergência sem explicação em
`base/conferidas/divergencias_explicadas.csv` sai com 1 e uma linha `FALHAS: ...` (o Kuma lê). Só lê a base.

Roda: manual (python -m scripts.conferir_cruzado); citado em cruzada.py.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from base import porta
from base.cruzada import (
    CAMINHO_EXPLICADAS,
    PARES,
    Par,
    Relatorio,
    comparar,
    ler_explicadas,
    montar_relatorio_do_dia,
    par_sem_dados,
)
from base.parquet import gravar_atomico
from src import acervo

COPOM = (
    Path(__file__).resolve().parent.parent
    / "base"
    / "conferidas"
    / "copom_reunioes.csv"
)

COLUNAS_DO_IFDATA = [
    "data_base",
    "tipo_instituicao",
    "cod_inst",
    "relatorio",
    "coluna",
    "saldo",
]
COLUNAS_DA_DFP = [
    "cnpj",
    "grupo",
    "demonstracao",
    "conta",
    "descricao",
    "documento",
    "referencia",
    "ordem",
    "valor",
]
BRASILIA = ZoneInfo("America/Sao_Paulo")
AMOSTRA_DO_ENET = (
    Path(__file__).resolve().parent.parent / "base" / "conferidas" / "amostra_enet.csv"
)


def acervo_placar() -> Path:
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        raise KeyError("o acervo está desligado")
    return pasta / "placar"


def _tabelas_da_selic(p: porta.Porta, dia: str) -> dict[str, pd.DataFrame]:
    return {
        "bcb_selic_focus": p.ler("bcb_selic_focus", como_era_em=dia),
        "copom_reunioes": pd.read_csv(COPOM, sep=";", encoding="utf-8"),
    }


def _tabelas_dos_bancos(p: porta.Porta, dia: str) -> dict[str, pd.DataFrame]:
    """Só os bancos da ligação do IF.data e só as colunas e linhas que os pares usam (a DFP inteira é enorme)."""
    ligacao = p.ler(
        "ligacao_dos_bancos"
    )  # sem `publico_em` no contrato: não há "como era em"
    cnpjs = sorted(ligacao["cnpj"].dropna().unique())
    ifdata = p.ler(
        "ifdata_valores",
        como_era_em=dia,
        filtros={"relatorio": 1, "coluna": ["Ativo Total", "Patrimônio Líquido"]},
        colunas=COLUNAS_DO_IFDATA,
    )
    dfp = p.ler(
        "demonstracoes_como_era",
        como_era_em=dia,
        filtros={"cnpj": cnpjs, "grupo": "con", "documento": "DFP", "ordem": "ultimo"},
        colunas=COLUNAS_DA_DFP,
    )
    return {
        "ligacao_dos_bancos": ligacao,
        "ifdata_valores": ifdata,
        "demonstracoes_como_era": dfp,
    }


def _tabelas_do_enet(p: porta.Porta, dia: str) -> dict[str, pd.DataFrame]:
    """A amostra sorteada: nossa leitura da versão sorteada e o que o ENET trouxe (`scripts/conferir_enet.py`)."""
    amostra = pd.read_csv(AMOSTRA_DO_ENET, dtype=str)
    arquivo = acervo_placar() / "enet_amostra.parquet"
    if not arquivo.exists():
        raise KeyError(
            f"falta o ENET da amostra ({arquivo.name}); rode scripts.conferir_enet baixar"
        )
    nossa = p.ler(
        "demonstracoes_como_era",
        como_era_em=dia,
        filtros={
            "cnpj": sorted(amostra["cnpj"]),
            "documento": "DFP",
            "referencia": sorted(set(amostra["referencia"])),
        },
        colunas=COLUNAS_DA_DFP + ["inicio", "fim", "versao"],
    )
    versao = amostra.set_index("cnpj")["versao"].astype(int)
    nossa = nossa[nossa["versao"] == nossa["cnpj"].map(versao)]
    return {"demonstracoes_como_era": nossa, "enet_amostra": pd.read_parquet(arquivo)}


def tabelas_do_par(p: porta.Porta, par: Par, dia: str) -> dict[str, pd.DataFrame]:
    if par.nome.startswith("selic"):
        return _tabelas_da_selic(p, dia)
    if par.nome.startswith("dfp_enet"):
        return _tabelas_do_enet(p, dia)
    return _tabelas_dos_bancos(p, dia)


def conferir(dia: str) -> list[Relatorio]:
    explicadas = ler_explicadas(CAMINHO_EXPLICADAS.read_text(encoding="utf-8"))
    relatorios: list[Relatorio] = []
    with porta.abrir() as p:
        for par in PARES:
            assert par.preparar is not None
            try:
                tabelas = tabelas_do_par(p, par, dia)
            except KeyError as erro:  # tabela ainda não montada nesta base
                relatorios.append(par_sem_dados(par, str(erro)))
                continue
            a, b = par.preparar(tabelas)
            relatorios.append(comparar(par, a, b, explicadas))
    return relatorios


def gravar(dia: str, relatorios: list[Relatorio]) -> Path:
    pasta = (acervo.pasta_do_acervo() or Path("acervo-desligado")) / "placar" / dia
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "cruzada.json"
    texto = json.dumps(
        montar_relatorio_do_dia(dia, relatorios), ensure_ascii=False, indent=2
    )
    gravar_atomico(destino, lambda t: t.write_text(texto, encoding="utf-8"))
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dia", default=datetime.now(BRASILIA).date().isoformat())
    args = parser.parse_args(argv)
    relatorios = conferir(args.dia)
    for r in relatorios:
        if r.sem_dados:
            print(f"AVISO: {r.par} não rodou ({r.sem_dados})")
            continue
        print(
            f"{r.par}: {r.comparadas} comparadas, {r.iguais} iguais, {r.pela_tolerancia} pela tolerância, "
            f"{r.diferentes} diferentes ({r.sem_explicacao} sem explicação), "
            f"só A {r.so_em_a}, só B {r.so_em_b}"
        )
        if r.informativo:
            print(f"  INFORMATIVO (fora da exigência 6): {r.informativo}")
    print(f"gravado em {gravar(args.dia, relatorios)}")
    vermelhos = [
        f"{r.par} ({r.sem_explicacao} sem explicação)" for r in relatorios if r.vermelho
    ]
    if vermelhos:
        print("FALHAS: " + "; ".join(vermelhos))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
