// @vitest-environment jsdom
// As animações do site (publico/movimento.js, ADR 0065): o que roda sem parar obedece ao botão de
// pausa (WCAG 2.2.2) e ao "reduzir movimento" do aparelho. Roda o arquivo de verdade no jsdom.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderizar } from "../src/entry-server";

const MOVIMENTO_JS = readFileSync(join(process.cwd(), "publico", "movimento.js"), "utf8");

// o pedaço do hero que importa aqui: o fundo em canvas e o botão de pausa
const HEROI = `
  <div class="escura v2-heroi-fundo">
    <canvas class="v2-mercado" data-fundo-mercado aria-hidden="true"></canvas>
    <button class="v2-pausa" type="button" data-pausa aria-pressed="false"><span>Pausar animação</span></button>
  </div>`;

/** Abre a página com o hero e roda o movimento.js, com ou sem "reduzir movimento". */
function abrir({ reduzirMovimento }: { reduzirMovimento: boolean }) {
  document.body.innerHTML = HEROI;
  // o jsdom não tem matchMedia nem desenho em canvas: um falso de cada
  window.matchMedia = ((consulta: string) => ({
    matches: consulta.includes("prefers-reduced-motion") ? reduzirMovimento : false,
  })) as unknown as typeof window.matchMedia;
  const pincel = new Proxy({}, { get: () => () => ({ addColorStop() {} }) });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    pincel as unknown as CanvasRenderingContext2D,
  );
  const quadros = vi.fn();
  window.requestAnimationFrame = quadros;
  new Function(MOVIMENTO_JS)();
  const botao = document.querySelector<HTMLButtonElement>("[data-pausa]")!;
  return { quadros, botao };
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  document.documentElement.className = "";
});

describe("movimento.js", () => {
  it("sem 'reduzir movimento', o fundo começa a se mexer (controle do teste abaixo)", () => {
    const { quadros, botao } = abrir({ reduzirMovimento: false });
    expect(quadros).toHaveBeenCalled();
    expect(botao.hidden).toBe(false);
  });

  it("com 'reduzir movimento', nada roda sem parar e o botão de pausa some", () => {
    const { quadros, botao } = abrir({ reduzirMovimento: true });
    expect(quadros).not.toHaveBeenCalled();
    expect(botao.hidden).toBe(true);
    // e nada fica escondido esperando uma animação que não vai acontecer
    expect(document.documentElement.classList.contains("v2-anima")).toBe(false);
  });

  it("pausar grava a escolha e troca o rótulo do botão", () => {
    const { botao } = abrir({ reduzirMovimento: false });
    botao.click();
    expect(localStorage.getItem("tl-animacao-pausada")).toBe("1");
    expect(botao.getAttribute("aria-pressed")).toBe("true");
    expect(botao.textContent).toBe("Retomar animação");
    expect(document.documentElement.classList.contains("v2-pausado")).toBe(true);
  });

  it("a pausa escolhida antes vale ao abrir outra página", () => {
    localStorage.setItem("tl-animacao-pausada", "1");
    const { quadros, botao } = abrir({ reduzirMovimento: false });
    expect(quadros).not.toHaveBeenCalled();
    expect(botao.textContent).toBe("Retomar animação");
  });

  it("navegador sem canvas: o script não quebra", () => {
    document.body.innerHTML = HEROI;
    window.matchMedia = (() => ({ matches: false })) as unknown as typeof window.matchMedia;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    expect(() => new Function(MOVIMENTO_JS)()).not.toThrow();
  });
});

describe("o HTML carrega o movimento.js", () => {
  it("com a versão no endereço e defer, em toda página", () => {
    const versao = /<script src="\/movimento\.js\?v=([0-9a-f]{12})" defer=""><\/script>/;
    expect(renderizar("index.html")).toMatch(versao);
    expect(renderizar("sobre.html")).toMatch(versao);
  });
});
