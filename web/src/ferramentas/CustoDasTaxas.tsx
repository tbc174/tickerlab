// Custo das taxas e da queda (contas/custos.ts, a mesma conta do Python): duas calculadoras curtas.
import { useState } from "react";
import { CampoDeNumero, Resultado } from "./campos";
import { ANOS_MAXIMOS, altaParaRecuperar, custoDaTaxa } from "./contas/custos";
import { formatarPorcentagem, formatarReais, lerNumero } from "./numeros";

export const EXEMPLO_DA_TAXA = { capital: "100.000", retorno: "8", taxa: "1", anos: "20" };

/** Lê os campos e faz a conta da taxa; devolve a mensagem quando algo não fecha. */
export function calcularTaxa(campos: typeof EXEMPLO_DA_TAXA) {
  const [capital, retorno, taxa, anos] = [campos.capital, campos.retorno, campos.taxa, campos.anos].map(lerNumero);
  if (capital === null || retorno === null || taxa === null || anos === null) {
    return "Preencha os campos com números (por exemplo, 1.000,50).";
  }
  if (!Number.isInteger(anos)) return "Use um prazo em anos inteiros.";
  if (anos > ANOS_MAXIMOS) return `O prazo vai até ${ANOS_MAXIMOS} anos.`;
  try {
    return custoDaTaxa(capital, retorno / 100, taxa / 100, anos);
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

export function CustoDaTaxa() {
  const [campos, setCampos] = useState(EXEMPLO_DA_TAXA);
  const mudar = (chave: keyof typeof campos) => (valor: string) =>
    setCampos((antes) => ({ ...antes, [chave]: valor }));
  const conta = calcularTaxa(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor investido" antes="R$" valor={campos.capital} aoMudar={mudar("capital")} />
        <CampoDeNumero
          rotulo="Rendimento antes da taxa"
          valor={campos.retorno}
          aoMudar={mudar("retorno")}
          depois={<span>% ao ano</span>}
        />
        <CampoDeNumero
          rotulo="Taxa sobre o patrimônio"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          depois={<span>% ao ano</span>}
          dica="Como a taxa de administração de um fundo: cobrada todo ano sobre tudo o que você tem lá."
        />
        <CampoDeNumero rotulo="Prazo" valor={campos.anos} aoMudar={mudar("anos")} depois={<span>anos</span>} />
      </form>
      <Resultado rotulo="A taxa levou" principal={r ? formatarReais(r.ficou_com_a_taxa) : ""} erro={erro}>
        {r ? (
          <dl className="ferramenta-numeros">
            <div>
              <dt>Do resultado sem taxa</dt>
              <dd>{formatarPorcentagem(r.fracao_do_resultado)}</dd>
            </div>
            <div>
              <dt>Sem a taxa, você teria</dt>
              <dd>{formatarReais(r.sem_taxa)}</dd>
            </div>
            <div>
              <dt>Com a taxa, ficou com</dt>
              <dd>{formatarReais(r.com_taxa)}</dd>
            </div>
          </dl>
        ) : null}
      </Resultado>
    </div>
  );
}

export const EXEMPLO_DA_QUEDA = "50";

/** "50" (uma queda de 50%) → a alta que recupera, ou a mensagem. */
export function calcularQueda(texto: string): number | string {
  const queda = lerNumero(texto);
  if (queda === null) return "Digite a queda em %, por exemplo 30.";
  // a pessoa escreve "30" ou "-30" para uma queda de 30%
  try {
    return altaParaRecuperar(-Math.abs(queda) / 100);
  } catch (erro) {
    if (erro instanceof RangeError) return "A queda precisa estar entre 0% e 99,99%.";
    throw erro;
  }
}

export function RecuperarAQueda() {
  const [queda, setQueda] = useState(EXEMPLO_DA_QUEDA);
  const conta = calcularQueda(queda);
  const erro = typeof conta === "string" ? conta : null;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Queda" valor={queda} aoMudar={setQueda} depois={<span>%</span>} />
      </form>
      <Resultado
        rotulo="Alta para voltar ao valor de antes"
        principal={erro ? "" : formatarPorcentagem(conta as number)}
        erro={erro}
      />
    </div>
  );
}
