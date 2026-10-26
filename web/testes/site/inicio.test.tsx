// A página inicial para quem analisa empresas (plano do site para quem analisa, PR 5, tarefa 9):
// a assinatura, o que a base tem (números do catálogo e da medição, nunca digitados), a chamada do
// Raio-X aberta, as cinco vagas da vitrine, os cruzamentos da base (PR 6), as quatro regras, as fontes com licença e os planos.
import { describe, expect, it } from "vitest";
import { baseEmNumeros, catalogo, fatosDaBase, vitrine } from "../../src/conteudo";
import { renderizar } from "../../src/entry-server";
import { css } from "../../src/estilo";
import { DADOS } from "../../src/paginas/Inicio";
import { DADOS as DADOS_DO_RAIO_X } from "../../src/paginas/RaioXDoChoque";
import { ASSINATURA, REGRAS_DA_BASE } from "../../src/site/textos";

const html = renderizar("index.html");
const semTags = (texto: string) => texto.replace(/<[^>]+>/g, "");
// o texto como o React escreve no HTML
const esc = (texto: string) =>
  texto.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");
/** O pedaço do HTML que começa em `inicio` e vai até o primeiro `fim` depois dele. */
function trecho(inicio: string, fim: string): string {
  const de = html.indexOf(inicio);
  expect(de, `não achei ${inicio}`).toBeGreaterThanOrEqual(0);
  return html.slice(de, html.indexOf(fim, de + inicio.length) + fim.length);
}
const principal = () => trecho("<main", "</main>");
const milhares = (n: number) => n.toLocaleString("pt-BR");

// frase que parece recomendação, previsão ou comparação por abrangência (plano, seção 7)
const PROIBIDAS = [
  /recomend/i,
  /vai subir/i,
  /oportunidade/i,
  /mais dados que/i,
  /maior base/i,
  /Bloomberg|FactSet|Refinitiv|Economatica|brapi|Status ?Invest/i,
];
// o aviso obrigatório é a única "recomendação" que pode aparecer
const AVISOS = /(Nada aqui|nada) é recomendação de investimento\.?/g;

