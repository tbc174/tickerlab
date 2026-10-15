// Renda fixa com IR (contas/renda_fixa.ts, a mesma conta do Python), v2: CDB, LCI/LCA, Tesouro Selic
// e poupança pelo CDI (parado no de hoje ou seguindo a Selic esperada pelo Focus), mais o Tesouro
// Prefixado e o IPCA+ com a taxa de hoje do título que vence mais perto do prazo; IOF, IR e custódia;
// o ponto de empate entre LCI/LCA e CDB; gráfico de barras e tabela. A ordem é fixa: nada de
// "o melhor".
import { Compartilhar } from "./Compartilhar";
import { Alternativas, CampoComDeslizante, CampoDeNumero, Escolha, Resultado } from "./campos";
import { ComDadosDoBc, DataDoDado } from "./Carregando";
import { em12Meses } from "./contas/inflacao";
import {
  DIAS_MAXIMOS,
  type Opcao,
  cdiPeloFocus,
  comparar,
  pontoDeEmpate,
  tesouroIpca,
  tesouroPrefixado,
} from "./contas/renda_fixa";
import { type DadosDoBc, type TituloDoTesouro, dataBrasileira, useDadosDoBc } from "./dados";
import { useCamposNoEndereco } from "./endereco";
import { formatarNumero, formatarPorcentagem, formatarReais, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDeBarras } from "../graficos/GraficoDeBarras";

type Unidade = "dias" | "meses" | "anos";
type ComoOCdiAnda = "focus" | "parado";
const DIAS_POR: Record<Unidade, number> = { dias: 1, meses: 30, anos: 365 };
const MS_POR_DIA = 24 * 3600 * 1000;

export const EXEMPLO_DA_RENDA_FIXA = {
  valor: "10.000",
  prazo: "2",
  unidade: "anos" as Unidade,
  cdb: "100",
  lci: "90",
  cdi: "focus" as ComoOCdiAnda,
};

const OPCOES = { unidade: ["dias", "meses", "anos"], cdi: ["focus", "parado"] } as const;

