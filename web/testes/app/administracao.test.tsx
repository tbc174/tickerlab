// @vitest-environment jsdom
// A Administração no app novo (linha 955, PRs 2 e 3): as organizações da API por chave, com as ações de
// criar, suspender e reativar a organização e de emitir, trocar e revogar chaves. Quem decide quem entra e o
// que vale é o servidor (404 para quem não é administrador); a tela só mostra o que a API devolve.
// Tudo inventado: nenhuma organização, chave ou conta real (o "valor" de chave daqui não abre nada).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { navegador } from "../../src/app/navegador";
import type {
  ChaveNovaV1,
  OrganizacaoDaListaV1,
  OrganizacoesV1,
  PainelDaOrganizacaoV1,
} from "../../src/app/tiposDaAdministracao";
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
  planos_da_api: [{ plano_da_api: "piloto", nome_do_plano: "Piloto" }],
  motivos_da_suspensao: ["contrato", "pagamento", "abuso", "pedido_do_cliente", "fonte"],
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
  motivo_da_suspensao: "pedido_do_cliente",
  consumo: { pedidos: 0, linhas: 0, negados: 0 },
  chaves_ativas: 0,
  chaves: [],
  direitos: [],
  ainda_desligado: [],
  pessoa_na_tela: true,
  membros: 1,
};

const PAINEIS: Record<string, PainelDaOrganizacaoV1> = { [ID_ALFA]: ALFA, [ID_BETA]: BETA };
const INICIO_DO_PAINEL = "/api/v1/admin/organizacao?id=";

interface Opcoes {
  eu?: typeof ANA;
  lista?: () => Response;
  painel?: (id: string) => Response | undefined;
  // os pedidos que mudam alguma coisa (POST): endereço e corpo → resposta
  mudar?: (endereco: string, corpo: unknown) => Response | undefined;
}

const painelPadrao = (id: string) => (PAINEIS[id] ? respostaJson(200, PAINEIS[id]) : undefined);

function abrir({ eu = ADMIN, lista, painel = painelPadrao, mudar }: Opcoes = {}) {
  return abrirApp("/admin", {
    comSessao: true,
    eu: () => respostaJson(200, eu),
    rotas: (endereco, pedido) => {
      if (pedido?.method === "POST") return mudar?.(endereco, JSON.parse(String(pedido.body)));
      if (endereco === ROTA_DA_LISTA) return lista ? lista() : respostaJson(200, LISTA);
      if (endereco.startsWith(INICIO_DO_PAINEL)) return painel(endereco.slice(INICIO_DO_PAINEL.length));
      return undefined;
    },
  });
}

type Buscar = ReturnType<typeof abrir>["buscar"];

const daAdministracao = (endereco: string) => endereco.startsWith("/api/v1/admin");

const pedidosDaAdministracao = (buscar: Buscar) =>
  buscar.mock.calls.map(([endereco]) => endereco).filter(daAdministracao);

/** Os pedidos que mudam alguma coisa, na ordem: o endereço e o corpo que a tela mandou. */
const escritas = (buscar: Buscar) =>
  buscar.mock.calls
    .filter(([endereco, pedido]) => daAdministracao(endereco) && pedido?.method === "POST")
    .map(([endereco, pedido]) => ({ endereco, corpo: JSON.parse(String(pedido?.body)) as unknown }));

