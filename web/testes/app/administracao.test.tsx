// @vitest-environment jsdom
// A Administração no app novo (linha 955, PR 2): as organizações da API por chave, só leitura. Quem decide
// quem entra é o servidor (404 para quem não é administrador); a tela só mostra o que a API devolve.
// Tudo inventado: nenhuma organização, chave ou conta real.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { navegador } from "../../src/app/navegador";
import type { OrganizacoesV1, PainelDaOrganizacaoV1 } from "../../src/app/tiposDaAdministracao";
import { ANA, abrirApp, respostaJson } from "./ajudantes";

const ADMIN = { ...ANA, administrador: true };
const ID_ALFA = "11111111-1111-1111-1111-111111111111";
const ID_BETA = "22222222-2222-2222-2222-222222222222";
const ROTA_DA_LISTA = "/api/v1/admin/organizacoes";
const rotaDoPainel = (id: string) => `/api/v1/admin/organizacao?id=${id}`;

const LISTA: OrganizacoesV1 = {
  organizacoes: [
    { id: ID_ALFA, nome: "Organização Alfa", plano_da_api: "piloto", nome_do_plano: "Piloto", suspensa: false },
    { id: ID_BETA, nome: "Organização Beta", plano_da_api: "piloto", nome_do_plano: "Piloto", suspensa: true },
  ],
};

const ALFA: PainelDaOrganizacaoV1 = {
  id: ID_ALFA,
  nome: "Organização Alfa",
  cnpj: null,
  plano_da_api: "piloto",
  nome_do_plano: "Piloto",
  criada_em: "2026-11-02T12:00:00Z",
  suspensa_em: null,
  motivo_da_suspensao: null,
  limites: { pedidos_por_minuto: 60, pedidos_por_mes: 20000, linhas_por_resposta: 500, chaves_ativas: 3 },
  consumo: { pedidos: 1284, linhas: 45210, negados: 7 },
  chaves_ativas: 1,
  chaves: [
    {
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      prefixo: "tld_inventada1",
      estado: "ativa",
      criada_em: "2026-11-03T09:00:00Z",
      expira_em: null,
      revogada_em: null,
      ultimo_uso: "2026-11-15T18:30:00Z",
    },
    {
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      prefixo: "tld_inventada2",
      estado: "revogada",
      criada_em: "2026-11-02T09:00:00Z",
      expira_em: null,
      revogada_em: "2026-11-03T09:00:00Z",
      ultimo_uso: null,
    },
  ],
  direitos: [
    { conjunto: "companies", finalidade: "analise", vigente_desde: "2026-11-02", vigente_ate: null },
    { conjunto: "financials", finalidade: "analise", vigente_desde: "2026-11-02", vigente_ate: "2027-11-01" },
  ],
  ainda_desligado: [
    { conjunto: "credit", finalidade: "credito", motivo: "sem_contrato" },
    { conjunto: "links", finalidade: "analise", motivo: "suspenso_para_todos" },
  ],
  pessoa_na_tela: false,
  membros: 2,
};

const BETA: PainelDaOrganizacaoV1 = {
  ...ALFA,
  id: ID_BETA,
  nome: "Organização Beta",
  suspensa_em: "2026-11-10T08:00:00Z",
  motivo_da_suspensao: "Pedido da própria organização.",
  consumo: { pedidos: 0, linhas: 0, negados: 0 },
  chaves_ativas: 0,
  chaves: [],
  direitos: [],
  ainda_desligado: [],
  pessoa_na_tela: true,
  membros: 1,
};

interface Opcoes {
  eu?: typeof ANA;
  lista?: () => Response;
  painel?: (id: string) => Response;
}

function abrir({ eu = ADMIN, lista, painel }: Opcoes = {}) {
  return abrirApp("/admin", {
    comSessao: true,
    eu: () => respostaJson(200, eu),
    rotas: (endereco) => {
      if (endereco === ROTA_DA_LISTA) return lista ? lista() : respostaJson(200, LISTA);
      if (endereco === rotaDoPainel(ID_ALFA)) return painel ? painel(ID_ALFA) : respostaJson(200, ALFA);
      if (endereco === rotaDoPainel(ID_BETA)) return painel ? painel(ID_BETA) : respostaJson(200, BETA);
      return undefined;
    },
  });
}

