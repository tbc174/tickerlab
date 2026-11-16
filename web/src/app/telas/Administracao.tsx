// A Administração no app novo (linha 955, PR 2): as organizações da API por chave, só para ver. Quem entra é
// decidido no servidor, a cada pedido (src/api_v1/administracao.py): para quem não é administrador a API
// responde o 404 de um endereço que não existe, e a tela mostra "página não encontrada". O `administrador`
// de /v1/eu só poupa o pedido e esconde o atalho do menu: não autoriza nada.
// A tela não liga nem muda nada: conceder direito, vincular conta e ligar "pessoa na tela" são do dono, pelo
// script. De uma chave aparece só o prefixo (a API nem manda o valor).
import { type ReactNode, useId, useState } from "react";
import { ENDERECO_DA_ADMINISTRACAO, TITULO_DA_ADMINISTRACAO } from "../administracao";
import { linkDoClassico } from "../classico";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import { Cabecalho } from "../pecas/Cabecalho";
import { Carregando } from "../pecas/Carregando";
import { CartaoDeNumero } from "../pecas/CartaoDeNumero";
import { Erro } from "../pecas/Erro";
import { Selo, type TomDoSelo } from "../pecas/Selo";
import { type Coluna, Tabela } from "../pecas/Tabela";
import { Vazio } from "../pecas/Vazio";
import type {
  ChaveDaOrganizacaoV1,
  ConjuntoDesligadoV1,
  DireitoEmVigorV1,
  OrganizacaoDaListaV1,
  OrganizacoesV1,
  PainelDaOrganizacaoV1,
} from "../tiposDaAdministracao";
import { usarPedido } from "../usarPedido";
import { NaoEncontrada } from "./Avisos";

const SEM_PARAMETROS = {};
const ROTA_DAS_ORGANIZACOES = "/v1/admin/organizacoes";
const ROTA_DA_ORGANIZACAO = "/v1/admin/organizacao";
// o 404 do painel: a organização saiu, ou o servidor deixou de reconhecer a conta como administradora
const ORGANIZACAO_NAO_ENCONTRADA =
  "Organização não encontrada. Ela pode ter sido apagada, ou a sua conta deixou de ser administradora.";

const inteiro = (n: number) => n.toLocaleString("pt-BR");
const plural = (n: number, um: string, varios: string) => `${inteiro(n)} ${n === 1 ? um : varios}`;

// os rótulos do que a API manda em código; código que a tela ainda não conhece aparece como veio
const ESTADOS_DA_CHAVE: Record<string, { rotulo: string; tom: TomDoSelo }> = {
  ativa: { rotulo: "Ativa", tom: "bom" },
  de_saida: { rotulo: "De saída", tom: "atencao" },
  expirada: { rotulo: "Expirada", tom: "neutro" },
  revogada: { rotulo: "Revogada", tom: "neutro" },
};
const FINALIDADES: Record<string, string> = { analise: "Análise", credito: "Crédito" };
const MOTIVOS_DO_DESLIGADO: Record<string, string> = {
  sem_contrato: "Sem contrato",
  suspenso_para_todos: "Suspenso para todos",
};

const finalidade = (codigo: string) => FINALIDADES[codigo] ?? codigo;

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="secao-do-relatorio" aria-labelledby={id}>
      <h3 id={id}>{titulo}</h3>
      {children}
    </section>
  );
}

// --- as tabelas do painel ---------------------------------------------------------------------

const COLUNAS_DAS_CHAVES: Coluna<ChaveDaOrganizacaoV1>[] = [
  { chave: "prefixo", titulo: "Prefixo", celula: (chave) => <code>{chave.prefixo}</code> },
  {
    chave: "estado",
    titulo: "Estado",
    celula: (chave) => {
      const estado = ESTADOS_DA_CHAVE[chave.estado];
      return <Selo tom={estado?.tom}>{estado?.rotulo ?? chave.estado}</Selo>;
    },
  },
  { chave: "criada", titulo: "Criada em", celula: (chave) => formatarData(chave.criada_em) },
  {
    chave: "expira",
    titulo: "Expira em",
    celula: (chave) => (chave.expira_em ? formatarData(chave.expira_em) : "Sem prazo"),
  },
  {
    chave: "uso",
    titulo: "Último uso",
    celula: (chave) => (chave.ultimo_uso ? formatarData(chave.ultimo_uso) : "Nunca usada"),
  },
];