/** A conta das quatro opções pelo CDI (a de sempre); serve também ao teste antigo da tela. */
export function calcularRendaFixa(
  campos: Pick<typeof EXEMPLO_DA_RENDA_FIXA, "valor" | "prazo" | "unidade" | "cdb" | "lci">,
  cdiPorAno: number[],
  poupancaAoMes: number,
): Opcao[] | string {
  const [valor, prazo, cdb, lci] = [campos.valor, campos.prazo, campos.cdb, campos.lci].map(lerNumero);
  if (valor === null || prazo === null || cdb === null || lci === null) {
    return "Preencha os campos com números (por exemplo, 10.000).";
  }
  const dias = Math.round(prazo * DIAS_POR[campos.unidade]);
  if (dias > DIAS_MAXIMOS) return "O prazo vai até 10 anos.";
  try {
    return comparar(valor, dias, cdiPorAno, cdb / 100, lci / 100, poupancaAoMes);
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

/** O título do tipo pedido que vence mais perto de `dias` depois da data das taxas. */
export function tituloMaisPerto(
  titulos: TituloDoTesouro[],
  tipo: string,
  dataDasTaxas: string,
  dias: number,
): TituloDoTesouro | null {
  const alvo = new Date(`${dataDasTaxas}T12:00:00`).getTime() + dias * MS_POR_DIA;
  const distancia = (t: TituloDoTesouro) => Math.abs(new Date(`${t.vencimento}T12:00:00`).getTime() - alvo);
  return titulos.filter((t) => t.titulo === tipo).reduce<TituloDoTesouro | null>((melhor, t) => (!melhor || distancia(t) < distancia(melhor) ? t : melhor), null);
}

/** A inflação de cada ano da aplicação: a esperada pelo Focus (o último ano vale para os seguintes)
 * ou, sem o Focus, a dos últimos 12 meses. */
function ipcaPorAno(dados: DadosDoBc, anoInicial: number, anos: number): number[] | null {
  const esperada = dados.focus?.ipca?.anos;
  if (esperada && Object.keys(esperada).length) {
    const caminho: number[] = [];
    for (let ano = anoInicial; ano < anoInicial + anos; ano++) {
      const valor = esperada[String(ano)];
      caminho.push(valor ?? caminho[caminho.length - 1] ?? Object.values(esperada)[0]);
    }
    return caminho;
  }
  return dados.ipca && dados.ipca.meses.length >= 12 ? [em12Meses(dados.ipca.meses)] : null;
}

const COLUNAS_DE_CUSTO: [keyof Opcao, string][] = [
  ["imposto", "IR"],
  ["iof", "IOF"],
  ["custodia", "Custódia"],
];

function Comparacao({ dados }: { dados: DadosDoBc }) {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DA_RENDA_FIXA, OPCOES);
  const cdi = dados.cdi!;
  const poupanca = dados.poupanca!;
  const valor = lerNumero(campos.valor) ?? 0;
  const prazo = lerNumero(campos.prazo) ?? 0;
  // prazo fora da faixa (até um endereço com "99999999 anos"): a conta recusa e mostra a mensagem;
  // o caminho do CDI, que anda um ano por vez, não passa dos 10 anos
  const dias = Math.min(Math.round(prazo * DIAS_POR[campos.unidade]), DIAS_MAXIMOS);
  const anos = Math.max(1, Math.ceil(dias / 365));
  const anoInicial = new Date().getFullYear();
  const comFocus = Boolean(dados.focus?.selic && dados.selic_meta);
  const peloFocus = comFocus && campos.cdi === "focus";
  const cdiPorAno = peloFocus
    ? cdiPeloFocus(cdi.ao_ano, dados.selic_meta!.ao_ano, dados.focus!.selic!.anos, anoInicial, anos)
    : [cdi.ao_ano];
  const conta = calcularRendaFixa(campos, cdiPorAno, poupanca.ao_mes);
  const erro = typeof conta === "string" ? conta : null;
  const opcoes = typeof conta === "string" ? [] : [...conta];
  if (!erro && dados.tesouro) {
    const prefixado = tituloMaisPerto(dados.tesouro.titulos, "Tesouro Prefixado", dados.tesouro.data, dias);
    if (prefixado) {
      opcoes.push({ ...tesouroPrefixado(valor, dias, prefixado.taxa), nome: `Tesouro Prefixado ${prefixado.vencimento.slice(0, 4)}` });
    }
    const ipcaMais = tituloMaisPerto(dados.tesouro.titulos, "Tesouro IPCA+", dados.tesouro.data, dias);
    const inflacao = ipcaPorAno(dados, anoInicial, anos);
    if (ipcaMais && inflacao) {
      opcoes.push({ ...tesouroIpca(valor, dias, ipcaMais.taxa, inflacao), nome: `Tesouro IPCA+ ${ipcaMais.vencimento.slice(0, 4)}` });
    }
  }
  const lci = (lerNumero(campos.lci) ?? 0) / 100;
  const empate = erro ? null : pontoDeEmpate(valor, dias, cdiPorAno, lci);
  const ipcaPeloFocus = Boolean(dados.focus?.ipca && Object.keys(dados.focus.ipca.anos).length);
  const colunas = COLUNAS_DE_CUSTO.filter(([chave]) => opcoes.some((o) => (o[chave] as number) > 0));

  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoComDeslizante rotulo="Valor aplicado" antes="R$" valor={campos.valor} aoMudar={mudar("valor")} min={1000} max={500000} passo={1000} />
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
        <CampoComDeslizante rotulo="CDB que paga" valor={campos.cdb} aoMudar={mudar("cdb")} min={80} max={130} passo={1} depois={<span>% do CDI</span>} />
        <CampoComDeslizante rotulo="LCI ou LCA que paga" valor={campos.lci} aoMudar={mudar("lci")} min={70} max={110} passo={1} depois={<span>% do CDI</span>} />
        {comFocus ? (
          <Alternativas
            rotulo="Como o CDI anda daqui para a frente"
            valor={campos.cdi}
            opcoes={[
              ["focus", "Seguindo a Selic esperada (Focus)"],
              ["parado", "Parado no de hoje"],
            ]}
            aoMudar={mudar("cdi")}
          />
        ) : null}
      </form>
      <Resultado rotulo="CDI hoje" principal={`${formatarPorcentagem(cdi.ao_ano)} ao ano`} erro={erro}>
        {empate !== null && empate !== undefined ? (
          <p className="ferramenta-destaque">
            Neste prazo, uma LCI ou LCA de {formatarNumero(lci * 100)}% do CDI (isenta) equivale a um CDB de{" "}
            {formatarNumero(empate * 100)}% do CDI, depois do IR.
          </p>
        ) : null}
        <DataDoDado data={cdi.data} rotulo="CDI de" />
        <DataDoDado data={poupanca.data} rotulo="rendimento da poupança do aniversário de" />
      </Resultado>
      {erro ? null : (
        <div className="ferramenta-largo">
          <GraficoDeBarras
            titulo="Quanto cada opção rende no prazo, já sem IR, IOF e custódia"
            barras={opcoes.map((o, k) => ({ nome: o.nome, valor: o.liquido - valor, cor: SERIES[k < 4 ? 0 : 2] }))}
            formatarValor={formatarReais}
          />
          <table className="ferramenta-comparacao">
            <thead>
              <tr>
                <th scope="col">Opção</th>
                {colunas.map(([, nome]) => (
                  <th scope="col" key={nome}>
                    {nome}
                  </th>
                ))}
                <th scope="col">Líquido no fim</th>
              </tr>
            </thead>
            <tbody>
              {opcoes.map((o) => (
                <tr key={o.nome}>
                  <th scope="row">{o.nome}</th>
                  {colunas.map(([chave, nome]) => (
                    <td key={nome}>{(o[chave] as number) > 0 ? formatarReais(o[chave] as number) : "—"}</td>
                  ))}
                  <td>{formatarReais(o.liquido)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="ferramenta-notas apagado">
            {peloFocus ? (
              <li>
                CDI seguindo a Selic esperada pelo Focus de {dataBrasileira(dados.focus!.selic!.data)}: é a
                expectativa do mercado na pesquisa do Banco Central, não uma previsão do TickerLab.
              </li>
            ) : null}
            {dados.tesouro ? (
              <li>
                Tesouro Prefixado e IPCA+: a taxa de compra de {dataBrasileira(dados.tesouro.data)} do título que vence
                mais perto do seu prazo, levando até o fim do prazo (vender antes muda o valor). Fonte: Tesouro Nacional.
                No IPCA+, a inflação é {ipcaPeloFocus ? "a esperada pelo Focus" : "a dos últimos 12 meses (sem o Focus agora)"}.
              </li>
            ) : null}
            <li>
              IOF nos primeiros 30 dias (a LCA é isenta; a LCI e a LCA costumam ter carência maior que isso). Custódia
              da B3 de 0,2% ao ano no Tesouro (o Selic é isento até R$ 10 mil).
            </li>
          </ul>
          <Compartilhar
            resultado={`${formatarReais(valor)} por ${campos.prazo} ${campos.unidade}: uma LCI/LCA de ${campos.lci}% do CDI equivale a um CDB de ${empate === null ? "?" : formatarNumero(empate * 100)}% do CDI`}
          />
        </div>
      )}
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