const pedidosDaAdministracao = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.map(([endereco]) => endereco).filter((endereco) => endereco.startsWith("/api/v1/admin"));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a Administração para o administrador", () => {
  it("abre em /admin com a primeira organização: nome, situação, plano e os números", async () => {
    const { buscar } = abrir();
    expect(await screen.findByRole("heading", { level: 1, name: "Administração" })).toBeTruthy();
    const painel = await screen.findByRole("region", { name: "Organização Alfa" });
    // os selos ficam ao lado do nome ("Ativa" também é o estado de uma chave, mais abaixo)
    const titulo = within(painel).getByRole("heading", { name: "Organização Alfa" }).parentElement!;
    expect(within(titulo).getByText("Ativa")).toBeTruthy();
    expect(within(titulo).getByText("Plano Piloto")).toBeTruthy();
    expect(within(painel).getByText("1 de 3")).toBeTruthy();
    expect(within(painel).getByText("1.284")).toBeTruthy();
    expect(within(painel).getByText(/de 20\.000 do plano/)).toBeTruthy();
    expect(within(painel).getByText("45.210")).toBeTruthy();
    expect(pedidosDaAdministracao(buscar)).toEqual([ROTA_DA_LISTA, rotaDoPainel(ID_ALFA)]);
  });

  it("mostra as chaves pelo prefixo, com o estado, e diz que o valor não aparece aqui", async () => {
    abrir();
    const chaves = await screen.findByRole("table", { name: "Chaves da organização" });
    const ativa = within(chaves).getByText("tld_inventada1").closest("tr")!;
    expect(within(ativa).getByText("Ativa")).toBeTruthy();
    expect(within(ativa).getByText("03/11/2026")).toBeTruthy();
    expect(within(ativa).getByText("15/11/2026")).toBeTruthy();
    const revogada = within(chaves).getByText("tld_inventada2").closest("tr")!;
    expect(within(revogada).getByText("Revogada")).toBeTruthy();
    expect(within(revogada).getByText("Nunca usada")).toBeTruthy();
    expect(screen.getByText(/O valor de uma chave aparece uma única vez/)).toBeTruthy();
  });

  it("mostra os direitos em vigor com a finalidade e o prazo", async () => {
    abrir();
    const direitos = await screen.findByRole("table", { name: "Direitos em vigor" });
    const semPrazo = within(direitos).getByText("companies").closest("tr")!;
    expect(within(semPrazo).getByText("Análise")).toBeTruthy();
    expect(within(semPrazo).getByText("Sem prazo")).toBeTruthy();
    const comPrazo = within(direitos).getByText("financials").closest("tr")!;
    expect(within(comPrazo).getByText("01/11/2027")).toBeTruthy();
  });

  it("mostra o que ainda está desligado, com o motivo, e o limite dessa lista", async () => {
    abrir();
    const desligados = await screen.findByRole("table", { name: "Ainda desligado" });
    const semContrato = within(desligados).getByText("credit").closest("tr")!;
    expect(within(semContrato).getByText("Crédito")).toBeTruthy();
    expect(within(semContrato).getByText("Sem contrato")).toBeTruthy();
    const suspenso = within(desligados).getByText("links").closest("tr")!;
    expect(within(suspenso).getByText("Suspenso para todos")).toBeTruthy();
    expect(screen.getByText(/Não olha se a tabela do conjunto está pronta/)).toBeTruthy();
    expect(screen.getByText(/Quem liga um direito é o dono, pelo script/)).toBeTruthy();
  });

  it("mostra a permissão de pessoa na tela só como estado, e as contas só como número", async () => {
    abrir();
    const equipe = await screen.findByRole("region", { name: "Equipe na tela" });
    expect(within(equipe).getByText("Desligada")).toBeTruthy();
    expect(within(equipe).getByText(/2 contas vinculadas/)).toBeTruthy();
    expect(within(equipe).getByText(/só do dono, pelo script/)).toBeTruthy();
    // só leitura: nenhum botão nem caixa que ligue alguma coisa
    expect(within(equipe).queryByRole("button")).toBeNull();
    expect(within(equipe).queryByRole("checkbox")).toBeNull();
  });

  it("trocar de organização pede o painel da outra: suspensa, com o motivo, e as listas vazias", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: "Organização Alfa" });
    fireEvent.change(screen.getByRole("combobox", { name: "Organização" }), { target: { value: ID_BETA } });
    const painel = await screen.findByRole("region", { name: "Organização Beta" });
    expect(within(painel).getByText("Suspensa")).toBeTruthy();
    expect(within(painel).getByText(/Suspensa em 10\/11\/2026/)).toBeTruthy();
    expect(within(painel).getByText(/Pedido da própria organização\./)).toBeTruthy();
    expect(within(painel).getByText("Nenhuma chave emitida.")).toBeTruthy();
    expect(within(painel).getByText("Nenhum direito em vigor.")).toBeTruthy();
    expect(within(painel).getByText(/Nada desligado/)).toBeTruthy();
    expect(within(painel).getByText("Ligada")).toBeTruthy();
    expect(within(painel).getByText(/1 conta vinculada/)).toBeTruthy();
    expect(pedidosDaAdministracao(buscar)).toEqual([ROTA_DA_LISTA, rotaDoPainel(ID_ALFA), rotaDoPainel(ID_BETA)]);
  });

  it("com uma organização só, não há o que escolher", async () => {
    abrir({ lista: () => respostaJson(200, { organizacoes: [LISTA.organizacoes[0]] }) });
    await screen.findByRole("region", { name: "Organização Alfa" });
    expect(screen.queryByRole("combobox", { name: "Organização" })).toBeNull();
  });

  it("sem organização nenhuma, diz isso e não pede painel", async () => {
    const { buscar } = abrir({ lista: () => respostaJson(200, { organizacoes: [] }) });
    // criar uma organização ainda é na tela antiga: a frase não pode mandar o administrador a um script
    expect(
      await screen.findByText(/Nenhuma organização cadastrada.*criar uma organização é na Administração antiga/),
    ).toBeTruthy();
    expect(pedidosDaAdministracao(buscar)).toEqual([ROTA_DA_LISTA]);
  });

  it("o painel que falha mostra o erro, sem derrubar a tela", async () => {
    abrir({ painel: () => respostaJson(500, { detail: "O TickerLab não respondeu agora." }) });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "Administração" })).toBeTruthy();
  });

  it("deixa o caminho para a Administração antiga, que continua valendo", async () => {
    abrir();
    const link = await screen.findByRole("link", { name: "Abrir a Administração antiga" });
    expect(link.getAttribute("href")).toBe("/classico/admin");
    expect(
      screen.getByText(/continuam na Administração antiga.*criar, suspender e reativar uma organização/),
    ).toBeTruthy();
  });

  it("tem a Administração no menu da conta", async () => {
    abrir();
    await screen.findByRole("heading", { level: 1, name: "Administração" });
    const link = screen.getByRole("link", { name: "Administração" });
    expect(link.getAttribute("href")).toBe("/admin");
  });
});

