// Custo das taxas e da queda (contas/custos.ts, a mesma conta do Python): duas calculadoras curtas,
// v2 com gráfico (o que a taxa levou, pintado por cima do que ficou com você; a queda e a alta lado a
// lado), atalhos e a simulação no endereço (cada uma com o seu prefixo, porque dividem a página).
import { Compartilhar } from "./Compartilhar";
import { CampoComDeslizante, CampoDeNumero, Resultado } from "./campos";
import { ANOS_MAXIMOS, altaParaRecuperar, custoDaTaxa, evolucaoDaTaxa } from "./contas/custos";
import { useCamposNoEndereco } from "./endereco";
import { formatarNumero, formatarPorcentagem, formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDeBarras } from "../graficos/GraficoDeBarras";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

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
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DA_TAXA, {}, "taxa.");
  const conta = calcularTaxa(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  const linhas = r
    ? evolucaoDaTaxa(lerNumero(campos.capital)!, lerNumero(campos.retorno)! / 100, lerNumero(campos.taxa)! / 100, lerNumero(campos.anos)!)
    : [];
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor investido" antes="R$" valor={campos.capital} aoMudar={mudar("capital")} />
        <CampoComDeslizante
          rotulo="Rendimento antes da taxa"
          valor={campos.retorno}
          aoMudar={mudar("retorno")}
          min={0}
          max={20}
          passo={0.5}
          depois={<span>% ao ano</span>}
        />
        <CampoComDeslizante
          rotulo="Taxa sobre o patrimônio"
          valor={campos.taxa}
          aoMudar={mudar("taxa")}
          min={0}
          max={3}
          passo={0.1}
          depois={<span>% ao ano</span>}
          dica="Como a taxa de administração de um fundo: cobrada todo ano sobre tudo o que você tem lá."
        />
        <CampoComDeslizante
          rotulo="Prazo"
          valor={campos.anos}
          aoMudar={mudar("anos")}
          min={1}
          max={50}
          passo={1}
          depois={<span>anos</span>}
        />
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
      {r && linhas.length > 1 ? (
        <div className="ferramenta-largo">
          <GraficoDoTempo
            titulo="Ano a ano: o que ficou com você e o que a taxa levou"
            meses={linhas.map((l) => l.ano * 12)}
            series={[
              { nome: "Ficou com você", cor: SERIES[0], valores: linhas.map((l) => l.com_taxa) },
              { nome: "A taxa levou", cor: SERIES[1], valores: linhas.map((l) => l.sem_taxa - l.com_taxa) },
            ]}
            empilhado
            formatarValor={formatarReais}
            formatarEixo={formatarReaisCurto}
          />
          <Compartilhar
            resultado={`Uma taxa de ${campos.taxa}% ao ano sobre ${formatarReais(lerNumero(campos.capital)!)} leva ${formatarReais(r.ficou_com_a_taxa)} em ${campos.anos} anos (${formatarPorcentagem(r.fracao_do_resultado, 0)} do resultado)`}
          />
        </div>
      ) : null}
    </div>
  );
}

export const EXEMPLO_DA_QUEDA = "50";
const QUEDAS_DE_EXEMPLO = [10, 20, 30, 50, 80];

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
  const [campos, mudar] = useCamposNoEndereco({ queda: EXEMPLO_DA_QUEDA }, {}, "queda.");
  const conta = calcularQueda(campos.queda);
  const erro = typeof conta === "string" ? conta : null;
  const queda = Math.abs(lerNumero(campos.queda) ?? 0) / 100;
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante
          rotulo="Queda"
          valor={campos.queda}
          aoMudar={mudar("queda")}
          min={0}
          max={90}
          passo={1}
          depois={<span>%</span>}
          atalhos={QUEDAS_DE_EXEMPLO.map((q) => ({ rotulo: `−${q}%`, valor: String(q) }))}
        />
      </form>
      <Resultado
        rotulo="Alta para voltar ao valor de antes"
        principal={erro ? "" : formatarPorcentagem(conta as number)}
        erro={erro}
      >
        {erro ? null : (
          <>
            <GraficoDeBarras
              titulo="A queda e a alta que a desfaz"
              barras={[
                { nome: "Queda", valor: -queda, cor: SERIES[1] },
                { nome: "Alta para voltar", valor: conta as number, cor: SERIES[0] },
              ]}
              formatarValor={(v) => formatarPorcentagem(v, 1)}
            />
            <p className="ferramenta-destaque">
              R$ 100 que caem {formatarNumero(queda * 100)}% viram {formatarReais(100 * (1 - queda))}; para voltar a R$ 100,
              precisam subir {formatarPorcentagem(conta as number, 1)}.
            </p>
          </>
        )}
      </Resultado>
    </div>
  );
}
