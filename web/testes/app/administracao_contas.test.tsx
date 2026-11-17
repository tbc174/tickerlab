// @vitest-environment jsdom
// A Administração no app novo (linha 962, PR 4): a aba "Contas do app", com os números do serviço, a busca
// de contas e as mudanças de plano, de papel e de bloqueio. Quem decide quem entra e o que vale é o servidor
// (404 para quem não é administrador); a tela só mostra o que a API devolve e manda o pedido que ele confere.
// Tudo inventado: nenhuma conta, e-mail, organização ou chave real (os e-mails são do domínio de teste).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  ChaveNovaV1,
  ContaV1,
  ContasV1,
  OrganizacoesV1,
  PainelDaOrganizacaoV1,
  ResumoV1,
} from "../../src/app/tiposDaAdministracao";
import { ANA, abrirApp, respostaJson } from "./ajudantes";

const ADMIN = { ...ANA, administrador: true };
const ID_DA_ORGANIZACAO = "11111111-1111-1111-1111-111111111111";
const ROTA_DA_LISTA = "/api/v1/admin/organizacoes";
const ROTA_DO_PAINEL = `/api/v1/admin/organizacao?id=${ID_DA_ORGANIZACAO}`;
const ROTA_DE_EMITIR = "/api/v1/admin/chaves/emitir";
const ROTA_DO_RESUMO = "/api/v1/admin/resumo";
const ROTA_DE_BUSCAR = "/api/v1/admin/contas/buscar";
const ROTA_DO_PLANO = "/api/v1/admin/conta/plano";
const ROTA_DO_PAPEL = "/api/v1/admin/conta/papel";
const ROTA_DE_BLOQUEAR = "/api/v1/admin/conta/bloquear";
const ROTA_DE_DESBLOQUEAR = "/api/v1/admin/conta/desbloquear";

const LISTA: OrganizacoesV1 = {
  organizacoes: [
    {
      id: ID_DA_ORGANIZACAO,
      nome: "Organização Alfa",
      plano_da_api: "piloto",
      nome_do_plano: "Piloto",
      suspensa: false,
    },
  ],
  planos_da_api: [{ plano_da_api: "piloto", nome_do_plano: "Piloto" }],
  motivos_da_suspensao: ["contrato", "pagamento"],
};

const PAINEL: PainelDaOrganizacaoV1 = {
  id: ID_DA_ORGANIZACAO,
  nome: "Organização Alfa",
  cnpj: null,
  plano_da_api: "piloto",
  nome_do_plano: "Piloto",
  criada_em: "2026-11-02T12:00:00Z",
  suspensa_em: null,
  motivo_da_suspensao: null,
  limites: { pedidos_por_minuto: 60, pedidos_por_mes: 20000, linhas_por_resposta: 500, chaves_ativas: 3 },
  consumo: { pedidos: 0, linhas: 0, negados: 0 },
  chaves_ativas: 0,
  chaves: [],
  direitos: [],
  ainda_desligado: [],
  pessoa_na_tela: false,
  membros: 0,
};

// o "valor" não abre nada: é só um texto para a tela mostrar
const CHAVE_NOVA: ChaveNovaV1 = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  prefixo: "tld_inventada9",
  valor: "tld_inventada9_valor-de-mentira-para-o-teste",
  antiga_vale_por_dias: null,
};

const RESUMO: ResumoV1 = {
  usuarios: 1284,
  gratuito: 1200,
  plus: 60,
  pro: 24,
  administradores: 2,
  novos_na_semana: 37,
  ativos_na_semana: 412,
  simulacoes: 5310,
  assinaturas_ativas: 71,
  eventos_do_stripe: 903,
};

const ID_DA_ADMIN = "a0000000-0000-0000-0000-000000000001";
const ID_DA_COMUM = "a0000000-0000-0000-0000-000000000002";
const ID_DA_BLOQUEADA = "a0000000-0000-0000-0000-000000000003";
const EMAIL_DA_ADMIN = "administradora@exemplo.test";
const EMAIL_DA_COMUM = "comum@exemplo.test";
const EMAIL_DA_BLOQUEADA = "bloqueada@exemplo.test";

