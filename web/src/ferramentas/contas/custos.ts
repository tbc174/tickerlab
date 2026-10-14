// Custo das taxas e da queda: cópia em TypeScript de src/ferramentas/custos.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.

export const ANOS_MAXIMOS = 100;

export interface CustoDaTaxa {
  sem_taxa: number;
  com_taxa: number;
  ficou_com_a_taxa: number;
  fracao_do_resultado: number;
}

export interface LinhaDaTaxa {
  ano: number;
  sem_taxa: number;
  com_taxa: number;
}

function conferir(capital: number, retorno: number, taxa: number, anos: number): void {
  if (capital < 0) throw new RangeError("O capital não pode ser negativo.");
  if (retorno <= -1) throw new RangeError("O retorno precisa ser maior que -100% ao ano.");
  if (taxa < 0 || taxa >= 1) throw new RangeError("A taxa precisa estar entre 0% e 100% ao ano.");
  if (anos < 0 || anos > ANOS_MAXIMOS) {
    throw new RangeError(`O prazo precisa estar entre 0 e ${ANOS_MAXIMOS} anos.`);
  }
}

/** Quanto o patrimônio fica com e sem a taxa anual depois de `anos` anos. */
export function custoDaTaxa(capital: number, retorno: number, taxa: number, anos: number): CustoDaTaxa {
  conferir(capital, retorno, taxa, anos);
  const sem = capital * (1 + retorno) ** anos;
  const com = capital * ((1 + retorno) * (1 - taxa)) ** anos;
  return {
    sem_taxa: sem,
    com_taxa: com,
    ficou_com_a_taxa: sem - com,
    fracao_do_resultado: sem > 0 ? (sem - com) / sem : 0,
  };
}

/** Ano a ano, do 0 ao último, o patrimônio sem e com a taxa. */
export function evolucaoDaTaxa(capital: number, retorno: number, taxa: number, anos: number): LinhaDaTaxa[] {
  conferir(capital, retorno, taxa, anos);
  return Array.from({ length: anos + 1 }, (_, ano) => ({
    ano,
    sem_taxa: capital * (1 + retorno) ** ano,
    com_taxa: capital * ((1 + retorno) * (1 - taxa)) ** ano,
  }));
}

/** A alta que volta ao valor de antes de uma `queda` (-0.5 → 1: cair 50% pede +100%). */
export function altaParaRecuperar(queda: number): number {
  if (queda <= -1 || queda > 0) {
    throw new RangeError("A queda precisa estar entre 0% e -100% (sem chegar a -100%).");
  }
  return 1 / (1 + queda) - 1;
}
