// O setor de "Encontrar empresas": as seções do CNAE achadas pelo nome delas ou pelo de uma atividade, sem repetir
// seção e sem as já escolhidas.
import { describe, expect, it } from "vitest";
import { carregarCnaes, nomeCombina } from "../../src/app/buscaDeCnaes";
import { sugestoesDeSecao } from "../../src/app/buscaDeSecoes";

const SECOES = [
  { codigo: "C", nome: "Indústrias de transformação" },
  { codigo: "G", nome: "Comércio; reparação de veículos automotores e motocicletas" },
  { codigo: "Q", nome: "Saúde humana e serviços sociais" },
];

describe("busca de seção do CNAE", () => {
  it("nome combina com todas as palavras, sem acento e pelo começo", () => {
    expect(nomeCombina("Saúde humana e serviços sociais", "saude")).toBe(true);
    expect(nomeCombina("Saúde humana e serviços sociais", "servico saude")).toBe(true);
    expect(nomeCombina("Saúde humana e serviços sociais", "saude animal")).toBe(false);
    expect(nomeCombina("Saúde humana e serviços sociais", "   ")).toBe(false);
  });

  it("campo vazio lista as seções livres, na ordem dada", () => {
    expect(sugestoesDeSecao(SECOES, null, "", ["G"]).map((s) => s.secao.codigo)).toEqual(["C", "Q"]);
  });

  it("acha pelo nome antes e pela atividade depois, dizendo qual atividade, sem repetir seção", async () => {
    const atividades = await carregarCnaes();
    const farmacia = sugestoesDeSecao(SECOES, atividades, "farmácia", []);
    expect(farmacia.map((s) => s.secao.codigo)).toContain("G");
    expect(new Set(farmacia.map((s) => s.secao.codigo)).size).toBe(farmacia.length);
    const viaG = farmacia.find((s) => s.secao.codigo === "G");
    expect(viaG?.pelaAtividade).toMatch(/farmac/i);
    const saude = sugestoesDeSecao(SECOES, atividades, "saúde", []);
    expect(saude[0]).toEqual({ secao: SECOES[2], pelaAtividade: null });
  });

  it("não sugere seção já escolhida, nem pela atividade", async () => {
    const atividades = await carregarCnaes();
    expect(sugestoesDeSecao(SECOES, atividades, "farmácia", ["G"]).map((s) => s.secao.codigo)).not.toContain("G");
  });
});
