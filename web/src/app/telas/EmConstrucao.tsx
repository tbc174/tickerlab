import type { PaginaDoApp } from "../../conteudo";
import { linkDoApp } from "../../site/textos";

/** Página com contrato na API, mas ainda sem a tela em React: leva à mesma página no app atual. */
export function EmConstrucao({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <section className="aviso-do-app">
      <h1>{pagina.titulo}</h1>
      <p>{pagina.descricao}</p>
      <p>Esta tela ainda está sendo feita na versão nova do app.</p>
      <a className="botao primario" href={linkDoApp(pagina.url)}>
        Abrir no app atual
      </a>
    </section>
  );
}
