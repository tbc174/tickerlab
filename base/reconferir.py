"""Refaz a conferência do contrato nos Parquets que já estão no disco (API A3, linha 224).

`gravar_tabela` confere o Parquet ao gravá-lo (`base/conferencia.py`), mas os Parquets montados antes de a
tabela ganhar `pasta` no dicionário ficaram com manifesto sem `conferencia_do_contrato`. Aqui o Parquet é
lido de novo, conferido, e só o manifesto `.json` ao lado é reescrito: o Parquet e o resto do manifesto
(hash, origens, licença, versão do código) não mudam.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from base.conferencia import conferir
from base.dicionario import TABELAS
from base.parquet import gravar_atomico, ler_tabela

log = logging.getLogger("tickerlab.reconferir")

# arquivos de versão anterior e de cópia de segurança (`2026-10.v1.parquet`, `x.antes-...`): não são a tabela
_ARQUIVO_ANTIGO = re.compile(r"\.v\d+\.|\.antes-")


@dataclass
class ResumoDaPasta:
    tabela: str
    arquivos: int = 0
    aprovados: int = 0
    reprovados: dict[str, list[str]] = field(
        default_factory=dict
    )  # arquivo → problemas
    sem_manifesto: list[str] = field(default_factory=list)


def parquets_da_tabela(base: Path, nome: str) -> list[Path]:
    """Os Parquets de `nome` dentro de `base` (a pasta `<acervo>/base`), sem as versões antigas."""
    pasta = TABELAS[nome].pasta
    if not pasta:
        raise ValueError(f"a tabela `{nome}` não tem `pasta` no dicionário")
    return sorted(
        p
        for p in (base / pasta).rglob("*.parquet")
        if not _ARQUIVO_ANTIGO.search(p.name)
    )


def reconferir_tabela(base: Path, nome: str, *, gravar: bool = True) -> ResumoDaPasta:
    """Confere cada Parquet de `nome` e grava o resultado no manifesto (se `gravar`)."""
    resumo = ResumoDaPasta(nome)
    for arquivo in parquets_da_tabela(base, nome):
        manifesto = arquivo.with_suffix(".json")
        rotulo = arquivo.relative_to(base).as_posix()
        if not manifesto.exists():
            resumo.sem_manifesto.append(rotulo)
            continue
        resultado = conferir(ler_tabela(arquivo), nome).para_manifesto()
        resumo.arquivos += 1
        if resultado["aprovada"]:
            resumo.aprovados += 1
        else:
            resumo.reprovados[rotulo] = list(resultado["problemas"])  # type: ignore[call-overload]
        if gravar:
            conteudo = json.loads(manifesto.read_text(encoding="utf-8"))
            conteudo["conferencia_do_contrato"] = resultado
            texto = json.dumps(conteudo, ensure_ascii=False, indent=1)
            gravar_atomico(
                manifesto,
                lambda c, texto=texto: Path(c).write_text(texto, encoding="utf-8"),
            )
        log.info("%s: %s", rotulo, "aprovada" if resultado["aprovada"] else "reprovada")
    return resumo
