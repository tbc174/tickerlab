// Visão geral de um ativo no app novo: o painel de números (os mesmos do Streamlit, pelos itens de
// src/analises.py) e a curva em base 100. A API não entrega o preço (licença dos preços, ADR 0008).
import { useSearchParams } from "react-router";
import { type ItemDoPainel, type PaginaDoApp, conteudoDoApp } from "../../conteudo";
import { Ajuda } from "../Ajuda";
import { Formulario, parametrosDoPedido, valoresIniciais } from "../Formulario";
import { formatar, formatarData, formatarPct } from "../formatar";
import { GraficoDeLinha } from "../graficos/GraficoDeLinha";
import type { PainelDeNumerosV1, VisaoGeralV1 } from "../tipos";
import { usarPedido } from "../usarPedido";
import { ErroDaTela } from "./ErroDaTela";

const { itens, legenda, frase_do_cvar } = conteudoDoApp.painel;
const GRUPOS = [...new Set(itens.map((i) => i.grupo))];

function rotuloDo(item: ItemDoPainel, painel: PainelDeNumerosV1): string {
  const data = item.campo_da_data
    ? formatarData(String(painel[item.campo_da_data as keyof PainelDeNumerosV1]))
    : "";
  return item.rotulo.replace("{data}", data).replace("{confianca}", String(painel.confianca_do_var));
}

function Painel({ painel }: { painel: PainelDeNumerosV1 }) {
  return (
    <section aria-label="Painel de números" className="painel-de-numeros">
      <h2>Painel de números</h2>
      <p className="apagado">{legenda}</p>
      {GRUPOS.map((grupo) => (
        <div key={grupo}>
          <h3>{grupo}</h3>
          <div className="numeros">
            {itens
              .filter((i) => i.grupo === grupo)
              .map((item, posicao) => {
                const rotulo = rotuloDo(item, painel);
                const valor = painel[item.campo as keyof PainelDeNumerosV1] as number | null;
                return (
                  <div
                    key={item.campo}
                    className={`numero-do-painel${posicao === 0 && grupo === GRUPOS[0] ? " principal" : ""}`}
                  >
                    <span className="numero-rotulo">
                      <span>{rotulo}</span>
                      <Ajuda termo={item.termo} rotulo={rotulo} />
                    </span>
                    <span className="numero-valor">{formatar(valor, item.formato)}</span>
                  </div>
                );
              })}
          </div>
        </div>
      ))}
      <p className="apagado">
        {frase_do_cvar
          .replace("{confianca}", String(painel.confianca_do_var))
          .replace("{cvar}", formatarPct(painel.cvar))}
      </p>
    </section>
  );
}

function Resultado({ dados }: { dados: VisaoGeralV1 }) {
  return (
    <>
      {dados.ativo.aviso_da_origem ? (
        <p className="erro-do-app" role="note">
          {dados.ativo.aviso_da_origem}
        </p>
      ) : null}
      <Painel painel={dados.painel} />
      {dados.motivo_sem_anualizar ? (
        <p className="apagado">Retorno anualizado: {dados.motivo_sem_anualizar}</p>
      ) : null}
      <h2>O caminho do ativo</h2>
      <p className="apagado">
        Quanto valeriam R$ 100 investidos no primeiro dia do período (base 100), sem o preço.
      </p>
      <GraficoDeLinha
        titulo={`${dados.ativo.ticker} em base 100`}
        datas={dados.curva.datas}
        series={[{ nome: dados.ativo.ticker, cor: "var(--azul)", valores: dados.curva.valores }]}
        referencia={100}
      />
    </>
  );
}

export function VisaoGeral({ pagina }: { pagina: PaginaDoApp }) {
  const contrato = pagina.contrato;
  const [busca, setBusca] = useSearchParams();
  const entradas = contrato?.entradas ?? [];
  const valores = valoresIniciais(entradas, busca);
  const pedido = usarPedido<VisaoGeralV1>(contrato?.rota ?? "", parametrosDoPedido(entradas, valores));
  return (
    <section>
      <h1>{pagina.titulo}</h1>
      <p className="apagado">{pagina.descricao}</p>
      <Formulario
        key={busca.toString()}
        entradas={entradas}
        valores={valores}
        aoAnalisar={(novos) => setBusca(new URLSearchParams(Object.entries(novos).filter(([, v]) => v !== "")))}
      />
      {pedido.estado === "carregando" ? (
        <p className="apagado" role="status">
          Calculando…
        </p>
      ) : pedido.estado === "erro" ? (
        <ErroDaTela erro={pedido.erro} />
      ) : (
        <Resultado dados={pedido.dados} />
      )}
    </section>
  );
}
