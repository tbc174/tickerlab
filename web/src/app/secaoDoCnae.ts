// A seção do CNAE (a letra do IBGE) de um código de 5 ou 7 dígitos, pelas duas primeiras (a divisão). A busca
// "Encontrar empresas" filtra pela seção, não pelo CNAE; o Setor usa essa tabela para abrir a busca já no setor
// certo. É a mesma tabela de `base/cnae.py` (`_DIVISOES`): `tests/test_secao_do_cnae_do_app.py` confere que as
// duas não se afastam.
const DIVISOES_DA_SECAO: Record<string, [number, number]> = {
  A: [1, 3],
  B: [5, 9],
  C: [10, 33],
  D: [35, 35],
  E: [36, 39],
  F: [41, 43],
  G: [45, 47],
  H: [49, 53],
  I: [55, 56],
  J: [58, 63],
  K: [64, 66],
  L: [68, 68],
  M: [69, 75],
  N: [77, 82],
  O: [84, 84],
  P: [85, 85],
  Q: [86, 88],
  R: [90, 93],
  S: [94, 96],
  T: [97, 97],
  U: [99, 99],
};
const CNAE_DE_CLASSE_OU_SUBCLASSE = /^(\d{2})(\d{3}|\d{5})$/;

/** A letra da seção do CNAE (5 ou 7 dígitos, só números), ou `null` se o código não é de uma divisão do CNAE. */
export function secaoDoCnae(cnae: string): string | null {
  const achado = CNAE_DE_CLASSE_OU_SUBCLASSE.exec(cnae);
  if (achado === null) return null;
  const divisao = Number(achado[1]);
  const secao = Object.entries(DIVISOES_DA_SECAO).find(([, [primeira, ultima]]) => divisao >= primeira && divisao <= ultima);
  return secao?.[0] ?? null;
}
