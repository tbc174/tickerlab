// Juro real (contas/taxas.ts) com o IPCA de 12 meses do Banco Central como sugestão, e a troca de
// taxa ao mês ↔ ao ano (contas/juros.ts), que não precisa de dado nenhum.
import { useEffect, useState } from "react";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { MesDoIpca } from "./Carregando";
import { em12Meses } from "./contas/inflacao";
import { taxaEquivalente } from "./contas/juros";
import { juroReal } from "./contas/taxas";
import { useDadosDoBc } from "./dados";
import { formatarNumero, formatarPorcentagem, lerNumero } from "./numeros";

export const EXEMPLO_DO_JURO_REAL = { nominal: "13,75", inflacao: "5" };

/** O juro real em % (ou a mensagem). */
export function calcularJuroReal(campos: typeof EXEMPLO_DO_JURO_REAL): number | string {
  const [nominal, inflacao] = [campos.nominal, campos.inflacao].map(lerNumero);
  if (nominal === null || inflacao === null) return "Preencha as duas taxas com números (por exemplo, 13,75).";
  try {
    return juroReal(nominal / 100, inflacao / 100);
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

export function JuroReal() {
  const carga = useDadosDoBc();
  const [campos, setCampos] = useState(EXEMPLO_DO_JURO_REAL);
  const ipca = carga.estado === "pronto" ? carga.dados.ipca : undefined;
  // com os dados, a inflação sugerida passa a ser o IPCA dos últimos 12 meses
  useEffect(() => {
    if (ipca) setCampos((antes) => ({ ...antes, inflacao: formatarNumero(em12Meses(ipca.meses) * 100) }));
  }, [ipca]);
  const mudar = (chave: keyof typeof campos) => (valor: string) => setCampos((antes) => ({ ...antes, [chave]: valor }));
  const conta = calcularJuroReal(campos);
  const erro = typeof conta === "string" ? conta : null;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Rendimento" valor={campos.nominal} aoMudar={mudar("nominal")} depois={<span>% ao ano</span>} />
        <CampoDeNumero
          rotulo="Inflação"
          valor={campos.inflacao}
          aoMudar={mudar("inflacao")}
          depois={<span>% ao ano</span>}
          dica={ipca ? "Já preenchida com o IPCA dos últimos 12 meses; troque se quiser." : undefined}
        />
      </form>
      <Resultado rotulo="Juro real" principal={erro ? "" : `${formatarPorcentagem(conta as number)} ao ano`} erro={erro}>
        <p>É quanto o dinheiro rende acima da inflação, no poder de compra.</p>
        {ipca ? <MesDoIpca ultimo={ipca.ultimo} /> : null}
      </Resultado>
    </div>
  );
}

export const EXEMPLO_DA_EQUIVALENTE = { taxa: "1", de: "mes" as "mes" | "ano" };

export function TaxaEquivalente() {
  const [campos, setCampos] = useState(EXEMPLO_DA_EQUIVALENTE);
  const taxa = lerNumero(campos.taxa);
  let resultado: number | null = null;
  let erro: string | null = taxa === null ? "Digite a taxa em números (por exemplo, 1,2)." : null;
  if (taxa !== null) {
    try {
      resultado = campos.de === "mes" ? taxaEquivalente(taxa / 100, 1, 12) : taxaEquivalente(taxa / 100, 12, 1);
    } catch (e) {
      if (!(e instanceof RangeError)) throw e;
      erro = e.message;
    }
  }
  const para = campos.de === "mes" ? "ao ano" : "ao mês";
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero
          rotulo="Taxa"
          valor={campos.taxa}
          aoMudar={(taxa) => setCampos((antes) => ({ ...antes, taxa }))}
          depois={
            <>
              <span aria-hidden="true">%</span>
              <Escolha
                rotulo="Período da taxa"
                valor={campos.de}
                opcoes={[
                  ["mes", "ao mês"],
                  ["ano", "ao ano"],
                ]}
                aoMudar={(de) => setCampos((antes) => ({ ...antes, de }))}
              />
            </>
          }
        />
      </form>
      <Resultado rotulo={`Equivale a, ${para}`} principal={resultado === null ? "" : `${formatarPorcentagem(resultado)} ${para}`} erro={erro} />
    </div>
  );
}
