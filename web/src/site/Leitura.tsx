// As páginas de leitura (Metodologia, Termos, Privacidade, Novidades): topo curto, sumário ao lado
// do texto e a barra de leitura no alto. O sumário sai pronto no HTML (funciona sem JavaScript e o
// Google lê os links); o movimento.js só marca a seção que está na tela.
import type { ReactNode } from "react";
import { TopoDaPagina } from "./Fundo";

export type ItemDoSumario = { id: string; texto: string };

const ENTIDADES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
};

/** "Seus direitos (LGPD, art. 18)" → "seus-direitos-lgpd-art-18" */
export function ancora(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * Dá um id a cada título `<nivel>` sem id de um HTML pronto (o dos Termos e da Privacidade, que
 * vem do Markdown) e devolve o HTML com os ids e os itens do sumário.
 */
export function ancorarTitulos(
  html: string,
  nivel: "h2" | "h3",
): { html: string; itens: ItemDoSumario[] } {
  const itens: ItemDoSumario[] = [];
  const comIds = html.replace(new RegExp(`<${nivel}>(.*?)</${nivel}>`, "gs"), (_, dentro: string) => {
    const texto = dentro
      .replace(/<[^>]+>/g, "")
      .replace(/&[#a-z0-9]+;/g, (e) => ENTIDADES[e] ?? e)
      .trim();
    let id = ancora(texto);
    while (itens.some((i) => i.id === id)) id += "-2";
    itens.push({ id, texto });
    return `<${nivel} id="${id}">${dentro}</${nivel}>`;
  });
  return { html: comIds, itens };
}

function Sumario({ itens }: { itens: ItemDoSumario[] }) {
  return (
    <nav className="v2-sumario" data-sumario="" aria-label="Nesta página">
      <p className="v2-sumario-titulo" aria-hidden="true">
        Nesta página
      </p>
      <ol>
        {itens.map((i) => (
          <li key={i.id}>
            <a href={`#${i.id}`}>{i.texto}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PaginaDeLeitura({
  olho,
  titulo,
  subtitulo,
  sumario,
  children,
}: {
  olho?: string;
  titulo: string;
  subtitulo?: string;
  sumario: ItemDoSumario[];
  children: ReactNode;
}) {
  // com uma seção só, um sumário não ajuda: o texto ocupa a largura toda
  const comSumario = sumario.length >= 2;
  return (
    <>
      <div className="v2-progresso" data-progresso="" aria-hidden="true" />
      <TopoDaPagina olho={olho} titulo={titulo} subtitulo={subtitulo} classe="v2-heroi-curto" />
      <div className={comSumario ? "faixa v2-leitura" : "faixa v2-leitura v2-leitura-simples"}>
        {comSumario ? <Sumario itens={sumario} /> : null}
        <section className="secao texto-longo v2-texto">{children}</section>
      </div>
    </>
  );
}
