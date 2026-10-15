// Fundo de renda fixa pelo CDI, mês a mês: cópia em TypeScript de src/ferramentas/fundos.py (a
// referência). Taxa de administração, de performance e come-cotas (Lei 14.754/2023, art. 17); as
// alíquotas vêm de src/regras_de_imposto.py pelo conteudo/regras_de_imposto.json.
import { regrasDeImposto } from "../../conteudo";
import { aliquotaDaRendaFixa } from "./renda_fixa";

export const PRAZO_MAXIMO = 120; // meses: 10 anos, o prazo máximo do CDB da comparação (renda_fixa)
const MESES_DO_COME_COTAS = [5, 11]; // maio e novembro
export const DIAS_POR_MES = 365 / 12;
const DIAS_UTEIS_POR_ANO = 252;
const DIAS_UTEIS_POR_MES = DIAS_UTEIS_POR_ANO / 12;

export interface Resultado {
  patrimonio_final: number; // depois das taxas e do come-cotas, antes do IR do resgate
  taxa_de_administracao: number;
  taxa_de_performance: number;
  come_cotas: number;
  vezes_do_come_cotas: number; // as vezes em que o come-cotas levou dinheiro
  ir_no_resgate: number;
  liquido: number;
}

/** A alíquota do IR no resgate: a tabela da renda fixa (longo prazo) ou a do curto prazo. */
export function aliquotaDoFundo(dias: number, longoPrazo: boolean): number {
  if (longoPrazo) return aliquotaDaRendaFixa(dias);
  if (dias < 1) throw new RangeError("O prazo da aplicação precisa ser de pelo menos 1 dia.");
  const { ate_dias, aliquotas } = regrasDeImposto.fundos.curto_prazo;
  return dias <= ate_dias ? aliquotas[0] : aliquotas[1];
}

function conferir(valor: number, meses: number, cdiAoAno: number, percentual: number, taxas: number[]): void {
  if (!(valor > 0)) throw new RangeError("O valor aplicado precisa ser maior que zero.");
  if (meses < 1 || meses > PRAZO_MAXIMO) throw new RangeError(`O prazo precisa estar entre 1 e ${PRAZO_MAXIMO} meses.`);
  if (cdiAoAno <= -1) throw new RangeError("O CDI precisa ser maior que -100% ao ano.");
  if (percentual < 0) throw new RangeError("O percentual do CDI não pode ser negativo.");
  if (taxas.some((t) => t < 0 || t >= 1)) throw new RangeError("Cada taxa do fundo precisa estar entre 0% e 100%.");
}

function rendimentoDoMes(cdiAoAno: number, percentual: number): number {
  const diaria = ((1 + cdiAoAno) ** (1 / DIAS_UTEIS_POR_ANO) - 1) * percentual;
  return (1 + diaria) ** DIAS_UTEIS_POR_MES - 1;
}

/** O mês do ano (1 a 12) do `mes`-ésimo mês da aplicação (o primeiro é o 1). */
const mesDoCalendario = (mesInicial: number, mes: number) => ((mesInicial - 1 + mes - 1) % 12) + 1;

/** O fundo durante a simulação: o patrimônio, as bases das taxas e o que já foi cobrado. */
class Carteira {
  administracao = 0;
  performance = 0;
  comeCotas = 0;
  vezes = 0;
  baseDoIr: number; // o patrimônio depois do último come-cotas que levou dinheiro
  referencia: number; // o patrimônio do começo do semestre, corrigido pelo CDI

  constructor(public patrimonio: number) {
    this.baseDoIr = patrimonio;
    this.referencia = patrimonio;
  }

  render(rendimento: number, rendimentoDoCdi: number, fica: number): void {
    this.patrimonio *= 1 + rendimento;
    this.referencia *= 1 + rendimentoDoCdi;
    const cobrada = this.patrimonio * (1 - fica);
    this.patrimonio -= cobrada;
    this.administracao += cobrada;
  }

  cobrarPerformance(taxa: number): void {
    const cobrada = taxa * Math.max(this.patrimonio - this.referencia, 0);
    this.patrimonio -= cobrada;
    this.performance += cobrada;
  }

  reterComeCotas(aliquota: number): void {
    const retido = aliquota * Math.max(this.patrimonio - this.baseDoIr, 0);
    if (retido > 0) {
      // sem ganho, a perda fica para abater do próximo
      this.patrimonio -= retido;
      this.comeCotas += retido;
      this.vezes += 1;
      this.baseDoIr = this.patrimonio;
    }
  }
}

/** O fundo aplicado com `valor` por `meses` meses (percentuais e taxas em fração). */
export function simular(
  valor: number,
  meses: number,
  cdiAoAno: number,
  percentualDoCdi: number,
  taxaDeAdministracao: number,
  taxaDePerformance: number,
  longoPrazo: boolean,
  mesInicial: number,
): Resultado {
  conferir(valor, meses, cdiAoAno, percentualDoCdi, [taxaDeAdministracao, taxaDePerformance]);
  if (mesInicial < 1 || mesInicial > 12) throw new RangeError("O mês inicial precisa estar entre 1 (janeiro) e 12.");
  const rendimento = rendimentoDoMes(cdiAoAno, percentualDoCdi);
  const rendimentoDoCdi = rendimentoDoMes(cdiAoAno, 1);
  const fica = (1 - taxaDeAdministracao) ** (1 / 12);
  const { come_cotas_longo, come_cotas_curto } = regrasDeImposto.fundos;
  const aliquotaDoComeCotas = longoPrazo ? come_cotas_longo : come_cotas_curto;
  const carteira = new Carteira(valor);
  for (let mes = 1; mes <= meses; mes++) {
    carteira.render(rendimento, rendimentoDoCdi, fica);
    const eComeCotas = MESES_DO_COME_COTAS.includes(mesDoCalendario(mesInicial, mes));
    if (eComeCotas || mes === meses) {
      carteira.cobrarPerformance(taxaDePerformance);
      if (eComeCotas) carteira.reterComeCotas(aliquotaDoComeCotas);
      carteira.referencia = carteira.patrimonio; // começa outro semestre
    }
  }
  const dias = Math.round(meses * DIAS_POR_MES);
  const ganho = carteira.patrimonio - valor + carteira.comeCotas;
  const irTotal = aliquotaDoFundo(dias, longoPrazo) * Math.max(ganho, 0);
  const irNoResgate = Math.max(irTotal - carteira.comeCotas, 0);
  return {
    patrimonio_final: carteira.patrimonio,
    taxa_de_administracao: carteira.administracao,
    taxa_de_performance: carteira.performance,
    come_cotas: carteira.comeCotas,
    vezes_do_come_cotas: carteira.vezes,
    ir_no_resgate: irNoResgate,
    liquido: carteira.patrimonio - irNoResgate,
  };
}
