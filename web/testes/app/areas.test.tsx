// As áreas do app (ADR 0096; linha 822): toda tela é de uma área, que dá o olho do cabeçalho e a seção da
// lista "Todas as telas". O menu de sete itens e a casca ficam em casca.test.tsx.
import { describe, expect, it } from "vitest";
import { AREAS, areaDoEndereco, itensDaArea, telasProntasDaArea } from "../../src/app/areas";

describe("as áreas (vindas de src/paginas.py)", () => {
  it("a ordem é Início, Empresas, Companhias abertas, Mais, Conta e Ajuda", () => {
    expect(AREAS.map((a) => a.rotulo)).toEqual(["Início", "Empresas", "Companhias abertas", "Mais", "Conta", "Ajuda"]);
  });

  it("cada endereço sabe a sua área; o início é a área Início", () => {
    expect(areaDoEndereco("/")).toBe("inicio");
    expect(areaDoEndereco("/risco")).toBe("ativo");
    expect(areaDoEndereco("/ficha-da-empresa")).toBe("empresas");
    expect(areaDoEndereco("/backtest/")).toBe("mais");
    expect(areaDoEndereco("/juros-e-inflacao")).toBe("mais");
    expect(areaDoEndereco("/planos")).toBe("conta");
    expect(areaDoEndereco("/nao-existe")).toBeNull();
  });

  it("as telas fora do menu (Termos e Privacidade) não entram em nenhuma área", () => {
    const todas = AREAS.flatMap((a) => itensDaArea(a.chave).map((i) => i.pagina.chave));
    expect(todas).not.toContain("termos");
    expect(todas).not.toContain("privacidade");
  });

  it("de cada área, só as telas que já abrem no app novo", () => {
    const prontas = telasProntasDaArea("ativo").map((p) => p.titulo);
    expect(prontas).toContain("Risco");
    expect(prontas).not.toContain("Correlação e beta");
  });
});
