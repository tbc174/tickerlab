import type { ErroDaApi } from "../api";

/** O erro de um pedido da tela, com a mensagem da API (já em português). */
export function ErroDaTela({ erro }: { erro: ErroDaApi }) {
  return (
    <p className="erro-do-app" role="alert">
      {erro.message}
    </p>
  );
}