const DA_ADMIN: ContaV1 = {
  id: ID_DA_ADMIN,
  email: EMAIL_DA_ADMIN,
  nome: "Conta Administradora",
  papel: "admin",
  plano: "pro",
  criado_em: "2026-10-01T10:00:00Z",
  ultimo_acesso: "2026-11-16T09:00:00Z",
  status_da_assinatura: null,
  simulacoes: 4,
  bloqueada_em: null,
  motivo_do_bloqueio: null,
  e_voce: true,
};
const DA_COMUM: ContaV1 = {
  ...DA_ADMIN,
  id: ID_DA_COMUM,
  email: EMAIL_DA_COMUM,
  nome: null,
  papel: "usuario",
  plano: "gratuito",
  criado_em: "2026-10-20T10:00:00Z",
  ultimo_acesso: null,
  status_da_assinatura: "active",
  simulacoes: 12,
  e_voce: false,
};
const DA_BLOQUEADA: ContaV1 = {
  ...DA_COMUM,
  id: ID_DA_BLOQUEADA,
  email: EMAIL_DA_BLOQUEADA,
  nome: "Conta Bloqueada",
  plano: "plus",
  status_da_assinatura: null,
  simulacoes: 0,
  bloqueada_em: "2026-11-12T08:00:00Z",
  motivo_do_bloqueio: "acesso_de_terceiro",
};

const contas = (lista: ContaV1[], cortada = false): ContasV1 => ({
  contas: lista,
  cortada,
  planos: ["gratuito", "plus", "pro"],
  papeis: ["usuario", "admin"],
  motivos_do_bloqueio: ["abuso", "acesso_de_terceiro", "incidente", "pedido_do_titular"],
});
const CONTAS = contas([DA_ADMIN, DA_COMUM, DA_BLOQUEADA]);
const RECUSA_DO_SERVIDOR = { detail: "Not Found" };
const FEITO = () => new Response(null, { status: 204 });

type Resposta = Response | Promise<Response> | undefined;

interface Opcoes {
  eu?: typeof ANA;
  lista?: () => Response;
  resumo?: () => Response;
  // a busca de contas (POST): o corpo que a tela mandou → resposta
  contas?: (corpo: unknown) => Resposta;
  // os outros pedidos que mudam alguma coisa (POST): endereço e corpo → resposta
  mudar?: (endereco: string, corpo: unknown) => Resposta;
}

function abrir({ eu = ADMIN, lista, resumo, contas: aoBuscar, mudar }: Opcoes = {}) {
  return abrirApp("/admin", {
    comSessao: true,
    eu: () => respostaJson(200, eu),
    rotas: (endereco, pedido) => {
      if (pedido?.method === "POST") {
        const corpo = JSON.parse(String(pedido.body)) as unknown;
        // o `fetch` de mentira é assíncrono: a promessa de uma resposta vale como a resposta
        if (endereco === ROTA_DE_BUSCAR)
          return (aoBuscar ? aoBuscar(corpo) : respostaJson(200, CONTAS)) as Response | undefined;
        return mudar?.(endereco, corpo) as Response | undefined;
      }
      if (endereco === ROTA_DA_LISTA) return lista ? lista() : respostaJson(200, LISTA);
      if (endereco === ROTA_DO_PAINEL) return respostaJson(200, PAINEL);
      if (endereco === ROTA_DO_RESUMO) return resumo ? resumo() : respostaJson(200, RESUMO);
      return undefined;
    },
  });
}

/** Abre a Administração e vai para a aba das contas, já com a lista na tela. */
async function abrirContas(opcoes: Opcoes = {}) {
  const aberto = abrir(opcoes);
  fireEvent.click(await screen.findByRole("tab", { name: "Contas do app" }));
  await screen.findByRole("search", { name: "Buscar contas" });
  return aberto;
}

async function gerenciar(email: string) {
  fireEvent.click(await screen.findByRole("button", { name: `Gerenciar a conta ${email}` }));
  return screen.findByRole("region", { name: email });
}

type Buscar = ReturnType<typeof abrir>["buscar"];

