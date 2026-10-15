// Preço médio de ações e FIIs (contas/preco_medio.ts, a mesma conta do Python): até 8 operações
// numa grade, na ordem em que foram feitas; a posição depois de cada uma, o preço médio final e o
// resultado das vendas. A simulação vai no endereço (linhas vazias ficam de fora).
import { Compartilhar } from "./Compartilhar";
import { Escolha, Resultado } from "./campos";
import { type Linha, type Operacao, TIPOS, calcular } from "./contas/preco_medio";
import { useCamposNoEndereco } from "./endereco";
import { formatarNumero, formatarReais, lerNumero } from "./numeros";

const LINHAS = Array.from({ length: 8 }, (_, i) => i + 1);
const NOMES_DOS_TIPOS: Record<(typeof TIPOS)[number], string> = {
  compra: "Compra",
  venda: "Venda",
  bonificacao: "Bonificação",
  desdobro: "Desdobro",
  grupamento: "Grupamento",
  amortizacao: "Amortização (FII)",
};
const DE_EXEMPLO: Record<number, [string, string, string, string]> = {
  1: ["compra", "100", "25", "4,90"],
  2: ["compra", "50", "30", "4,90"],
  3: ["venda", "60", "32", "4,90"],
};

export const EXEMPLO_DO_PRECO_MEDIO: Record<string, string> = Object.fromEntries(
  LINHAS.flatMap((i) => {
    const [tipo, quantidade, preco, taxas] = DE_EXEMPLO[i] ?? ["compra", "", "", ""];
    return [
      [`t${i}`, tipo],
      [`q${i}`, quantidade],
      [`p${i}`, preco],
      [`x${i}`, taxas],
    ];
  }),
);
const OPCOES = Object.fromEntries(LINHAS.map((i) => [`t${i}`, TIPOS]));

const vazioOuZero = (texto: string | undefined) => (texto === undefined || texto.trim() === "" ? 0 : lerNumero(texto));

/** A operação da linha `i`, ou null se ela está vazia (a amortização vale pelo valor por cota; as
 * outras, pela quantidade). */
function operacaoDaLinha(campos: Record<string, string>, i: number): Operacao | null {
  const [quantidade, preco, custos] = [campos[`q${i}`], campos[`p${i}`], campos[`x${i}`]].map((t) => vazioOuZero(t) ?? 0);
  const tipo = campos[`t${i}`];
  const preenchida = tipo === "amortizacao" ? preco > 0 : quantidade > 0;
  return preenchida ? { tipo, quantidade, preco, custos } : null;
}

/** As operações preenchidas, na ordem da grade. */
export function operacoesDosCampos(campos: Record<string, string>): Operacao[] {
  return LINHAS.flatMap((i) => operacaoDaLinha(campos, i) ?? []);
}

function calcularPrecoMedio(campos: Record<string, string>): { linhas: Linha[]; porLinha: Map<number, Linha> } | string {
  const invalida = LINHAS.some((i) => [campos[`q${i}`], campos[`p${i}`], campos[`x${i}`]].some((t) => vazioOuZero(t) === null));
  if (invalida) return "Preencha as operações com números (por exemplo, 1.000,50).";
  try {
    const linhas = calcular(operacoesDosCampos(campos));
    // a linha da grade de cada resultado (as vazias não têm)
    const preenchidas = LINHAS.filter((i) => operacaoDaLinha(campos, i) !== null);
    return { linhas, porLinha: new Map(preenchidas.map((i, k) => [i, linhas[k]])) };
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

export function PrecoMedio() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO_DO_PRECO_MEDIO, OPCOES);
  const conta = calcularPrecoMedio(campos);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  const fim = r?.linhas[r.linhas.length - 1];
  const resultadoDasVendas = r ? r.linhas.reduce((soma, l) => soma + (l.resultado ?? 0), 0) : 0;
  const campo = (chave: string, rotulo: string) => (
    <input
      type="text"
      inputMode="decimal"
      aria-label={rotulo}
      value={campos[chave]}
      onChange={(evento) => mudar(chave)(evento.target.value)}
    />
  );
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos ferramenta-largo darf-do-ano preco-medio" onSubmit={(evento) => evento.preventDefault()}>
        <p className="apagado">Uma operação por linha, na ordem em que foram feitas. Linha sem quantidade fica de fora. No desdobro e no grupamento, a quantidade é a que entra ou sai, não o total novo.</p>
        <div className="ferramenta-rolagem">
          <table>
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Operação</th>
                <th scope="col">Quantidade</th>
                <th scope="col">Preço (R$)</th>
                <th scope="col">Taxas (R$)</th>
                <th scope="col">Fica com</th>
                <th scope="col">Preço médio</th>
                <th scope="col">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {LINHAS.map((i) => {
                const linha = r?.porLinha.get(i);
                return (
                  <tr key={i}>
                    <th scope="row">{i}</th>
                    <td>
                      <Escolha
                        rotulo={`Tipo da operação ${i}`}
                        valor={campos[`t${i}`]}
                        opcoes={TIPOS.map((t): [string, string] => [t, NOMES_DOS_TIPOS[t]])}
                        aoMudar={mudar(`t${i}`)}
                      />
                    </td>
                    <td>{campo(`q${i}`, `Quantidade na operação ${i}`)}</td>
                    <td>{campo(`p${i}`, `Preço na operação ${i}`)}</td>
                    <td>{campo(`x${i}`, `Taxas na operação ${i}`)}</td>
                    <td>{linha ? formatarNumero(linha.quantidade) : ""}</td>
                    <td>{linha ? (linha.preco_medio === null ? "—" : formatarReais(linha.preco_medio)) : ""}</td>
                    <td>{linha?.resultado != null ? formatarReais(linha.resultado) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </form>
      <Resultado
        rotulo="Preço médio"
        principal={fim ? (fim.preco_medio === null ? "Sem ações" : formatarReais(fim.preco_medio)) : "Sem operações"}
        erro={erro}
      >
        {fim ? (
          <>
            <dl className="ferramenta-numeros">
              <div>
                <dt>Quantidade</dt>
                <dd>{formatarNumero(fim.quantidade)}</dd>
              </div>
              <div>
                <dt>Custo total (com as taxas)</dt>
                <dd>{formatarReais(fim.custo_total)}</dd>
              </div>
              <div>
                <dt>Resultado (vendas e amortização acima do custo)</dt>
                <dd>{formatarReais(resultadoDasVendas)}</dd>
              </div>
            </dl>
            <Compartilhar
              resultado={`Preço médio: ${fim.preco_medio === null ? "sem ações" : formatarReais(fim.preco_medio)} em ${formatarNumero(fim.quantidade)} ações; resultado das vendas: ${formatarReais(resultadoDasVendas)}`}
            />
          </>
        ) : null}
      </Resultado>
    </div>
  );
}