const quantasVezes = (buscar: Buscar, endereco: string) =>
  buscar.mock.calls.filter(([pedido, opcoes]) => pedido === endereco && opcoes?.method !== "POST").length;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "clipboard");
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
    // lendo a tela, nenhum valor de chave: só os prefixos
    expect(screen.queryByRole("region", { name: "Chave nova" })).toBeNull();
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
    // só o estado: nenhum botão nem caixa que ligue alguma coisa
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
    expect(within(painel).getByText(/Motivo: Pedido do cliente\./)).toBeTruthy();
    expect(within(painel).getByText("Nenhuma chave emitida.")).toBeTruthy();
    expect(within(painel).getByText("Nenhum direito em vigor.")).toBeTruthy();
    expect(within(painel).getByText(/Nada desligado/)).toBeTruthy();
    expect(within(painel).getByText("Ligada")).toBeTruthy();
    expect(within(painel).getByText(/1 conta vinculada/)).toBeTruthy();
    expect(pedidosDaAdministracao(buscar)).toEqual([ROTA_DA_LISTA, rotaDoPainel(ID_ALFA), rotaDoPainel(ID_BETA)]);
  });

  it("com uma organização só, não há o que escolher", async () => {
    abrir({ lista: () => respostaJson(200, { ...LISTA, organizacoes: [LISTA.organizacoes[0]] }) });
    await screen.findByRole("region", { name: "Organização Alfa" });
    expect(screen.queryByRole("combobox", { name: "Organização" })).toBeNull();
  });

  it("sem organização nenhuma, diz isso, já abre o formulário de criar e não pede painel", async () => {
    const { buscar } = abrir({ lista: () => respostaJson(200, { ...LISTA, organizacoes: [] }) });
    expect(await screen.findByText(/Nenhuma organização cadastrada\. Crie a primeira/)).toBeTruthy();
    expect(screen.getByRole("form", { name: "Nova organização" })).toBeTruthy();
    expect(screen.queryByText(/criar uma organização é na Administração antiga/)).toBeNull();
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
    // o que ainda não veio para cá: contas, registro, eventos de cobrança e acervo
    expect(screen.getByText(/os eventos de cobrança e o acervo continuam na Administração antiga\./)).toBeTruthy();
    expect(screen.queryByText(/assim como criar, suspender e reativar/)).toBeNull();
  });

  it("tem a Administração no menu da conta", async () => {
    abrir();
    await screen.findByRole("heading", { level: 1, name: "Administração" });
    const link = screen.getByRole("link", { name: "Administração" });
    expect(link.getAttribute("href")).toBe("/admin");
  });
});

// --- as ações (PR 3) --------------------------------------------------------------------------

const ROTA_DE_SUSPENDER = "/api/v1/admin/organizacao/suspender";
const ROTA_DE_REATIVAR = "/api/v1/admin/organizacao/reativar";
const ROTA_DE_EMITIR = "/api/v1/admin/chaves/emitir";
const ROTA_DE_TROCAR = "/api/v1/admin/chaves/rotacionar";
const ROTA_DE_REVOGAR = "/api/v1/admin/chaves/revogar";
const ID_DA_CHAVE_ATIVA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const ID_GAMA = "33333333-3333-3333-3333-333333333333";
const CNPJ_INVENTADO = "11.222.333/0001-81";
const GAMA: OrganizacaoDaListaV1 = {
  id: ID_GAMA,
  nome: "Organização Gama",
  plano_da_api: "piloto",
  nome_do_plano: "Piloto",
  suspensa: false,
};
// inventada: não é nem nunca foi uma chave de verdade
const CHAVE_NOVA: ChaveNovaV1 = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  prefixo: "tld_inventada3",
  valor: "tld_inventada3_valor-de-mentira-so-do-teste",
  antiga_vale_por_dias: null,
};
const RECUSA_DO_SERVIDOR = { detail: "Not Found" };

const guardado = () => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });

async function abrirFormularioDeCriar() {
  await screen.findByRole("region", { name: "Organização Alfa" });
  fireEvent.click(screen.getByRole("button", { name: "Nova organização" }));
  return screen.getByRole("form", { name: "Nova organização" });
}

function preencher(formulario: HTMLElement, nome: string, cnpj = "") {
  fireEvent.change(within(formulario).getByLabelText("Nome"), { target: { value: nome } });
  fireEvent.change(within(formulario).getByLabelText("CNPJ (opcional)"), { target: { value: cnpj } });
}

