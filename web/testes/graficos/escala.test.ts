import { describe, expect, it } from "vitest";
import { limitesDoEixo, marcasDeMeses, passoRedondo, rotuloDoMes } from "../../src/graficos/escala";

describe("escala dos gráficos", () => {
  it("o passo é sempre 1, 2, 2,5, 5 ou 10 vezes uma potência de 10", () => {
    const fatores = [1, 2, 2.5, 5, 10];
    for (const faixa of [0.003, 0.7, 1, 3.3, 47, 94, 15937, 1e6, 7.3e8]) {
      const passo = passoRedondo(faixa, 4);
      const potencia = 10 ** Math.floor(Math.log10(passo));
      expect(fatores.some((f) => Math.abs(passo / potencia - f) < 1e-9)).toBe(true);
      expect(passo * 4).toBeGreaterThanOrEqual(faixa);
    }
  });

  it("os limites contêm todos os valores e caem em números redondos", () => {
    expect(limitesDoEixo([3, 97])).toEqual([0, 100, 25]);
    expect(limitesDoEixo([10000, 25937.42])).toEqual([10000, 30000, 5000]);
    expect(limitesDoEixo([10000, 25937.42], 0)).toEqual([0, 30000, 10000]);
  });

  it("valores todos iguais não dão um eixo sem altura", () => {
    const [baixo, alto] = limitesDoEixo([5, 5]);
    expect(baixo).toBeLessThan(5);
    expect(alto).toBeGreaterThan(5);
  });

  it("as marcas do eixo de meses são redondas: meses até 2 anos, anos depois", () => {
    expect(marcasDeMeses(12)).toEqual([0, 3, 6, 9, 12]);
    expect(marcasDeMeses(24)).toEqual([0, 6, 12, 18, 24]);
    expect(marcasDeMeses(120)).toEqual([0, 24, 48, 72, 96, 120]);
    expect(marcasDeMeses(600)).toEqual([0, 120, 240, 360, 480, 600]);
    expect(marcasDeMeses(25)).toEqual([0, 12, 24]);
    expect(marcasDeMeses(1)).toEqual([0, 1]);
  });

  it("o rótulo diz mês ou ano conforme o prazo", () => {
    expect(rotuloDoMes(6, 12)).toBe("mês 6");
    expect(rotuloDoMes(0, 120)).toBe("início");
    expect(rotuloDoMes(48, 120)).toBe("ano 4");
    expect(rotuloDoMes(30, 120)).toBe("ano 2,5");
  });
});
