// Aba "Quem já se mexeu" do setor (linha 903, PR D): empresas (só pessoa jurídica) que entraram como sócias
// de empresas do setor, fundos sócios e companhias abertas com controlada nele. É movimento passado, não
// intenção de compra, e a tela diz isso à vista. O setor (CNAE e UF) vai no corpo do POST, nunca no endereço.
// O que a rota não dá (contagem por UF, aberturas por ano) a tela diz que não tem, em vez de inventar.
// O setor se escolhe pelo nome da atividade (a tabela de CNAEs da Receita) ou pelo código; a UF e os anos são
// listas prontas. A ficha da empresa abre esta aba com o CNAE dela no estado da navegação, e a busca já sai.
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";
import { type AtividadeDoCnae, cnaeComPontuacao, cnaeDigitado, nomeDoCnae, rotuloDoSetor } from "../buscaDeCnaes";
import { useEstadoDaNavegacaoUmaVez } from "../estadoDaNavegacao";
import { CampoDoSetor, useAtividadesDoCnae } from "../pecas/CampoDoSetor";
import { Carregando } from "../pecas/Carregando";
import { Erro } from "../pecas/Erro";
import { Fontes, type FonteDaSecao } from "../pecas/Fonte";
import { Limites } from "../pecas/Limites";
import { Tabela, type Coluna } from "../pecas/Tabela";
import { NumerosDoSetor } from "./NumerosDoSetor";
import { Vazio } from "../pecas/Vazio";
import { formatarData } from "../formatar";
import type { CompradorDoSetorV1, CompradoresDoSetorV1, ExemploDeProvaV1 } from "../tipos";
import { UFS } from "../ufs";
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
// a janela de anos: as opções da lista e o padrão (o mesmo da API, ANOS_PADRAO em
// src/api_externa/conjuntos/compradores.py; o máximo dela é 10)
const OPCOES_DE_ANOS = [1, 3, 5, 10];
const ANOS_PADRAO = 3;
const AVISO_DO_SETOR = "Escolha uma atividade da lista ou digite o CNAE com 5 ou 7 dígitos.";
const CNAE_DA_FICHA = /^\d{7}$/;

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