const COLUNAS_DOS_DIREITOS: Coluna<DireitoEmVigorV1>[] = [
  { chave: "conjunto", titulo: "Conjunto", celula: (direito) => <code>{direito.conjunto}</code> },
  { chave: "finalidade", titulo: "Finalidade", celula: (direito) => finalidade(direito.finalidade) },
  { chave: "desde", titulo: "Desde", celula: (direito) => formatarData(direito.vigente_desde) },
  {
    chave: "ate",
    titulo: "Até",
    celula: (direito) => (direito.vigente_ate ? formatarData(direito.vigente_ate) : "Sem prazo"),
  },
];

const COLUNAS_DOS_DESLIGADOS: Coluna<ConjuntoDesligadoV1>[] = [
  { chave: "conjunto", titulo: "Conjunto", celula: (item) => <code>{item.conjunto}</code> },
  { chave: "finalidade", titulo: "Finalidade", celula: (item) => finalidade(item.finalidade) },
  { chave: "motivo", titulo: "Motivo", celula: (item) => MOTIVOS_DO_DESLIGADO[item.motivo] ?? item.motivo },
];

const oPar = (item: { conjunto: string; finalidade: string }) => `${item.conjunto}/${item.finalidade}`;

// --- o painel de uma organização --------------------------------------------------------------

function Numeros({ painel }: { painel: PainelDaOrganizacaoV1 }) {
  const { limites, consumo } = painel;
  return (
    <div className="numeros">
      <CartaoDeNumero
        rotulo="Chaves ativas"
        valor={`${inteiro(painel.chaves_ativas)} de ${inteiro(limites.chaves_ativas)}`}
        detalhe="limite do plano"
        principal
      />
      <CartaoDeNumero
        rotulo="Direitos em vigor"
        valor={inteiro(painel.direitos.length)}
        detalhe={`${plural(painel.ainda_desligado.length, "ainda desligado", "ainda desligados")}`}
      />
      <CartaoDeNumero
        rotulo="Pedidos no mês"
        valor={inteiro(consumo.pedidos)}
        detalhe={`de ${inteiro(limites.pedidos_por_mes)} do plano`}
      />
      <CartaoDeNumero rotulo="Pedidos negados" valor={inteiro(consumo.negados)} detalhe="no mês" />
      <CartaoDeNumero
        rotulo="Linhas no mês"
        valor={inteiro(consumo.linhas)}
        detalhe={`até ${inteiro(limites.linhas_por_resposta)} por resposta`}
      />
    </div>
  );
}

function Situacao({ painel }: { painel: PainelDaOrganizacaoV1 }) {
  if (painel.suspensa_em === null) return null;
  return (
    <p role="note">
      Suspensa em {formatarData(painel.suspensa_em)}. Motivo: {painel.motivo_da_suspensao ?? "sem motivo registrado."}
    </p>
  );
}

function EquipeNaTela({ painel }: { painel: PainelDaOrganizacaoV1 }) {
  return (
    <Secao titulo="Equipe na tela">
      <p>
        Pessoa na tela:{" "}
        <Selo tom={painel.pessoa_na_tela ? "atencao" : "neutro"}>{painel.pessoa_na_tela ? "Ligada" : "Desligada"}</Selo>
      </p>
      <p>{plural(painel.membros, "conta vinculada", "contas vinculadas")} a esta organização.</p>
      <p className="apagado">
        Aqui é só o estado. Ligar a permissão e vincular uma conta é só do dono, pelo script.
      </p>
    </Secao>
  );
}