describe("criar uma organização", () => {
  it("manda nome, CNPJ e plano, recarrega a lista e abre a organização criada", async () => {
    let criada = false;
    const { buscar } = abrir({
      lista: () => respostaJson(200, criada ? { ...LISTA, organizacoes: [...LISTA.organizacoes, GAMA] } : LISTA),
      painel: (id) => (id === ID_GAMA ? respostaJson(200, { ...BETA, ...GAMA, suspensa_em: null }) : painelPadrao(id)),
      mudar: (endereco) => {
        if (endereco !== ROTA_DA_LISTA) return undefined;
        criada = true;
        return respostaJson(200, GAMA);
      },
    });
    const formulario = await abrirFormularioDeCriar();
    preencher(formulario, "  Organização Gama ", CNPJ_INVENTADO);
    fireEvent.click(within(formulario).getByRole("button", { name: "Criar organização" }));
    expect(await screen.findByRole("region", { name: "Organização Gama" })).toBeTruthy();
    expect(escritas(buscar)).toEqual([
      { endereco: ROTA_DA_LISTA, corpo: { nome: "Organização Gama", cnpj: CNPJ_INVENTADO, plano_da_api: "piloto" } },
    ]);
    expect(screen.getByText("Organização criada: Organização Gama.")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Nova organização" })).toBeNull();
    expect((screen.getByRole("combobox", { name: "Organização" }) as HTMLSelectElement).value).toBe(ID_GAMA);
    expect(quantasVezes(buscar, ROTA_DA_LISTA)).toBe(2);
  });

  it("sem CNPJ, manda nulo", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, GAMA) });
    const formulario = await abrirFormularioDeCriar();
    preencher(formulario, "Organização Gama");
    fireEvent.click(within(formulario).getByRole("button", { name: "Criar organização" }));
    await waitFor(() => expect(escritas(buscar)).toHaveLength(1));
    expect(escritas(buscar)[0].corpo).toEqual({ nome: "Organização Gama", cnpj: null, plano_da_api: "piloto" });
  });

  it("o pedido leva a marca de que saiu do próprio app (a trava contra pedido de fora)", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, GAMA) });
    const formulario = await abrirFormularioDeCriar();
    preencher(formulario, "Organização Gama");
    fireEvent.click(within(formulario).getByRole("button", { name: "Criar organização" }));
    await waitFor(() => expect(escritas(buscar)).toHaveLength(1));
    const [, pedido] = buscar.mock.calls.find(([, opcoes]) => opcoes?.method === "POST")!;
    expect((pedido?.headers as Record<string, string>)["X-TickerLab-Pedido"]).toBe("1");
  });

  it("sem nome, o botão não manda nada", async () => {
    const { buscar } = abrir();
    const formulario = await abrirFormularioDeCriar();
    preencher(formulario, "   ");
    const criar = within(formulario).getByRole("button", { name: "Criar organização" }) as HTMLButtonElement;
    expect(criar.disabled).toBe(true);
    fireEvent.submit(formulario);
    expect(escritas(buscar)).toEqual([]);
  });

  it("a recusa do servidor aparece com a frase dele, e o formulário fica como estava", async () => {
    abrir({ mudar: () => respostaJson(409, { detail: "Já existe uma organização com este CNPJ." }) });
    const formulario = await abrirFormularioDeCriar();
    preencher(formulario, "Organização Gama", CNPJ_INVENTADO);
    fireEvent.click(within(formulario).getByRole("button", { name: "Criar organização" }));
    expect(await within(formulario).findByText("Já existe uma organização com este CNPJ.")).toBeTruthy();
    expect((within(formulario).getByLabelText("Nome") as HTMLInputElement).value).toBe("Organização Gama");
    expect(screen.queryByText(/Organização criada/)).toBeNull();
  });
});

