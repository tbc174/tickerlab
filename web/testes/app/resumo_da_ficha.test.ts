// O Resumo da ficha (linha 903): a frase do topo e os números saem só da ficha, com fonte e data, e o que
// falta é dito ("Não temos"), nunca um zero. Dados de mentira.
import { describe, expect, it } from "vitest";
import { NAO_TEMOS, ABAS_DA_FICHA, fraseDoTopo, nomeDaEmpresa, numerosDoResumo } from "../../src/app/telas/resumoDaFicha";
import type { CampoComFonteV1, FichaDoCnpjV1 } from "../../src/app/tipos";

const campo = (valor: CampoComFonteV1["valor"], fonte = "rfb-cnpj", publico_em = "2026-09-30"): CampoComFonteV1 => ({
  valor,
  fonte,
  publico_em,
  visto_em: null,
});

const FICHA: FichaDoCnpjV1 = {
  cnpj: "02429144000193",
  como_era_em: "2026-11-10",
  cadastro_na_receita: {
    razao_social: campo("EMPRESA MODELO S.A."),
    situacao_cadastral: campo("02"),
    data_situacao_cadastral: campo("2005-11-03"),
    matriz: campo(true),
    optante_simples: campo(false),
  },
  entregas: [
    { documento: campo("DFP", "cvm-hist-dfp", "2026-03-20") },
    { documento: campo("ITR", "cvm-hist-itr", "2026-05-12") },
  ],
  entregas_nao_disponiveis: [],
  campos_do_cadastro_nao_disponiveis: [],
};

describe("resumo da ficha", () => {
  it("a ordem das abas é a do plano", () => {
    expect(ABAS_DA_FICHA.map((aba) => aba.titulo)).toEqual([
      "Resumo", "Cadastro", "Quem controla", "Sinais", "Eventos", "Vínculos", "Fontes e limites",
    ]);
  });

  it("a frase do topo diz quem é, a situação e se é matriz", () => {
    expect(fraseDoTopo(FICHA)).toBe("EMPRESA MODELO S.A. consta como ativa na Receita desde 03/11/2005; é a matriz.");
    expect(nomeDaEmpresa(FICHA)).toBe("EMPRESA MODELO S.A.");
  });

  it("sem razão social usa o CNPJ; sem situação diz que não tem", () => {
    const sem = { ...FICHA, cadastro_na_receita: {} };
    expect(fraseDoTopo(sem)).toBe("A empresa do CNPJ 02.429.144/0001-93 não tem a situação cadastral na base.");
    expect(nomeDaEmpresa(sem)).toBeNull();
  });

  it("cada número leva a fonte e a data; entregas contam e usam a data mais recente", () => {
    const [situacao, desde, simples, entregas] = numerosDoResumo(FICHA);
    expect(situacao).toEqual({ rotulo: "Situação cadastral", valor: "Ativa", fonte: "rfb-cnpj", publicoEm: "2026-09-30" });
    expect(desde.valor).toBe("03/11/2005");
    expect(simples.valor).toBe("Não");
    expect(entregas).toMatchObject({ valor: "2", fonte: "cvm-hist-dfp, cvm-hist-itr", publicoEm: "2026-05-12" });
  });

  it("o que falta vira 'Não temos', nunca zero", () => {
    const sem = { ...FICHA, cadastro_na_receita: {}, entregas: null };
    for (const numero of numerosDoResumo(sem)) {
      expect(numero).toMatchObject({ valor: NAO_TEMOS, fonte: null, publicoEm: null });
    }
    expect(numerosDoResumo({ ...FICHA, entregas: [] })[3].valor).toBe(NAO_TEMOS);
  });

  it("documento barrado: não conta entregas como se fosse a lista inteira", () => {
    const parcial = { ...FICHA, entregas_nao_disponiveis: ["ITR"] };
    expect(numerosDoResumo(parcial)[3].valor).toBe("Não consultado por inteiro");
  });
  it("campo barrado não vira 'a empresa não tem': a frase e o cartão dizem que não foi consultado", () => {
    const barrada = { ...FICHA, cadastro_na_receita: {}, campos_do_cadastro_nao_disponiveis: ["registration_status"] };
    const barrados = new Set(["situacao_cadastral", "optante_simples"]);
    expect(fraseDoTopo(barrada, barrados)).toBe(
      "A empresa do CNPJ 02.429.144/0001-93 tem a situação cadastral fora desta consulta.",
    );
    const [situacao, , simples] = numerosDoResumo(barrada, barrados);
    expect(situacao.valor).toBe("Não consultado");
    expect(simples.valor).toBe("Não consultado");
  });

  it("entrega não feita não entra na contagem das entregas", () => {
    const naoEntregue = { documento: campo("ITR", "cvm-hist-itr", "2026-08-01"), situacao_da_entrega: campo("not_filed", "cvm-hist-itr", "2026-08-01") };
    const ficha = { ...FICHA, entregas: [...(FICHA.entregas ?? []), naoEntregue] };
    expect(numerosDoResumo(ficha)[3]).toMatchObject({ valor: "2", publicoEm: "2026-05-12" });
    const so = { ...FICHA, entregas: [naoEntregue] };
    expect(numerosDoResumo(so)[3].valor).toBe(NAO_TEMOS);
  });
});
