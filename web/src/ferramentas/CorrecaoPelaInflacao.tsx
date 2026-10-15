// Correção pela inflação (contas/inflacao.ts, a mesma conta do Python), com o IPCA mensal do Banco
// Central desde o Plano Real. v2: no mesmo período, quanto o valor teria virado na poupança e no CDI,
// o gráfico das três linhas e em quantos anos a poupança perdeu para a inflação.
import { useEffect } from "react";
import { Compartilhar } from "./Compartilhar";
import { CampoDeNumero, Escolha, Resultado } from "./campos";
import { ComDadosDoBc, MesDoIpca } from "./Carregando";
import { type Correcao, type Meses, anosAbaixo, corrigir, evolucao } from "./contas/inflacao";
import { type DadosDoBc, useDadosDoBc } from "./dados";
import { useCamposNoEndereco } from "./endereco";
import { formatarPorcentagem, formatarReais, formatarReaisCurto, lerNumero } from "./numeros";
import { SERIES } from "../graficos/cores";
import { GraficoDoTempo } from "../graficos/GraficoDoTempo";

const NOMES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const OPCOES_DE_MES: [string, string][] = NOMES.map((nome, i) => [String(i + 1).padStart(2, "0"), nome]);
const ANOS_PARA_TRAS = 10; // o exemplo: um valor de 10 anos atrás
const ANOS_DA_COMPARACAO = 10; // "a poupança perdeu para a inflação em N dos últimos 10 anos"

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

/** O mesmo valor corrigido por outra série mensal no mesmo período, ou null se ela não cobre. */
function noMesmoPeriodo(valor: number, inicio: string, fim: string, serie: Meses | undefined): number[] | null {
  if (!serie?.length) return null;
  try {
    return evolucao(valor, inicio, fim, serie);
  } catch {
    return null;
  }
}

/** "jan/15": o rótulo do mês no eixo e na dica. */
const rotuloDoMesDaSerie = (iso: string) => `${NOMES[Number(iso.slice(5, 7)) - 1]}/${iso.slice(2, 4)}`;

function Calculadora({ dados, meses, ultimo }: { dados: DadosDoBc; meses: Meses; ultimo: string }) {
  const [campos, mudar, definir] = useCamposNoEndereco(EXEMPLO_DA_CORRECAO);
  // o exemplo passa a ir até o último IPCA divulgado, começando 10 anos antes (se o endereço não
  // trouxer outro período)
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("anoFinal")) return;
    const [ano, numero] = ultimo.split("-");
    definir((antes) => ({
      ...antes,
      mesFinal: numero,
      anoFinal: ano,
      mesInicial: numero,
      anoInicial: String(Number(ano) - ANOS_PARA_TRAS),
    }));
  }, [ultimo, definir]);
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
      {r ? (
        <Comparacao
          dados={dados}
          valor={lerNumero(campos.valor) ?? 0}
          inicio={mes(campos.mesInicial, campos.anoInicial)}
          fim={mes(campos.mesFinal, campos.anoFinal)}
          ipca={meses}
          corrigido={r.valor_corrigido}
        />
      ) : null}
    </div>
  );
}

function Comparacao({
  dados,
  valor,
  inicio,
  fim,
  ipca,
  corrigido,
}: {
  dados: DadosDoBc;
  valor: number;
  inicio: string;
  fim: string;
  ipca: Meses;
  corrigido: number;
}) {
  const linhaDoIpca = noMesmoPeriodo(valor, inicio, fim, ipca);
  const poupanca = noMesmoPeriodo(valor, inicio, fim, dados.poupanca_mensal?.meses);
  const cdi = noMesmoPeriodo(valor, inicio, fim, dados.cdi_mensal?.meses);
  if (!linhaDoIpca) return null;
  const mesesDoPeriodo = ipca.filter(([m]) => inicio <= m && m <= fim).map(([m]) => m);
  const series = [
    { nome: "Só repondo a inflação (IPCA)", cor: SERIES[2], valores: linhaDoIpca },
    ...(poupanca ? [{ nome: "Na poupança", cor: SERIES[1], valores: poupanca }] : []),
    ...(cdi ? [{ nome: "No CDI", cor: SERIES[0], valores: cdi }] : []),
  ];
  const [anoDoUltimo, mesDoUltimo] = ipca[ipca.length - 1][0].split("-").map(Number);
  const ultimoAnoCompleto = mesDoUltimo === 12 ? anoDoUltimo : anoDoUltimo - 1;
  const [perdeu, comparados] = dados.poupanca_mensal
    ? anosAbaixo(dados.poupanca_mensal.meses, ipca, ultimoAnoCompleto, ANOS_DA_COMPARACAO)
    : [0, 0];
  // eixo: o índice do ponto (0 = o começo de `inicio`); marca em janeiro, a cada ano ou a cada 2
  const passoDeAnos = mesesDoPeriodo.length > 8 * 12 ? 2 : 1;
  const marcas = [0, ...mesesDoPeriodo.flatMap((m, i) => (m.endsWith("-01") && Number(m.slice(0, 4)) % passoDeAnos === 0 ? [i + 1] : []))];
  const rotulo = (i: number) => (i === 0 ? "início" : rotuloDoMesDaSerie(mesesDoPeriodo[i - 1]));
  return (
    <div className="ferramenta-largo">
      <dl className="ferramenta-numeros">
        {poupanca ? (
          <div>
            <dt>Na poupança, no mesmo período, teria virado</dt>
            <dd>{formatarReais(poupanca[poupanca.length - 1])}</dd>
          </div>
        ) : null}
        {cdi ? (
          <div>
            <dt>A 100% do CDI, antes do IR, teria virado</dt>
            <dd>{formatarReais(cdi[cdi.length - 1])}</dd>
          </div>
        ) : null}
      </dl>
      {comparados ? (
        <p className="ferramenta-destaque">
          Nos últimos {comparados} anos completos, a poupança perdeu para a inflação em {perdeu} dos {comparados}{" "}
          (o rendimento do ano ficou abaixo do IPCA do ano).
        </p>
      ) : null}
      <GraficoDoTempo
        titulo="O valor mês a mês: só repondo a inflação, na poupança e no CDI"
        meses={linhaDoIpca.map((_, i) => i)}
        series={series}
        eixoX={{ marcas, rotulo, dica: rotulo }}
        formatarValor={formatarReais}
        formatarEixo={formatarReaisCurto}
      />
      <Compartilhar
        resultado={`${formatarReais(valor)} de ${rotuloDoMesDaSerie(inicio)} equivalem a ${formatarReais(corrigido)} em ${rotuloDoMesDaSerie(fim)} pelo IPCA${poupanca ? `; na poupança teriam virado ${formatarReais(poupanca[poupanca.length - 1])}` : ""}`}
      />
    </div>
  );
}

export function CorrecaoPelaInflacao() {
  const carga = useDadosDoBc();
  return (
    <ComDadosDoBc carga={carga}>
      {(dados) =>
        dados.ipca ? (
          <Calculadora dados={dados} meses={dados.ipca.meses} ultimo={dados.ipca.ultimo} />
        ) : (
          <p className="ferramenta-erro">Sem o IPCA agora.</p>
        )
      }
    </ComDadosDoBc>
  );
}