describe("suspender e reativar uma organização", () => {
  it("suspender pede confirmação antes; confirmando, manda o motivo e recarrega o painel e a lista", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, { mudou: true }) });
    const painel = await screen.findByRole("region", { name: "Organização Alfa" });
    const suspensao = within(painel).getByRole("region", { name: "Suspensão" });
    fireEvent.change(within(suspensao).getByLabelText("Motivo"), { target: { value: "pagamento" } });
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender organização" }));
    // o primeiro clique só pergunta
    expect(within(suspensao).getByText(/Suspender Organização Alfa\?/)).toBeTruthy();
    expect(escritas(buscar)).toEqual([]);
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender mesmo" }));
    expect(await screen.findByText("Organização suspensa: nenhuma chave entra.")).toBeTruthy();
    expect(escritas(buscar)).toEqual([{ endereco: ROTA_DE_SUSPENDER, corpo: { id: ID_ALFA, motivo: "pagamento" } }]);
    await waitFor(() => expect(quantasVezes(buscar, rotaDoPainel(ID_ALFA))).toBe(2));
    expect(quantasVezes(buscar, ROTA_DA_LISTA)).toBe(2);
  });

  it("os motivos vêm da lista do servidor, com nome por extenso", async () => {
    abrir();
    const suspensao = await screen.findByRole("region", { name: "Suspensão" });
    const opcoes = within(within(suspensao).getByLabelText("Motivo")).getAllByRole("option");
    expect(opcoes.map((opcao) => (opcao as HTMLOptionElement).value)).toEqual(LISTA.motivos_da_suspensao);
    expect(opcoes.map((opcao) => opcao.textContent)).toContain("Pedido do cliente");
  });

  it("cancelar a confirmação não manda nada", async () => {
    const { buscar } = abrir();
    const suspensao = await screen.findByRole("region", { name: "Suspensão" });
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender organização" }));
    fireEvent.click(within(suspensao).getByRole("button", { name: "Cancelar" }));
    expect(within(suspensao).queryByRole("button", { name: "Suspender mesmo" })).toBeNull();
    expect(escritas(buscar)).toEqual([]);
  });

  it("quando o servidor diz que nada mudou, a tela diz o mesmo", async () => {
    abrir({ mudar: () => respostaJson(200, { mudou: false }) });
    const suspensao = await screen.findByRole("region", { name: "Suspensão" });
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender organização" }));
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender mesmo" }));
    expect(await screen.findByText("Nada mudou: já estava assim.")).toBeTruthy();
    expect(screen.queryByText(/Organização suspensa: nenhuma chave entra/)).toBeNull();
  });

  it("a organização suspensa tem o reativar, também com confirmação", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, { mudou: true }) });
    await screen.findByRole("region", { name: "Organização Alfa" });
    fireEvent.change(screen.getByRole("combobox", { name: "Organização" }), { target: { value: ID_BETA } });
    const painel = await screen.findByRole("region", { name: "Organização Beta" });
    const suspensao = within(painel).getByRole("region", { name: "Suspensão" });
    expect(within(suspensao).queryByRole("button", { name: "Suspender organização" })).toBeNull();
    fireEvent.click(within(suspensao).getByRole("button", { name: "Reativar organização" }));
    expect(escritas(buscar)).toEqual([]);
    fireEvent.click(within(suspensao).getByRole("button", { name: "Reativar mesmo" }));
    expect(await screen.findByText("Organização reativada: as chaves voltam.")).toBeTruthy();
    expect(escritas(buscar)).toEqual([{ endereco: ROTA_DE_REATIVAR, corpo: { id: ID_BETA } }]);
  });

  it("motivo fora da lista: a frase do servidor aparece, e nada é dado como feito", async () => {
    abrir({ mudar: () => respostaJson(422, { detail: "Motivo da suspensão fora da lista." }) });
    const suspensao = await screen.findByRole("region", { name: "Suspensão" });
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender organização" }));
    fireEvent.click(within(suspensao).getByRole("button", { name: "Suspender mesmo" }));
    expect(await screen.findByText("Motivo da suspensão fora da lista.")).toBeTruthy();
    expect(screen.queryByText(/Organização suspensa: nenhuma chave entra/)).toBeNull();
  });
});

