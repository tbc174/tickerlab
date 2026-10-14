// Aportes e metas: três perguntas com a mesma conta (contas/aportes.ts, a mesma do Python), v2:
// gráfico do que saiu do bolso e dos juros (com a meta), aporte que sobe a cada ano, o mês em que
// os juros passam o aporte, deslizantes e a simulação no endereço.
import { Compartilhar } from "./Compartilhar";
import { Alternativas, CampoComDeslizante, CampoDeNumero, Escolha, Resultado } from "./campos";
import { type Linha, aporteParaMeta, evolucao, mesDaVirada, mesesAteMeta, valorFuturo } from "./contas/aportes";
import { PRAZO_MAXIMO, type Unidade, taxaPorMes } from "./contas/juros";
import { useCamposNoEndereco } from "./endereco";
import { formatarNumero, formatarPorcentagem, formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

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
  reajuste: "0", // % ao ano que o aporte sobe
};

const OPCOES = {
  pergunta: ["quanto-terei", "quanto-guardar", "quanto-tempo"],
  unidadeDaTaxa: ["mes", "ano"],
} as const;

type Campos = typeof EXEMPLO_DE_APORTES;

export interface Resposta {
  principal: string;
  rotulo: string;
  linhas: Linha[];
  aporte: number; // o aporte do 1º mês (o achado, em "quanto guardar")
  porMes: number; // a taxa ao mês
  reajuste: number;
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
  const reajusteEmPct = lerNumero(campos.reajuste ?? "0");
  const pergunta = campos.pergunta;
  const faltando =
    inicial === null ||
    taxa === null ||
    reajusteEmPct === null ||
    (pergunta !== "quanto-guardar" && aporte === null) ||
    (pergunta !== "quanto-terei" && meta === null) ||
    (pergunta !== "quanto-tempo" && anos === null);
  if (faltando) return "Preencha os campos com números (por exemplo, 1.000,50).";
  const reajuste = reajusteEmPct / 100;
  try {
    const porMes = taxaPorMes(taxa / 100, campos.unidadeDaTaxa);
    const comum = { porMes, reajuste };
    if (pergunta === "quanto-tempo") {
      const meses = mesesAteMeta(meta!, inicial, aporte!, porMes, false, reajuste);
      if (meses === null) return `Com esses números, a meta não chega em ${PRAZO_MAXIMO / 12} anos.`;
      return {
        ...comum,
        rotulo: "Tempo até a meta",
        principal: prazoPorExtenso(meses),
        linhas: evolucao(inicial, aporte!, porMes, meses, false, reajuste),
        aporte: aporte!,
      };
    }
    const meses = anos! * 12;
    if (!Number.isInteger(meses)) return "Use um prazo em meses inteiros (por exemplo, 1,5 ano).";
    if (pergunta === "quanto-guardar") {
      const achado = aporteParaMeta(meta!, inicial, porMes, meses, false, reajuste);
      return {
        ...comum,
        rotulo: reajuste ? "Guardar por mês no 1º ano" : "Guardar por mês",
        principal: formatarReais(achado),
        linhas: evolucao(inicial, achado, porMes, meses, false, reajuste),
        aporte: achado,
      };
    }
    return {
      ...comum,
      rotulo: "Valor no fim do prazo",
      principal: formatarReais(valorFuturo(inicial, aporte!, porMes, meses, false, reajuste)),
      linhas: evolucao(inicial, aporte!, porMes, meses, false, reajuste),
      aporte: aporte!,
    };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

/** Os pontos do gráfico: todo mês até 10 anos; depois, um por ano (e o último mês). */
function pontosDoGrafico(linhas: Linha[]): Linha[] {
  if (linhas.length <= 121) return linhas;
  return linhas.filter((l, i) => l.mes % 12 === 0 || i === linhas.length - 1);
}

function textoParaCopiar(campos: Campos, resposta: Resposta): string {
  const fim = resposta.linhas.at(-1)!;
  if (campos.pergunta === "quanto-tempo") {
    return `Com ${formatarReais(lerNumero(campos.inicial) ?? 0)} e ${formatarReais(resposta.aporte)} por mês, a meta de ${formatarReais(lerNumero(campos.meta) ?? 0)} chega em ${resposta.principal}`;
  }
  if (campos.pergunta === "quanto-guardar") {
    return `Para ter ${formatarReais(lerNumero(campos.meta) ?? 0)} em ${campos.anos} anos, guardar ${resposta.principal} por mês`;
  }
  return `${formatarReais(resposta.aporte)} por mês por ${campos.anos} anos viram ${formatarReais(fim.saldo)}`;
}

export function AportesEMetas() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DE_APORTES, OPCOES);
  const resposta = responder(campos);
  const erro = typeof resposta === "string" ? resposta : null;
  const certa = erro ? null : (resposta as Resposta);
  const fim = certa ? certa.linhas.at(-1)! : null;
  const pergunta = campos.pergunta;
  const virada = certa
    ? mesDaVirada(certa.linhas[0].saldo, certa.aporte, certa.porMes, certa.linhas.length - 1, false, certa.reajuste)
    : null;
  const meta = lerNumero(campos.meta);

  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <Alternativas rotulo="Pergunta" valor={pergunta} opcoes={PERGUNTAS} aoMudar={mudar("pergunta")} />
        <CampoDeNumero rotulo="Valor que já tenho" antes="R$" valor={campos.inicial} aoMudar={mudar("inicial")} />
        {pergunta !== "quanto-guardar" ? (
          <CampoComDeslizante
            rotulo="Aporte por mês"
            antes="R$"
            valor={campos.aporte}
            aoMudar={mudar("aporte")}
            min={0}
            max={10000}
            passo={50}
          />
        ) : null}
        {pergunta !== "quanto-terei" ? (
          <CampoDeNumero rotulo="Meta" antes="R$" valor={campos.meta} aoMudar={mudar("meta")} />
        ) : null}
        <CampoComDeslizante
          rotulo="Rendimento"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          min={0}
          max={campos.unidadeDaTaxa === "ano" ? 20 : 2}
          passo={campos.unidadeDaTaxa === "ano" ? 0.5 : 0.05}
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
          <CampoComDeslizante
            rotulo="Prazo"
            valor={campos.anos}
            aoMudar={mudar("anos")}
            min={1}
            max={50}
            passo={1}
            depois={<span>anos</span>}
          />
        ) : null}
        <CampoDeNumero
          rotulo="Aumento do aporte a cada ano"
          valor={campos.reajuste}
          aoMudar={mudar("reajuste")}
          depois={<span>%</span>}
          dica="Quem guarda mais quando o salário sobe. Zero: o mesmo aporte o tempo todo."
        />
      </form>
      <Resultado rotulo={certa?.rotulo ?? ""} principal={certa?.principal ?? ""} erro={erro}>
        {fim ? (
          <dl className="ferramenta-numeros">
            <div>
              <dt>Saiu do seu bolso</dt>
              <dd>{formatarReais(fim.aportado)}</dd>
            </div>
            <div>
              <dt>Veio dos juros</dt>
              <dd>
                {formatarReais(fim.juros)}
                {fim.saldo > 0 ? <small className="apagado"> ({formatarPorcentagem(fim.juros / fim.saldo, 0)} do saldo)</small> : null}
              </dd>
            </div>
            <div>
              <dt>Saldo no fim</dt>
              <dd>{formatarReais(fim.saldo)}</dd>
            </div>
          </dl>
        ) : null}
        {certa ? (
          <p className="ferramenta-destaque">
            {virada
              ? `A partir do mês ${formatarNumero(virada)}, os juros do mês passam o aporte (${prazoPorExtenso(virada)}): daí em diante, o dinheiro trabalha mais que você.`
              : "No prazo escolhido, os juros de um mês ainda não chegam ao aporte do mês."}
          </p>
        ) : null}
      </Resultado>
      {certa ? (
        <div className="ferramenta-largo">
          <GraficoDoTempo
            titulo="O que saiu do bolso e o que veio dos juros, mês a mês"
            meses={pontosDoGrafico(certa.linhas).map((l) => l.mes)}
            series={[
              { nome: "Saiu do bolso", cor: SERIES[2], valores: pontosDoGrafico(certa.linhas).map((l) => l.aportado) },
              { nome: "Juros", cor: SERIES[0], valores: pontosDoGrafico(certa.linhas).map((l) => l.juros) },
            ]}
            empilhado
            referencia={pergunta !== "quanto-terei" && meta !== null ? { valor: meta, rotulo: "Meta" } : undefined}
            formatarValor={formatarReais}
            formatarEixo={formatarReaisCurto}
          />
          <Compartilhar resultado={textoParaCopiar(campos, certa)} />
        </div>
      ) : null}
    </div>
  );
}
