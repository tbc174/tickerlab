// Correção pela inflação (contas/inflacao.ts, a mesma conta do Python), com o IPCA mensal do Banco
// Central desde o Plano Real.
import { useEffect, useState } from "react";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { ComDadosDoBc, MesDoIpca } from "./Carregando";
import { type Correcao, type Meses, corrigir } from "./contas/inflacao";
import { useDadosDoBc } from "./dados";
import { formatarPorcentagem, formatarReais, lerNumero } from "./numeros";

const NOMES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const OPCOES_DE_MES: [string, string][] = NOMES.map((nome, i) => [String(i + 1).padStart(2, "0"), nome]);
const ANOS_PARA_TRAS = 10; // o exemplo: um valor de 10 anos atrás

export const EXEMPLO_DA_CORRECAO = { valor: "100", mesInicial: "01", anoInicial: "2015", mesFinal: "12", anoFinal: "2024" };
type Campos = typeof EXEMPLO_DA_CORRECAO;

/** "2015-01" a partir dos campos. */
const mes = (numero: string, ano: string) => `${ano.trim()}-${numero}`;

export function calcularCorrecao(campos: Campos, meses: Meses): Correcao | string {
  const valor = lerNumero(campos.valor);
  if (valor === null) return "Digite o valor em números (por exemplo, 1.000,50).";
  try {
    return corrigir(valor, mes(campos.mesInicial, campos.anoInicial), mes(campos.mesFinal, campos.anoFinal), meses);
  } catch (erro) {
    if (erro instanceof RangeError) return erro.message;
    throw erro;
  }
}

function Calculadora({ meses, ultimo }: { meses: Meses; ultimo: string }) {
  const [campos, setCampos] = useState(EXEMPLO_DA_CORRECAO);
  // o exemplo passa a ir até o último IPCA divulgado, começando 10 anos antes
  useEffect(() => {
    const [ano, numero] = ultimo.split("-");
    setCampos((antes) => ({
      ...antes,
      mesFinal: numero,
      anoFinal: ano,
      mesInicial: numero,
      anoInicial: String(Number(ano) - ANOS_PARA_TRAS),
    }));
  }, [ultimo]);
  const mudar = (chave: keyof Campos) => (valor: string) => setCampos((antes) => ({ ...antes, [chave]: valor }));
  const conta = calcularCorrecao(campos, meses);
  const erro = typeof conta === "string" ? conta : null;
  const r = typeof conta === "string" ? null : conta;
  const campoDoMes = (rotulo: string, chaveMes: keyof Campos, chaveAno: keyof Campos) => (
    <div className="ferramenta-campo">
      <span className="ferramenta-rotulo">{rotulo}</span>
      <div className="ferramenta-entrada">
        <Escolha rotulo={`${rotulo}: mês`} valor={campos[chaveMes]} opcoes={OPCOES_DE_MES} aoMudar={mudar(chaveMes)} />
        <input aria-label={`${rotulo}: ano`} type="text" inputMode="numeric" value={campos[chaveAno]} onChange={(e) => mudar(chaveAno)(e.target.value)} />
      </div>
    </div>
  );
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <CampoDeNumero rotulo="Valor" antes="R$" valor={campos.valor} aoMudar={mudar("valor")} />
        {campoDoMes("A partir de", "mesInicial", "anoInicial")}
        {campoDoMes("Até", "mesFinal", "anoFinal")}
      </form>
      <Resultado rotulo="Corrigido pelo IPCA" principal={r ? formatarReais(r.valor_corrigido) : ""} erro={erro}>
        {r ? (
          <dl className="ferramenta-numeros">
            <div>
              <dt>Inflação no período</dt>
              <dd>{formatarPorcentagem(r.variacao)}</dd>
            </div>
            <div>
              <dt>Meses de IPCA</dt>
              <dd>{r.meses}</dd>
            </div>
          </dl>
        ) : null}
        <MesDoIpca ultimo={ultimo} />
      </Resultado>
    </div>
  );
}

export function CorrecaoPelaInflacao() {
  const carga = useDadosDoBc();
  return (
    <ComDadosDoBc carga={carga}>
      {(dados) =>
        dados.ipca ? (
          <Calculadora meses={dados.ipca.meses} ultimo={dados.ipca.ultimo} />
        ) : (
          <p className="ferramenta-erro">Sem o IPCA agora.</p>
        )
      }
    </ComDadosDoBc>
  );
}
