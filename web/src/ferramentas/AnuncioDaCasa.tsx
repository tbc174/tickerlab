// "Anúncio da casa": os espaços que seriam de anúncio nas ferramentas divulgam o próprio TickerLab
// (decisão do Tiago na Central, 13/10/2026: sem AdSense nem anúncio de terceiros). Os links levam a
// origem no padrão da campanha (campanha-medicao.md): utm_source=site, utm_medium=casa,
// utm_campaign=ferramentas e utm_content=<a ferramenta>. Nenhum script ou cookie de terceiros.
import { TICKER_DO_EXEMPLO, linkDoApp } from "../site/textos";

interface Destino {
  titulo: string;
  texto: string;
  botao: string;
  pagina: string; // a página do app
  parametros: Record<string, string>;
}

// A lista de espera entra aqui quando a Campanha a criar (PR 2 da série dela).
export const DESTINOS = {
  ficha: {
    titulo: "Seu resultado foi sorte?",
    texto:
      "No TickerLab você testa uma regra de compra e venda no passado, com custos, e a ficha " +
      "“Foi sorte?” mostra se o resultado resiste quando tiramos o acaso da conta.",
    botao: "Testar uma estratégia",
    pagina: "backtest",
    parametros: { ticker: TICKER_DO_EXEMPLO },
  },
  cadastro: {
    titulo: "Analise ações da B3 e dos EUA",
    texto:
      "Gráficos, risco, fundamentos da CVM e testes de estratégia, com cada número explicado. " +
      "O plano Gratuito não pede cartão.",
    botao: "Criar conta grátis",
    pagina: "",
    parametros: {},
  },
} satisfies Record<string, Destino>;

export type NomeDoDestino = keyof typeof DESTINOS;

const CODIGO_SIMPLES = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** O link do anúncio, com a origem da campanha; `ferramenta` é o código da página (sem acento). */
export function linkDoAnuncio(destino: NomeDoDestino, ferramenta: string): string {
  if (!CODIGO_SIMPLES.test(ferramenta)) {
    throw new RangeError(`Código de ferramenta inválido para o link: ${ferramenta}`);
  }
  const { pagina, parametros } = DESTINOS[destino];
  return linkDoApp(pagina, {
    ...parametros,
    utm_source: "site",
    utm_medium: "casa",
    utm_campaign: "ferramentas",
    utm_content: ferramenta,
  });
}

export function AnuncioDaCasa({
  destino,
  ferramenta,
}: {
  destino: NomeDoDestino;
  ferramenta: string;
}) {
  const { titulo, texto, botao } = DESTINOS[destino];
  return (
    <aside className="anuncio-da-casa" aria-label="Do TickerLab">
      <p className="olho">Do TickerLab</p>
      <h2>{titulo}</h2>
      <p>{texto}</p>
      <a className="botao primario seta" href={linkDoAnuncio(destino, ferramenta)}>
        {botao}
      </a>
    </aside>
  );
}
