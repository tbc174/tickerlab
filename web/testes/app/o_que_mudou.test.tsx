// @vitest-environment jsdom
// O que mudou (linha 804): uma linha por dia com o que entrou no app e o link para abrir a página.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { OQueMudouV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const O_QUE_MUDOU: OQueMudouV1 = {
  entregas: [
    { data: "2026-11-11", o_que: "Esta página.", titulo: "O que mudou", url: "o-que-mudou" },
    { data: "2026-11-10", o_que: "Ficha por CNPJ.", titulo: "Ficha da empresa", url: "ficha-da-empresa" },
    { data: "2026-11-10", o_que: "Outra no mesmo dia.", titulo: "Planos e assinatura", url: "planos" },
  ],
};

afterEach(cleanup);

describe("o que mudou", () => {
  it("agrupa por dia, a mais nova primeiro, com o link de cada página", async () => {
    abrirApp("/o-que-mudou", {
      rotas: (endereco) => (endereco === "/api/v1/o-que-mudou" ? respostaJson(200, O_QUE_MUDOU) : undefined),
    });
    const dias = await screen.findAllByRole("region", {}, { timeout: 5000 });
    const nomes = dias.map((dia) => dia.getAttribute("aria-label"));
    expect(nomes).toEqual(["11/11/2026", "10/11/2026"]);
    const links = within(dias[1]).getAllByRole("link");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Ficha da empresa", "/ficha-da-empresa"],
      ["Planos e assinatura", "/planos"],
    ]);
    expect(within(dias[1]).getByText("Ficha por CNPJ.")).toBeTruthy();
  });

  it("sem nenhuma linha: uma frase, não uma lista vazia", async () => {
    abrirApp("/o-que-mudou", {
      rotas: (endereco) => (endereco === "/api/v1/o-que-mudou" ? respostaJson(200, { entregas: [] }) : undefined),
    });
    expect(await screen.findByText(/Nada novo por enquanto/, {}, { timeout: 5000 })).toBeTruthy();
  });
});
