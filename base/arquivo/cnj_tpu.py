"""As classes processuais das Tabelas Processuais Unificadas (TPU) do CNJ (Resolução CNJ 46/2007), para
dar nome e ramo à classe de cada processo do DJEN (plano de 03/11/2026 dos processos judiciais, PR 1b).

O serviço público da TPU no PJe entrega todas as classes num JSON só (849 em 03/11/2026, ativas e
inativas, cada uma com o código da classe mãe). Os campos `usuario_inclusao` e `usuario_alteracao` trazem
o login de quem cadastrou a classe no CNJ (nome de pessoa): saem antes de guardar.
"""

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from base.arquivo.coleta import Alvo, Cliente, Fonte, Obter

ID = "cnj-tpu"
CLASSES = "https://gateway.cloud.pje.jus.br/tpu/api/v1/publico/download/classes"
CAMPOS_DE_PESSOA = ("usuario_inclusao", "usuario_alteracao")


def obter_classes(url: str) -> Obter:
    """Baixa a lista das classes e grava sem os campos de pessoa."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            classes = json.loads(bruto.read_bytes())
        finally:
            bruto.unlink(missing_ok=True)
        if not isinstance(classes, list) or not all("cod_item" in c for c in classes):
            raise ValueError("a TPU do CNJ não respondeu a lista das classes")
        limpas = [
            {k: v for k, v in c.items() if k not in CAMPOS_DE_PESSOA} for c in classes
        ]
        destino.write_text(json.dumps(limpas, ensure_ascii=False), encoding="utf-8")
        return cabecalhos

    return obter


def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(CLASSES, ".json", obter=obter_classes(CLASSES))]


def fonte() -> Fonte:
    return Fonte(ID, "mensal", _descobrir, "json")
