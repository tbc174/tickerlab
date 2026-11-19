// Aba "Quem já se mexeu" do setor (linha 903, PR D): empresas (só pessoa jurídica) que entraram como sócias
// de empresas do setor, fundos sócios e companhias abertas com controlada nele. É movimento passado, não
// intenção de compra, e a tela diz isso à vista. O setor (CNAE e UF) vai no corpo do POST, nunca no endereço.
// O que a rota não dá (contagem por UF, aberturas por ano) a tela diz que não tem, em vez de inventar.
import { type FormEvent, useState } from "react";
import { Link } from "react-router";
import { Carregando } from "../pecas/Carregando";
import { Erro } from "../pecas/Erro";
import { Fontes, type FonteDaSecao } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import { Tabela, type Coluna } from "../pecas/Tabela";
import { NumerosDoSetor } from "./NumerosDoSetor";
import { Vazio } from "../pecas/Vazio";
import { formatarData } from "../formatar";
import type { CompradorDoSetorV1, CompradoresDoSetorV1, ExemploDeProvaV1 } from "../tipos";
import { usarPedido } from "../usarPedido";

const ROTA = "/v1/analista/setor/compradores";
const FRASE_DOS_SINAIS: Record<string, string> = {
  entrou_como_socio: "Entrou como sócia de empresa do setor",
  fundo_socio: "Fundo sócio de empresa do setor",
  controla_no_setor: "Companhia aberta com controlada no setor",
};
// o tipo na coluna "Tipo": o mesmo movimento da frase longa, em poucas palavras
const TIPO_DOS_SINAIS: Record<string, string> = {
  entrou_como_socio: "Entrou como sócia",
  fundo_socio: "Fundo sócio",
  controla_no_setor: "Controla no setor",
};
const DIGITOS_DO_CNAE = /^(\d{5}|\d{7})$/;
const UFS = /^[A-Za-z]{2}$/;
const MAXIMO_DE_ANOS = 10;

interface Pedido {
  cnae: string;
  uf: string | null;
  anos: number | null;
}

function rotuloDaRaiz(raiz: string | null): string {
  return raiz ? `CNPJ ${raiz}/…` : "Sem CNPJ";
}

function oQueFez(exemplo: ExemploDeProvaV1, sinal: string): string {
  const alvo = exemplo.empresa_do_setor.razao_social?.valor;
  const onde = exemplo.uf ? ` (${exemplo.uf})` : "";
  const nome = typeof alvo === "string" ? alvo : "empresa do setor";
  if (sinal === "controla_no_setor") return `Controla ${nome}${onde}`;
  const fim = exemplo.ainda_socio === false ? " · já saiu" : "";
  return `${nome}${onde}${fim}`;
}

function dataDoExemplo(exemplo: ExemploDeProvaV1): string | null {
  const valor = (exemplo.campos["data_entrada"] ?? exemplo.campos["referencia"])?.valor;
  return typeof valor === "string" && valor ? valor : null;
}

function quandoFoi(exemplo: ExemploDeProvaV1): string {
  const data = dataDoExemplo(exemplo);
  return data ? formatarData(data) : "Sem data";
}

/** A data da coluna "Quando": a do registro mais recente entre os exemplos de todos os sinais (a data vem em
 * ISO, então a comparação de texto é a de data). Sem nenhuma data nos exemplos, "Sem data". */
function quandoDoComprador(comprador: CompradorDoSetorV1): string {
  const datas = comprador.sinais.flatMap((sinal) =>
    (comprador.provas[sinal]?.exemplos ?? []).map(dataDoExemplo).filter((d): d is string => d !== null),
  );
  const maisRecente = datas.reduce<string | null>((a, d) => (a === null || d > a ? d : a), null);
  return maisRecente ? formatarData(maisRecente) : "Sem data";
}

/** O nome da fonte para quem lê: a atribuição que a resposta traz (o código interno só se ela faltar). */
function nomeDaFonte(codigo: string, fontes: FonteDaSecao[]): string {
  const atribuicao = fontes.find((f) => f.fonte === codigo)?.atribuicao.trim().replace(/\.$/, "");
  return atribuicao || codigo;
}

