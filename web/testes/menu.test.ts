// @vitest-environment jsdom
// O menu do celular (publico/site.js): o botão do topo abre e fecha a mesma lista de itens.
// Roda o site.js de verdade no jsdom, sobre o topo que o React gera.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderizar } from "../src/entry-server";

const SITE_JS = readFileSync(join(process.cwd(), "publico", "site.js"), "utf8");
const TOPO = renderizar("sobre.html").match(/<header[\s\S]*?<\/header>/)![0];

function abrir() {
  document.body.innerHTML = TOPO + "<main><p>conteúdo</p></main>";
  window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
  vi.useFakeTimers(); // o site.js confere o tema a cada minuto
  new Function(SITE_JS)();
  const botao = document.querySelector<HTMLButtonElement>("[data-menu-botao]")!;
  const menu = document.getElementById(botao.getAttribute("aria-controls")!)!;
  return { botao, menu };
}

beforeEach(() => vi.useRealTimers());

describe("menu do celular", () => {
  it("abre a lista do topo, com os mesmos itens, e fecha no segundo toque", () => {
    const { botao, menu } = abrir();
    expect(menu.getAttribute("aria-label")).toBe("Principal");
    expect(menu.querySelectorAll("a").length).toBeGreaterThanOrEqual(5);
    expect(botao.getAttribute("aria-expanded")).toBe("false");

    botao.click();
    expect(menu.hasAttribute("data-aberto")).toBe(true);
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    expect(botao.getAttribute("aria-label")).toBe("Fechar o menu");

    botao.click();
    expect(menu.hasAttribute("data-aberto")).toBe(false);
    expect(botao.getAttribute("aria-label")).toBe("Abrir o menu");
  });

  it("fecha com Esc (e devolve o foco ao botão), com um toque fora e ao escolher um item", () => {
    const { botao, menu } = abrir();
    botao.click();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(menu.hasAttribute("data-aberto")).toBe(false);
    expect(document.activeElement).toBe(botao);

    botao.click();
    document.querySelector("main")!.click();
    expect(menu.hasAttribute("data-aberto")).toBe(false);

    botao.click();
    const item = menu.querySelector("a")!;
    item.addEventListener("click", (e) => e.preventDefault()); // o jsdom não navega
    item.click();
    expect(menu.hasAttribute("data-aberto")).toBe(false);
  });
});
