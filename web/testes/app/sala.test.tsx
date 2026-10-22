// @vitest-environment jsdom
// A sala de dados no app novo (B-20, PR 5): só para administradores, tudo vindo da API. Dados de mentira:
// nenhum documento real.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PainelV1, SalaV1 } from "../../src/app/tiposDaSala";
import { ANA, abrirApp, respostaJson } from "./ajudantes";

const ADMIN = { ...ANA, administrador: true };
const ID = "11111111-1111-1111-1111-111111111111";

const OPERACAO = {
  id: ID,
  tipo: "ma",
  nome: "Aquisição da Alfa",
  situacao: "aberta" as const,
  retencao_ate: "2026-11-02",
  criada_em: "2026-10-21T10:00:00Z",
  dias_ate_sumir: 12,
  aviso_de_prazo: "A operação some em 12 dias. Baixe a sala antes disso ou prorrogue o prazo.",
  documentos: 2,
  contradicoes_abertas: 1,
};

const SALA: SalaV1 = {
  conceitos: {
    sala: "A sala guarda os documentos de uma operação.",
    evidencia: "Uma evidência é um número com o trecho de onde veio.",
    contradicao: "Contradição é quando dois documentos dizem números diferentes.",
    checklist: "O checklist lista os documentos esperados.",
    prazo: "No fim do prazo a operação é apagada.",
    baixar: "O ZIP traz tudo o que está na sala.",
    dados_de_terceiros: "Documentos podem trazer dados de outras pessoas.",
  },
  tipos: [{ valor: "ma", rotulo: "Fusão ou aquisição" }],
  prazos_em_dias: [90, 180, 365],
  prazo_padrao_em_dias: 180,
  operacoes: [OPERACAO],
};

const PAINEL: PainelV1 = {
  operacao: OPERACAO,
  tipo_rotulo: "Fusão ou aquisição",
  documentos: [
    {
      id: "d1",
      nome: "dfs.pdf",
      tipo: "pdf",
      tamanho_bytes: 2048,
      paginas: 3,
      situacao: "lido",
      rotulo_da_situacao: "Lido",
      recebido_em: "2026-10-21T10:00:00Z",
    },
  ],
  evidencias: [
    {
      id: "e1",
      documento: "dfs.pdf",
      metrica: "receita_liquida",
      periodo: "2025",
      valor: "1000 milhares BRL",
      pagina: 1,
      trecho: "Receita liquida 1000",
      conferida: true,
      estado_de_revisao: "extraida",
    },
  ],
  contradicoes: [
    {
      id: "c1",
      estado: "aberta",
      rotulo_do_estado: "Aberta",
      nota: null,
      metrica: "receita_liquida",
      periodo: "2025",
      documento_a: "dfs.pdf",
      documento_b: "apresentacao.pdf",
      valor_a: "1000 milhares BRL",
      valor_b: "1200 milhares BRL",
    },
  ],
  checklist: [
    {
      codigo: "ma_estatuto",
      titulo: "Estatuto social",
      ajuda: "O estatuto vigente da empresa.",
      estado: "pendente",
      rotulo_do_estado: "Pendente",
      documento: null,
      nota: null,
    },
  ],
  estados_do_checklist: [
    { valor: "pendente", rotulo: "Pendente" },
    { valor: "recebido", rotulo: "Recebido" },
    { valor: "revisado", rotulo: "Revisado por você" },
  ],
  itens_a_revisar: 1,
};

