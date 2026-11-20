// @vitest-environment jsdom
// A Administração no app novo (linha 962, PR 5): a aba "Registro", com o registro de ações e os eventos do
// Stripe. São só leituras: quem decide quem entra é o servidor (404 para quem não é administrador); a tela
// mostra o que a API devolve, com a hora de Brasília e os códigos por extenso.
// Tudo inventado: nenhuma conta, e-mail, organização, chave ou evento real (os e-mails são do domínio de teste).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { dataEHora } from "../../src/app/telas/RegistroDaAdministracao";
import type {
  AcaoV1,
  EventosDoStripeV1,
  OrganizacoesV1,
  PainelDaOrganizacaoV1,
  RegistroV1,
} from "../../src/app/tiposDaAdministracao";
import { ANA, abrirApp, respostaJson } from "./ajudantes";

const ADMIN = { ...ANA, administrador: true };
const ID_DA_ORGANIZACAO = "11111111-1111-1111-1111-111111111111";
const ROTA_DA_LISTA = "/api/v1/admin/organizacoes";
const ROTA_DO_PAINEL = `/api/v1/admin/organizacao?id=${ID_DA_ORGANIZACAO}`;
const ROTA_DO_REGISTRO = "/api/v1/admin/registro";
const ROTA_DOS_EVENTOS = "/api/v1/admin/eventos-do-stripe";

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

const ID_DA_ADMIN = "a0000000-0000-0000-0000-000000000001";
const ID_DA_COMUM = "a0000000-0000-0000-0000-000000000002";
const ID_DA_CHAVE = "c0ffee00-0000-0000-0000-000000000009";
const EMAIL_DA_ADMIN = "administradora@exemplo.test";
const EMAIL_DA_COMUM = "comum@exemplo.test";

const MUDOU_O_PLANO: AcaoV1 = {
  id: "e0000000-0000-0000-0000-000000000001",
  // 02h30 em UTC é 23h30 da véspera em Brasília
  quando: "2026-11-17T02:30:00Z",
  acao: "plano_alterado",
  ator_id: ID_DA_ADMIN,
  ator_email: EMAIL_DA_ADMIN,
  alvo_id: ID_DA_COMUM,
  alvo_email: EMAIL_DA_COMUM,
  foi_voce: true,
  detalhes: { de: "gratuito", para: "pro" },
};
const EMITIU_CHAVE: AcaoV1 = {
  ...MUDOU_O_PLANO,
  id: "e0000000-0000-0000-0000-000000000002",
  quando: "2026-11-16T15:00:00Z",
  acao: "chave_emitida",
  ator_id: "a0000000-0000-0000-0000-000000000007",
  ator_email: "outra-admin@exemplo.test",
  alvo_id: ID_DA_CHAVE,
  alvo_email: null,
  foi_voce: false,
  detalhes: { finalidade: "analise", limite: 3 },
};
const ACEITOU_OS_TERMOS: AcaoV1 = {
  ...MUDOU_O_PLANO,
  id: "e0000000-0000-0000-0000-000000000003",
  quando: "2026-11-15T12:00:00Z",
  acao: "termos_aceitos",
  ator_id: ID_DA_COMUM,
  ator_email: EMAIL_DA_COMUM,
  alvo_id: ID_DA_COMUM,
  alvo_email: EMAIL_DA_COMUM,
  foi_voce: false,
  detalhes: {},
};
const DE_CONTA_APAGADA: AcaoV1 = {
  ...MUDOU_O_PLANO,
  id: "e0000000-0000-0000-0000-000000000004",
  quando: "2026-11-14T12:00:00Z",
  acao: "acao_que_a_tela_nao_conhece",
  ator_id: null,
  ator_email: null,
  alvo_id: null,
  alvo_email: null,
  foi_voce: false,
  detalhes: {},
};

const registro = (acoes: AcaoV1[], cortado = false): RegistroV1 => ({ acoes, cortado });
const REGISTRO = registro([MUDOU_O_PLANO, EMITIU_CHAVE, ACEITOU_OS_TERMOS, DE_CONTA_APAGADA]);
const EVENTOS: EventosDoStripeV1 = {
  eventos: [
    { id: "evt_inventado_2", tipo: "invoice.paid", processado_em: "2026-11-16T18:05:00Z" },
    { id: "evt_inventado_1", tipo: "checkout.session.completed", processado_em: "2026-11-16T18:00:00Z" },
  ],
  cortado: false,
};
const RECUSA_DO_SERVIDOR = { detail: "Not Found" };

