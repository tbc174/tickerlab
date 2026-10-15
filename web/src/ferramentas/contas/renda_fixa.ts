// Renda fixa com IR: cópia em TypeScript de src/ferramentas/renda_fixa.py (a referência).
// As regras (IR, IOF e custódia) vêm de src/regras_de_imposto.py pelo conteudo/regras_de_imposto.json.
// O CDI pode mudar de um ano para o outro: cdiPorAno[k] vale do dia 365·k ao 365·(k+1).
import { regrasDeImposto } from "../../conteudo";

const DIAS_UTEIS_POR_ANO = 252;
const DIAS_POR_ANO = 365;
const DIAS_DO_ANIVERSARIO = 30;
export const DIAS_MAXIMOS = 3650;
const EMPATE_MAXIMO = 10;
const PASSOS_DO_EMPATE = 100;
const FOLGA_DO_TETO = 1e-9; // a busca que encosta no teto não achou o empate

export interface Opcao {
  nome: string;
  bruto: number;
  aliquota: number;
  imposto: number;
  liquido: number;
  iof: number;
  custodia: number;
}

/** A alíquota da tabela regressiva para `dias` dias corridos. */
export function aliquotaDaRendaFixa(dias: number): number {
  if (dias < 1) throw new RangeError("O prazo da aplicação precisa ser de pelo menos 1 dia.");
  const faixa = regrasDeImposto.renda_fixa.find((f) => f.ate_dias === null || dias <= f.ate_dias);
  if (!faixa) throw new Error("a última faixa da tabela vale para qualquer prazo");
  return faixa.aliquota;
}

/** A fração do rendimento que o IOF leva num resgate depois de `dias` dias corridos. */
export function aliquotaDoIof(dias: number): number {
  if (dias < 1) throw new RangeError("O prazo da aplicação precisa ser de pelo menos 1 dia.");
  return dias <= regrasDeImposto.iof.length ? regrasDeImposto.iof[dias - 1] : 0;
}

const diasUteis = (dias: number) => (dias * DIAS_UTEIS_POR_ANO) / DIAS_POR_ANO;

function conferir(valor: number, dias: number): void {
  if (valor < 0) throw new RangeError("O valor aplicado não pode ser negativo.");
  if (dias < 1 || dias > DIAS_MAXIMOS) throw new RangeError(`O prazo precisa estar entre 1 e ${DIAS_MAXIMOS} dias.`);
}

/** Os pedaços de até 365 dias da aplicação, cada um com a taxa do seu ano. */
function porAno(dias: number, taxas: number[]): [number, number][] {
  const pedacos: [number, number][] = [];
  for (let comeco = 0; comeco < dias; comeco += DIAS_POR_ANO) {
    const ano = Math.min(Math.floor(comeco / DIAS_POR_ANO), taxas.length - 1);
    pedacos.push([Math.min(DIAS_POR_ANO, dias - comeco), taxas[ano]]);
  }
  return pedacos;
}

function peloCdi(valor: number, dias: number, cdiPorAno: number[], percentual: number): number {
  let fator = 1;
  for (const [diasDoPedaco, cdi] of porAno(dias, cdiPorAno)) {
    const diaria = ((1 + cdi) ** (1 / DIAS_UTEIS_POR_ANO) - 1) * percentual;
    fator *= (1 + diaria) ** diasUteis(diasDoPedaco);
  }
  return valor * fator;
}

/** 0,2% ao ano sobre o saldo médio que passa da isenção, pelo prazo. */
function custodia(valor: number, bruto: number, dias: number, isentoAte: number): number {
  const saldoMedio = (valor + bruto) / 2;
  return (regrasDeImposto.custodia_do_tesouro.taxa * Math.max(saldoMedio - isentoAte, 0) * dias) / DIAS_POR_ANO;
}

/** IOF sobre o rendimento (antes de 30 dias), IR sobre o que sobra dele, custódia à parte. */
function tributado(nome: string, valor: number, bruto: number, dias: number, custo = 0): Opcao {
  const rendimento = Math.max(bruto - valor, 0);
  const iof = rendimento * aliquotaDoIof(dias);
  const aliquota = aliquotaDaRendaFixa(dias);
  const imposto = (rendimento - iof) * aliquota;
  return { nome, bruto, aliquota, imposto, liquido: bruto - iof - imposto - custo, iof, custodia: custo };
}

const isento = (nome: string, bruto: number): Opcao => ({
  nome,
  bruto,
  aliquota: 0,
  imposto: 0,
  liquido: bruto,
  iof: 0,
  custodia: 0,
});

