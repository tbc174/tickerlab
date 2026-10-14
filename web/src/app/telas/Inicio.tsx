import { Link } from "react-router";
import { linkDoApp } from "../../site/textos";
import { FundoDoApp } from "../FundoDoApp";
import { TELAS_DO_APP } from "../rotas";

/** O começo do app novo: as telas que já existem nele, cada uma com a frase de para que serve. */
export function Inicio() {
  return (
    <section>
      <FundoDoApp>
        <p className="olho">Versão nova do app</p>
        <h1>As telas novas do TickerLab</h1>
        <p>
          Os mesmos números do app de sempre, numa interface nova. As outras telas continuam no{" "}
          <a href={linkDoApp()}>app atual</a>.
        </p>
      </FundoDoApp>
      <ul className="telas-do-app">
        {TELAS_DO_APP.map((pagina) => (
          <li key={pagina.chave} className="cartao">
            <Link to={`/${pagina.url}`}>{pagina.titulo}</Link>
            <p className="apagado">{pagina.descricao}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
