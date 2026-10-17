import { Link } from "react-router";
import { linkDoApp } from "../../site/textos";
import { FundoDoApp } from "../FundoDoApp";
import { TELAS_DO_APP } from "../rotas";
import { EstrategiasAcompanhadas } from "./workspace/Estrategias";

// o Pulse é o próprio Workspace: não entra na lista de telas embaixo dele
const TELAS_NA_LISTA = TELAS_DO_APP.filter((pagina) => pagina.chave !== "pulse");

/** O começo do app novo é o Workspace (ADR 0062): o que mudou desde a última visita e, embaixo, as
 * telas que já existem nele, cada uma com a frase de para que serve. */
export function Inicio() {
  return (
    <section>
      <FundoDoApp>
        <p className="olho">Versão nova do app</p>
        <h1>Seu Workspace</h1>
        <p>
          O que mudou desde a sua última visita, com os mesmos números do app de sempre. As outras telas
          continuam no <a href={linkDoApp()}>app atual</a>.
        </p>
      </FundoDoApp>
      <EstrategiasAcompanhadas />
      <h2>As telas novas do TickerLab</h2>
      <ul className="telas-do-app" aria-label="Telas novas">
        {TELAS_NA_LISTA.map((pagina) => (
          <li key={pagina.chave} className="cartao">
            <Link to={`/${pagina.url}`}>{pagina.titulo}</Link>
            <p className="apagado">{pagina.descricao}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
