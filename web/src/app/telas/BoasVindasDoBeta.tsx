// Boas-vindas ao beta por convite (ADR 0109, item 11; linha 211): o roteiro dos 10 minutos, ligado às
// páginas do app. O texto e o roteiro vêm da API (src/beta.py): a tela só mostra.
import { Link } from "react-router";
import type { PaginaDoApp } from "../../conteudo";
import type { BoasVindasDoBetaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const SEM_PARAMETROS = {};

export function BoasVindasDoBeta({ pagina }: { pagina: PaginaDoApp }) {
  const pedido = usarPedido<BoasVindasDoBetaV1>(pagina.contrato?.rota ?? "", SEM_PARAMETROS);
  if (pedido.estado === "carregando") {
    return (
      <p className="apagado" role="status">
        Preparando o roteiro…
      </p>
    );
  }
  if (pedido.estado === "erro") return <ErroDaTela erro={pedido.erro} />;
  const dados = pedido.dados;
  return (
    <section>
      <h1>{dados.titulo}</h1>
      <p>{dados.texto_de_boas_vindas}</p>
      <h2>O roteiro de {dados.total_de_minutos} minutos</h2>
      <ol className="telas-do-app" aria-label="Roteiro do beta">
        {dados.roteiro.map((passo) => (
          <li key={passo.ordem} className="cartao">
            <Link to={`/${passo.url}`}>
              {passo.ordem}. {passo.titulo}
            </Link>
            <span className="apagado"> · {passo.minutos} min</span>
            <p className="apagado">{passo.o_que_fazer}</p>
          </li>
        ))}
      </ol>
      <h2>Sobre o beta</h2>
      <p className="apagado">{dados.sobre_o_beta}</p>
      <p className="apagado">{dados.como_responder}</p>
    </section>
  );
}
