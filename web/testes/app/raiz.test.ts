// O app saiu de /novo/ para a raiz (plano de 18/10). Quem ainda tem o endereço antigo (favorito, app
// instalado, service worker velho) é levado ao mesmo caminho na raiz, e o service worker de /novo/ é
// desregistrado: rede de segurança para o caso de o redirecionamento do nginx falhar.
import { describe, expect, it, vi } from "vitest";
import { caminhoSemONovo, desregistrarServicoDoNovo } from "../../src/app/raiz";

describe("quem chega pelo endereço antigo /novo", () => {
  it("vai ao mesmo caminho na raiz, com a consulta e o #", () => {
    expect(caminhoSemONovo({ pathname: "/novo/", search: "", hash: "" })).toBe("/");
    expect(caminhoSemONovo({ pathname: "/novo", search: "", hash: "" })).toBe("/");
    expect(caminhoSemONovo({ pathname: "/novo/planos", search: "?assinatura=ok", hash: "" })).toBe(
      "/planos?assinatura=ok",
    );
    expect(caminhoSemONovo({ pathname: "/novo/c", search: "", hash: "#codigo" })).toBe("/c#codigo");
  });

  it("quem já está na raiz (ou num caminho parecido) fica onde está", () => {
    expect(caminhoSemONovo({ pathname: "/", search: "", hash: "" })).toBeNull();
    expect(caminhoSemONovo({ pathname: "/visao-geral", search: "?ticker=PETR4", hash: "" })).toBeNull();
    expect(caminhoSemONovo({ pathname: "/novos-dados", search: "", hash: "" })).toBeNull();
    expect(caminhoSemONovo({ pathname: "/classico/novo", search: "", hash: "" })).toBeNull();
  });
});

describe("o service worker antigo de /novo/", () => {
  it("é desregistrado; o da raiz e os de outros escopos ficam", async () => {
    const registros = [
      { scope: "https://app.tickerlab.com.br/novo/", unregister: vi.fn(async () => true) },
      { scope: "https://app.tickerlab.com.br/", unregister: vi.fn(async () => true) },
    ];
    await desregistrarServicoDoNovo({ getRegistrations: async () => registros });
    expect(registros[0].unregister).toHaveBeenCalled();
    expect(registros[1].unregister).not.toHaveBeenCalled();
  });
});
