"""O formato do memorando: seções em ordem fixa, frases com as notas e as evidências citadas.

A frase é a mesma `Frase` da análise escrita (`src/analise_escrita/saida.py`): o texto, as notas (os
ids das evidências) e as contas declaradas. Assim o memorando escrito por regra hoje e um escrito pelo
modelo amanhã passam pela mesma conferência.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from src.analise_escrita.saida import Frase
from src.memorando_ma.evidencia import Evidencia

SECOES = {
    "perfil": "Perfil: a companhia, o grupo e a rede",
    "pares": "Pares do mesmo setor",
    "dcf_e_multiplos": "DCF reverso e múltiplos",
    "comps_por_transacao": "Comps por transação",
    "lbo": "LBO com as premissas declaradas",
    "red_flags": "Red flags (cruzamentos e crédito)",
}


@dataclass(frozen=True)
class SecaoDoMemorando:
    chave: str
    frases: tuple[Frase, ...]

    @property
    def titulo(self) -> str:
        return SECOES.get(self.chave, self.chave)


@dataclass(frozen=True)
class Memorando:
    cnpj: str
    empresa: str
    como_era_em: date  # o dia do memorando: nada publicado depois entra
    secoes: tuple[SecaoDoMemorando, ...]
    evidencias: tuple[Evidencia, ...]
    limites: tuple[
        str, ...
    ] = ()  # as notas de método de cada parte (não são afirmações)

    def evidencia(self, id: str) -> Evidencia | None:
        return next((e for e in self.evidencias if e.id == id), None)

    def como_dict(self) -> dict[str, Any]:
        """Para a API: as seções com o título, as frases com as notas e as evidências inteiras."""
        return {
            "cnpj": self.cnpj,
            "empresa": self.empresa,
            "como_era_em": self.como_era_em.isoformat(),
            "secoes": [
                {
                    "chave": s.chave,
                    "titulo": s.titulo,
                    "frases": [
                        {"texto": f.texto, "notas": list(f.notas)} for f in s.frases
                    ],
                }
                for s in self.secoes
            ],
            "evidencias": [e.como_dict() for e in self.evidencias],
            "limites": list(self.limites),
        }

    def como_texto(self) -> str:
        """O memorando para ler, com as notas entre colchetes no fim de cada frase."""
        blocos = [
            f"{self.empresa} ({self.cnpj}), como era em {self.como_era_em:%d/%m/%Y}"
        ]
        for secao in self.secoes:
            frases = [f"{f.texto} [{', '.join(f.notas)}]" for f in secao.frases]
            blocos.append("\n".join([secao.titulo, *frases]))
        return "\n\n".join(blocos)
