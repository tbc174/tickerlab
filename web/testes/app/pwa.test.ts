// O app instalável (PWA, ADR 0066; série site e app v2, PR 5): o manifesto e o service worker que
// guarda só a casca do app. Risco 6 do plano: nunca guardar resposta da API, o token nem dado de conta.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { marca } from "../../src/conteudo";
import { ICONES, manifesto, servicoDaCasca } from "../../src/app/pwa";

describe("manifesto", () => {
  const m = manifesto();

  it("abre o app em /novo/ em tela cheia, com as cores da marca", () => {
    expect(m).toMatchObject({
      name: "TickerLab",
      start_url: "/novo/",
      scope: "/novo/",
      display: "standalone",
      lang: "pt-BR",
      theme_color: marca.marinho,
      background_color: marca.marinho,
    });
    expect(m.short_name.length).toBeLessThanOrEqual(12); // cabe embaixo do ícone
  });

  it("ícones de 192 e 512 e o maskable (que o celular recorta)", () => {
    const tamanhos = m.icons.map((i) => `${i.sizes} ${i.purpose ?? "any"}`);
    expect(tamanhos).toEqual(expect.arrayContaining(["192x192 any", "512x512 any", "512x512 maskable"]));
    for (const icone of m.icons) expect(icone.src).toMatch(/^\/novo\/icones\/[a-z0-9-]+\.png$/);
    expect(Object.keys(ICONES)).toContain("apple-touch-icon.png");
  });
});

// um service worker de mentira: os `addEventListener` do sw.js, o cache e a rede espiados
function rodarServico(casca: string[]) {
  const ouvintes: Record<string, (evento: unknown) => void> = {};
  // como depois da instalação: a casca já está guardada
  const guardado = new Map<string, string>(casca.map((u) => [u, "casca"]));
  const cache = {
    addAll: vi.fn(async (urls: string[]) => urls.forEach((u) => guardado.set(u, "casca"))),
    put: vi.fn(),
  };
  const caches = {
    open: vi.fn(async () => cache),
    keys: vi.fn(async () => ["tl-casca-velha", "outro-cache"]),
    delete: vi.fn(async () => true),
    match: vi.fn(async (pedido: Request | string) =>
      guardado.has(typeof pedido === "string" ? pedido : new URL(pedido.url).pathname + new URL(pedido.url).search)
        ? new Response("da casca")
        : undefined,
    ),
  };
  const rede = vi.fn(async () => new Response("da rede"));
  const self = {
    addEventListener: (tipo: string, f: (evento: unknown) => void) => (ouvintes[tipo] = f),
    location: { origin: "https://app.tickerlab.com.br" },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  };
  new Function("self", "caches", "fetch", servicoDaCasca(casca, "abc123"))(self, caches, rede);

  /** Um pedido passando pelo service worker: devolve se ele respondeu e com o quê. */
  async function pedir(caminho: string, { mode, ...opcoes }: RequestInit = {}) {
    // o Request do Node não aceita mode "navigate" (só o navegador cria esse pedido)
    const pedido = new Request(`https://app.tickerlab.com.br${caminho}`, opcoes);
    if (mode) Object.defineProperty(pedido, "mode", { value: mode });
    let resposta: Promise<Response> | undefined;
    ouvintes.fetch({ request: pedido, respondWith: (r: Promise<Response>) => (resposta = r) });
    return resposta ? (await resposta).text() : "sem interferir";
  }
  return { ouvintes, cache, caches, rede, pedir };
}

