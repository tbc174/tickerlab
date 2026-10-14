// Conversor de moedas pela PTAX do Banco Central (contas/moedas.ts, a mesma conta do Python).
import { useState } from "react";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { ComDadosDoBc, DataDoDado } from "./Carregando";
import { REAL, converter } from "./contas/moedas";
import { type DadosDoBc, type Moeda, useDadosDoBc } from "./dados";
import { lerNumero } from "./numeros";

export const EXEMPLO_DO_CONVERSOR = { valor: "100", de: "USD", para: REAL };

/** "US$ 100,00", "€ 89,30", "R$ 500,00": o valor com o símbolo da moeda. Código que o navegador
 * não conhece (o BC pode acrescentar uma moeda) sai como "1.234,56 XYZ", sem quebrar a página. */
export function formatarNaMoeda(valor: number, codigo: string): string {
  const casas = codigo === "JPY" ? 0 : 2;
  try {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: codigo,
      minimumFractionDigits: casas,
      maximumFractionDigits: casas,
    }).format(valor);
  } catch (erro) {
    if (!(erro instanceof RangeError)) throw erro;
    const numero = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
    return `${numero.format(valor)} ${codigo}`;
  }
}

export function cotacoesDeVenda(moedas: Moeda[]): Record<string, number> {
  return Object.fromEntries(moedas.map((m) => [m.codigo, m.venda]));
}

function Conversor({ moedas }: { moedas: Moeda[] }) {
  const [campos, setCampos] = useState(EXEMPLO_DO_CONVERSOR);
  const mudar = (chave: keyof typeof campos) => (valor: string) => setCampos((antes) => ({ ...antes, [chave]: valor }));
  const opcoes: [string, string][] = [[REAL, "Real (BRL)"], ...moedas.map((m): [string, string] => [m.codigo, `${m.nome} (${m.codigo})`])];
  const valor = lerNumero(campos.valor);
  const cotacoes = cotacoesDeVenda(moedas);
  const estrangeira = moedas.find((m) => m.codigo === (campos.de === REAL ? campos.para : campos.de));
  const resultado = valor === null ? null : converter(valor, campos.de, campos.para, cotacoes);
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor" valor={campos.valor} aoMudar={mudar("valor")} />
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">De</span>
          <Escolha rotulo="De" valor={campos.de} opcoes={opcoes} aoMudar={mudar("de")} />
        </div>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Para</span>
          <Escolha rotulo="Para" valor={campos.para} opcoes={opcoes} aoMudar={mudar("para")} />
        </div>
      </form>
      <Resultado
        rotulo={valor === null ? "" : `${formatarNaMoeda(valor, campos.de)} são`}
        principal={resultado === null ? "" : formatarNaMoeda(resultado, campos.para)}
        erro={valor === null ? "Digite o valor em números (por exemplo, 1.000,50)." : null}
      >
        {estrangeira ? (
          <>
            <p>
              1 {estrangeira.codigo} = {formatarNaMoeda(estrangeira.venda, REAL)} pela PTAX de venda.
            </p>
            <DataDoDado data={estrangeira.data} rotulo="PTAX de fechamento de" />
          </>
        ) : null}
      </Resultado>
    </div>
  );
}

export function ConversorDeMoedas() {
  const carga = useDadosDoBc();
  return (
    <ComDadosDoBc carga={carga}>
      {(dados: DadosDoBc) =>
        dados.moedas?.length ? <Conversor moedas={dados.moedas} /> : <p className="ferramenta-erro">Sem a PTAX agora.</p>
      }
    </ComDadosDoBc>
  );
}
