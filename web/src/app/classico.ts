// A versão clássica do app (o Streamlit), servida em app.tickerlab.com.br/classico/ desde que o app
// em React passou a ser o principal (ADR 0062, Emenda 1). Único lugar que sabe esse caminho: o service
// worker (pwa.ts) o deixa em paz, e todo link do app novo para o Streamlit sai daqui.

export const CAMINHO_DO_CLASSICO = "/classico";

/** Endereço de uma página da versão clássica, com os parâmetros na ordem dada (sem codificar, como o
 * `linkDoApp` do site). Relativo: o Streamlit está no mesmo endereço do app novo. */
export function linkDoClassico(pagina = "", parametros: Record<string, string> = {}): string {
  const consulta = Object.entries(parametros)
    .map(([chave, valor]) => `${chave}=${valor}`)
    .join("&");
  return `${CAMINHO_DO_CLASSICO}/${pagina}` + (consulta ? `?${consulta}` : "");
}
