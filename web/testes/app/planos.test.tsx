// @vitest-environment jsdom
// Planos e assinatura no app novo (conta e planos, PRs 3 e 4): o plano da conta, quanto já usou, a
// tabela dos planos (a mesma do Streamlit, src/planos.py) e assinar ou gerenciar pelo Stripe (modo de
// teste). O botão vem da API (src/cobranca.acao_da_assinatura): a tela só mostra.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { navegador } from "../../src/app/navegador";
import { conteudoDoApp, planos } from "../../src/conteudo";
import { abrirApp, respostaJson } from "./ajudantes";

const MEU_PLANO = {
  plano: "gratuito",
  nome_do_plano: "Gratuito",
  simulacoes: "1 de 5",
  favoritos: "2 de 3",
  frase_da_assinatura: null,
  aviso: "Pagamento em modo de teste do Stripe: nenhum dinheiro real é cobrado.",
  tabela: planos.tabela,
  acao: null as string | null,
  texto_da_acao: "Os planos pagos chegam em breve." as string | null,
  nota_do_cartao: "Modo de teste: use o cartão 4242 4242 4242 4242, qualquer data futura.",
};
const CHECKOUT = "https://checkout.stripe.com/c/pay/cs_test_1";
const PORTAL = "https://billing.stripe.com/p/session/test_1";

function abrir(resposta: unknown = MEU_PLANO, caminho = "/planos", stripe = CHECKOUT) {
  return abrirApp(caminho, {
    rotas: (endereco) => {
      if (endereco === "/api/v1/meu-plano") return respostaJson(200, resposta);
      if (endereco === "/api/v1/pagamento-da-assinatura") return respostaJson(200, { url: stripe });
      if (endereco === "/api/v1/portal-da-assinatura") return respostaJson(200, { url: PORTAL });
      return undefined;
    },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("planos", () => {
  it("o plano da conta e quanto já usou", async () => {
    abrir();
    const uso = await screen.findByRole("region", { name: "Seu plano" });
    for (const [rotulo, valor] of [
      ["Seu plano", "Gratuito"],
      ["Simulações salvas", "1 de 5"],
      ["Favoritos", "2 de 3"],
    ]) {
      const numero = within(uso).getByText(rotulo, { exact: true }).closest(".numero-do-painel");
      expect(within(numero as HTMLElement).getByText(valor), rotulo).toBeTruthy();
    }
  });

  it("a tabela dos planos, uma coluna por plano", async () => {
    abrir();
    const tabela = await screen.findByRole("table", { name: "O que cada plano inclui" });
    expect(within(tabela).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Recurso",
      ...planos.nomes,
    ]);
    expect(within(tabela).getAllByRole("row")).toHaveLength(planos.tabela.length + 1);
    expect(within(tabela).getByText("Simulações salvas")).toBeTruthy();
  });

  it("conta comum: sem botão, com a frase que explica (só admins assinam, ADR 0029)", async () => {
    abrir();
    expect(await screen.findByText("Os planos pagos chegam em breve.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Assinar|Gerenciar/ })).toBeNull();
    expect(screen.getByText(MEU_PLANO.aviso)).toBeTruthy();
  });

  it("assinar leva à página de pagamento do Stripe, com o cartão de teste à vista", async () => {
    const ir = vi.spyOn(navegador, "ir").mockImplementation(() => undefined);
    const { buscar } = abrir({ ...MEU_PLANO, acao: "assinar", texto_da_acao: null });
    expect(await screen.findByText(MEU_PLANO.nota_do_cartao)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Assinar o plano Pro" }));
    await waitFor(() => expect(ir).toHaveBeenCalledWith(CHECKOUT));
    const pedido = buscar.mock.calls.find(([e]) => e === "/api/v1/pagamento-da-assinatura");
    expect(pedido?.[1]?.method).toBe("POST");
  });

  it("assinante gerencia pelo portal do Stripe", async () => {
    const ir = vi.spyOn(navegador, "ir").mockImplementation(() => undefined);
    abrir({ ...MEU_PLANO, plano: "pro", nome_do_plano: "Pro", acao: "gerenciar", texto_da_acao: null });
    fireEvent.click(await screen.findByRole("button", { name: "Gerenciar a assinatura" }));
    await waitFor(() => expect(ir).toHaveBeenCalledWith(PORTAL));
  });

  it("endereço que não é do Stripe não abre (segunda barreira)", async () => {
    const ir = vi.spyOn(navegador, "ir").mockImplementation(() => undefined);
    abrir({ ...MEU_PLANO, acao: "assinar", texto_da_acao: null }, "/planos", "https://outro-site.com/pagar");
    fireEvent.click(await screen.findByRole("button", { name: "Assinar o plano Pro" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(ir).not.toHaveBeenCalled();
  });

  it("a volta do pagamento avisa e deixa atualizar o plano", async () => {
    const { buscar } = abrir(MEU_PLANO, "/planos?assinatura=ok");
    expect(await screen.findByText(conteudoDoApp.assinatura.retorno_ok)).toBeTruthy();
    const antes = buscar.mock.calls.filter(([e]) => e === "/api/v1/meu-plano").length;
    fireEvent.click(screen.getByRole("button", { name: "Atualizar o meu plano" }));
    await waitFor(() =>
      expect(buscar.mock.calls.filter(([e]) => e === "/api/v1/meu-plano").length).toBe(antes + 1),
    );
  });

  it("pagamento cancelado: nada foi cobrado", async () => {
    abrir(MEU_PLANO, "/planos?assinatura=cancelada");
    expect(await screen.findByText(conteudoDoApp.assinatura.retorno_cancelado)).toBeTruthy();
  });

  it("com assinatura, diz quando renova", async () => {
    abrir({ ...MEU_PLANO, plano: "pro", nome_do_plano: "Pro", frase_da_assinatura: "Sua assinatura renova em 14/11/2026." });
    expect(await screen.findByText("Sua assinatura renova em 14/11/2026.")).toBeTruthy();
  });

  it("o motivo de uma página fora do plano leva aos planos do app novo", async () => {
    abrirApp("/risco", {
      rotas: (endereco) =>
        endereco.startsWith("/api/v1/risco")
          ? respostaJson(403, { detail: "Faz parte do plano Pro." }, { "X-TickerLab-Motivo": "plano" })
          : undefined,
    });
    const link = await screen.findByRole("link", { name: "Conhecer os planos" });
    expect(link.getAttribute("href")).toBe("/planos");
  });
});