const daAdministracao = (endereco: string) => endereco.startsWith("/api/v1/admin");

/** Os pedidos POST da Administração, na ordem: o endereço e o corpo que a tela mandou. */
const escritas = (buscar: Buscar) =>
  buscar.mock.calls
    .filter(([endereco, pedido]) => daAdministracao(endereco) && pedido?.method === "POST")
    .map(([endereco, pedido]) => ({ endereco, corpo: JSON.parse(String(pedido?.body)) as unknown }));

/** Só as mudanças: as escritas menos a busca (que é POST para o termo não ir no endereço). */
const mudancas = (buscar: Buscar) => escritas(buscar).filter(({ endereco }) => endereco !== ROTA_DE_BUSCAR);
const buscas = (buscar: Buscar) => escritas(buscar).filter(({ endereco }) => endereco === ROTA_DE_BUSCAR);

const leituras = (buscar: Buscar, endereco: string) =>
  buscar.mock.calls.filter(([pedido, opcoes]) => pedido === endereco && opcoes?.method !== "POST").length;

const guardado = () => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("as abas da Administração", () => {
  it("abre nas organizações e não pede nada das contas enquanto a aba delas não abre", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: "Organização Alfa" });
    expect(screen.getByRole("tab", { name: "Organizações" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Contas do app" }).getAttribute("aria-selected")).toBe("false");
    expect(buscar.mock.calls.map(([endereco]) => endereco).filter(daAdministracao)).toEqual([
      ROTA_DA_LISTA,
      ROTA_DO_PAINEL,
    ]);
  });

  it("a aba das contas pede os números e as contas, com a busca vazia no corpo", async () => {
    const { buscar } = await abrirContas();
    await screen.findByRole("table", { name: "Contas encontradas" });
    expect(leituras(buscar, ROTA_DO_RESUMO)).toBe(1);
    expect(buscas(buscar)).toEqual([{ endereco: ROTA_DE_BUSCAR, corpo: { busca: "" } }]);
    // as organizações saem da vista, e o que sobra na Administração antiga continua dito
    expect(screen.queryByRole("region", { name: "Organização Alfa" })).toBeNull();
    expect(screen.getByText(/registro de ações, os eventos de cobrança e o acervo continuam/)).toBeTruthy();
  });

  it("a chave nova na tela não se perde ao ir para as contas e voltar", async () => {
    abrir({ mudar: (endereco) => (endereco === ROTA_DE_EMITIR ? respostaJson(200, CHAVE_NOVA) : undefined) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    await screen.findByRole("region", { name: "Chave nova" });
    fireEvent.click(screen.getByRole("tab", { name: "Contas do app" }));
    await screen.findByRole("table", { name: "Contas encontradas" });
    // escondida com a aba dela: quem lê a tela das contas não a encontra
    expect(screen.queryByRole("region", { name: "Chave nova" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Organizações" }));
    const caixa = screen.getByRole("region", { name: "Chave nova" });
    expect(within(caixa).getByText(CHAVE_NOVA.valor)).toBeTruthy();
  });

  it("a conta aberta e a lista continuam lá ao ir às organizações e voltar, sem pedir de novo", async () => {
    const { buscar } = await abrirContas();
    await gerenciar(EMAIL_DA_COMUM);
    fireEvent.click(screen.getByRole("tab", { name: "Organizações" }));
    // escondida com a aba dela: quem lê as organizações não encontra conta nenhuma
    expect(screen.queryByRole("region", { name: EMAIL_DA_COMUM })).toBeNull();
    expect(screen.queryByRole("table", { name: "Contas encontradas" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Contas do app" }));
    expect(screen.getByRole("region", { name: EMAIL_DA_COMUM })).toBeTruthy();
    expect(buscas(buscar)).toHaveLength(1);
    expect(leituras(buscar, ROTA_DO_RESUMO)).toBe(1);
  });

  it("a chave que chega com a aba das contas aberta traz as organizações de volta, com o valor à vista", async () => {
    let entregar: (resposta: Response) => void = () => {};
    const emitida = new Promise<Response>((resolver) => {
      entregar = resolver;
    });
    abrir({ mudar: (endereco) => (endereco === ROTA_DE_EMITIR ? emitida : undefined) });
    fireEvent.click(await screen.findByRole("button", { name: "Emitir chave nova" }));
    fireEvent.click(screen.getByRole("tab", { name: "Contas do app" }));
    await screen.findByRole("table", { name: "Contas encontradas" });
    entregar(respostaJson(200, CHAVE_NOVA));
    // a chave já vale no servidor e o valor não dá para ver de novo: ele não pode ficar numa aba fechada
    const caixa = await screen.findByRole("region", { name: "Chave nova" });
    expect(within(caixa).getByText(CHAVE_NOVA.valor)).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Organizações" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("os números do serviço", () => {
  it("mostra as contas por plano, a semana, as assinaturas, as simulações e os eventos de cobrança", async () => {
    await abrirContas();
    const numeros = await screen.findByRole("region", { name: "Números do serviço" });
    await within(numeros).findByText("1.284");
    for (const valor of ["1.200", "60", "24", "37", "412", "71", "5.310", "903"])
      expect(within(numeros).getByText(valor)).toBeTruthy();
    expect(within(numeros).getByText("2 administradores")).toBeTruthy();
    for (const rotulo of ["Contas", "Plano Gratuito", "Plano Plus", "Plano Pro", "Novas na semana"])
      expect(within(numeros).getByText(rotulo)).toBeTruthy();
    for (const rotulo of ["Ativas na semana", "Assinaturas ativas", "Simulações salvas", "Eventos do Stripe"])
      expect(within(numeros).getByText(rotulo)).toBeTruthy();
  });

  it("os números que falham mostram o erro, sem derrubar a lista de contas", async () => {
    await abrirContas({ resumo: () => respostaJson(503, { detail: "Serviço fora do ar." }) });
    expect(await screen.findByText("Serviço fora do ar.")).toBeTruthy();
    expect(await screen.findByRole("table", { name: "Contas encontradas" })).toBeTruthy();
  });
});

describe("a lista de contas", () => {
  it("mostra cada conta com plano, papel, situação, assinatura e datas, por extenso", async () => {
    await abrirContas();
    const tabela = await screen.findByRole("table", { name: "Contas encontradas" });
    const admin = within(tabela).getByText(EMAIL_DA_ADMIN).closest("tr")!;
    expect(within(admin).getByText("Conta Administradora")).toBeTruthy();
    expect(within(admin).getByText("Pro")).toBeTruthy();
    expect(within(admin).getByText("Administrador")).toBeTruthy();
    expect(within(admin).getByText("Sua conta")).toBeTruthy();
    expect(within(admin).getByText("01/10/2026")).toBeTruthy();
    expect(within(admin).getByText("16/11/2026")).toBeTruthy();
    const comum = within(tabela).getByText(EMAIL_DA_COMUM).closest("tr")!;
    expect(within(comum).getByText("Gratuito")).toBeTruthy();
    expect(within(comum).getByText("Usuário")).toBeTruthy();
    expect(within(comum).getByText("Ativa")).toBeTruthy();
    expect(within(comum).getByText("Nunca entrou")).toBeTruthy();
    expect(within(comum).getByText("12")).toBeTruthy();
    expect(within(comum).queryByText("Sua conta")).toBeNull();
    const bloqueada = within(tabela).getByText(EMAIL_DA_BLOQUEADA).closest("tr")!;
    expect(within(bloqueada).getByText("Bloqueada")).toBeTruthy();
    expect(within(bloqueada).getByText(/12\/11\/2026 · Acesso de terceiro/)).toBeTruthy();
    expect(within(bloqueada).getByText("Plus")).toBeTruthy();
  });

  it("a busca manda o termo no corpo do pedido: nada no endereço nem no armazenamento do navegador", async () => {
    const antes = guardado();
    const { buscar } = await abrirContas({
      contas: (corpo) => respostaJson(200, (corpo as { busca: string }).busca ? contas([DA_COMUM]) : CONTAS),
    });
    await screen.findByRole("table", { name: "Contas encontradas" });
    const formulario = screen.getByRole("search", { name: "Buscar contas" });
    fireEvent.change(within(formulario).getByLabelText("Buscar por e-mail ou nome"), {
      target: { value: `  ${EMAIL_DA_COMUM} ` },
    });
    fireEvent.click(within(formulario).getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(screen.queryByText(EMAIL_DA_ADMIN)).toBeNull());
    expect(await screen.findByText(EMAIL_DA_COMUM)).toBeTruthy();
    expect(buscas(buscar)).toEqual([
      { endereco: ROTA_DE_BUSCAR, corpo: { busca: "" } },
      { endereco: ROTA_DE_BUSCAR, corpo: { busca: EMAIL_DA_COMUM } },
    ]);
    for (const [endereco] of buscar.mock.calls) expect(endereco).not.toContain("comum");
    expect(window.location.href).not.toContain("comum");
    expect(guardado()).toBe(antes);
  });

  it("buscar de novo o mesmo termo refaz o pedido", async () => {
    const { buscar } = await abrirContas();
    await screen.findByRole("table", { name: "Contas encontradas" });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(buscas(buscar)).toHaveLength(2));
  });

  it("lista cortada: diz quantas vieram e pede para afinar a busca", async () => {
    await abrirContas({ contas: () => respostaJson(200, contas([DA_ADMIN, DA_COMUM], true)) });
    expect(await screen.findByText(/Estas são as 2 contas mais novas.*Há mais: afine a busca/)).toBeTruthy();
  });

  it("sem conta nenhuma, diz isso", async () => {
    await abrirContas({ contas: () => respostaJson(200, contas([])) });
    expect(await screen.findByText("Nenhuma conta encontrada.")).toBeTruthy();
  });

  it("a busca que falha mostra o erro e deixa tentar de novo", async () => {
    let falhar = true;
    await abrirContas({
      contas: () => (falhar ? respostaJson(503, { detail: "Serviço fora do ar." }) : respostaJson(200, CONTAS)),
    });
    expect(await screen.findByText("Serviço fora do ar.")).toBeTruthy();
    falhar = false;
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByRole("table", { name: "Contas encontradas" })).toBeTruthy();
  });
});

describe("mudar uma conta", () => {
  it("o plano pede confirmação; confirmando, manda a conta e o plano e relê as contas e os números", async () => {
    const { buscar } = await abrirContas({ mudar: FEITO });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.change(within(painel).getByLabelText("Plano"), { target: { value: "pro" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano" }));
    expect(mudancas(buscar)).toEqual([]);
    expect(within(painel).getByText(/de Gratuito para Pro\? Isso não cria nem cancela assinatura no Stripe/)).toBeTruthy();
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano mesmo" }));
    expect(await screen.findByText(`Plano de ${EMAIL_DA_COMUM} mudado para Pro.`)).toBeTruthy();
    expect(mudancas(buscar)).toEqual([{ endereco: ROTA_DO_PLANO, corpo: { id: ID_DA_COMUM, plano: "pro" } }]);
    await waitFor(() => expect(buscas(buscar)).toHaveLength(2));
    await waitFor(() => expect(leituras(buscar, ROTA_DO_RESUMO)).toBe(2));
  });

  it("os planos vêm da lista do servidor, e o plano que a conta já tem não tem o que mudar", async () => {
    await abrirContas();
    const painel = await gerenciar(EMAIL_DA_COMUM);
    const opcoes = within(within(painel).getByLabelText("Plano")).getAllByRole("option");
    expect(opcoes.map((opcao) => opcao.textContent)).toEqual(["Gratuito", "Plus", "Pro"]);
    expect((within(painel).getByRole("button", { name: "Mudar o plano" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("cancelar a confirmação não manda nada", async () => {
    const { buscar } = await abrirContas({ mudar: FEITO });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.change(within(painel).getByLabelText("Plano"), { target: { value: "plus" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano" }));
    fireEvent.click(within(painel).getByRole("button", { name: "Cancelar" }));
    expect(within(painel).queryByRole("button", { name: "Mudar o plano mesmo" })).toBeNull();
    expect(mudancas(buscar)).toEqual([]);
  });

  it("trocar a escolha desfaz a pergunta aberta: o sim nunca vale para o que não está mais escolhido", async () => {
    const { buscar } = await abrirContas({ mudar: FEITO });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.change(within(painel).getByLabelText("Plano"), { target: { value: "pro" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano" }));
    fireEvent.change(within(painel).getByLabelText("Plano"), { target: { value: "plus" } });
    expect(within(painel).queryByRole("button", { name: "Mudar o plano mesmo" })).toBeNull();
    expect(mudancas(buscar)).toEqual([]);
  });

  it("respondida a pergunta, o foco volta ao painel da conta, em vez de cair no topo da página", async () => {
    await abrirContas({ mudar: FEITO });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.change(within(painel).getByLabelText("Plano"), { target: { value: "pro" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano" }));
    fireEvent.click(within(painel).getByRole("button", { name: "Cancelar" }));
    expect(document.activeElement).toBe(painel);
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano" }));
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano mesmo" }));
    expect(document.activeElement).toBe(painel);
  });

  it("o papel pede confirmação e manda a conta e o papel", async () => {
    const { buscar } = await abrirContas({ mudar: FEITO });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.change(within(painel).getByLabelText("Papel"), { target: { value: "admin" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o papel" }));
    expect(within(painel).getByText(/passa a ver e a mudar tudo o que esta Administração mostra/)).toBeTruthy();
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o papel mesmo" }));
    expect(await screen.findByText(`Papel de ${EMAIL_DA_COMUM} mudado para Administrador.`)).toBeTruthy();
    expect(mudancas(buscar)).toEqual([{ endereco: ROTA_DO_PAPEL, corpo: { id: ID_DA_COMUM, papel: "admin" } }]);
  });

  it("bloquear pede o motivo e a confirmação, e diz quantas sessões o servidor encerrou", async () => {
    const { buscar } = await abrirContas({ mudar: () => respostaJson(200, { sessoes_encerradas: 2 }) });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    const motivos = within(within(painel).getByLabelText("Motivo do bloqueio")).getAllByRole("option");
    expect(motivos.map((opcao) => opcao.textContent)).toEqual([
      "Abuso",
      "Acesso de terceiro",
      "Incidente",
      "Pedido do titular",
    ]);
    fireEvent.change(within(painel).getByLabelText("Motivo do bloqueio"), { target: { value: "incidente" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Bloquear conta" }));
    expect(mudancas(buscar)).toEqual([]);
    expect(within(painel).getByText(/As sessões da conta são encerradas na hora e o login para/)).toBeTruthy();
    fireEvent.click(within(painel).getByRole("button", { name: "Bloquear mesmo" }));
    expect(await screen.findByText(`Conta ${EMAIL_DA_COMUM} bloqueada: 2 sessões encerradas.`)).toBeTruthy();
    expect(mudancas(buscar)).toEqual([
      { endereco: ROTA_DE_BLOQUEAR, corpo: { id: ID_DA_COMUM, motivo: "incidente" } },
    ]);
  });

  it("a conta bloqueada mostra quando e por quê, e só oferece desbloquear, com confirmação", async () => {
    const { buscar } = await abrirContas({ mudar: FEITO });
    const painel = await gerenciar(EMAIL_DA_BLOQUEADA);
    expect(within(painel).getByText(/Bloqueada em 12\/11\/2026\. Motivo: Acesso de terceiro\./)).toBeTruthy();
    expect(within(painel).queryByRole("button", { name: "Bloquear conta" })).toBeNull();
    fireEvent.click(within(painel).getByRole("button", { name: "Desbloquear conta" }));
    expect(mudancas(buscar)).toEqual([]);
    fireEvent.click(within(painel).getByRole("button", { name: "Desbloquear mesmo" }));
    expect(await screen.findByText(`Conta ${EMAIL_DA_BLOQUEADA} desbloqueada: o login volta.`)).toBeTruthy();
    expect(mudancas(buscar)).toEqual([{ endereco: ROTA_DE_DESBLOQUEAR, corpo: { id: ID_DA_BLOQUEADA } }]);
  });

  it("na própria conta, a tela não oferece tirar o próprio acesso nem se bloquear", async () => {
    await abrirContas();
    const painel = await gerenciar(EMAIL_DA_ADMIN);
    expect(within(painel).getByLabelText("Plano")).toBeTruthy();
    expect(within(painel).queryByLabelText("Papel")).toBeNull();
    expect(within(painel).queryByRole("button", { name: /Bloquear|Mudar o papel/ })).toBeNull();
    expect(within(painel).getByText(/Esta é a sua conta/)).toBeTruthy();
  });

  it("a recusa da regra aparece com a frase do servidor, e nada é dado como feito", async () => {
    const frase = "O serviço não pode ficar sem administrador.";
    await abrirContas({ mudar: () => respostaJson(409, { detail: frase }) });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.change(within(painel).getByLabelText("Plano"), { target: { value: "pro" } });
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano" }));
    fireEvent.click(within(painel).getByRole("button", { name: "Mudar o plano mesmo" }));
    expect((await screen.findByRole("alert")).textContent).toBe(frase);
    expect(screen.queryByText(/mudado para/)).toBeNull();
  });

  it("conta que o servidor não acha mais: a frase dele aparece e a lista é relida", async () => {
    const { buscar } = await abrirContas({
      mudar: () => respostaJson(404, { detail: "Usuário não encontrado." }),
    });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.click(within(painel).getByRole("button", { name: "Bloquear conta" }));
    fireEvent.click(within(painel).getByRole("button", { name: "Bloquear mesmo" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Usuário não encontrado.");
    await waitFor(() => expect(buscas(buscar)).toHaveLength(2));
    expect(screen.queryByText(/bloqueada:/)).toBeNull();
  });

  it("fechar tira o painel da conta da tela", async () => {
    await abrirContas();
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.click(within(painel).getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("region", { name: EMAIL_DA_COMUM })).toBeNull();
  });
});

describe("as contas quando o servidor deixa de reconhecer o administrador", () => {
  it("a mudança recusada (404) não é dada como feita, e a tela vira página não encontrada", async () => {
    let rebaixado = false;
    const recusa = () => respostaJson(404, RECUSA_DO_SERVIDOR);
    await abrirContas({
      lista: () => (rebaixado ? recusa() : respostaJson(200, LISTA)),
      contas: () => (rebaixado ? recusa() : respostaJson(200, CONTAS)),
      mudar: () => {
        rebaixado = true;
        return recusa();
      },
    });
    const painel = await gerenciar(EMAIL_DA_COMUM);
    fireEvent.click(within(painel).getByRole("button", { name: "Bloquear conta" }));
    fireEvent.click(within(painel).getByRole("button", { name: "Bloquear mesmo" }));
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
    expect(screen.queryByText(EMAIL_DA_COMUM)).toBeNull();
    expect(screen.queryByText("Not Found")).toBeNull();
  });

  it("a busca recusada (404) não mostra conta nenhuma, e a tela vira página não encontrada", async () => {
    let rebaixado = false;
    const { buscar } = abrir({
      lista: () => (rebaixado ? respostaJson(404, RECUSA_DO_SERVIDOR) : respostaJson(200, LISTA)),
      contas: () => respostaJson(404, RECUSA_DO_SERVIDOR),
      resumo: () => respostaJson(404, RECUSA_DO_SERVIDOR),
    });
    const aba = await screen.findByRole("tab", { name: "Contas do app" });
    rebaixado = true;
    fireEvent.click(aba);
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Contas encontradas" })).toBeNull();
    expect(leituras(buscar, ROTA_DA_LISTA)).toBe(2);
  });

  it("conta comum não vê a aba nem faz pedido nenhum à Administração", async () => {
    const { buscar } = abrir({ eu: ANA });
    await screen.findByText(/Página não encontrada/);
    expect(screen.queryByRole("tab", { name: "Contas do app" })).toBeNull();
    expect(buscar.mock.calls.map(([endereco]) => endereco).filter(daAdministracao)).toEqual([]);
  });
});
