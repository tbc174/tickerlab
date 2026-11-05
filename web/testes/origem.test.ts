// @vitest-environment jsdom
// A origem do cadastro (publico/origem.js): quem chega por um link de campanha ganha o cookie
// próprio `tl_origem`, que o app lê no primeiro login (src/origem.py tem o formato e a validação).
// Roda o origem.js de verdade no jsdom, com o endereço e os cookies de cada caso.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ORIGEM_JS = readFileSync(join(process.cwd(), "publico", "origem.js"), "utf8");

function chegarEm(endereco: string) {
  window.history.replaceState(null, "", endereco);
  new Function(ORIGEM_JS)();
}

function cookieDaOrigem(): string | null {
  const par = document.cookie.split("; ").find((c) => c.startsWith("tl_origem="));
  return par ? decodeURIComponent(par.slice("tl_origem=".length)) : null;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-03T15:00:00Z"));
});

afterEach(() => {
  document.cookie = "tl_origem=; Max-Age=0; Path=/";
  vi.useRealTimers();
});

describe("origem do cadastro", () => {
  it("grava as UTMs, o ref e o dia da 1ª visita no formato que o app lê", () => {
    chegarEm(
      "/relatorio-de-setor-eletricas.html?utm_source=linkedin&utm_medium=organico" +
        "&utm_campaign=relatorio-eletricas&utm_content=post-2026-11-03&ref=liga-ibmec",
    );
    expect(cookieDaOrigem()).toBe(
      "s=linkedin|m=organico|c=relatorio-eletricas|t=post-2026-11-03|r=liga-ibmec|v=2026-11-03",
    );
  });

  it("sem link de campanha, não grava nada", () => {
    chegarEm("/produto.html?ticker=PETR4.SA");
    expect(cookieDaOrigem()).toBeNull();
  });

  it("só a primeira origem fica: outro link depois não troca o cookie", () => {
    chegarEm("/?utm_source=ibmec&utm_medium=oficina");
    chegarEm("/?utm_source=google&utm_medium=cpc");
    expect(cookieDaOrigem()).toBe("s=ibmec|m=oficina|v=2026-11-03");
  });

  it("valor fora do padrão (e-mail, maiúscula, espaço) fica de fora, para nada pessoal entrar", () => {
    chegarEm("/?utm_source=linkedin&utm_campaign=ana%40exemplo.com&utm_content=Post%201");
    expect(cookieDaOrigem()).toBe("s=linkedin|v=2026-11-03");
  });

  it("link só com valores inválidos não grava nada", () => {
    chegarEm("/?utm_source=Ana%20Silva&ref=" + "x".repeat(61));
    expect(cookieDaOrigem()).toBeNull();
  });

  it("o cookie vale para o app (domínio do TickerLab) e é só do nosso site", () => {
    const escritos: string[] = [];
    vi.spyOn(document, "cookie", "set").mockImplementation((v: string) => {
      escritos.push(v);
    });
    vi.spyOn(document, "cookie", "get").mockImplementation(() => "");
    const local = { hostname: "tickerlab.com.br", protocol: "https:", search: "?utm_source=email" };
    new Function("location", ORIGEM_JS)(local);
    expect(escritos).toHaveLength(1);
    expect(escritos[0]).toContain("Domain=.tickerlab.com.br");
    expect(escritos[0]).toContain("SameSite=Lax");
    expect(escritos[0]).toContain("Secure");
    expect(escritos[0]).toMatch(/Max-Age=\d+/);
    vi.restoreAllMocks();
  });
});
