// Textos e endereços do site público (eram constantes de scripts/gerar_site.py).

export const URL_DO_SITE = "https://tickerlab.com.br";
export const URL_DO_APP = "https://app.tickerlab.com.br";
export const URL_DO_CODIGO = "https://github.com/tbc174/tickerlab";
export const EMAIL_DE_CONTATO = "contato@tickerlab.com.br";

// Beta fechado: só contas convidadas entram (o aviso aparece no topo da página inicial)
export const BETA_FECHADO = false;
export const TICKER_DO_EXEMPLO = "PETR4.SA";

export const AVISO =
  "Nada aqui é recomendação de investimento. Os dados vêm do Yahoo " +
  "Finance e podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro.";

// a assinatura institucional do manual de identidade
export const ASSINATURA = "Menos ruído. Mais inteligência para investir.";

/** Endereço de uma página do app, com os parâmetros na ordem dada (sem codificar, como antes). */
export function linkDoApp(pagina = "", parametros: Record<string, string> = {}): string {
  const consulta = Object.entries(parametros)
    .map(([chave, valor]) => `${chave}=${valor}`)
    .join("&");
  return `${URL_DO_APP}/${pagina}` + (consulta ? `?${consulta}` : "");
}