interface Opcoes {
  eu?: typeof ANA;
  lista?: () => Response;
  registro?: () => Response;
  eventos?: () => Response;
}

function abrir({ eu = ADMIN, lista, registro: doRegistro, eventos }: Opcoes = {}) {
  return abrirApp("/admin", {
    comSessao: true,
    eu: () => respostaJson(200, eu),
    rotas: (endereco) => {
      if (endereco === ROTA_DA_LISTA) return lista ? lista() : respostaJson(200, LISTA);
      if (endereco === ROTA_DO_PAINEL) return respostaJson(200, PAINEL);
      if (endereco === ROTA_DO_REGISTRO) return doRegistro ? doRegistro() : respostaJson(200, REGISTRO);
      if (endereco === ROTA_DOS_EVENTOS) return eventos ? eventos() : respostaJson(200, EVENTOS);
      return undefined;
    },
  });
}

/** Abre a Administração e vai para a aba do registro. */
async function abrirRegistro(opcoes: Opcoes = {}) {
  const aberto = abrir(opcoes);
  fireEvent.click(await screen.findByRole("tab", { name: "Registro" }));
  await screen.findByRole("region", { name: "Registro de ações" });
  return aberto;
}

type Buscar = ReturnType<typeof abrir>["buscar"];

const leituras = (buscar: Buscar, endereco: string) =>
  buscar.mock.calls.filter(([pedido]) => pedido === endereco).length;

const guardado = () => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });

/** As células de cada linha do corpo de uma tabela, como texto. */
const linhasDe = (tabela: HTMLElement) =>
  within(tabela)
    .getAllByRole("row")
    .slice(1)
    .map((linha) =>
      within(linha)
        .getAllByRole("cell")
        .map((celula) => celula.textContent),
    );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a hora do registro", () => {
  it("é a de Brasília, com dia, mês, ano, hora e minuto", () => {
    expect(dataEHora("2026-11-17T02:30:00Z")).toBe("16/11/2026 23:30");
    expect(dataEHora("2026-01-05T15:04:59+00:00")).toBe("05/01/2026 12:04");
  });
});

