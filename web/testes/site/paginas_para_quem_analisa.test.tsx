// O site inteiro fala com quem analisa empresas (plano do site para quem analisa, PR 9, tarefa 15):
// todas as páginas, menos a vitrine de Ferramentas, as calculadoras, os textos legais e a 404, têm
// título e descrição sem "investir", nenhuma frase de recomendação ou de comparação por abrangência,
// e a assinatura antiga não volta. As páginas novas do PR (Como funciona, Produto, Metodologia, Sobre)
// têm cada uma o seu teste de conteúdo.
import { describe, expect, it } from "vitest";
import { renderizar } from "../../src/entry-server";
import { ROTAS } from "../../src/rotas";

const semTags = (html: string) => html.replace(/<[^>]+>/g, "");
const principal = (html: string) => html.slice(html.indexOf("<main"), html.indexOf("</main>"));
// o texto como o React escreve no HTML
const esc = (texto: string) =>
  texto.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");

const FORA_DA_FRENTE = new Set(["ferramentas.html", "404.html", "termos.html", "privacidade.html"]);
const PAGINAS = ROTAS.filter(
  (r) => !FORA_DA_FRENTE.has(r.arquivo) && !renderizar(r.arquivo).includes("data-ferramenta="),
);

// frase que parece recomendação, previsão ou comparação por abrangência (plano, seção 7), e o que a
// assinatura antiga dizia (ADR 0099)
const PROIBIDAS = [
  /recomend/i,
  /vai subir/i,
  /oportunidade/i,
  /mais dados que/i,
  /maior base/i,
  /Bloomberg|FactSet|Refinitiv|Economatica|brapi|Status ?Invest/i,
  /para investir/i,
  /Menos ruído/i,
];
// o aviso obrigatório e a negação ("não é recomendação") são as únicas "recomendações" que podem aparecer
const AVISOS = /(nada aqui é|nada é|não é uma|não é|não uma|nem) recomendação( de investimento)?/gi;

describe("as páginas do site falam com quem analisa empresas", () => {
  it("a lista confere: as páginas de frente estão dentro, as fora da frente não", () => {
    const nomes = PAGINAS.map((r) => r.arquivo);
    for (const dentro of [
      "index.html",
      "produto.html",
      "como-funciona.html",
      "dados.html",
      "aprender.html",
      "sobre.html",
      "precos.html",
      "metodologia.html",
      "relatorios.html",
      "relatorio-de-exemplo.html",
    ])
      expect(nomes, dentro).toContain(dentro);
    for (const fora of ["ferramentas.html", "calculadora-de-juros-compostos.html", "404.html"])
      expect(nomes, fora).not.toContain(fora);
  });

  it.each(PAGINAS.map((r) => [r.arquivo, r] as const))(
    "%s: título e descrição sem 'investir' e a descrição cabe no Google",
    (_arquivo, rota) => {
      for (const texto of [rota.dados.titulo, rota.dados.descricao])
        expect(texto, texto).not.toMatch(/investir|investidor/i);
      expect(rota.dados.descricao.length).toBeLessThanOrEqual(160);
      expect(renderizar(rota.arquivo)).toContain(
        `<meta name="description" content="${esc(rota.dados.descricao)}"`,
      );
    },
  );

  it.each(PAGINAS.map((r) => [r.arquivo] as const))(
    "%s: sem frase de recomendação, de comparação ou da assinatura antiga",
    (arquivo) => {
      const html = renderizar(arquivo);
      const texto = semTags(principal(html)).replace(AVISOS, "");
      for (const proibida of PROIBIDAS) expect(proibida.test(texto), String(proibida)).toBe(false);
      expect(semTags(html)).not.toMatch(/Menos ruído|Mais inteligência para investir/);
    },
  );
});

