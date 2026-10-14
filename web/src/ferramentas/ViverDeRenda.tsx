// Viver de renda (contas/viver_de_renda.ts, a mesma conta do Python): quanto juntar e o risco de
// começar num ano ruim. Tudo em dinheiro de hoje.
import { useState } from "react";
import { prazoPorExtenso } from "./AportesEMetas";
import { Alternativas, CampoDeNumero, Resultado } from "./campos";
import { ANOS_MAXIMOS, duracaoEmMeses, patrimonioNecessario, rendaDaRegraDos4 } from "./contas/viver_de_renda";
import { formatarReais, lerNumero } from "./numeros";

type Forma = "so-juros" | "gastando";
export const QUEDA_NO_PRIMEIRO_ANO = -0.3;

export const EXEMPLO_DE_RENDA = {
  renda: "5.000",
  taxa: "4",
  forma: "so-juros" as Forma,
  anos: "30",
};

export interface RespostaDaRenda {
  patrimonio: number;
  duracaoNormal: number | null; // meses; null = mais de 100 anos
  duracaoComQueda: number | null;
  regraDos4: number;
}

/** "mais de 100 anos" ou "28 anos e 4 meses". */
export function duracaoPorExtenso(meses: number | null): string {
  return meses === null ? `mais de ${ANOS_MAXIMOS} anos` : prazoPorExtenso(meses);
}

export function calcularRenda(campos: typeof EXEMPLO_DE_RENDA): RespostaDaRenda | string {
  const renda = lerNumero(campos.renda);
  const taxa = lerNumero(campos.taxa);
  const anos = campos.forma === "gastando" ? lerNumero(campos.anos) : null;
  if (renda === null || taxa === null || (campos.forma === "gastando" && anos === null)) {
    return "Preencha os campos com números (por exemplo, 5.000).";
  }
  if (renda <= 0) return "A renda mensal precisa ser maior que zero.";
  if (anos !== null && !Number.isInteger(anos)) return "Use um prazo em anos inteiros.";
  try {
    const patrimonio = patrimonioNecessario(renda, taxa / 100, anos);
    return {
      patrimonio,
      duracaoNormal: duracaoEmMeses(patrimonio, renda, [taxa / 100]),
      duracaoComQueda: duracaoEmMeses(patrimonio, renda, [QUEDA_NO_PRIMEIRO_ANO, taxa / 100]),
      regraDos4: rendaDaRegraDos4(patrimonio),
    };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

export function ViverDeRenda() {
  const [campos, setCampos] = useState(EXEMPLO_DE_RENDA);
  const mudar = <K extends keyof typeof campos>(chave: K) => (valor: (typeof campos)[K]) =>
    setCampos((antes) => ({ ...antes, [chave]: valor }));
  const conta = calcularRenda(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Renda por mês" antes="R$" valor={campos.renda} aoMudar={mudar("renda")} />
        <CampoDeNumero
          rotulo="Rendimento acima da inflação"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          depois={<span>% ao ano</span>}
          dica="O juro real: quanto o dinheiro rende além da inflação. Na dúvida, use de 3% a 5%."
        />
        <Alternativas
          rotulo="Como viver de renda"
          valor={campos.forma}
          opcoes={[
            ["so-juros", "Só com os juros (o dinheiro não acaba)"],
            ["gastando", "Gastando também o que juntei"],
          ]}
          aoMudar={mudar("forma")}
        />
        {campos.forma === "gastando" ? (
          <CampoDeNumero rotulo="Por quantos anos" valor={campos.anos} aoMudar={mudar("anos")} depois={<span>anos</span>} />
        ) : null}
      </form>
      <Resultado rotulo="Patrimônio necessário, em dinheiro de hoje" principal={r ? formatarReais(r.patrimonio) : ""} erro={erro}>
        {r ? (
          <dl className="ferramenta-numeros">
            <div>
              <dt>Se render isso todo ano, dura</dt>
              <dd>{duracaoPorExtenso(r.duracaoNormal)}</dd>
            </div>
            <div>
              <dt>Se o 1º ano cair 30%, dura</dt>
              <dd>{duracaoPorExtenso(r.duracaoComQueda)}</dd>
            </div>
            <div>
              <dt>Pela “regra dos 4%”, daria por mês</dt>
              <dd>{formatarReais(r.regraDos4)}</dd>
            </div>
          </dl>
        ) : null}
      </Resultado>
    </div>
  );
}
