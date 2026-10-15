// Renda fixa com IR (contas/renda_fixa.ts, a mesma conta do Python): CDB, LCI/LCA, Tesouro Selic e
// poupança pelo mesmo prazo, com o CDI e a poupança de hoje. A ordem é fixa: nada de "o melhor".
import { useState } from "react";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { ComDadosDoBc, DataDoDado } from "./Carregando";
import { DIAS_MAXIMOS, type Opcao, comparar } from "./contas/renda_fixa";
import { type DadosDoBc, useDadosDoBc } from "./dados";
import { formatarPorcentagem, formatarReais, lerNumero } from "./numeros";

type Unidade = "dias" | "meses" | "anos";
const DIAS_POR: Record<Unidade, number> = { dias: 1, meses: 30, anos: 365 };

export const EXEMPLO_DA_RENDA_FIXA = { valor: "10.000", prazo: "2", unidade: "anos" as Unidade, cdb: "100", lci: "90" };

export function calcularRendaFixa(
  campos: typeof EXEMPLO_DA_RENDA_FIXA,
  cdiAoAno: number,
  poupancaAoMes: number,
): Opcao[] | string {
  const [valor, prazo, cdb, lci] = [campos.valor, campos.prazo, campos.cdb, campos.lci].map(lerNumero);
  if (valor === null || prazo === null || cdb === null || lci === null) {
    return "Preencha os campos com números (por exemplo, 10.000).";
  }
  const dias = Math.round(prazo * DIAS_POR[campos.unidade]);
  if (dias > DIAS_MAXIMOS) return "O prazo vai até 10 anos.";
  try {
    return comparar(valor, dias, [cdiAoAno], cdb / 100, lci / 100, poupancaAoMes);
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

function Comparacao({ dados }: { dados: DadosDoBc }) {
  const [campos, setCampos] = useState(EXEMPLO_DA_RENDA_FIXA);
  const mudar = <K extends keyof typeof campos>(chave: K) => (valor: (typeof campos)[K]) =>
    setCampos((antes) => ({ ...antes, [chave]: valor }));
  const cdi = dados.cdi!;
  const poupanca = dados.poupanca!;
  const conta = calcularRendaFixa(campos, cdi.ao_ano, poupanca.ao_mes);
  const erro = typeof conta === "string" ? conta : null;
  const opcoes = typeof conta === "string" ? [] : conta;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor aplicado" antes="R$" valor={campos.valor} aoMudar={mudar("valor")} />
        <CampoDeNumero
          rotulo="Prazo"
          valor={campos.prazo}
          aoMudar={mudar("prazo")}
          depois={
            <Escolha
              rotulo="Unidade do prazo"
              valor={campos.unidade}
              opcoes={[
                ["dias", "dias"],
                ["meses", "meses"],
                ["anos", "anos"],
              ]}
              aoMudar={mudar("unidade")}
            />
          }
        />
        <CampoDeNumero rotulo="CDB que paga" valor={campos.cdb} aoMudar={mudar("cdb")} depois={<span>% do CDI</span>} />
        <CampoDeNumero rotulo="LCI ou LCA que paga" valor={campos.lci} aoMudar={mudar("lci")} depois={<span>% do CDI</span>} />
      </form>
      <Resultado rotulo="CDI hoje" principal={`${formatarPorcentagem(cdi.ao_ano)} ao ano`} erro={erro}>
        <table className="ferramenta-comparacao">
          <thead>
            <tr>
              <th scope="col">Opção</th>
              <th scope="col">IR</th>
              <th scope="col">Líquido no fim</th>
            </tr>
          </thead>
          <tbody>
            {opcoes.map((o) => (
              <tr key={o.nome}>
                <th scope="row">{o.nome}</th>
                <td>{o.aliquota ? formatarPorcentagem(o.aliquota) : "isento"}</td>
                <td>{formatarReais(o.liquido)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <DataDoDado data={cdi.data} rotulo="CDI de" />
        <DataDoDado data={poupanca.data} rotulo="rendimento da poupança do aniversário de" />
      </Resultado>
    </div>
  );
}

export function RendaFixa() {
  const carga = useDadosDoBc();
  return (
    <ComDadosDoBc carga={carga}>
      {(dados) =>
        dados.cdi && dados.poupanca ? <Comparacao dados={dados} /> : <p className="ferramenta-erro">Sem o CDI agora.</p>
      }
    </ComDadosDoBc>
  );
}
