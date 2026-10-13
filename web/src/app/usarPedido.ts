// Pedir uma rota da API com o token da conta, refazendo o pedido quando os parâmetros mudam.
import { useEffect, useState } from "react";
import { ErroDaApi, type Parametros, pedir } from "./api";
import { useConta } from "./conta";

export type Pedido<T> =
  | { estado: "carregando" }
  | { estado: "pronto"; dados: T }
  | { estado: "erro"; erro: ErroDaApi };

export function usarPedido<T>(rota: string, parametros: Parametros): Pedido<T> {
  const token = useConta()?.token ?? null;
  const [pedido, setPedido] = useState<Pedido<T>>({ estado: "carregando" });
  // a chave muda só quando um parâmetro muda (o objeto é recriado a cada desenho da tela)
  const chave = JSON.stringify(parametros);
  useEffect(() => {
    if (token === null) return;
    let valendo = true;
    setPedido({ estado: "carregando" });
    pedir<T>(rota, token, JSON.parse(chave) as Parametros)
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
  }, [rota, token, chave]);
  return pedido;
}
