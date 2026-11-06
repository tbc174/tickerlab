// A página de uma ferramenta: topo, a calculadora (ilha), a explicação em português (o que o Google
// lê e o que a pessoa precisa para entender o número), o anúncio da casa, o aviso e as ferramentas
// que continuam a conta (continuar.ts).
import type { ReactNode } from "react";
import { TopoDaPagina } from "../site/Fundo";
import { AnuncioDaCasa, type NomeDoDestino } from "./AnuncioDaCasa";
import { AvisoDaFerramenta } from "./AvisoDaFerramenta";
import { CONTINUACOES, enderecoDaContinuacao } from "./continuar";
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
      <TopoDaPagina
        olho="Ferramentas grátis"
        linkDoOlho="/ferramentas.html"
        titulo={titulo}
        subtitulo={subtitulo}
      />
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
      <nav className="faixa secao continue-a-conta" aria-label="Continue a conta">
        <h2>Continue a conta</h2>
        <ul>
          {(CONTINUACOES[`${codigo}.html`] ?? []).map((c) => (
            <li key={c.para}>
              <a
                className="seta"
                href={enderecoDaContinuacao(c, "")}
                data-levar={JSON.stringify({ para: c.para, levar: c.levar, fixos: c.fixos })}
              >
                {c.texto}
              </a>
            </li>
          ))}
        </ul>
        <a className="seta" href="/ferramentas.html">
          Ver todas as ferramentas grátis
        </a>
      </nav>
    </>
  );
}
