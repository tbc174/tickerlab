// @vitest-environment jsdom
// Meus dados no app novo (conta e planos, PR 5): baixar a cópia dos dados (LGPD) e os links
// compartilhados, com revogar. Apagar a conta, o tema, as Novidades e os PDFs continuam no app atual.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOKEN, abrirApp, respostaJson } from "./ajudantes";

const ATIVO = {
  id: "11111111-1111-1111-1111-111111111111",
  titulo: 'Ficha "Foi sorte?": PETR4 · Cruzamento de médias',
  situacao: "ativo",
  descricao: 'Ficha "Foi sorte?" · ativo · criado em 14/10/2026 · vale até 13/11/2026 · 2 visita(s)',
};
const VENCIDO = { ...ATIVO, id: "22222222-2222-2222-2222-222222222222", situacao: "vencido", titulo: "PDF antigo" };
const LINKS = {
  explicacao: "Quem tem o link vê o que você compartilhou, sem o seu nome nem o seu e-mail.",
  sem_links: "Você ainda não compartilhou nada.",
  links: [ATIVO, VENCIDO],
};

function abrir(lista = LINKS) {
  return abrirApp("/meus-dados", {
    rotas: (endereco, pedido) => {
      if (endereco === "/api/v1/links-compartilhados") return respostaJson(200, lista);
      if (endereco === "/api/v1/revogar-link") {
        const { id } = JSON.parse(String(pedido?.body));
        return respostaJson(200, {
          ...lista,
          links: lista.links.map((l) => (l.id === id ? { ...l, situacao: "revogado" } : l)),
        });
      }
      if (endereco === "/api/v1/meus-dados") return respostaJson(200, { perfil: { email: "ana@exemplo.com" } });
      return undefined;
    },
  });
}

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:dados"), revokeObjectURL: vi.fn() }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("meus dados", () => {
  it("lista os links com a descrição, e só os ativos podem ser revogados", async () => {
    abrir();
    const lista = await screen.findByRole("list", { name: "Links compartilhados" });
    const itens = within(lista).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(within(itens[0]).getByText(ATIVO.descricao)).toBeTruthy();
    expect(within(itens[0]).getByRole("button", { name: /Revogar/ })).toBeTruthy();
    expect(within(itens[1]).queryByRole("button", { name: /Revogar/ })).toBeNull();
    expect(screen.getByText(LINKS.explicacao)).toBeTruthy();
  });

  it("revogar manda o id do link e atualiza a lista", async () => {
    const { buscar } = abrir();
    fireEvent.click(await screen.findByRole("button", { name: /Revogar/ }));
    // folga para máquina carregada: a lista nova chega depois do pedido
    await waitFor(() => expect(screen.queryByRole("button", { name: /Revogar/ })).toBeNull(), { timeout: 5000 });
    const pedido = buscar.mock.calls.find(([e]) => e === "/api/v1/revogar-link");
    expect(JSON.parse(String(pedido?.[1]?.body))).toEqual({ id: ATIVO.id });
    expect(pedido?.[1]?.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` });
  });

  it("sem links, a frase de quando a lista está vazia", async () => {
    abrir({ ...LINKS, links: [] });
    expect(await screen.findByText(LINKS.sem_links)).toBeTruthy();
  });

  it("baixar meus dados pede a exportação com o token e entrega um arquivo", async () => {
    const { buscar } = abrir();
    fireEvent.click(await screen.findByRole("button", { name: "Baixar meus dados (JSON)" }));
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    expect(buscar).toHaveBeenCalledWith("/api/v1/meus-dados", {
      method: "GET",
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
  });

  it("apagar a conta continua no app atual", async () => {
    abrir();
    const link = await screen.findByRole("link", { name: /Apagar a conta, tema, Novidades e PDFs/ });
    expect(link.getAttribute("href")).toBe("https://app.tickerlab.com.br/meus-dados");
  });
});