function Resultado({ dados, atividades }: { dados: CompradoresDoSetorV1; atividades: AtividadeDoCnae[] | null }) {
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
          <strong>{rotuloDoSetor(setor.cnae_principal, nomeDoCnae(atividades, setor.cnae_principal))}</strong>
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

function Consulta({ pedido, atividades }: { pedido: Pedido; atividades: AtividadeDoCnae[] | null }) {
  const resposta = usarPedido<CompradoresDoSetorV1>(ROTA, {}, pedido);
  if (resposta.estado === "carregando") return <Carregando tipo="painel" rotulo="Procurando quem já se mexeu no setor…" />;
  if (resposta.estado === "erro") return <Erro erro={resposta.erro} />;
  return <Resultado dados={resposta.dados} atividades={atividades} />;
}

function ConsultaCompleta({ pedido, atividades }: { pedido: Pedido; atividades: AtividadeDoCnae[] | null }) {
  return (
    <>
      <NumerosDoSetor cnae={pedido.cnae} uf={pedido.uf} nome={nomeDoCnae(atividades, pedido.cnae)} />
      <Consulta pedido={pedido} atividades={atividades} />
    </>
  );
}

/** O CNAE que a ficha da empresa mandou pelo estado da navegação ({ quemSeMexeu: { cnae } }), ou null. */
function cnaeDaNavegacao(estado: unknown): string | null {
  if (typeof estado !== "object" || estado === null || !("quemSeMexeu" in estado)) return null;
  const { quemSeMexeu } = estado;
  if (typeof quemSeMexeu !== "object" || quemSeMexeu === null || !("cnae" in quemSeMexeu)) return null;
  const { cnae } = quemSeMexeu;
  return typeof cnae === "string" && CNAE_DA_FICHA.test(cnae) ? cnae : null;
}

/** A linha embaixo do campo: o código da atividade escolhida ou, para um código digitado, o nome dele. */
function dicaDoSetor(escolhida: AtividadeDoCnae | null, texto: string, atividades: AtividadeDoCnae[] | null): string {
  if (escolhida) return `CNAE ${cnaeComPontuacao(escolhida.codigo)}`;
  const digitado = cnaeDigitado(texto);
  if (digitado === null) return "";
  const nome = nomeDoCnae(atividades, digitado);
  if (nome) return nome;
  return digitado.length === 5 ? "Classe do CNAE: entram todas as atividades dela." : "";
}

function Periodo({ anos, aoMudar }: { anos: number; aoMudar(anos: number): void }) {
  return (
    <label>
      <span>Período</span>
      <select value={anos} onChange={(ev) => aoMudar(Number(ev.target.value))}>
        {OPCOES_DE_ANOS.map((n) => (
          <option key={n} value={n}>
            {n === 1 ? "Último ano" : `Últimos ${n} anos`}
          </option>
        ))}
      </select>
    </label>
  );
}

function Estado({ uf, aoMudar }: { uf: string; aoMudar(uf: string): void }) {
  return (
    <label>
      <span>Estado</span>
      <select value={uf} onChange={(ev) => aoMudar(ev.target.value)}>
        <option value="">Brasil inteiro</option>
        {UFS.map((sigla) => (
          <option key={sigla} value={sigla}>
            {sigla}
          </option>
        ))}
      </select>
    </label>
  );
}

export function QuemSeMexeuNoSetor() {
  const daFicha = cnaeDaNavegacao(useEstadoDaNavegacaoUmaVez());
  const atividades = useAtividadesDoCnae();
  const [texto, setTexto] = useState(daFicha ? cnaeComPontuacao(daFicha) : "");
  const [escolhida, setEscolhida] = useState<AtividadeDoCnae | null>(null);
  const [uf, setUf] = useState("");
  const [anos, setAnos] = useState(ANOS_PADRAO);
  const [pedido, setPedido] = useState<Pedido | null>(daFicha ? { cnae: daFicha, uf: null, anos: ANOS_PADRAO } : null);
  const [aviso, setAviso] = useState<string | null>(null);

  // quem veio da ficha vê o nome da atividade no campo assim que a lista chega (antes, o código); só na
  // chegada da lista: depois, o campo é de quem digita
  useEffect(() => {
    const atividade = daFicha ? atividades?.find((a) => a.codigo === daFicha) : undefined;
    if (atividade) {
      setEscolhida(atividade);
      setTexto(atividade.nome);
    }
  }, [atividades]);

  const digitar = (novo: string) => {
    setTexto(novo);
    setEscolhida(null);
  };
  const escolher = (atividade: AtividadeDoCnae) => {
    setTexto(atividade.nome);
    setEscolhida(atividade);
  };
  const buscar = (evento: FormEvent) => {
    evento.preventDefault();
    const cnae = escolhida?.codigo ?? cnaeDigitado(texto);
    if (cnae === null) return setAviso(AVISO_DO_SETOR);
    setAviso(null);
    setPedido({ cnae, uf: uf === "" ? null : uf, anos });
  };

  return (
    <>
      <p className="apagado">
        Empresas (só pessoa jurídica) que já entraram como sócias de empresas do setor, fundos sócios e companhias
        abertas com controlada nele. É movimento passado, não intenção de compra.
      </p>
      <form className="formulario-do-app" onSubmit={buscar}>
        <div className="campos-do-formulario campos-do-setor">
          <CampoDoSetor
            rotulo="Setor"
            texto={texto}
            atividades={atividades}
            dica={dicaDoSetor(escolhida, texto, atividades)}
            aoDigitar={digitar}
            aoEscolher={escolher}
          />
          <Estado uf={uf} aoMudar={setUf} />
          <Periodo anos={anos} aoMudar={setAnos} />
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
      {pedido ? <ConsultaCompleta key={JSON.stringify(pedido)} pedido={pedido} atividades={atividades} /> : null}
    </>
  );
}