describe("a Administração para quem não é administrador", () => {
  it("conta comum: página não encontrada, sem nenhum pedido à Administração", async () => {
    const { buscar } = abrir({ eu: ANA });
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Administração" })).toBeNull();
    expect(pedidosDaAdministracao(buscar)).toEqual([]);
  });

  it("conta comum não vê a Administração no menu da conta", async () => {
    abrir({ eu: ANA });
    await screen.findByText(/Página não encontrada/);
    expect(screen.queryByRole("link", { name: "Administração" })).toBeNull();
  });

  it("quem o servidor recusa (404) vê página não encontrada, mesmo se a tela achava que era administrador", async () => {
    abrir({ lista: () => respostaJson(404, { detail: "Not Found" }) });
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Administração" })).toBeNull();
  });

  it("o painel recusado (404) não mostra nada da organização", async () => {
    abrir({ painel: () => respostaJson(404, { detail: "Not Found" }) });
    await screen.findByRole("heading", { level: 1, name: "Administração" });
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.queryByRole("region", { name: "Organização Alfa" })).toBeNull();
    expect(screen.queryByText("tld_inventada1")).toBeNull();
  });

  it("visitante: a página de entrada, sem nenhum pedido à Administração", async () => {
    const { buscar, google } = abrirApp("/admin", { entraSozinho: false });
    await waitFor(() => expect(google.id.initialize).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Administração" })).toBeNull();
    expect(pedidosDaAdministracao(buscar)).toEqual([]);
  });
});

describe("/admin sem a API do app novo", () => {
  it("vai para a Administração antiga (ela não depende da API)", async () => {
    const trocar = vi.spyOn(navegador, "trocar").mockImplementation(() => undefined);
    abrirApp("/admin", { configuracao: respostaJson(404, { detail: "Not Found" }), entraSozinho: false });
    const link = await screen.findByRole("link", { name: /Abrir na versão clássica/ });
    expect(link.getAttribute("href")).toBe("/classico/admin");
    // a troca de endereço sai de um efeito, que roda depois do desenho do link
    await waitFor(() => expect(trocar).toHaveBeenCalledWith("/classico/admin"));
    trocar.mockRestore();
  });
});
