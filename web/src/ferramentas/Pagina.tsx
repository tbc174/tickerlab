// A página de uma ferramenta: topo, a calculadora (ilha), a explicação em português (o que o Google
// lê e o que a pessoa precisa para entender o número), o anúncio da casa e o aviso.
import type { ReactNode } from "react";
import { TopoDaPagina } from "../site/Fundo";
import { AnuncioDaCasa, type NomeDoDestino } from "./AnuncioDaCasa";
import { AvisoDaFerramenta } from "./AvisoDaFerramenta";
import { Ilha, type NomeDaFerramenta } from "./registro";

export function PaginaDeFerramenta({
  titulo,
  subtitulo,
  ilha,
  codigo,
  anuncio,
  foraDaConta,
  fonte,
  children,
}: {
  titulo: string;
  subtitulo: string;
  // uma calculadora, ou várias com um título cada ([nome, título])
  ilha: NomeDaFerramenta | [NomeDaFerramenta, string][];
  codigo: string; // o nome do arquivo sem ".html": vai no link do anúncio (utm_content)
  anuncio: NomeDoDestino;
  foraDaConta: string[];
  fonte?: string;
  children: ReactNode; // a explicação
}) {
  return (
    <>
      <TopoDaPagina olho="Ferramentas grátis" titulo={titulo} subtitulo={subtitulo} />
      <section className="faixa secao ferramenta-secao" aria-label={titulo}>
        {typeof ilha === "string" ? (
          <Ilha nome={ilha} />
        ) : (
          ilha.map(([nome, tituloDaIlha]) => (
            <div className="ferramenta-bloco" key={nome}>
              <h2>{tituloDaIlha}</h2>
              <Ilha nome={nome} />
            </div>
          ))
        )}
        <AvisoDaFerramenta foraDaConta={foraDaConta} fonte={fonte} />
      </section>
      <section className="faixa secao ferramenta-explicacao">
        <div className="ferramenta-texto">{children}</div>
        <AnuncioDaCasa destino={anuncio} ferramenta={codigo} />
      </section>
      <nav className="faixa secao" aria-label="Outras ferramentas">
        <a className="seta" href="/ferramentas.html">
          Ver todas as ferramentas grátis
        </a>
      </nav>
    </>
  );
}
