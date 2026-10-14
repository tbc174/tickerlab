// Risco ao longo do tempo no app novo: a frase da pior queda (a mesma do Streamlit), a queda desde o
// topo dia a dia e a volatilidade móvel da janela escolhida.
import type { PaginaDoApp } from "../../conteudo";
import { Ajuda } from "../Ajuda";
import { formatarPct } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { RiscoDoAtivoV1 } from "../tipos";
import { TelaDoContrato } from "./TelaDoContrato";

const emPct = (v: number) => formatarPct(v);

function Resultado({ dados }: { dados: RiscoDoAtivoV1 }) {
  const { risco, ativo } = dados;
  return (
    <>
      {ativo.aviso_da_origem ? (
        <p className="erro-do-app" role="note">
          {ativo.aviso_da_origem}
        </p>
      ) : null}
      <p>{risco.frase_da_pior_queda}</p>
      <h2>
        Queda desde o topo <Ajuda termo="Drawdown" rotulo="queda desde o topo (drawdown)" />
      </h2>
      <GraficoDeLinha
        titulo={`Queda desde o topo de ${ativo.codigo}`}
        datas={risco.drawdown.datas}
        series={[{ nome: "Queda desde o topo", cor: "var(--serie-1)", valores: risco.drawdown.valores }]}
        referencia={0}
        formatarValor={emPct}
      />
      <h2>
        Volatilidade móvel <Ajuda termo="Volatilidade móvel" rotulo="volatilidade móvel" />
      </h2>
      {risco.aviso_da_janela ? (
        <p className="apagado">{risco.aviso_da_janela}</p>
      ) : (
        <GraficoDeLinha
          titulo={`Volatilidade móvel de ${risco.janela} dias (ao ano) de ${ativo.codigo}`}
          datas={risco.volatilidade_movel.datas}
          series={[
            { nome: `Volatilidade (${risco.janela} dias)`, cor: "var(--serie-1)", valores: risco.volatilidade_movel.valores },
          ]}
          formatarValor={emPct}
        />
      )}
    </>
  );
}

export function Risco({ pagina }: { pagina: PaginaDoApp }) {
  return (
    <TelaDoContrato<RiscoDoAtivoV1>
      pagina={pagina}
      carregando="Calculando o risco…"
      resultado={(dados) => <Resultado dados={dados} />}
    />
  );
}
