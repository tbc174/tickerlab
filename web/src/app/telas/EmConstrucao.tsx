import type { PaginaDoApp } from "../../conteudo";
import { linkDoClassico } from "../classico";

/** Página com contrato na API, mas ainda sem a tela em React: leva à mesma página na versão clássica. */
export function EmConstrucao({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <section className="aviso-do-app">
      <h1>{pagina.titulo}</h1>
      <p>{pagina.descricao}</p>
      <p>Esta tela ainda está sendo feita na versão nova do app.</p>
      <a className="botao primario" href={linkDoClassico(pagina.url)}>
        Abrir na versão clássica
      </a>
    </section>
  );
}
