import { Link } from "react-router";
import type { ErroDaApi } from "../api";
import { useConta } from "../conta";

/** O erro de um pedido da tela, com a mensagem da API (já em português). Página fora do plano
 * ganha o caminho para os planos; termos novos, o caminho para o aceite. */
export function ErroDaTela({ erro }: { erro: ErroDaApi }) {
  const conta = useConta();
  return (
    <div role="alert">
      <p className="erro-do-app">{erro.message}</p>
      {erro.tipo === "plano" ? (
        <Link className="botao primario" to="/planos">
          Conhecer os planos
        </Link>
      ) : null}
      {erro.tipo === "termos" && conta ? (
        <button type="button" className="botao primario" onClick={conta.pedirAceite}>
          Ler e aceitar os termos
        </button>
      ) : null}
    </div>
  );
}
