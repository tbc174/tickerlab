// Pedir uma rota da API com o token da conta (GET, ou POST com `corpo`), refazendo o pedido quando
// os parâmetros ou o corpo mudam.
import { useEffect, useState } from "react";
import { ErroDaApi, type Parametros, pedir } from "./api";
import { useConta } from "./conta";

export type Pedido<T> =
  | { estado: "carregando" }
  | { estado: "pronto"; dados: T }
  | { estado: "erro"; erro: ErroDaApi };

export function usarPedido<T>(rota: string, parametros: Parametros, corpo?: unknown): Pedido<T> {
  const token = useConta()?.token ?? null;
  const [pedido, setPedido] = useState<Pedido<T>>({ estado: "carregando" });
  // a chave muda só quando um parâmetro muda (o objeto é recriado a cada desenho da tela)
  const chave = JSON.stringify(parametros);
  const chaveDoCorpo = corpo === undefined ? "" : JSON.stringify(corpo);
  useEffect(() => {
    if (token === null) return;
    let valendo = true;
    setPedido({ estado: "carregando" });
    const corpoDoPedido = chaveDoCorpo === "" ? undefined : JSON.parse(chaveDoCorpo);
    pedir<T>(rota, token, JSON.parse(chave) as Parametros, corpoDoPedido)
      .then((dados) => {
        if (valendo) setPedido({ estado: "pronto", dados });
      })
      .catch((falha: unknown) => {
        if (!valendo) return;
        const erro = falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha));
        setPedido({ estado: "erro", erro });
      });
    return () => {
      valendo = false;
    };
  }, [rota, token, chave, chaveDoCorpo]);
  return pedido;
}
