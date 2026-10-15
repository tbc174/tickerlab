// "Quanto daria? Foi sorte?" (ADR 0070): R$ X aplicados num mês do passado, quanto dariam hoje no CDI,
// na poupança, no dólar, parados, no Ibovespa e em bitcoin, e se a data foi de sorte. A conta é toda
// no servidor (src/ferramentas/ponte.py), pela rota pública do app, que devolve só números soltos
// (nunca a série de preços). Esta tela só busca ao ligar e ao apertar "Calcular" (há limite por IP).
import { useEffect, useState } from "react";
import { Compartilhar } from "./Compartilhar";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { lerDoEndereco, useCamposNoEndereco } from "./endereco";
import { formatarPorcentagem, formatarReais, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { FaixaDePosicao } from "../graficos/FaixaDePosicao";
import { GraficoDeBarras } from "../graficos/GraficoDeBarras";
import { URL_DO_APP } from "../site/textos";

export const ENDERECO_DA_PONTE = `${URL_DO_APP}/api/v1/ferramentas/quanto-daria`;
const NOMES_DOS_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES: [string, string][] = NOMES_DOS_MESES.map((nome, i) => [String(i + 1).padStart(2, "0"), nome]);
const ATIVOS_COM_JANELAS = ["cdi", "poupanca", "dolar", "ibovespa", "bitcoin"] as const;

export const EXEMPLO_DA_PONTE = { mes: "01", ano: "2020", valor: "1.000", ativo: "ibovespa" };
const OPCOES = { mes: MESES.map(([m]) => m), ativo: ATIVOS_COM_JANELAS } as const;
type Campos = typeof EXEMPLO_DA_PONTE;

interface Janelas {
  quantas: number;
  pior: number;
  mediana: number;
  melhor: number;
  abaixo_da_sua: number;
}
interface Ativo {
  ativo: string;
  nome: string;
  fonte: string;
  inicio: string;
  fim: string;
  valor_final: number;
  retorno: number;
  valor_real: number;
  janelas: Janelas | null;
}
export interface RespostaDaPonte {
  desde: string;
  valor: number;
  ativos: Ativo[];
  indisponiveis: { nome: string; motivo: string }[];
  aviso: string;
}
type Carga =
  | { estado: "carregando" }
  | { estado: "pronto"; dados: RespostaDaPonte }
  | { estado: "erro"; mensagem: string };

const INDISPONIVEL = "A ferramenta está indisponível agora. Tente de novo em alguns minutos.";

/** O endereço do pedido, ou a mensagem quando os campos não fecham. */
export function enderecoDoPedido(campos: Campos): string {
  const valor = lerNumero(campos.valor);
  const ano = Number(campos.ano);
  if (valor === null || !Number.isInteger(ano)) throw new RangeError("Preencha o ano e o valor com números.");
  return `${ENDERECO_DA_PONTE}?desde=${ano}-${campos.mes}-01&valor=${valor}`;
}

async function pedir(campos: Campos): Promise<Carga> {
  let endereco: string;
  try {
    endereco = enderecoDoPedido(campos);
  } catch (erro) {
    return { estado: "erro", mensagem: (erro as Error).message };
  }
  try {
    const resposta = await fetch(endereco);
    if (resposta.ok) return { estado: "pronto", dados: (await resposta.json()) as RespostaDaPonte };
    if (resposta.status === 422 || resposta.status === 429) {
      const corpo = (await resposta.json().catch(() => ({}))) as { detail?: unknown };
      return { estado: "erro", mensagem: typeof corpo.detail === "string" ? corpo.detail : INDISPONIVEL };
    }
    return { estado: "erro", mensagem: INDISPONIVEL };
  } catch {
    return { estado: "erro", mensagem: INDISPONIVEL };
  }
}

const mesPorExtenso = (iso: string) => `${NOMES_DOS_MESES[Number(iso.slice(5, 7)) - 1]}/${iso.slice(0, 4)}`;

export function QuantoDaria() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DA_PONTE, OPCOES);
  const [carga, setCarga] = useState<Carga>({ estado: "carregando" });
  const calcular = (com: Campos) => {
    setCarga({ estado: "carregando" });
    pedir(com).then(setCarga);
  };
  // ao ligar: o que está no endereço (o gancho do endereço ainda não aplicou) ou o exemplo
  useEffect(() => {
    calcular(lerDoEndereco(window.location.search, EXEMPLO_DA_PONTE, OPCOES));
  }, []);

  return (
    <div className="ferramenta">
      <form
        className="ferramenta-campos"
        onSubmit={(evento) => {
          evento.preventDefault();
          calcular(campos);
        }}
      >
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Aplicados em</span>
          <div className="ferramenta-entrada">
            <Escolha rotulo="Mês" valor={campos.mes} opcoes={MESES} aoMudar={mudar("mes")} />
            <input
              aria-label="Ano"
              type="text"
              inputMode="numeric"
              value={campos.ano}
              onChange={(evento) => mudar("ano")(evento.target.value)}
            />
          </div>
        </div>
        <CampoDeNumero rotulo="Valor" antes="R$" valor={campos.valor} aoMudar={mudar("valor")} />
        <button type="submit" className="botao primario">
          Calcular
        </button>
      </form>
      <Resposta carga={carga} campos={campos} aoMudarAtivo={mudar("ativo")} />
    </div>
  );
}

