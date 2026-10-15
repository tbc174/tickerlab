// Juro real (contas/taxas.ts) com o IPCA de 12 meses do Banco Central como sugestão, e a troca de
// taxa ao mês ↔ ao ano (contas/juros.ts), que não precisa de dado nenhum.
import { useEffect, useState } from "react";
import { atalhosDeInflacao, atalhosDeJuros } from "./atalhos";
import { CampoComDeslizante, CampoDeNumero, Escolha, Resultado } from "./campos";
import { MesDoIpca } from "./Carregando";
import { em12Meses } from "./contas/inflacao";
import { taxaEquivalente } from "./contas/juros";
import { juroReal } from "./contas/taxas";
import { useDadosDoBc } from "./dados";
import { useCamposNoEndereco } from "./endereco";
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
  const [campos, mudar, , sugerir] = useCamposNoEndereco(EXEMPLO_DO_JURO_REAL, {}, "real.");
  const dados = carga.estado === "pronto" ? carga.dados : null;
  const ipca = dados?.ipca;
  const hoje = new Date();
  // com os dados, a inflação sugerida passa a ser o IPCA dos últimos 12 meses (se o endereço não
  // trouxer outra, de um link de outra ferramenta)
  useEffect(() => {
    if (!ipca || new URLSearchParams(window.location.search).has("real.inflacao")) return;
    sugerir((antes) => ({ ...antes, inflacao: formatarNumero(em12Meses(ipca.meses) * 100) }));
  }, [ipca, sugerir]);
  const conta = calcularJuroReal(campos);
  const erro = typeof conta === "string" ? conta : null;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante
          rotulo="Rendimento"
          valor={campos.nominal}
          aoMudar={mudar("nominal")}
          min={0}
          max={25}
          passo={0.25}
          atalhos={dados ? atalhosDeJuros(dados, hoje) : []}
          depois={<span>% ao ano</span>}
        />
        <CampoComDeslizante
          rotulo="Inflação"
          valor={campos.inflacao}
          aoMudar={mudar("inflacao")}
          min={0}
          max={15}
          passo={0.25}
          atalhos={dados ? atalhosDeInflacao(dados, hoje) : []}
          depois={<span>% ao ano</span>}
          dica={ipca ? "Já preenchida com o IPCA dos últimos 12 meses; troque se quiser." : undefined}
        />
      </form>
      <Resultado rotulo="Juro real" principal={erro ? "" : `${formatarPorcentagem(conta as number)} ao ano`} erro={erro}>
        <p>É quanto o dinheiro rende acima da inflação, no poder de compra.</p>
        {erro ? null : (
          <p className="ferramenta-destaque">
            A conta é (1 + {campos.nominal}%) ÷ (1 + {campos.inflacao}%) − 1 ={" "}
            {formatarPorcentagem(conta as number)}, não {formatarNumero((lerNumero(campos.nominal) ?? 0) - (lerNumero(campos.inflacao) ?? 0))}% (a
            subtração simples, um erro comum, exagera o ganho real).
          </p>
        )}
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