describe("Como funciona começa pela coleta", () => {
  const html = renderizar("como-funciona.html");
  const texto = semTags(principal(html));

  it("os cinco passos, na ordem: fonte, original com hash, versões, porta e relatório", () => {
    const passos = [
      ...principal(html).matchAll(/<ol class="passos">([\s\S]*?)<\/ol>/g),
    ][0][1].match(/<h3>[^<]+<\/h3>/g);
    expect(passos?.map((h) => semTags(h))).toEqual([
      "A fonte",
      "O original, com hash",
      "As versões",
      "A porta",
      "O relatório",
    ]);
  });

  it("a coleta vem antes de 'para quem é' e das perguntas", () => {
    const quem = texto.indexOf("Para quem é");
    expect(texto.indexOf("A fonte")).toBeGreaterThanOrEqual(0);
    expect(texto.indexOf("A fonte")).toBeLessThan(quem);
    expect(quem).toBeLessThan(texto.indexOf("Perguntas frequentes"));
  });

  it("diz para quem é: analista, estudante ou pesquisador e equipe", () => {
    for (const quem of ["Quem analisa empresas", "Estudantes e pesquisadores", "Equipes"])
      expect(texto, quem).toContain(quem);
  });

  it("as explicações técnicas ficam recolhidas em 'Como foi calculado'", () => {
    expect(principal(html)).toContain('<details class="como-foi-calculado">');
  });
});

describe("Metodologia: como era na data e linhagem", () => {
  const html = renderizar("metodologia.html");

  it("tem a seção, no sumário e antes das contas de mercado", () => {
    expect(html).toContain('<h2 id="como-era-na-data-e-linhagem">');
    expect(html).toContain('href="#como-era-na-data-e-linhagem"');
    expect(html.indexOf('id="como-era-na-data-e-linhagem"')).toBeLessThan(
      html.indexOf('id="dados-de-mercado"'),
    );
  });

  it("explica os dois princípios com as mesmas frases da página inicial", () => {
    const texto = semTags(html);
    expect(texto).toContain("nunca enxerga o que só ficou público depois dela");
    expect(texto).toContain("de qual fonte vem");
    expect(texto).toContain("versão do contrato");
  });

  it("as contas de mercado e do teste de estratégia ficam em 'Como foi calculado'", () => {
    const calculos = html.slice(html.indexOf('id="como-os-numeros-sao-calculados"'));
    expect(calculos.indexOf('<details class="como-foi-calculado">')).toBeGreaterThanOrEqual(0);
    expect(calculos.indexOf('<details class="como-foi-calculado">')).toBeLessThan(
      calculos.indexOf("Retornos diários a partir do fechamento"),
    );
  });
});

describe("Sobre diz para quem é", () => {
  const html = renderizar("sobre.html");

  it("tem a seção 'Para quem é', com quem analisa, estudantes e equipes", () => {
    expect(html).toContain('id="para-quem-e"');
    const texto = semTags(html.slice(html.indexOf('id="para-quem-e"')));
    for (const quem of ["analistas", "estudantes", "equipes"])
      expect(texto.toLowerCase(), quem).toContain(quem);
  });

  it("não perde as seções do texto aprovado", () => {
    for (const secao of ["quem-somos", "nossa-historia", "no-que-acreditamos"])
      expect(html).toContain(`id="${secao}"`);
  });
});

describe("Produto: o resumo em três blocos", () => {
  const html = renderizar("produto.html");

  it("tem os blocos relatórios, a base e exportar, cada um com o seu caminho", () => {
    const principalHtml = principal(html);
    for (const [id, destino] of [
      ["bloco-relatorios", "/relatorios.html"],
      ["bloco-a-base", "/dados.html"],
      ["bloco-exportar", "/metodologia.html#relatorios-em-pdf"],
    ] as const) {
      expect(principalHtml, id).toContain(`id="${id}"`);
      expect(principalHtml, id).toContain(`href="${destino}"`);
    }
  });

  it("os blocos vêm antes dos módulos do app", () => {
    expect(html.indexOf('id="bloco-exportar"')).toBeLessThan(html.indexOf('id="research"'));
  });
});