describe("a aba Registro", () => {
  it("nada do registro é pedido enquanto a aba não abre", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: "Organização Alfa" });
    expect(screen.getByRole("tab", { name: "Registro" }).getAttribute("aria-selected")).toBe("false");
    expect(leituras(buscar, ROTA_DO_REGISTRO)).toBe(0);
    expect(leituras(buscar, ROTA_DOS_EVENTOS)).toBe(0);
  });

  it("mostra cada ação com a hora de Brasília, por extenso, quem fez, sobre quem e os detalhes", async () => {
    const antes = guardado();
    const { buscar } = await abrirRegistro();
    const tabela = await screen.findByRole("table", { name: "Ações registradas" });
    expect(linhasDe(tabela)).toEqual([
      ["16/11/2026 23:30", "Plano alterado", "Você", EMAIL_DA_COMUM, "de: gratuito · para: pro"],
      [
        "16/11/2026 12:00",
        "Chave emitida",
        "outra-admin@exemplo.test",
        ID_DA_CHAVE.slice(0, 8),
        "finalidade: analise · limite: 3",
      ],
      ["15/11/2026 09:00", "Termos aceitos", EMAIL_DA_COMUM, "A própria conta", "—"],
      ["14/11/2026 09:00", "acao_que_a_tela_nao_conhece", "—", "—", "—"],
    ]);
    // o id inteiro do alvo que não é conta fica na dica, para quem precisa procurar por ele
    expect(within(tabela).getByText(ID_DA_CHAVE.slice(0, 8)).getAttribute("title")).toBe(ID_DA_CHAVE);
    expect(leituras(buscar, ROTA_DO_REGISTRO)).toBe(1);
    // são leituras sem parâmetro: nada de e-mail no endereço nem no armazenamento do navegador
    for (const [endereco] of buscar.mock.calls) expect(endereco).not.toContain("exemplo.test");
    expect(window.location.href).not.toContain("exemplo.test");
    expect(guardado()).toBe(antes);
  });

  it("o filtro mostra só as ações do tipo escolhido, sem pedir nada ao servidor", async () => {
    const { buscar } = await abrirRegistro();
    const tabela = await screen.findByRole("table", { name: "Ações registradas" });
    const filtro = screen.getByLabelText("Mostrar");
    expect(within(filtro).getAllByRole("option").map((opcao) => opcao.textContent)).toEqual([
      "Todas as ações",
      "acao_que_a_tela_nao_conhece",
      "Chave emitida",
      "Plano alterado",
      "Termos aceitos",
    ]);
    fireEvent.change(filtro, { target: { value: "chave_emitida" } });
    expect(linhasDe(tabela).map((linha) => linha[1])).toEqual(["Chave emitida"]);
    fireEvent.change(filtro, { target: { value: "" } });
    expect(linhasDe(tabela)).toHaveLength(4);
    expect(leituras(buscar, ROTA_DO_REGISTRO)).toBe(1);
  });

  it("com um tipo só de ação, não há o que filtrar", async () => {
    await abrirRegistro({ registro: () => respostaJson(200, registro([MUDOU_O_PLANO])) });
    await screen.findByRole("table", { name: "Ações registradas" });
    expect(screen.queryByLabelText("Mostrar")).toBeNull();
  });

  it("registro cortado: diz quantas vieram e que as mais antigas continuam guardadas", async () => {
    await abrirRegistro({ registro: () => respostaJson(200, registro([MUDOU_O_PLANO, EMITIU_CHAVE], true)) });
    expect(await screen.findByText(/Estas são as 2 ações mais novas\. As mais antigas continuam guardadas/)).toBeTruthy();
  });

  it("sem ação nenhuma, diz isso", async () => {
    await abrirRegistro({ registro: () => respostaJson(200, registro([])) });
    expect(await screen.findByText("Nada registrado ainda.")).toBeTruthy();
  });

  it("atualizar lê o registro e os eventos de novo, sem tirar a tabela da tela", async () => {
    let acoes = [EMITIU_CHAVE];
    const { buscar } = await abrirRegistro({ registro: () => respostaJson(200, registro(acoes)) });
    const tabela = await screen.findByRole("table", { name: "Ações registradas" });
    acoes = [MUDOU_O_PLANO, EMITIU_CHAVE];
    fireEvent.click(screen.getByRole("button", { name: "Atualizar" }));
    await waitFor(() => expect(linhasDe(tabela).map((linha) => linha[1])).toEqual(["Plano alterado", "Chave emitida"]));
    expect(leituras(buscar, ROTA_DO_REGISTRO)).toBe(2);
    expect(leituras(buscar, ROTA_DOS_EVENTOS)).toBe(2);
  });

  it("voltar à aba lê o registro de novo: a mudança feita nas outras abas já aparece", async () => {
    const { buscar } = await abrirRegistro();
    await screen.findByRole("table", { name: "Ações registradas" });
    fireEvent.click(screen.getByRole("tab", { name: "Organizações" }));
    expect(screen.queryByRole("region", { name: "Registro de ações" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Registro" }));
    await screen.findByRole("table", { name: "Ações registradas" });
    expect(leituras(buscar, ROTA_DO_REGISTRO)).toBe(2);
  });

  it("o registro que falha mostra o erro e deixa tentar de novo, sem derrubar os eventos", async () => {
    let falhar = true;
    await abrirRegistro({
      registro: () => (falhar ? respostaJson(503, { detail: "Serviço fora do ar." }) : respostaJson(200, REGISTRO)),
    });
    expect(await screen.findByText("Serviço fora do ar.")).toBeTruthy();
    expect(await screen.findByRole("table", { name: "Eventos do Stripe processados" })).toBeTruthy();
    falhar = false;
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByRole("table", { name: "Ações registradas" })).toBeTruthy();
  });
});

