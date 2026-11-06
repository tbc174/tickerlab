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
function abrir({ reduzirMovimento, resto = "" }: { reduzirMovimento: boolean; resto?: string }) {
  document.body.innerHTML = HEROI + resto;
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
  it("o sumário marca a seção que está na tela (páginas de leitura)", () => {
    // um IntersectionObserver falso: o teste diz quando cada seção aparece
    const observados = new Map<Element, (es: unknown[]) => void>();
    window.IntersectionObserver = class {
      constructor(private aoVer: (es: unknown[]) => void) {}
      observe(el: Element) { observados.set(el, this.aoVer); }
      unobserve() {}
      disconnect() {}
    } as unknown as typeof IntersectionObserver;
    abrir({
      reduzirMovimento: true,
      resto: `
        <nav class="v2-sumario" data-sumario><ol>
          <li><a href="#um">Um</a></li><li><a href="#dois">Dois</a></li>
        </ol></nav>
        <section class="v2-texto"><h2 id="um">Um</h2><h2 id="dois">Dois</h2></section>`,
    });
    const dois = document.getElementById("dois")!;
    observados.get(dois)!([{ isIntersecting: true, target: dois }]);
    const [linkUm, linkDois] = document.querySelectorAll(".v2-sumario a");
    expect(linkDois.getAttribute("aria-current")).toBe("true");
    expect(linkUm.hasAttribute("aria-current")).toBe(false);
    delete (window as { IntersectionObserver?: unknown }).IntersectionObserver;
  });

  it("o que a rolagem rápida pulou não fica escondido acima da tela", () => {
    // o IntersectionObserver só avisa quando o estado muda entre dois quadros: o que passou de baixo
    // para cima da tela num pulo (âncora, rolagem rápida) nunca "apareceu"
    window.IntersectionObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof IntersectionObserver;
    abrir({
      reduzirMovimento: false,
      resto: `<section class="secao"><div class="grade"><article id="pulado"></article><article id="adiante"></article></div></section>`,
    });
    const pulado = document.getElementById("pulado")!;
    const adiante = document.getElementById("adiante")!;
    expect(pulado.classList.contains("v2-revelar")).toBe(true);
    vi.spyOn(pulado, "getBoundingClientRect").mockReturnValue({ top: -900, bottom: -500 } as DOMRect);
    vi.spyOn(adiante, "getBoundingClientRect").mockReturnValue({ top: 2000, bottom: 2400 } as DOMRect);
    window.requestAnimationFrame = ((f: FrameRequestCallback) => { f(0); return 0; }) as typeof requestAnimationFrame;
    window.dispatchEvent(new Event("scroll"));
    expect(pulado.classList.contains("visivel")).toBe(true);
    expect(adiante.classList.contains("visivel")).toBe(false);
    delete (window as { IntersectionObserver?: unknown }).IntersectionObserver;
  });

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
