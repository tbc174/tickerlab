// O app saiu de /novo/ para a raiz de app.tickerlab.com.br (plano de 18/10; ADR 0062, Emenda 1). O
// nginx redireciona /novo para a raiz; isto é a rede de segurança no próprio app, para o favorito, o
// app instalado e o service worker antigos: mesmo caminho na raiz, e o service worker de /novo/ sai.

const CAMINHO_ANTIGO = "/novo";

/** O mesmo endereço na raiz, para quem chegou por /novo; null para quem já está na raiz. */
export function caminhoSemONovo(local: { pathname: string; search: string; hash: string }): string | null {
  const { pathname, search, hash } = local;
  if (pathname !== CAMINHO_ANTIGO && !pathname.startsWith(`${CAMINHO_ANTIGO}/`)) return null;
  const resto = pathname.slice(CAMINHO_ANTIGO.length);
  return (resto.startsWith("/") ? resto : "/") + search + hash;
}

interface Registro {
  scope: string;
  unregister(): Promise<boolean>;
}

/** Desregistra o service worker antigo (escopo /novo/); os outros ficam. */
export async function desregistrarServicoDoNovo(servico: {
  getRegistrations(): Promise<readonly Registro[]>;
}): Promise<void> {
  const registros = await servico.getRegistrations();
  await Promise.all(
    registros
      .filter((r) => new URL(r.scope).pathname === `${CAMINHO_ANTIGO}/`)
      .map((r) => r.unregister()),
  );
}
