// O endereço e o nome da Administração. Ela fica fora do mapa de páginas do bundle de propósito
// (scripts/exportar_conteudo.py não exporta página só de administrador), então o endereço mora aqui.
// Arquivo à parte, sem importar tela nenhuma: o menu da conta (conta.tsx) e as rotas (rotas.tsx) leem daqui.

export const ENDERECO_DA_ADMINISTRACAO = "admin";
export const TITULO_DA_ADMINISTRACAO = "Administração";

/** O caminho é o da Administração? (Com ou sem barra nas pontas.) */
export const eDaAdministracao = (pathname: string) =>
  pathname.replace(/^\/+|\/+$/g, "") === ENDERECO_DA_ADMINISTRACAO;
