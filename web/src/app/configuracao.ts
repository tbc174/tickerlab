// A API de leitura está ligada neste endereço? O app novo só funciona com ela (ADR 0048, item 5).
import { useEffect, useState } from "react";

// a tela e a API no mesmo endereço (app.tickerlab.com.br/api/v1): sem CORS
export const PREFIXO_DA_API = "/api/v1";

export type EstadoDaApi =
  | { estado: "carregando" }
  | { estado: "desligada" } // 404, ou o endereço ainda não leva à API (responde outra coisa)
  | { estado: "fora do ar" }
  | { estado: "ligada"; googleClientId: string | null };

/** Lê `/api/v1/configuracao` (sem token): o client ID do Google, se a API estiver ligada. */
export async function lerConfiguracao(): Promise<EstadoDaApi> {
  let resposta: Response;
  try {
    resposta = await fetch(`${PREFIXO_DA_API}/configuracao`);
  } catch {
    return { estado: "fora do ar" };
  }
  const json = (resposta.headers.get("content-type") ?? "").includes("application/json");
  if (resposta.status === 404 || (resposta.ok && !json)) return { estado: "desligada" };
  if (!resposta.ok) return { estado: "fora do ar" };
  const dados = (await resposta.json()) as { google_client_id: string | null };
  return { estado: "ligada", googleClientId: dados.google_client_id };
}

export function useConfiguracao(): EstadoDaApi {
  const [estado, setEstado] = useState<EstadoDaApi>({ estado: "carregando" });
  useEffect(() => {
    let valendo = true;
    void lerConfiguracao().then((lido) => {
      if (valendo) setEstado(lido);
    });
    return () => {
      valendo = false;
    };
  }, []);
  return estado;
}
