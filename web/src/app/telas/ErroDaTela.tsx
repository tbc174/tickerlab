import { linkDoApp } from "../../site/textos";
import type { ErroDaApi } from "../api";
import { useConta } from "../conta";

/** O erro de um pedido da tela, com a mensagem da API (já em português). Página fora do plano
 * ganha o caminho para os planos, que ainda ficam no app atual. */
export function ErroDaTela({ erro }: { erro: ErroDaApi }) {
  const conta = useConta();
  return (
    <div role="alert">
      <p className="erro-do-app">{erro.message}</p>
      {erro.tipo === "plano" ? (
        <a className="botao primario" href={linkDoApp("planos")}>
          Conhecer os planos
        </a>
      ) : null}
      {erro.tipo === "termos" && conta ? (
        <button type="button" className="botao primario" onClick={conta.pedirAceite}>
          Ler e aceitar os termos
        </button>
      ) : null}
    </div>
  );
}