function PainelPronto({ painel }: { painel: PainelDaOrganizacaoV1 }) {
  const id = useId();
  const suspensa = painel.suspensa_em !== null;
  return (
    <section aria-labelledby={id}>
      <div className="cabecalho-titulo">
        <h2 id={id}>{painel.nome}</h2>
        <Selo tom={suspensa ? "alerta" : "bom"}>{suspensa ? "Suspensa" : "Ativa"}</Selo>
        <Selo>Plano {painel.nome_do_plano}</Selo>
      </div>
      <p className="apagado">
        {painel.cnpj ? `CNPJ ${painel.cnpj} · ` : ""}Criada em {formatarData(painel.criada_em)} · até{" "}
        {inteiro(painel.limites.pedidos_por_minuto)} pedidos por minuto
      </p>
      <Situacao painel={painel} />
      <Numeros painel={painel} />
      <Secao titulo="Chaves">
        <Tabela
          legenda="Chaves da organização"
          legendaEscondida
          colunas={COLUNAS_DAS_CHAVES}
          linhas={painel.chaves}
          chaveDaLinha={(chave) => chave.id}
          vazio="Nenhuma chave emitida."
        />
        <p className="apagado">
          O valor de uma chave aparece uma única vez, para quem a emite. Aqui fica só o prefixo.
        </p>
      </Secao>
      <Secao titulo="Direitos em vigor">
        <Tabela
          legenda="Direitos em vigor"
          legendaEscondida
          colunas={COLUNAS_DOS_DIREITOS}
          linhas={painel.direitos}
          chaveDaLinha={oPar}
          vazio="Nenhum direito em vigor."
        />
      </Secao>
      <Secao titulo="Ainda desligado">
        <Tabela
          legenda="Ainda desligado"
          legendaEscondida
          colunas={COLUNAS_DOS_DESLIGADOS}
          linhas={painel.ainda_desligado}
          chaveDaLinha={oPar}
          vazio="Nada desligado: o contrato cobre tudo o que a API por chave oferece."
        />
        <p className="apagado">
          A lista compara o que a API por chave oferece (o par conjunto e finalidade) com o contrato da organização e
          com a suspensão para todos. Não olha se a tabela do conjunto está pronta nem as marcas da fonte: um conjunto
          fora da lista ainda pode ser negado. Quem liga um direito é o dono, pelo script.
        </p>
      </Secao>
      <EquipeNaTela painel={painel} />
    </section>
  );
}

function Painel({ id }: { id: string }) {
  const pedido = usarPedido<PainelDaOrganizacaoV1>(ROTA_DA_ORGANIZACAO, { id });
  if (pedido.estado === "carregando") return <Carregando tipo="painel" rotulo="Carregando a organização…" />;
  if (pedido.estado === "erro") {
    return <Erro erro={pedido.erro.tipo === "nao-encontrado" ? ORGANIZACAO_NAO_ENCONTRADA : pedido.erro} />;
  }
  return <PainelPronto painel={pedido.dados} />;
}

// --- a tela -----------------------------------------------------------------------------------

function Organizacoes({ organizacoes }: { organizacoes: OrganizacaoDaListaV1[] }) {
  const [escolhida, setEscolhida] = useState(organizacoes[0]?.id ?? "");
  if (organizacoes.length === 0) {
    return <Vazio frase="Nenhuma organização cadastrada. Quem cria uma organização é o dono, pelo script." />;
  }
  return (
    <>
      {organizacoes.length > 1 ? (
        <div className="formulario-do-app">
          <div className="campos-do-formulario">
            <label>
              <span>Organização</span>
              <select value={escolhida} onChange={(ev) => setEscolhida(ev.target.value)}>
                {organizacoes.map((organizacao) => (
                  <option key={organizacao.id} value={organizacao.id}>
                    {organizacao.nome}
                    {organizacao.suspensa ? " (suspensa)" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      ) : null}
      <Painel key={escolhida} id={escolhida} />
    </>
  );
}

function AdministracaoAberta() {
  const lista = usarPedido<OrganizacoesV1>(ROTA_DAS_ORGANIZACOES, SEM_PARAMETROS);
  // o servidor disse que este endereço não existe para esta conta: a tela diz o mesmo
  if (lista.estado === "erro" && lista.erro.tipo === "nao-encontrado") return <NaoEncontrada />;
  return (
    <section>
      <Cabecalho
        titulo={TITULO_DA_ADMINISTRACAO}
        descricao="As organizações da API por chave: situação, consumo do mês, chaves e o que o contrato liga. Só para ver."
        acoes={
          <a className="botao pequeno" href={linkDoClassico(ENDERECO_DA_ADMINISTRACAO)}>
            Abrir a Administração antiga
          </a>
        }
      />
      <p className="apagado">
        As contas do app, o registro de ações, os eventos de cobrança e o acervo continuam na Administração antiga,
        assim como emitir, trocar e revogar chaves.
      </p>
      {lista.estado === "carregando" && <Carregando tipo="lista" rotulo="Carregando as organizações…" />}
      {lista.estado === "erro" && <Erro erro={lista.erro} />}
      {lista.estado === "pronto" && <Organizacoes organizacoes={lista.dados.organizacoes} />}
    </section>
  );
}

export function Administracao() {
  const conta = useConta();
  // só poupa o pedido: quem recusa de verdade é o servidor, a cada pedido
  if (!conta?.eu?.administrador) return <NaoEncontrada />;
  return <AdministracaoAberta />;
}