function fonteDoExemplo(exemplo: ExemploDeProvaV1, fontes: FonteDaSecao[]): string {
  const campo = exemplo.campos["data_entrada"] ?? Object.values(exemplo.campos)[0];
  return campo ? `${nomeDaFonte(campo.fonte, fontes)} · dado de ${formatarData(campo.publico_em)}` : "Sem fonte";
}

function ProvasDe({ comprador, fontes }: { comprador: CompradorDoSetorV1; fontes: FonteDaSecao[] }) {
  return (
    <ul>
      {comprador.sinais.map((sinal) => {
        const prova = comprador.provas[sinal];
        return (
          <li key={sinal}>
            <strong>{FRASE_DOS_SINAIS[sinal] ?? sinal}</strong>
            {prova ? <span className="apagado"> · {prova.quantas} no setor</span> : null}
            <ul>
              {(prova?.exemplos ?? []).map((exemplo, i) => (
                <li key={`${sinal}-${i}`}>
                  {oQueFez(exemplo, sinal)}
                  <span className="apagado">
                    {" "}
                    · {quandoFoi(exemplo)} · Fonte: {fonteDoExemplo(exemplo, fontes)}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}

const colunas = (fontes: FonteDaSecao[]): Coluna<CompradorDoSetorV1>[] => [
  {
    chave: "quem",
    titulo: "Quem",
    celula: (c) => (
      <>
        <strong>{String(c.razao_social?.valor ?? "Sem nome no retrato da Receita")}</strong>
        <br />
        <span className="apagado">{rotuloDaRaiz(c.raiz_do_cnpj)}</span>
      </>
    ),
  },
  {
    chave: "tipo",
    titulo: "Tipo",
    celula: (c) => c.sinais.map((s) => TIPO_DOS_SINAIS[s] ?? s).join(" · "),
  },
  { chave: "quando", titulo: "Quando", celula: quandoDoComprador },
  { chave: "o_que_fez", titulo: "O que fez no setor", celula: (c) => <ProvasDe comprador={c} fontes={fontes} /> },
];

function Resultado({ dados }: { dados: CompradoresDoSetorV1 }) {
  if (dados.estado === "nao_liberada") {
    return (
      <>
        <Vazio frase="Este dado ainda não foi liberado nesta base. Nada aqui diz que o setor não tem movimento." />
        <Limites itens={dados.limites} id="limites-quem-se-mexeu" />
      </>
    );
  }
  const setor = dados.setor;
  return (
    <>
      {setor ? (
        <p>
          <strong>CNAE {setor.cnae_principal}</strong>
          {setor.uf ? ` · ${setor.uf}` : " · Brasil"} · {setor.empresas_ativas} empresas ativas · desde{" "}
          {formatarData(setor.desde)} ({setor.anos} {setor.anos === 1 ? "ano" : "anos"})
          {dados.como_era_em ? <span className="apagado"> · retrato de {formatarData(dados.como_era_em)}</span> : null}
        </p>
      ) : null}
      {dados.sinais_nao_disponiveis.length > 0 ? (
        <p className="erro-do-app" role="note">
          Não consultados nesta base: {dados.sinais_nao_disponiveis.map((s) => FRASE_DOS_SINAIS[s] ?? s).join("; ")}.
          A lista não diz nada sobre eles.
        </p>
      ) : null}
      {dados.cortada ? (
        <p className="apagado" role="note">
          Mostrando os primeiros de {dados.total_de_compradores}. Estreite o setor para ver os demais.
        </p>
      ) : null}
      <section className="quadro-como-ler" aria-labelledby="como-ler-quem-se-mexeu">
        <h2 id="como-ler-quem-se-mexeu">Como ler esta lista</h2>
        <ul>
          <li>
            Cada linha é movimento passado, não intenção de compra: quem aparece já fez algo no setor, não disse que quer
            comprar ou vender. Holding de família e reorganização também entram, e entrar como sócia não é aquisição.
          </li>
          <li>
            A ordem é pelo número de tipos de movimento (entrou como sócia, fundo sócio, controla no setor) e, depois, pelo
            de entradas como sócia: não é uma classificação de quem compraria.
          </li>
          <li>
            A coluna Quando traz a data do registro mais recente entre os exemplos de cada empresa; cada tipo mostra só
            alguns exemplos, os mais recentes.
          </li>
          <li>Só pessoa jurídica: MEI, empresário individual e sócio pessoa física não entram.</li>
        </ul>
      </section>
      <Tabela
        legenda="Quem já se mexeu neste setor"
        colunas={colunas(dados.fontes)}
        linhas={dados.compradores}
        chaveDaLinha={(c) => c.raiz_do_cnpj ?? String(c.razao_social?.valor ?? "")}
        vazio="Nenhuma empresa com esse movimento no setor e no período pedidos."
      />
      <section className="secao-do-relatorio" aria-labelledby="nao-temos-quem-se-mexeu">
        <h2 id="nao-temos-quem-se-mexeu">O que não temos aqui</h2>
        <p>
          Esta lista mostra só o que já aconteceu: não diz quem pretende comprar nem vender.{" "}
          Para ver as empresas do setor uma a uma, <Link to="/encontrar-empresas">encontre empresas pelo setor, estado ou tamanho</Link>.
        </p>
      </section>
      <Fontes fontes={dados.fontes} id="fontes-quem-se-mexeu" />
      <Limites itens={dados.limites} id="limites-quem-se-mexeu" />
    </>
  );
}

function Consulta({ pedido }: { pedido: Pedido }) {
  const resposta = usarPedido<CompradoresDoSetorV1>(ROTA, {}, pedido);
  if (resposta.estado === "carregando") return <Carregando tipo="painel" rotulo="Procurando quem já se mexeu no setor…" />;
  if (resposta.estado === "erro") return <Erro erro={resposta.erro} />;
  return <Resultado dados={resposta.dados} />;
}

function ConsultaCompleta({ pedido }: { pedido: Pedido }) {
  return (
    <>
      <NumerosDoSetor cnae={pedido.cnae} uf={pedido.uf} />
      <Consulta pedido={pedido} />
    </>
  );
}

export function QuemSeMexeuNoSetor() {
  const [cnae, setCnae] = useState("");
  const [uf, setUf] = useState("");
  const [anos, setAnos] = useState("");
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const buscar = (evento: FormEvent) => {
    evento.preventDefault();
    const numero = anos.trim() === "" ? null : Number(anos);
    if (!DIGITOS_DO_CNAE.test(cnae.trim())) return setAviso("Use o CNAE com 5 ou 7 dígitos.");
    if (uf.trim() !== "" && !UFS.test(uf.trim())) return setAviso("A UF tem 2 letras.");
    if (numero !== null && (!Number.isInteger(numero) || numero < 1 || numero > MAXIMO_DE_ANOS))
      return setAviso(`Os anos vão de 1 a ${MAXIMO_DE_ANOS}.`);
    setAviso(null);
    setPedido({ cnae: cnae.trim(), uf: uf.trim() === "" ? null : uf.trim().toUpperCase(), anos: numero });
  };

  return (
    <>
      <p className="apagado">
        Empresas (só pessoa jurídica) que já entraram como sócias de empresas do setor, fundos sócios e companhias
        abertas com controlada nele. É movimento passado, não intenção de compra.
      </p>
      <form className="formulario-do-app" onSubmit={buscar}>
        <div className="campos-do-formulario">
          <label>
            <span>CNAE</span>
            <input value={cnae} inputMode="numeric" onChange={(ev) => setCnae(ev.target.value)} />
          </label>
          <label>
            <span>UF (opcional)</span>
            <input value={uf} maxLength={2} onChange={(ev) => setUf(ev.target.value)} />
          </label>
          <label>
            <span>Anos (1 a {MAXIMO_DE_ANOS})</span>
            <input value={anos} inputMode="numeric" onChange={(ev) => setAnos(ev.target.value)} />
          </label>
        </div>
        <button type="submit" className="botao">
          Ver quem já se mexeu
        </button>
      </form>
      {aviso ? (
        <p className="erro-do-app" role="alert">
          {aviso}
        </p>
      ) : null}
      {pedido ? <ConsultaCompleta key={JSON.stringify(pedido)} pedido={pedido} /> : null}
    </>
  );
}
