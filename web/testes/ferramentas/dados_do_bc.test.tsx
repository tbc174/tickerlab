// @vitest-environment jsdom
// As ferramentas com dados do Banco Central: buscam /dados/ferramentas.json no navegador, dizem a
// data de cada número, avisam quando ele está velho e não quebram quando o arquivo falta.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { em12Meses } from "../../src/ferramentas/contas/inflacao";
import { formatarNaMoeda } from "../../src/ferramentas/ConversorDeMoedas";
import { type DadosDoBc, ENDERECO_DOS_DADOS, diasUteisDesde, estaVelho } from "../../src/ferramentas/dados";
import { formatarNumero } from "../../src/ferramentas/numeros";
import { type NomeDaFerramenta, Ilha } from "../../src/ferramentas/registro";

const hoje = new Date();
const ontem = new Date(hoje.getTime() - 24 * 3600 * 1000).toISOString().slice(0, 10);
const IPCA: [string, number][] = Array.from({ length: 24 }, (_, i) => [
  `20${24 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`,
  0.004,
]);
const DADOS: DadosDoBc = {
  gerado_em: `${ontem}T13:40:00-03:00`,
  fonte: "Banco Central do Brasil",
  moedas: [
    { codigo: "EUR", nome: "Euro", compra: 5.6, venda: 5.6092, data: ontem },
    { codigo: "USD", nome: "Dólar dos Estados Unidos", compra: 5.0, venda: 5.0096, data: ontem },
  ],
  cdi: { ao_ano: 0.1365, data: ontem },
  selic_meta: { ao_ano: 0.1375, data: ontem },
  poupanca: { ao_mes: 0.006704, data: ontem },
  ipca: { meses: IPCA, ultimo: "2025-12" },
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

/** Liga a ferramenta com um fetch falso; a resposta só é criada se ele for chamado (uma promessa
 * rejeitada criada antes, e nunca usada, vira erro "não tratado" no fim do teste). */
async function abrir(nome: NomeDaFerramenta, resposta: () => Promise<Response>) {
  const buscar = vi.fn(resposta);
  vi.stubGlobal("fetch", buscar);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome={nome} />);
  await act(async () => {
    ligarFerramentas(document);
  });
  return buscar;
}

const ok = () => Promise.resolve(new Response(JSON.stringify(DADOS), { status: 200 }));
const falha = () => Promise.reject(new Error("sem rede"));
const resultado = () => document.querySelector("[data-resultado]")?.textContent;

describe("dados do Banco Central", () => {
  it("o HTML pronto diz que está carregando, e o navegador busca o arquivo uma vez", async () => {
    expect(renderToStaticMarkup(<Ilha nome="moedas" />)).toContain("Carregando os dados do Banco Central");
    const buscar = await abrir("moedas", ok);
    expect(buscar).toHaveBeenCalledTimes(1);
    expect(buscar).toHaveBeenCalledWith(ENDERECO_DOS_DADOS);
  });

  it("sem o arquivo, a ferramenta diz que está indisponível", async () => {
    await abrir("moedas", () => Promise.resolve(new Response("", { status: 404 })));
    expect(document.body.textContent).toContain("indisponíveis agora");
    await abrir("rendaFixa", falha);
    expect(document.body.textContent).toContain("indisponíveis agora");
  });

  it("dias úteis: o fim de semana não conta, e passar de 4 é dado velho", () => {
    const segunda = new Date("2026-10-12T15:00:00");
    expect(diasUteisDesde("2026-10-09", segunda)).toBe(1); // sexta → segunda
    expect(diasUteisDesde("2026-10-12", segunda)).toBe(0);
    expect(estaVelho("2026-10-06", segunda)).toBe(false); // 4 dias úteis
    expect(estaVelho("2026-10-05", segunda)).toBe(true); // 5
  });
});

describe("conversor de moedas", () => {
  it("converte pela PTAX de venda e mostra a data da cotação", async () => {
    await abrir("moedas", ok);
    expect(resultado()).toBe(formatarNaMoeda(100 * 5.0096, "BRL"));
    expect(document.body.textContent).toContain("PTAX de fechamento de");
    expect(document.body.textContent).not.toContain("Atenção");
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Para"), { target: { value: "EUR" } });
    });
    expect(resultado()).toBe(formatarNaMoeda((100 * 5.0096) / 5.6092, "EUR"));
  });

  it("código de moeda que o navegador não conhece não quebra a página", () => {
    expect(formatarNaMoeda(1234.5, "ZZZ")).toBe("ZZZ 1.234,50"); // 3 letras: o Intl aceita
    expect(formatarNaMoeda(1234.5, "EURO")).toBe("1.234,50 EURO"); // malformado: plano B
  });

  it("cotação de vários dias atrás leva o aviso", async () => {
    const velhos = { ...DADOS, moedas: DADOS.moedas!.map((m) => ({ ...m, data: "2026-01-02" })) };
    await abrir("moedas", () => Promise.resolve(new Response(JSON.stringify(velhos))));
    expect(document.body.textContent).toContain("Atenção: dado de vários dias atrás");
  });
});

describe("renda fixa, juro real e inflação", () => {
  it("a renda fixa mostra as quatro opções em ordem fixa e o CDI de hoje", async () => {
    await abrir("rendaFixa", ok);
    const linhas = [...document.querySelectorAll(".ferramenta-comparacao tbody th")].map((th) => th.textContent);
    expect(linhas).toEqual(["CDB", "LCI ou LCA", "Tesouro Selic", "Poupança"]);
    expect(resultado()).toBe("13,65% ao ano");
  });

  it("o juro real já vem com o IPCA dos últimos 12 meses", async () => {
    await abrir("juroReal", ok);
    const inflacao = screen.getByLabelText("Inflação") as HTMLInputElement;
    expect(inflacao.value).toBe(formatarNumero(em12Meses(IPCA) * 100));
    expect(document.body.textContent).toContain("IPCA até dez/2025");
  });

  it("a correção vai até o último IPCA divulgado, começando 10 anos antes", async () => {
    await abrir("inflacao", ok);
    expect((screen.getByLabelText("Até: ano") as HTMLInputElement).value).toBe("2025");
    expect((screen.getByLabelText("A partir de: ano") as HTMLInputElement).value).toBe("2015");
    // o IPCA do exemplo só começa em 2024: a conta avisa, em vez de quebrar
    expect(document.body.textContent).toContain("começa em 2024-01");
    await act(async () => {
      fireEvent.change(screen.getByLabelText("A partir de: ano"), { target: { value: "2025" } });
    });
    expect(resultado()).toBe("R$ 100,40"); // dez/2025 a dez/2025: um mês só
    await act(async () => {
      fireEvent.change(screen.getByLabelText("A partir de: mês"), { target: { value: "01" } });
    });
    expect(resultado()).toBe("R$ 104,91"); // jan a dez/2025: 100 × 1,004^12
  });

  it("a taxa equivalente não precisa de dado nenhum", async () => {
    const buscar = await abrir("equivalente", falha);
    expect(resultado()).toBe("12,68% ao ano");
    expect(buscar).not.toHaveBeenCalled();
  });
});
