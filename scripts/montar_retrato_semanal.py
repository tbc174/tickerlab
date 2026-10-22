"""Refaz o retrato do relatório de setor da semana a partir das fichas da noite (ADR 0109, item 10).

Uso: python -m scripts.montar_retrato_semanal <pasta das fichas do dia>
O retrato vai para conteudo/relatorios_semanais/eletricas.json e é versionado: o site não lê o acervo.
"""

import json
import sys
from pathlib import Path

from src import relatorio_semanal

CNPJS_DAS_ELETRICAS = [
    "01083200000118",  # Neoenergia
    "03220438000173",  # Equatorial
    "02429144000193",  # CPFL Energia
    "17155730000164",  # Cemig
    "76483817000120",  # Copel
    "00864214000106",  # Energisa
    "03378521000175",  # Light
    "61584140000149",  # Rede Energia Participações
    "83878892000155",  # Celesc
]
DE_FORA = [
    {
        "nome": "AXIA Energia",
        "motivo": "a ligação com as distribuidoras da ANEEL foi feita só pelo nome e ainda não foi conferida",
    },
    {
        "nome": "AES Elpa",
        "motivo": "a ligação com as distribuidoras da ANEEL foi feita só pelo nome e ainda não foi conferida",
    },
    {
        "nome": "CEB",
        "motivo": "o último dado da base é de 12/2005",
    },
]


def main(pasta: Path) -> None:
    retrato = relatorio_semanal.montar_retrato(pasta, CNPJS_DAS_ELETRICAS, DE_FORA)
    destino = relatorio_semanal.PASTA / f"{relatorio_semanal.CHAVE_DO_SETOR}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(retrato, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{destino} ({len(retrato['grupos'])} companhias)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