describe("página inicial para quem analisa", () => {
  it("o título é a assinatura e o subtítulo fala da coleta auditável", () => {
    expect(semTags(trecho('<h1 id="titulo-heroi">', "</h1>"))).toBe(ASSINATURA);
    expect(principal()).toContain(
      "Coleta segura e auditável das fontes públicas brasileiras: cada número com data, fonte e " +
        "caminho até o original.",
    );
  });

  it("os botões do herói levam aos dados e ao app", () => {
    const heroi = trecho('<section class="heroi faixa"', "</section>");
    expect(heroi).toMatch(/href="\/dados\.html">Ver os dados<\/a>/);
    expect(heroi).toContain(">Abrir o app</a>");
  });

  it("a descrição da página fala com quem analisa e cabe no Google", () => {
    expect(DADOS.descricao.length).toBeLessThanOrEqual(160);
    expect(DADOS.descricao).toMatch(/fonte/);
    expect(html).toContain(`<meta name="description" content="${esc(DADOS.descricao)}"`);
  });

  it("o que a base tem: tabelas, fontes e companhias vindos do catálogo e da medição", () => {
    const painel = trecho('<article class="v2-painel v2-painel-base"', "</article>");
    const texto = semTags(painel);
    expect(texto).toContain("O que a base tem");
    for (const numero of [
      catalogo.totais.tabelas,
      catalogo.totais.fontes,
      baseEmNumeros.numeros.empresas,
    ])
      expect(painel).toContain(`<dd class="v2-numero">${milhares(numero)}</dd>`);
    for (const rotulo of ["tabelas", "fontes públicas", "companhias abertas"])
      expect(texto).toContain(rotulo);
    expect(texto).toContain(`Medido em ${baseEmNumeros.medido_em_curto}`);
    // cada número com a conta recolhida, que abre sem JavaScript
    expect(painel.match(/<details class="como-foi-calculado">/g)).toHaveLength(3);
    expect(painel).not.toMatch(/<details[^>]*\sopen/);
  });

  it("o painel da base também aparece no celular", () => {
    expect(css()).not.toContain(".v2-painel-pilha { display: none; }");
  });

  it("a chamada do Raio-X continua aberta, logo abaixo do herói", () => {
    const estudo = trecho('<section class="faixa v2-estudo"', "</section>");
    expect(estudo).toContain(`href="${DADOS_DO_RAIO_X.caminho}">Ler o Raio-X</a>`);
    expect(html.indexOf("v2-estudo")).toBeLessThan(html.indexOf('class="faixa secao v2-vitrine"'));
  });

  it("as cinco vagas: as prontas em cima com link, as em breve embaixo, sem link", () => {
    const secao = trecho('<section class="faixa secao v2-vitrine"', "</section>");
    const cartoes = secao.split('<article class="cartao v2-vaga').slice(1);
    expect(cartoes).toHaveLength(vitrine.length);
    expect(vitrine.map((v) => v.chave)).toEqual(["setor", "ficha", "cnpj", "ma", "cruzamentos"]);
    const naTela = [
      ...vitrine.filter((v) => v.estado === "pronta"),
      ...vitrine.filter((v) => v.estado !== "pronta"),
    ];
    naTela.forEach((vaga, i) => {
      const cartao = cartoes[i];
      expect(semTags(cartao), vaga.chave).toContain(esc(vaga.titulo));
      expect(semTags(cartao), vaga.chave).toContain(esc(vaga.para_que_serve));
      if (vaga.estado === "pronta") {
        expect(cartao, vaga.chave).toContain(`href="${vaga.link}"`);
      } else {
        expect(cartao, vaga.chave).toContain('<span class="selo breve">Em breve</span>');
        expect(cartao, vaga.chave).not.toContain("href=");
      }
    });
  });

  it("os cruzamentos: cada fato com o número, a fonte e a conta recolhida, sem nome de empresa", () => {
    const secao = trecho('<section class="faixa secao v2-cruzamentos" id="cruzamentos"', "</section>");
    expect(semTags(secao)).toContain(`medidas em ${fatosDaBase.medido_em_curto}`);
    const cartoes = secao.split('<article class="cartao v2-fato"').slice(1);
    expect(fatosDaBase.fatos.map((f) => f.chave)).toEqual(["lucros", "auditor", "ofertas"]);
    expect(cartoes).toHaveLength(fatosDaBase.fatos.length);
    fatosDaBase.fatos.forEach((fato, i) => {
      const texto = semTags(cartoes[i]);
      expect(texto, fato.chave).toContain(fato.numero);
      expect(texto, fato.chave).toContain(esc(fato.texto));
      expect(texto, fato.chave).toContain(`Fonte: ${esc(fato.fonte)}`);
      expect(cartoes[i], fato.chave).toContain("<summary>Como foi calculado</summary>");
      expect(texto, fato.chave).toContain(esc(fato.como_foi_calculado));
    });
    // a vaga "cruzamentos" da vitrine leva até aqui
    expect(vitrine.find((v) => v.chave === "cruzamentos")?.link).toBe("/#cruzamentos");
  });

  it("as quatro regras da base, cada uma recolhida", () => {
    const secao = trecho('<section class="faixa secao v2-regras"', "</section>");
    expect(semTags(secao)).toContain("Por que confiar num número daqui");
    for (const [titulo, texto] of REGRAS_DA_BASE) {
      expect(secao, titulo).toContain(`<summary>${esc(titulo)}</summary>`);
      expect(semTags(secao), titulo).toContain(texto);
    }
  });

  it("as fontes com licença: todas as do catálogo, com o selo nas que estão em consulta", () => {
    const secao = trecho('<section class="faixa secao v2-fontes-da-base"', "</section>");
    const texto = semTags(secao);
    for (const f of catalogo.fontes) expect(texto, f.orgao).toContain(esc(f.orgao));
    expect(secao.match(/licença em consulta/g)).toHaveLength(catalogo.totais.fontes_em_consulta);
    expect(secao).toContain('href="/dados.html');
  });

  it("os planos levam aos preços e dizem que o Gratuito não pede cartão", () => {
    const final = trecho('<section class="faixa secao final"', "</section>");
    expect(final).toContain('href="/precos.html"');
    expect(semTags(final)).toContain("O plano Gratuito não pede cartão");
  });

  it("sem fita de cotações, sem busca de ativos e sem o painel de PETR4", () => {
    for (const peca of ["v2-fita", "data-busca", "v2-grafico", "exemplo-PETR4", "Por que o TickerLab"])
      expect(html, peca).not.toContain(peca);
  });

  it("diz que nada é recomendação e não usa frase proibida", () => {
    const texto = semTags(principal());
    expect(texto).toContain("Nada aqui é recomendação de investimento");
    const semAviso = texto.replace(AVISOS, "");
    for (const proibida of PROIBIDAS) expect(proibida.test(semAviso), String(proibida)).toBe(false);
  });
});
