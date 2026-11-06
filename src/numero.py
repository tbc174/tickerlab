"""O contrato de todo número do relatório (relatórios v2, PR 1; plano de 17/10/2026).

Um número sozinho não diz nada a quem lê: "ROE de 26%" só vira informação com de quando ele é, de onde
veio e contra o quê comparar. Por isso todo número mostrado traz os três:

- `medido_em`: a data ou o período ("12 meses até 30/06/2026", "dez/2025", "FRE de 2026");
- `fonte`: a tabela ou o documento de origem ("DFP e ITR entregues à CVM");
- `comparacao`: contra o quê (a mediana do setor, uma faixa fixa, a escala do artigo, o balanço
  anterior, o ano anterior) e o que ela mostra. Quando não há com o quê comparar (uma contagem que só
  existe no documento mais recente), `sem_comparacao` diz por quê, em vez de calar.

Tipos simples, sem Streamlit: o PDF, a página, a API e o React leem a mesma coisa (ADR 0044).
"""

from dataclasses import dataclass

DATA, FONTE, COMPARACAO = "data", "fonte", "comparação"


@dataclass(frozen=True)
class Comparacao:
    contra: str  # contra o quê ("setor Energia, 108 empresas, corte de 31/08/2026")
    texto: str  # o que a comparação mostra ("mediana 12,4%; metade entre 8,1% e 17,0%")
    valor: float | None = None  # o número comparado, quando é um só (o do ano anterior)


@dataclass(frozen=True)
class Numero:
    valor: float | None
    medido_em: str
    fonte: str
    comparacao: Comparacao | None
    sem_comparacao: str = ""  # por que não há com o quê comparar

    def o_que_falta(self) -> list[str]:
        """As partes do contrato que faltam (vazia quando o número está completo)."""
        falta = []
        if not self.medido_em:
            falta.append(DATA)
        if not self.fonte:
            falta.append(FONTE)
        if self.comparacao is None and not self.sem_comparacao:
            falta.append(COMPARACAO)
        return falta