describe("emitir, trocar e revogar chaves", () => {
  it("emitir mostra o valor uma vez, com o aviso, e recarrega o painel", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    const painel = await screen.findByRole("region", { name: "Organização Alfa" });
    expect(screen.queryByText(CHAVE_NOVA.valor)).toBeNull();
    fireEvent.click(within(painel).getByRole("button", { name: "Emitir chave nova" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    expect(within(caixa).getByText(CHAVE_NOVA.valor)).toBeTruthy();
    expect(within(caixa).getByText(/Chave emitida \(prefixo tld_inventada3\)/)).toBeTruthy();
    expect(within(caixa).getByText(/Esta chave aparece só agora: copie e entregue ao cliente/)).toBeTruthy();
    expect(escritas(buscar)).toEqual([{ endereco: ROTA_DE_EMITIR, corpo: { organizacao_id: ID_ALFA } }]);
    await waitFor(() => expect(quantasVezes(buscar, rotaDoPainel(ID_ALFA))).toBe(2));
    // o painel recarregou e a chave continua na tela, até a pessoa tirar
    expect(screen.getByText(CHAVE_NOVA.valor)).toBeTruthy();
  });

  it("dois cliques seguidos em emitir mandam um pedido só (não saem duas chaves)", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    const emitir = await screen.findByRole("button", { name: "Emitir chave nova" });
    fireEvent.click(emitir);
    fireEvent.click(emitir);
    await screen.findByRole("region", { name: "Chave nova" });
    expect(escritas(buscar)).toHaveLength(1);
  });

  it("o valor fica só na tela: nada no armazenamento do navegador nem no endereço", async () => {
    const antes = guardado();
    abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    await screen.findByRole("region", { name: "Chave nova" });
    expect(guardado()).toBe(antes);
    expect(guardado()).not.toContain(CHAVE_NOVA.valor);
    expect(window.location.href).not.toContain(CHAVE_NOVA.valor);
  });

  it("tirar da tela apaga o valor; não há como ver de novo", async () => {
    abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    fireEvent.click(within(caixa).getByRole("button", { name: "Já copiei: tirar da tela" }));
    expect(screen.queryByRole("region", { name: "Chave nova" })).toBeNull();
    expect(screen.queryByText(CHAVE_NOVA.valor)).toBeNull();
  });

  it("com uma chave na tela, não dá para emitir nem trocar outra (o valor dela sumiria sem aviso)", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    expect(within(caixa).getByText(/some se você trocar de organização ou sair desta tela/)).toBeTruthy();
    const botao = (nome: string) => screen.getByRole("button", { name: nome }) as HTMLButtonElement;
    // revogar não mostra valor nenhum: volta a valer assim que o pedido termina
    await waitFor(() => expect(botao("Revogar a chave tld_inventada1").disabled).toBe(false));
    expect(botao("Emitir chave nova").disabled).toBe(true);
    expect(botao("Trocar a chave tld_inventada1").disabled).toBe(true);
    expect(screen.getByText(/Tire a chave nova da tela para emitir ou trocar outra/)).toBeTruthy();
    fireEvent.click(botao("Emitir chave nova"));
    expect(escritas(buscar)).toHaveLength(1);
    fireEvent.click(within(caixa).getByRole("button", { name: "Já copiei: tirar da tela" }));
    expect(botao("Emitir chave nova").disabled).toBe(false);
    expect(botao("Trocar a chave tld_inventada1").disabled).toBe(false);
    expect(screen.queryByText(/Tire a chave nova da tela/)).toBeNull();
  });

  it("com uma chave na tela, não dá para criar organização (abrir a criada apagaria o valor sem aviso)", async () => {
    const { buscar } = abrir({
      mudar: (endereco) => respostaJson(200, endereco === ROTA_DE_EMITIR ? CHAVE_NOVA : GAMA),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    fireEvent.click(screen.getByRole("button", { name: "Nova organização" }));
    const formulario = screen.getByRole("form", { name: "Nova organização" });
    preencher(formulario, "Organização Gama");
    const criar = within(formulario).getByRole("button", { name: "Criar organização" }) as HTMLButtonElement;
    expect(criar.disabled).toBe(true);
    expect(within(formulario).getByText(/Copie a chave nova e tire-a da tela antes de criar/)).toBeTruthy();
    // nem o Enter no campo manda o pedido
    fireEvent.submit(formulario);
    expect(escritas(buscar)).toHaveLength(1);
    expect(screen.getByText(CHAVE_NOVA.valor)).toBeTruthy();
    fireEvent.click(within(caixa).getByRole("button", { name: "Já copiei: tirar da tela" }));
    expect(criar.disabled).toBe(false);
    expect(within(formulario).queryByText(/Copie a chave nova e tire-a da tela antes de criar/)).toBeNull();
    fireEvent.click(criar);
    await waitFor(() => expect(escritas(buscar)).toHaveLength(2));
  });

  it("trocar de organização tira a chave da tela", async () => {
    abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    await screen.findByRole("region", { name: "Chave nova" });
    fireEvent.change(screen.getByRole("combobox", { name: "Organização" }), { target: { value: ID_BETA } });
    await screen.findByRole("region", { name: "Organização Beta" });
    expect(screen.queryByText(CHAVE_NOVA.valor)).toBeNull();
  });

  it("se recarregar o painel falhar, a chave recém-emitida não some", async () => {
    let emitida = false;
    abrir({
      painel: (id) => (emitida ? respostaJson(500, { detail: "O TickerLab não respondeu agora." }) : painelPadrao(id)),
      mudar: () => {
        emitida = true;
        return respostaJson(200, CHAVE_NOVA);
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    expect(await screen.findByText("O TickerLab não respondeu agora.")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Chave nova" })).getByText(CHAVE_NOVA.valor)).toBeTruthy();
  });

  it("copiar manda o valor para a área de transferência", async () => {
    const escrever = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: escrever }, configurable: true });
    abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    fireEvent.click(within(caixa).getByRole("button", { name: "Copiar a chave" }));
    expect(await within(caixa).findByText(/Copiada\./)).toBeTruthy();
    expect(escrever).toHaveBeenCalledWith(CHAVE_NOVA.valor);
  });

  it("sem área de transferência, diz para selecionar o texto", async () => {
    abrir({ mudar: () => respostaJson(200, CHAVE_NOVA) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    fireEvent.click(within(caixa).getByRole("button", { name: "Copiar a chave" }));
    expect(await within(caixa).findByText(/Não deu para copiar; selecione o texto/)).toBeTruthy();
  });

  it("a recusa de emitir (limite do plano, organização suspensa) mostra a frase do servidor, sem chave", async () => {
    abrir({ mudar: () => respostaJson(409, { detail: "O plano permite até 3 chaves ativas." }) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    expect(await screen.findByText("O plano permite até 3 chaves ativas.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Chave nova" })).toBeNull();
  });

  it("trocar pede confirmação e depois mostra a chave nova e o prazo da antiga", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, { ...CHAVE_NOVA, antiga_vale_por_dias: 7 }) });
    const chaves = await screen.findByRole("table", { name: "Chaves da organização" });
    fireEvent.click(within(chaves).getByRole("button", { name: "Trocar a chave tld_inventada1" }));
    expect(screen.getByText(/Trocar a chave tld_inventada1\?/)).toBeTruthy();
    expect(escritas(buscar)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Trocar mesmo" }));
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    expect(within(caixa).getByText(/Chave rotacionada: a antiga vale mais 7 dias \(prefixo tld_inventada3\)/)).toBeTruthy();
    expect(within(caixa).getByText(CHAVE_NOVA.valor)).toBeTruthy();
    expect(escritas(buscar)).toEqual([
      { endereco: ROTA_DE_TROCAR, corpo: { organizacao_id: ID_ALFA, chave_id: ID_DA_CHAVE_ATIVA } },
    ]);
  });

  it("revogar pede confirmação; confirmando, manda a chave e a organização juntas", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(200, { mudou: true }) });
    const chaves = await screen.findByRole("table", { name: "Chaves da organização" });
    fireEvent.click(within(chaves).getByRole("button", { name: "Revogar a chave tld_inventada1" }));
    expect(screen.getByText(/Revogar a chave tld_inventada1\?/)).toBeTruthy();
    expect(escritas(buscar)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Revogar mesmo" }));
    expect(await screen.findByText("Chave revogada: ela não entra mais.")).toBeTruthy();
    expect(escritas(buscar)).toEqual([
      { endereco: ROTA_DE_REVOGAR, corpo: { organizacao_id: ID_ALFA, chave_id: ID_DA_CHAVE_ATIVA } },
    ]);
    await waitFor(() => expect(quantasVezes(buscar, rotaDoPainel(ID_ALFA))).toBe(2));
  });

  it("cancelar a confirmação de revogar não manda nada", async () => {
    const { buscar } = abrir();
    const chaves = await screen.findByRole("table", { name: "Chaves da organização" });
    fireEvent.click(within(chaves).getByRole("button", { name: "Revogar a chave tld_inventada1" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("button", { name: "Revogar mesmo" })).toBeNull();
    expect(escritas(buscar)).toEqual([]);
  });

  it("chave revogada não tem ação; a de saída só pode ser revogada", async () => {
    const deSaida = { ...ALFA.chaves[0], id: "dddddddd-dddd-dddd-dddd-dddddddddddd", prefixo: "tld_inventada4", estado: "de_saida" };
    abrir({ painel: () => respostaJson(200, { ...ALFA, chaves: [...ALFA.chaves, deSaida] }) });
    const chaves = await screen.findByRole("table", { name: "Chaves da organização" });
    const revogada = within(chaves).getByText("tld_inventada2").closest("tr")!;
    expect(within(revogada).queryByRole("button")).toBeNull();
    const saindo = within(chaves).getByText("tld_inventada4").closest("tr")!;
    expect(within(saindo).queryByRole("button", { name: /Trocar/ })).toBeNull();
    expect(within(saindo).getByRole("button", { name: "Revogar a chave tld_inventada4" })).toBeTruthy();
  });

  it("chave que o servidor não acha mais: a frase dele aparece e o painel recarrega", async () => {
    const { buscar } = abrir({ mudar: () => respostaJson(404, { detail: "Chave inexistente ou já revogada." }) });
    const chaves = await screen.findByRole("table", { name: "Chaves da organização" });
    fireEvent.click(within(chaves).getByRole("button", { name: "Revogar a chave tld_inventada1" }));
    fireEvent.click(screen.getByRole("button", { name: "Revogar mesmo" }));
    expect(await screen.findByText("Chave inexistente ou já revogada.")).toBeTruthy();
    expect(screen.queryByText(/Chave revogada: ela não entra mais/)).toBeNull();
    await waitFor(() => expect(quantasVezes(buscar, rotaDoPainel(ID_ALFA))).toBe(2));
  });
});

describe("as ações quando o servidor deixa de reconhecer o administrador", () => {
  it("a ação recusada (404) não é dada como feita, e a tela vira página não encontrada", async () => {
    let rebaixado = false;
    abrir({
      lista: () => (rebaixado ? respostaJson(404, RECUSA_DO_SERVIDOR) : respostaJson(200, LISTA)),
      painel: (id) => (rebaixado ? respostaJson(404, RECUSA_DO_SERVIDOR) : painelPadrao(id)),
      mudar: () => {
        rebaixado = true;
        return respostaJson(404, RECUSA_DO_SERVIDOR);
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Chave nova" })).toBeNull();
    expect(screen.queryByText("tld_inventada1")).toBeNull();
    expect(screen.queryByText("Not Found")).toBeNull();
  });

  it("conta comum não vê botão nenhum de ação (e o servidor recusaria de qualquer jeito)", async () => {
    const { buscar } = abrir({ eu: ANA });
    await screen.findByText(/Página não encontrada/);
    expect(screen.queryByRole("button", { name: /Emitir|Revogar|Trocar|Suspender|Reativar|Nova organização/ })).toBeNull();
    expect(pedidosDaAdministracao(buscar)).toEqual([]);
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
    expect(trocar).toHaveBeenCalledWith("/classico/admin");
    trocar.mockRestore();
  });
});