/** As quatro opções pelo CDI, na ordem fixa: CDB, LCI ou LCA, Tesouro Selic, poupança. */
export function comparar(
  valor: number,
  dias: number,
  cdiPorAno: number[],
  percentualDoCdb: number,
  percentualDaLci: number,
  poupancaAoMes: number,
): Opcao[] {
  conferir(valor, dias);
  if (cdiPorAno.length === 0) throw new RangeError("Informe o CDI de pelo menos um ano.");
  if (percentualDoCdb < 0 || percentualDaLci < 0) throw new RangeError("O percentual do CDI não pode ser negativo.");
  const aniversarios = Math.floor(dias / DIAS_DO_ANIVERSARIO);
  const selic = peloCdi(valor, dias, cdiPorAno, 1);
  const isentoNoSelic = regrasDeImposto.custodia_do_tesouro.isento_no_selic_ate;
  return [
    tributado("CDB", valor, peloCdi(valor, dias, cdiPorAno, percentualDoCdb), dias),
    isento("LCI ou LCA", peloCdi(valor, dias, cdiPorAno, percentualDaLci)),
    tributado("Tesouro Selic", valor, selic, dias, custodia(valor, selic, dias, isentoNoSelic)),
    isento("Poupança", valor * (1 + poupancaAoMes) ** aniversarios),
  ];
}

/** O Tesouro Prefixado comprado hoje a `taxaAoAno`, levado até o fim de `dias`. */
export function tesouroPrefixado(valor: number, dias: number, taxaAoAno: number): Opcao {
  conferir(valor, dias);
  const bruto = valor * (1 + taxaAoAno) ** (diasUteis(dias) / DIAS_UTEIS_POR_ANO);
  return tributado("Tesouro Prefixado", valor, bruto, dias, custodia(valor, bruto, dias, 0));
}

/** O Tesouro IPCA+ comprado hoje a `juroReal`, com a inflação de cada ano de `ipcaPorAno`. */
export function tesouroIpca(valor: number, dias: number, juroReal: number, ipcaPorAno: number[]): Opcao {
  conferir(valor, dias);
  if (ipcaPorAno.length === 0) throw new RangeError("Informe a inflação de pelo menos um ano.");
  let fator = 1;
  for (const [diasDoPedaco, ipca] of porAno(dias, ipcaPorAno)) fator *= (1 + ipca) ** (diasDoPedaco / DIAS_POR_ANO);
  const real = (1 + juroReal) ** (diasUteis(dias) / DIAS_UTEIS_POR_ANO);
  const bruto = valor * real * fator;
  return tributado("Tesouro IPCA+", valor, bruto, dias, custodia(valor, bruto, dias, 0));
}

/** O CDI de cada ano: a Selic esperada pelo Focus para o fim daquele ano, menos a diferença de
 * hoje entre a Selic e o CDI. Depois do último ano do Focus, repete o último. */
export function cdiPeloFocus(
  cdiHoje: number,
  selicHoje: number,
  selicEsperada: Record<string, number>,
  anoInicial: number,
  anos: number,
): number[] {
  const diferenca = selicHoje - cdiHoje;
  const caminho: number[] = [];
  for (let ano = anoInicial; ano < anoInicial + anos; ano++) {
    const esperada = selicEsperada[String(ano)];
    if (esperada === undefined) caminho.push(caminho.length ? caminho[caminho.length - 1] : cdiHoje);
    else caminho.push(esperada - diferenca);
  }
  return caminho;
}

/** O percentual do CDI que um CDB precisa pagar para render, depois do IR e do IOF, o mesmo que a
 * LCI ou LCA isenta de `percentualDaLci` (busca por bisseção); null se nem 1.000% do CDI empata. */
export function pontoDeEmpate(valor: number, dias: number, cdiPorAno: number[], percentualDaLci: number): number | null {
  conferir(valor, dias);
  const alvo = peloCdi(valor, dias, cdiPorAno, percentualDaLci);
  let [baixo, alto] = [0, EMPATE_MAXIMO];
  for (let passo = 0; passo < PASSOS_DO_EMPATE; passo++) {
    const meio = (baixo + alto) / 2;
    const cdb = tributado("CDB", valor, peloCdi(valor, dias, cdiPorAno, meio), dias).liquido;
    if (cdb < alvo) baixo = meio;
    else alto = meio;
  }
  if (baixo >= EMPATE_MAXIMO * (1 - FOLGA_DO_TETO)) return null;
  return (baixo + alto) / 2;
}
