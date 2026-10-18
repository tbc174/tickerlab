// A escala de espaçamento e de tipos do app novo (ADR 0096): nenhuma margem, respiro ou vão com número
// solto em app.css. Tudo sai de --e1…--e7 (4, 8, 12, 16, 24, 32 e 48 px) e o texto de --t-1…--t3.
// Fica de fora só o que tem medida própria: as abas do celular (altura de toque e área segura do iPhone),
// o cartão do fundo animado (clamp responsivo) e o respiro do fim da página atrás das abas.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(process.cwd(), "src", "app", "app.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const ESPACOS = /^(margin|padding)(-[a-z]+)*$|^(row-|column-)?gap$/;
const FORA_DA_ESCALA = ["body", ".app-abas", ".app-fundo"];
const ESCALA = { "--e1": ".25rem", "--e2": ".5rem", "--e3": ".75rem", "--e4": "1rem", "--e5": "1.5rem", "--e6": "2rem", "--e7": "3rem" };

function blocos() {
  return [...CSS.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, seletor, corpo]) => ({
    seletor: seletor.trim(),
    declaracoes: corpo
      .split(";")
      .map((d) => d.trim())
      .filter(Boolean)
      .map((d) => [d.slice(0, d.indexOf(":")).trim(), d.slice(d.indexOf(":") + 1).trim()] as const),
  }));
}

describe("escala de espaçamento e tipos do app novo", () => {
  it("define --e1…--e7 e --t-1…--t3 no :root", () => {
    const raiz = blocos().find((b) => b.seletor === ":root");
    const declaradas = Object.fromEntries(raiz?.declaracoes ?? []);
    expect(Object.keys(declaradas).filter((n) => /^--[et]/.test(n)).sort()).toEqual(
      ["--e1", "--e2", "--e3", "--e4", "--e5", "--e6", "--e7", "--t-1", "--t0", "--t1", "--t2", "--t3"].sort(),
    );
    for (const [nome, valor] of Object.entries(ESCALA)) expect(declaradas[nome]).toBe(valor);
  });

  it("margem, respiro e vão só usam a escala (ou 0 e auto)", () => {
    const soltos: string[] = [];
    for (const { seletor, declaracoes } of blocos()) {
      if (FORA_DA_ESCALA.some((f) => seletor.startsWith(f))) continue;
      for (const [propriedade, valor] of declaracoes) {
        if (!ESPACOS.test(propriedade)) continue;
        const semVar = valor.replace(/var\(--e[1-7]\)/g, "");
        if (/\d*\.?\d+(rem|em|px|vw|vh|%)/.test(semVar) || /var\(--(?!e[1-7]\))/.test(valor)) {
          soltos.push(`${seletor} { ${propriedade}: ${valor} }`);
        }
      }
    }
    expect(soltos).toEqual([]);
  });

  it("os títulos e o texto usam os tamanhos da escala", () => {
    const tamanho = (seletor: string) =>
      blocos().find((b) => b.seletor === seletor)?.declaracoes.find(([p]) => p === "font-size")?.[1];
    expect(tamanho(".app-corpo main h1")).toBe("var(--t3)");
    expect(tamanho(".app-corpo main h2")).toBe("var(--t2)");
    expect(tamanho(".legenda-do-numero")).toBe("var(--t-1)");
  });
});
