// Aportes e metas: três perguntas com a mesma conta (contas/aportes.ts, a mesma do Python).
import { useState } from "react";
import { Alternativas, CampoDeNumero, Escolha, Resultado } from "./campos";
import { type Linha, aporteParaMeta, evolucao, mesesAteMeta, valorFuturo } from "./contas/aportes";
import { PRAZO_MAXIMO, type Unidade, taxaPorMes } from "./contas/juros";
import { formatarNumero, formatarReais, lerNumero } from "./numeros";

export type Pergunta = "quanto-terei" | "quanto-guardar" | "quanto-tempo";

export const PERGUNTAS: [Pergunta, string][] = [
  ["quanto-terei", "Quanto vou ter?"],
  ["quanto-guardar", "Quanto guardar por mês?"],
  ["quanto-tempo", "Em quanto tempo chego lá?"],
];

export const EXEMPLO_DE_APORTES = {
  pergunta: "quanto-terei" as Pergunta,
  inicial: "5.000",
  aporte: "500",
  meta: "200.000",
  taxa: "8",
  unidadeDaTaxa: "ano" as Unidade,
  anos: "20",
};

type Campos = typeof EXEMPLO_DE_APORTES;

export interface Resposta {
  principal: string;
  rotulo: string;
  linhas: Linha[];
}

/** "1 ano e 3 meses", "8 meses", "12 anos". */
export function prazoPorExtenso(meses: number): string {
  const anos = Math.floor(meses / 12);
  const resto = meses % 12;
  const partes: string[] = [];
  if (anos) partes.push(`${formatarNumero(anos)} ${anos === 1 ? "ano" : "anos"}`);
  if (resto || !anos) partes.push(`${resto} ${resto === 1 ? "mês" : "meses"}`);
  return partes.join(" e ");
}

/** Lê os campos da pergunta escolhida e responde; devolve a mensagem quando algo não fecha. */
export function responder(campos: Campos): Resposta | string {
  const inicial = lerNumero(campos.inicial);
  const taxa = lerNumero(campos.taxa);
  const aporte = lerNumero(campos.aporte);
  const meta = lerNumero(campos.meta);
  const anos = lerNumero(campos.anos);
  const pergunta = campos.pergunta;
  const faltando =
    inicial === null ||
    taxa === null ||
    (pergunta !== "quanto-guardar" && aporte === null) ||
    (pergunta !== "quanto-terei" && meta === null) ||
    (pergunta !== "quanto-tempo" && anos === null);
  if (faltando) return "Preencha os campos com números (por exemplo, 1.000,50).";
  try {
    const porMes = taxaPorMes(taxa / 100, campos.unidadeDaTaxa);
    if (pergunta === "quanto-tempo") {
      const meses = mesesAteMeta(meta!, inicial, aporte!, porMes);
      if (meses === null) return `Com esses números, a meta não chega em ${PRAZO_MAXIMO / 12} anos.`;
      return {
        rotulo: "Tempo até a meta",
        principal: prazoPorExtenso(meses),
        linhas: evolucao(inicial, aporte!, porMes, meses),
      };
    }
    const meses = anos! * 12;
    if (!Number.isInteger(meses)) return "Use um prazo em meses inteiros (por exemplo, 1,5 ano).";
    if (pergunta === "quanto-guardar") {
      const porMesParaMeta = aporteParaMeta(meta!, inicial, porMes, meses);
      return {
        rotulo: "Guardar por mês",
        principal: formatarReais(porMesParaMeta),
        linhas: evolucao(inicial, porMesParaMeta, porMes, meses),
      };
    }
    return {
      rotulo: "Valor no fim do prazo",
      principal: formatarReais(valorFuturo(inicial, aporte!, porMes, meses)),
      linhas: evolucao(inicial, aporte!, porMes, meses),
    };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

export function AportesEMetas() {
  const [campos, setCampos] = useState(EXEMPLO_DE_APORTES);
  const mudar = <K extends keyof Campos>(chave: K) => (valor: Campos[K]) =>
    setCampos((antes) => ({ ...antes, [chave]: valor }));
  const resposta = responder(campos);
  const erro = typeof resposta === "string" ? resposta : null;
  const fim = erro ? null : (resposta as Resposta).linhas.at(-1)!;
  const pergunta = campos.pergunta;

  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <Alternativas rotulo="Pergunta" valor={pergunta} opcoes={PERGUNTAS} aoMudar={mudar("pergunta")} />
        <CampoDeNumero rotulo="Valor que já tenho" antes="R$" valor={campos.inicial} aoMudar={mudar("inicial")} />
        {pergunta !== "quanto-guardar" ? (
          <CampoDeNumero rotulo="Aporte por mês" antes="R$" valor={campos.aporte} aoMudar={mudar("aporte")} />
        ) : null}
        {pergunta !== "quanto-terei" ? (
          <CampoDeNumero rotulo="Meta" antes="R$" valor={campos.meta} aoMudar={mudar("meta")} />
        ) : null}
        <CampoDeNumero
          rotulo="Rendimento"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          dica="Use o rendimento depois da inflação para ver o resultado em dinheiro de hoje."
          depois={
            <>
              <span aria-hidden="true">%</span>
              <Escolha
                rotulo="Período do rendimento"
                valor={campos.unidadeDaTaxa}
                opcoes={[
                  ["mes", "ao mês"],
                  ["ano", "ao ano"],
                ]}
                aoMudar={mudar("unidadeDaTaxa")}
              />
            </>
          }
        />
        {pergunta !== "quanto-tempo" ? (
          <CampoDeNumero
            rotulo="Prazo"
            valor={campos.anos}
            aoMudar={mudar("anos")}
            depois={<span>anos</span>}
          />
        ) : null}
      </form>
      <Resultado rotulo={erro ? "" : (resposta as Resposta).rotulo} principal={erro ? "" : (resposta as Resposta).principal} erro={erro}>
        {fim ? (
          <dl className="ferramenta-numeros">
            <div>
              <dt>Saiu do seu bolso</dt>
              <dd>{formatarReais(fim.aportado)}</dd>
            </div>
            <div>
              <dt>Veio dos juros</dt>
              <dd>{formatarReais(fim.juros)}</dd>
            </div>
            <div>
              <dt>Saldo no fim</dt>
              <dd>{formatarReais(fim.saldo)}</dd>
            </div>
          </dl>
        ) : null}
      </Resultado>
    </div>
  );
}