function Resposta({
  carga,
  campos,
  aoMudarAtivo,
}: {
  carga: Carga;
  campos: Campos;
  aoMudarAtivo: (ativo: Campos["ativo"]) => void;
}) {
  if (carga.estado === "carregando") {
    return <Resultado rotulo="Calculando" principal="…" erro={null} />;
  }
  if (carga.estado === "erro") {
    return <Resultado rotulo="" principal="" erro={carga.mensagem} />;
  }
  const { dados } = carga;
  const comJanelas = dados.ativos.filter((a) => a.janelas);
  const escolhido = comJanelas.find((a) => a.ativo === campos.ativo) ?? comJanelas[0];
  const j = escolhido?.janelas;
  return (
    <>
      <Resultado
        rotulo={escolhido ? `${formatarReais(dados.valor)} em ${escolhido.nome} desde ${mesPorExtenso(dados.desde)}` : ""}
        principal={escolhido ? formatarReais(escolhido.valor_final) : ""}
        erro={escolhido ? null : "Nenhum ativo disponível agora."}
      >
        {escolhido && j ? (
          <>
            <div className="ferramenta-campo">
              <span className="ferramenta-rotulo">Foi sorte? Ver o</span>
              <Escolha
                rotulo="Foi sorte? Ver o"
                valor={escolhido.ativo as Campos["ativo"]}
                opcoes={comJanelas.map((a): [Campos["ativo"], string] => [a.ativo as Campos["ativo"], a.nome])}
                aoMudar={aoMudarAtivo}
              />
            </div>
            <p className="ferramenta-destaque">
              Entre as {j.quantas.toLocaleString("pt-BR")} datas de início com o mesmo prazo,{" "}
              {Math.round(j.abaixo_da_sua * 100)}% das outras dariam menos que a sua; a do meio daria {formatarReais(j.mediana)}, a pior {formatarReais(j.pior)} e a
              melhor {formatarReais(j.melhor)}. As janelas se sobrepõem: não são sorteios independentes.
            </p>
            <FaixaDePosicao
              titulo={`${escolhido.nome}: a sua data entre todas as do mesmo prazo`}
              pior={j.pior}
              mediana={j.mediana}
              melhor={j.melhor}
              sua={escolhido.valor_final}
              abaixoDaSua={j.abaixo_da_sua}
              formatarValor={formatarReais}
            />
          </>
        ) : null}
      </Resultado>
      <div className="ferramenta-largo">
        <GraficoDeBarras
          titulo={`${formatarReais(dados.valor)} aplicados em ${mesPorExtenso(dados.desde)}: quanto dariam hoje`}
          barras={dados.ativos.map((a) => ({
            nome: a.nome,
            valor: a.valor_final,
            cor: a.ativo === escolhido?.ativo ? SERIES[0] : SERIES[2],
          }))}
          formatarValor={formatarReais}
        />
        <table className="ferramenta-comparacao">
          <thead>
            <tr>
              <th scope="col">Ativo</th>
              <th scope="col">Hoje</th>
              <th scope="col">Retorno</th>
              <th scope="col">Em poder de compra de {mesPorExtenso(dados.desde)}</th>
            </tr>
          </thead>
          <tbody>
            {dados.ativos.map((a) => (
              <tr key={a.ativo}>
                <th scope="row">{a.nome}</th>
                <td>{formatarReais(a.valor_final)}</td>
                <td>{formatarPorcentagem(a.retorno)}</td>
                <td>{formatarReais(a.valor_real)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="ferramenta-notas apagado">
          {dados.indisponiveis.map((i) => (
            <li key={i.nome}>
              {i.nome}: {i.motivo}
            </li>
          ))}
          {dados.ativos.map((a) => (
            <li key={a.ativo}>
              {a.nome}: {a.fonte}; de {mesPorExtenso(a.inicio)} a {mesPorExtenso(a.fim)}.
            </li>
          ))}
          <li>{dados.aviso}</li>
        </ul>
        {escolhido ? (
          <Compartilhar
            resultado={`${formatarReais(dados.valor)} em ${escolhido.nome} desde ${mesPorExtenso(dados.desde)} dariam ${formatarReais(escolhido.valor_final)} hoje${j ? `; ${Math.round(j.abaixo_da_sua * 100)}% das outras datas com o mesmo prazo dariam menos` : ""}`}
          />
        ) : null}
      </div>
    </>
  );
}
