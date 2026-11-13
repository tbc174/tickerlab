// Peça única: o erro de um pedido da tela, com a mensagem da API (já em português). Página fora do plano
// ganha o caminho para os planos; termos novos, o caminho para o aceite; com `tentarDeNovo`, o botão que
// refaz o pedido. Uma frase solta (erro que não veio da API) também serve.
import { Link } from "react-router";
import type { ErroDaApi } from "../api";
import { useConta } from "../conta";

interface Propriedades {
  erro: ErroDaApi | string;
  tentarDeNovo?(): void;
}

export function Erro({ erro, tentarDeNovo }: Propriedades) {
  const conta = useConta();
  const tipo = typeof erro === "string" ? null : erro.tipo;
  return (
    <div role="alert">
      <p className="erro-do-app">{typeof erro === "string" ? erro : erro.message}</p>
      {tipo === "plano" ? (
        <Link className="botao primario" to="/planos">
          Conhecer os planos
        </Link>
      ) : null}
      {tipo === "termos" && conta ? (
        <button type="button" className="botao primario" onClick={conta.pedirAceite}>
          Ler e aceitar os termos
        </button>
      ) : null}
      {tentarDeNovo && tipo !== "plano" && tipo !== "termos" ? (
        <button type="button" className="botao pequeno" onClick={tentarDeNovo}>
          Tentar de novo
        </button>
      ) : null}
    </div>
  );
}
