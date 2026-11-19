// O CNPJ como o analista digita ou cola: 14 posições (letras nas 12 primeiras desde 2026), com ou sem pontuação.
// Módulo sem dependências: as telas conferem o CNPJ daqui sem importar a busca do topo (que importa as rotas e,
// com elas, as próprias telas).
const PONTUACAO_DO_CNPJ = /[./\-\s]/g;
const CNPJ = /^[0-9A-Z]{12}\d{2}$/;

/** O CNPJ digitado inteiro, sem a pontuação; outro texto, null. */
export function cnpjDigitado(texto: string): string | null {
  const limpo = texto.replace(PONTUACAO_DO_CNPJ, "").toUpperCase();
  return CNPJ.test(limpo) ? limpo : null;
}
