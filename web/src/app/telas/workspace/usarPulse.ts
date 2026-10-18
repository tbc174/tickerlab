// O pedido ao Pulse do Workspace: um só para os três cartões, porque abrir o Pulse marca a visita.
//
// Sem sessão no servidor, a aba guarda o início da janela que mostrou e o reenvia em `desde` no F5: senão a
// janela encolheria para os segundos desde a visita que ela mesma marcou.
import { useEffect, useState } from "react";
import type { PulseV1 } from "../../tipos";
import { type Pedido, usarPedido } from "../../usarPedido";

const ROTA_DO_PULSE = "/v1/pulse";
const CHAVE_DA_JANELA = "tickerlab.workspace.inicio-da-janela";

/** O início da janela que esta aba já mostrou (o sessionStorage pode faltar: aba anônima, bloqueio). */
function inicioGuardado(): string | undefined {
  try {
    const guardado = sessionStorage.getItem(CHAVE_DA_JANELA);
    return guardado && !Number.isNaN(Date.parse(guardado)) ? guardado : undefined;
  } catch {
    return undefined;
  }
}

function guardarInicio(inicio: string) {
  try {
    sessionStorage.setItem(CHAVE_DA_JANELA, inicio);
  } catch {
    // sem sessionStorage, o F5 volta à janela desde a última visita: nada quebra
  }
}

export function usarPulse(): Pedido<PulseV1> {
  // lido uma vez só: os parâmetros não mudam depois, e a página pede o Pulse uma vez
  const [parametros] = useState(() => ({ desde: inicioGuardado() }));
  const pedido = usarPedido<PulseV1>(ROTA_DO_PULSE, parametros);
  const inicio = pedido.estado === "pronto" ? pedido.dados.janela.inicio : null;
  useEffect(() => {
    if (inicio !== null) guardarInicio(inicio);
  }, [inicio]);
  return pedido;
}
