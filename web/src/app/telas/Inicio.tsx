import { Link } from "react-router";
import { linkDoClassico } from "../classico";
import { Carregando } from "../Carregando";
import { FundoDoApp } from "../FundoDoApp";
import { TELAS_DO_APP } from "../rotas";
import { ErroDaTela } from "./ErroDaTela";
import { AcontecimentosNovos } from "./workspace/Acontecimentos";
import { EstrategiasAcompanhadas } from "./workspace/Estrategias";
import { usarPulse } from "./workspace/usarPulse";
import { VariacaoDoPreco } from "./workspace/Variacao";

// o Pulse é o próprio Workspace: não entra na lista de telas embaixo dele
const TELAS_NA_LISTA = TELAS_DO_APP.filter((pagina) => pagina.chave !== "pulse");

/** Os cartões do Workspace, de um pedido só ao Pulse: enquanto ele não chega (ou se falha), um aviso só. */
function OQueMudou() {
  const pedido = usarPulse();
  if (pedido.estado !== "pronto") {
    return (
      <section className="cartao-do-workspace" aria-labelledby="titulo-do-que-mudou">
        <h2 id="titulo-do-que-mudou">O que mudou</h2>
        {pedido.estado === "carregando" ? (
          <Carregando tipo="lista" rotulo="Lendo os acontecimentos e conferindo as suas estratégias com os preços de hoje…" />
        ) : (
          <ErroDaTela erro={pedido.erro} />
        )}
      </section>
    );
  }
  return (
    <>
      <p className="apagado">{pedido.dados.janela.texto}</p>
      <AcontecimentosNovos dados={pedido.dados} />
      <VariacaoDoPreco dados={pedido.dados} />
      <EstrategiasAcompanhadas dados={pedido.dados} />
    </>
  );
}

/** O começo do app novo é o Workspace (ADR 0062): o que mudou desde a última visita e, embaixo, as
 * telas que já existem nele, cada uma com a frase de para que serve. */
export function Inicio() {
  return (
    <section>
      <FundoDoApp>
        <p className="olho">Versão nova do app</p>
        <h1>Seu Workspace</h1>
        <p>
          O que mudou desde a sua última visita, com os mesmos números da versão clássica. As outras telas
          continuam no <a href={linkDoClassico()}>versão clássica</a>.
        </p>
      </FundoDoApp>
      <OQueMudou />
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