describe("os eventos do Stripe", () => {
  it("mostra quando, o tipo e o id de cada evento, dos mais novos para os mais antigos", async () => {
    await abrirRegistro();
    const tabela = await screen.findByRole("table", { name: "Eventos do Stripe processados" });
    expect(linhasDe(tabela)).toEqual([
      ["16/11/2026 15:05", "invoice.paid", "evt_inventado_2"],
      ["16/11/2026 15:00", "checkout.session.completed", "evt_inventado_1"],
    ]);
  });

  it("sem evento nenhum, diz isso", async () => {
    await abrirRegistro({ eventos: () => respostaJson(200, { eventos: [], cortado: false }) });
    expect(await screen.findByText("Nenhum evento recebido ainda.")).toBeTruthy();
  });

  it("lista cortada: diz quantos vieram", async () => {
    await abrirRegistro({ eventos: () => respostaJson(200, { ...EVENTOS, cortado: true }) });
    expect(await screen.findByText("Estes são os 2 eventos mais novos.")).toBeTruthy();
  });
});

describe("o registro quando o servidor deixa de reconhecer o administrador", () => {
  it("a leitura recusada (404) não mostra ação nenhuma, e a tela vira página não encontrada", async () => {
    let admin = true;
    const { buscar } = abrir({
      lista: () => (admin ? respostaJson(200, LISTA) : respostaJson(404, RECUSA_DO_SERVIDOR)),
      registro: () => respostaJson(404, RECUSA_DO_SERVIDOR),
      eventos: () => respostaJson(404, RECUSA_DO_SERVIDOR),
    });
    await screen.findByRole("region", { name: "Organização Alfa" });
    admin = false;
    fireEvent.click(screen.getByRole("tab", { name: "Registro" }));
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Ações registradas" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Registro" })).toBeNull();
    // a tela releu as organizações para saber o que o servidor diz agora
    expect(leituras(buscar, ROTA_DA_LISTA)).toBe(2);
  });

  it("a releitura recusada (404) vira página não encontrada, sem as ações que já tinham vindo", async () => {
    let admin = true;
    await abrirRegistro({
      lista: () => (admin ? respostaJson(200, LISTA) : respostaJson(404, RECUSA_DO_SERVIDOR)),
      registro: () => (admin ? respostaJson(200, REGISTRO) : respostaJson(404, RECUSA_DO_SERVIDOR)),
    });
    await screen.findByRole("table", { name: "Ações registradas" });
    admin = false;
    fireEvent.click(screen.getByRole("button", { name: "Atualizar" }));
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeTruthy();
    expect(screen.queryByText(EMAIL_DA_COMUM)).toBeNull();
  });

  it("só o registro recusado (404): a aba fica, mas o que já tinha vindo sai da tela", async () => {
    // as organizações continuam respondendo: quem tira as ações da tela é a própria aba, e não a
    // Administração inteira saindo
    let recusar = false;
    const { buscar } = await abrirRegistro({
      registro: () => (recusar ? respostaJson(404, RECUSA_DO_SERVIDOR) : respostaJson(200, REGISTRO)),
    });
    await screen.findByRole("table", { name: "Ações registradas" });
    await screen.findByRole("table", { name: "Eventos do Stripe processados" });
    recusar = true;
    fireEvent.click(screen.getByRole("button", { name: "Atualizar" }));
    expect(await screen.findByText(/a sua conta pode ter deixado de ser administradora/)).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Ações registradas" })).toBeNull();
    expect(screen.queryByRole("table", { name: "Eventos do Stripe processados" })).toBeNull();
    expect(screen.queryByText(EMAIL_DA_COMUM)).toBeNull();
    expect(screen.queryByText("evt_inventado_1")).toBeNull();
    expect(screen.getByRole("tab", { name: "Registro" })).toBeTruthy();
    // a tela perguntou de novo ao servidor quem é esta conta
    await waitFor(() => expect(leituras(buscar, ROTA_DA_LISTA)).toBe(2));
  });

  it("conta comum não vê a aba nem faz pedido nenhum à Administração", async () => {
    const { buscar } = abrir({ eu: ANA });
    expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: "Registro" })).toBeNull();
    expect(buscar.mock.calls.filter(([endereco]) => endereco.startsWith("/api/v1/admin"))).toEqual([]);
  });
});