describe("service worker só da casca (risco 6)", () => {
  const CASCA = ["/novo/", "/novo/assets/index-abc.js", "/novo/estilo.css?v=123"];

  it("ao instalar, guarda só a lista da casca, num cache com a versão do build", async () => {
    const { ouvintes, cache, caches } = rodarServico(CASCA);
    let espera: Promise<unknown> = Promise.resolve();
    ouvintes.install({ waitUntil: (p: Promise<unknown>) => (espera = p) });
    await espera;
    expect(caches.open).toHaveBeenCalledWith("tl-casca-abc123");
    expect(cache.addAll).toHaveBeenCalledWith(CASCA);
  });

  it("ao ativar, apaga as cascas antigas (e só as dele)", async () => {
    const { ouvintes, caches } = rodarServico(CASCA);
    let espera: Promise<unknown> = Promise.resolve();
    ouvintes.activate({ waitUntil: (p: Promise<unknown>) => (espera = p) });
    await espera;
    expect(caches.delete).toHaveBeenCalledWith("tl-casca-velha");
    expect(caches.delete).not.toHaveBeenCalledWith("outro-cache");
  });

  it("a API e qualquer pedido com token nunca passam pelo cache", async () => {
    const { pedir, caches } = rodarServico(CASCA);
    expect(await pedir("/api/v1/eu")).toBe("sem interferir");
    expect(await pedir("/novo/assets/index-abc.js", { headers: { Authorization: "Bearer x" } })).toBe(
      "sem interferir",
    );
    expect(await pedir("/api/v1/conta", { method: "POST" })).toBe("sem interferir");
    expect(caches.match).not.toHaveBeenCalled();
  });

  it("o que é da casca vem do cache; o resto, da rede, sem guardar nada novo", async () => {
    const { pedir, cache } = rodarServico(CASCA);
    expect(await pedir("/novo/assets/index-abc.js")).toBe("da casca");
    expect(await pedir("/novo/assets/outro.js")).toBe("da rede");
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("abrir uma tela vai à rede primeiro; sem internet, mostra a casca guardada", async () => {
    const { pedir, rede } = rodarServico(CASCA);
    expect(await pedir("/novo/visao-geral", { mode: "navigate" })).toBe("da rede");
    rede.mockRejectedValueOnce(new TypeError("sem internet"));
    expect(await pedir("/novo/visao-geral", { mode: "navigate" })).toBe("da casca");
  });

  it("fora do /novo/ (o Streamlit em app.tickerlab.com.br/) ele não se mete", async () => {
    const { pedir } = rodarServico(CASCA);
    expect(await pedir("/visao-geral", { mode: "navigate" })).toBe("sem interferir");
  });

  it("o código não tem como guardar nada além da casca", () => {
    const codigo = servicoDaCasca(CASCA, "abc123");
    expect(codigo).not.toMatch(/\.put\(|localStorage|indexedDB/);
  });
});

describe("o build gravado em novo/ (rode `npm run app` se falhar)", () => {
  const NOVO = join(process.cwd(), "..", "novo");
  const sw = readFileSync(join(NOVO, "sw.js"), "utf8");
  const casca: string[] = JSON.parse(sw.match(/var CASCA = (\[.*\]);/)![1]);
  const pagina = readFileSync(join(NOVO, "index.html"), "utf8");

  it("todo arquivo da casca existe no build", () => {
    for (const url of casca.filter((u) => u !== "/novo/"))
      expect(existsSync(join(NOVO, url.replace(/^\/novo\//, "").replace(/\?.*$/, ""))), url).toBe(true);
  });

  it("o que a página pede está na casca com o mesmo endereço (o ?v= também), para abrir sem internet", () => {
    const pedidos = [...pagina.matchAll(/(?:href|src)="(\/novo\/[^"]+)"/g)].map((m) => m[1]);
    expect(pedidos.length).toBeGreaterThan(3);
    for (const url of pedidos) expect(casca, url).toContain(url);
  });

  it("o manifesto gravado é o de pwa.ts, ligado na página", () => {
    expect(JSON.parse(readFileSync(join(NOVO, "manifest.json"), "utf8"))).toEqual(manifesto());
    expect(pagina).toContain('<link rel="manifest" href="/novo/manifest.json">');
  });
});