function abrir(extra?: (endereco: string, pedido?: RequestInit) => Response | undefined, eu = ADMIN) {
  return abrirApp("/sala-de-dados", {
    eu: () => respostaJson(200, eu),
    rotas: (endereco, pedido) => {
      const outra = extra?.(endereco, pedido);
      if (outra) return outra;
      if (endereco.startsWith("/api/v1/sala")) return respostaJson(200, SALA);
      if (endereco === `/api/v1/operacoes/${ID}/painel` || endereco.startsWith(`/api/v1/operacoes/${ID}/painel?`)) {
        return respostaJson(200, PAINEL);
      }
      return undefined;
    },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("sala de dados", () => {
  it("o admin vê o link no menu e a lista com o aviso de prazo e os conceitos", async () => {
    abrir();
    await screen.findByRole("heading", { name: "Sala de dados" });
    expect(screen.getAllByRole("link", { name: "Sala de dados" }).length).toBeGreaterThan(0);
    expect(await screen.findByText(/A sala guarda os documentos/)).toBeTruthy();
    expect(screen.getByText(/1 contradições abertas/)).toBeTruthy();
    expect(screen.getByText("prazo perto")).toBeTruthy();
  });

  it("quem não é admin não vê o link e, pelo endereço, recebe 'não encontrada'", async () => {
    abrir(undefined, ANA);
    await screen.findByRole("heading", { name: /não encontrada/i });
    expect(screen.queryByRole("link", { name: "Sala de dados" })).toBeNull();
  });

  it("abrir a operação mostra documentos, evidências, contradições e checklist, com os textos da API", async () => {
    abrir();
    fireEvent.click(await screen.findByRole("button", { name: "Aquisição da Alfa" }));
    await screen.findByRole("heading", { name: /Documentos \(1\)/ });
    expect(screen.getByText(/Lido/)).toBeTruthy();
    expect(screen.getByText(/1000 milhares BRL/, { selector: "span, li" })).toBeTruthy();
    expect(screen.getByText(/Contradição é quando dois documentos/)).toBeTruthy();
    expect(screen.getByText(/apresentacao.pdf/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Checklist \(faltam revisar 1 de 1\)/ })).toBeTruthy();
    expect(screen.getByText(/O estatuto vigente/)).toBeTruthy();
    expect(screen.getByText(/A operação some em 12 dias/)).toBeTruthy();
  });

  it("explicar uma contradição envia o estado e a nota por PATCH", async () => {
    const { buscar } = abrir((_endereco, pedido) =>
      pedido?.method === "PATCH" ? respostaJson(200, { id: "c1" }) : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Aquisição da Alfa" }));
    const lista = await screen.findByRole("heading", { name: /Contradições \(1\)/ });
    const secao = lista.closest("section") as HTMLElement;
    fireEvent.change(within(secao).getByRole("textbox"), { target: { value: "A apresentação usa outra base." } });
    fireEvent.click(within(secao).getByRole("button", { name: "Explicar" }));
    await waitFor(() => expect(buscar.mock.calls.some(([, p]) => p?.method === "PATCH")).toBe(true));
    const [endereco, pedido] = buscar.mock.calls.find(([, p]) => p?.method === "PATCH")!;
    expect(String(endereco)).toBe(`/api/v1/operacoes/${ID}/contradicoes/c1`);
    expect(JSON.parse(String(pedido?.body))).toEqual({ estado: "explicada", nota: "A apresentação usa outra base." });
  });

  it("marcar um item do checklist envia o estado por PATCH no código do item", async () => {
    const { buscar } = abrir((_endereco, pedido) =>
      pedido?.method === "PATCH" ? respostaJson(200, { codigo: "ma_estatuto" }) : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Aquisição da Alfa" }));
    fireEvent.change(await screen.findByLabelText("Estado de Estatuto social"), { target: { value: "revisado" } });
    await waitFor(() => expect(buscar.mock.calls.some(([, p]) => p?.method === "PATCH")).toBe(true));
    const [endereco, pedido] = buscar.mock.calls.find(([, p]) => p?.method === "PATCH")!;
    expect(String(endereco)).toBe(`/api/v1/operacoes/${ID}/checklist/ma_estatuto`);
    expect(JSON.parse(String(pedido?.body))).toEqual({ estado: "revisado" });
  });

  it("Baixar a sala pede o ZIP por GET e entrega o arquivo", async () => {
    const criar = vi.fn(() => "blob:zip");
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() });
    const clicar = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { buscar } = abrir((endereco) =>
      endereco === `/api/v1/operacoes/${ID}/sala`
        ? new Response("PK", { status: 200, headers: { "content-type": "application/zip" } })
        : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Aquisição da Alfa" }));
    fireEvent.click(await screen.findByRole("button", { name: "Baixar a sala" }));
    await waitFor(() => expect(clicar).toHaveBeenCalled());
    const [[endereco, pedido]] = buscar.mock.calls.filter(([e]) => String(e).endsWith("/sala") && String(e).includes(ID));
    expect(String(endereco)).toBe(`/api/v1/operacoes/${ID}/sala`);
    expect(pedido?.method).toBe("GET");
    clicar.mockRestore();
  });

  it("enviar um documento manda o arquivo no campo 'arquivo' (multipart, sem Content-Type fixo)", async () => {
    const { buscar } = abrir((endereco, pedido) =>
      pedido?.method === "POST" && endereco.endsWith("/documentos") ? respostaJson(201, { id: "d2" }) : undefined,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Aquisição da Alfa" }));
    const formulario = await screen.findByRole("form", { name: "Enviar documento" });
    const arquivo = new File(["%PDF-1.7"], "novo.pdf", { type: "application/pdf" });
    fireEvent.change(within(formulario).getByLabelText(/Enviar documento \(PDF/), { target: { files: [arquivo] } });
    fireEvent.submit(formulario);
    await waitFor(() => expect(buscar.mock.calls.some(([e, p]) => p?.method === "POST" && String(e).endsWith("/documentos"))).toBe(true));
    const [, pedido] = buscar.mock.calls.find(([e, p]) => p?.method === "POST" && String(e).endsWith("/documentos"))!;
    expect(pedido?.body).toBeInstanceOf(FormData);
    expect((pedido?.body as FormData).get("arquivo")).toBeTruthy();
    expect((pedido?.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });
});
