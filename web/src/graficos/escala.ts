// A escala dos gráficos do site e do app: limites e marcas "redondos" (1, 2, 2,5 e 5 × 10^n) no eixo
// dos valores e, nas ferramentas, o eixo do tempo em meses (até 2 anos) ou anos (depois).

export const LINHAS_DA_GRADE = 4;
const MESES_ATE_VIRAR_ANOS = 24;
const PASSOS_EM_MESES = [1, 2, 3, 6, 12];
const PASSOS_EM_ANOS = [1, 2, 5, 10, 20, 25, 50, 100];

/** Um passo "redondo" (1, 2, 2,5, 5 ou 10 × 10^n) que divide a faixa em até `partes`. */
export function passoRedondo(faixa: number, partes: number): number {
  const bruto = faixa / partes;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const fator = [1, 2, 2.5, 5, 10].find((f) => f * potencia >= bruto) ?? 10;
  return fator * potencia;
}

/** [baixo, alto, passo] do eixo dos valores, contendo todos os valores (e a referência, se houver). */
export function limitesDoEixo(
  valores: number[],
  referencia?: number,
  linhas = LINHAS_DA_GRADE,
): [number, number, number] {
  const todos = referencia === undefined ? valores : [...valores, referencia];
  const minimo = Math.min(...todos);
  const maximo = Math.max(...todos);
  const faixa = maximo - minimo || Math.abs(maximo) || 1;
  const passo = passoRedondo(faixa, linhas);
  const baixo = Math.floor(minimo / passo) * passo;
  const alto = Math.ceil(maximo / passo) * passo;
  // todos iguais e redondos: abre meio passo para cada lado, para o eixo ter altura
  return baixo === alto ? [baixo - passo, alto + passo, passo] : [baixo, alto, passo];
}

/** As marcas do eixo do tempo, em meses desde o início: até `maximo` marcas, em passos redondos
 * (meses até 2 anos; anos inteiros depois). */
export function marcasDeMeses(meses: number, maximo = 6): number[] {
  const emAnos = meses > MESES_ATE_VIRAR_ANOS;
  const unidade = emAnos ? 12 : 1;
  const total = meses / unidade;
  const candidatos = emAnos ? PASSOS_EM_ANOS : PASSOS_EM_MESES;
  const passo = (candidatos.find((p) => total / p <= maximo - 1) ?? candidatos[candidatos.length - 1]) * unidade;
  const marcas: number[] = [];
  for (let m = 0; m <= meses; m += passo) marcas.push(m);
  return marcas;
}

/** "início", "mês 6", "ano 4", "ano 2,5": o rótulo de um ponto do eixo do tempo. */
export function rotuloDoMes(mes: number, totalDeMeses: number): string {
  if (mes === 0) return "início";
  if (totalDeMeses <= MESES_ATE_VIRAR_ANOS) return `mês ${mes}`;
  return `ano ${(mes / 12).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}`;
}

/** O ponto apontado, por extenso, para a dica: "mês 8", "6 anos e 8 meses", "10 anos". */
export function rotuloDaDica(mes: number, totalDeMeses: number): string {
  if (mes === 0) return "início";
  if (totalDeMeses <= MESES_ATE_VIRAR_ANOS) return `mês ${mes}`;
  const anos = Math.floor(mes / 12);
  const resto = mes % 12;
  const textoDosAnos = anos === 1 ? "1 ano" : `${anos} anos`;
  if (resto === 0) return textoDosAnos;
  const textoDosMeses = resto === 1 ? "1 mês" : `${resto} meses`;
  return anos === 0 ? textoDosMeses : `${textoDosAnos} e ${textoDosMeses}`;
}
