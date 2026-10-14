// HTML pronto que entra sem passar pelo React (o símbolo em SVG e o script do tema no <head>).
// O React não escreve HTML cru sem um elemento em volta; então ele escreve uma marca
// <tl-bruto data-html="..."> e `expandirBruto` troca a marca pelo HTML depois de renderizar.

export function Bruto({ html }: { html: string }) {
  return <tl-bruto data-html={html} />;
}

const ENTIDADES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
};

/** "S&amp;P" → "S&P": desfaz as entidades que o React (e o Markdown) escrevem. */
export function desfazerEntidades(texto: string): string {
  return texto.replace(/&amp;|&lt;|&gt;|&quot;|&#x27;/g, (e) => ENTIDADES[e]);
}

export function expandirBruto(html: string): string {
  return html.replace(/<tl-bruto data-html="([^"]*)"><\/tl-bruto>/g, (_, codificado: string) =>
    desfazerEntidades(codificado),
  );
}

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "tl-bruto": { "data-html": string };
    }
  }
}
