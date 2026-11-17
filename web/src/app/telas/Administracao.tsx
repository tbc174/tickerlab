// A Administração no app novo (linha 955, PRs 2 e 3): as organizações da API por chave, com as ações de
// criar, suspender e reativar a organização e de emitir, trocar e revogar chaves. Quem entra e o que cada
// ação pode é decidido no servidor, a cada pedido (src/api_v1/administracao.py): para quem não é
// administrador a API responde o 404 de um endereço que não existe, e a tela mostra "página não encontrada".
// O `administrador` de /v1/eu só poupa o pedido e esconde o atalho do menu: não autoriza nada.
// A tela não liga permissão nem direito: conceder direito, vincular conta e ligar "pessoa na tela" são do
// dono, pelo script. De uma chave aparece só o prefixo; o valor, só na caixa de quem acabou de emitir.
import { type ReactNode, useId, useState } from "react";
import { ENDERECO_DA_ADMINISTRACAO, TITULO_DA_ADMINISTRACAO } from "../administracao";
import { mudar } from "../api";
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
  ChaveNovaV1,
  ConjuntoDesligadoV1,
  DireitoEmVigorV1,
  MudouV1,
  OrganizacaoDaListaV1,
  OrganizacoesV1,
  PainelDaOrganizacaoV1,
} from "../tiposDaAdministracao";
import {
  Aviso,
  ChaveNova,
  Confirmacao,
  Falha,
  NovaOrganizacao,
  ROTA_DAS_ORGANIZACOES,
  useAcao,
  usarLeitura,
} from "./AcoesDaAdministracao";
import { NaoEncontrada } from "./Avisos";

const SEM_PARAMETROS = {};
const ROTA_DA_ORGANIZACAO = "/v1/admin/organizacao";
const ROTA_DE_SUSPENDER = "/v1/admin/organizacao/suspender";
const ROTA_DE_REATIVAR = "/v1/admin/organizacao/reativar";
const ROTA_DE_EMITIR = "/v1/admin/chaves/emitir";
const ROTA_DE_TROCAR = "/v1/admin/chaves/rotacionar";
const ROTA_DE_REVOGAR = "/v1/admin/chaves/revogar";
const NADA_MUDOU = "Nada mudou: já estava assim.";
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

const MOTIVOS_DA_SUSPENSAO: Record<string, string> = {
  contrato: "Contrato",
  pagamento: "Pagamento",
  abuso: "Abuso",
  pedido_do_cliente: "Pedido do cliente",
  fonte: "Fonte",
};
// só estas ocupam vaga e ainda entram: as outras não têm o que trocar nem revogar
const ESTADOS_QUE_TROCAM = new Set(["ativa"]);
const ESTADOS_QUE_REVOGAM = new Set(["ativa", "de_saida"]);

const finalidade = (codigo: string) => FINALIDADES[codigo] ?? codigo;
const motivoDaSuspensao = (codigo: string) => MOTIVOS_DA_SUSPENSAO[codigo] ?? codigo;

/** O que o painel sabe fazer; cada uma vira um pedido que o servidor confere de novo. */
interface AcoesDoPainel {
  ocupada: boolean;
  /** Há uma chave nova ainda na tela: emitir ou trocar outra apagaria, sem aviso, o valor não copiado. */
  chaveNaTela: boolean;
  emitir(): void;
  trocar(chave: ChaveDaOrganizacaoV1): void;
  revogar(chave: ChaveDaOrganizacaoV1): void;
  suspender(motivo: string): void;
  reativar(): void;
}

/** A ação que espera o "sim" de quem clicou. */
type Pendente =
  | { acao: "trocar" | "revogar"; chave: ChaveDaOrganizacaoV1 }
  | { acao: "suspender"; motivo: string }
  | { acao: "reativar" }
  | null;

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

const COLUNAS_DOS_DADOS_DA_CHAVE: Coluna<ChaveDaOrganizacaoV1>[] = [
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

/** As colunas das chaves com a de ações: os botões só abrem a pergunta; quem faz é o "sim" dela. */
function colunasDasChaves(
  ocupada: boolean,
  semChaveNova: boolean,
  pedir: (pendente: Pendente) => void,
): Coluna<ChaveDaOrganizacaoV1>[] {
  const acoes: Coluna<ChaveDaOrganizacaoV1> = {
    chave: "acoes",
    titulo: "Ações",
    celula: (chave) => (
      <span className="acoes-da-administracao">
        {ESTADOS_QUE_TROCAM.has(chave.estado) ? (
          <button
            type="button"
            className="botao pequeno"
            disabled={semChaveNova}
            aria-label={`Trocar a chave ${chave.prefixo}`}
            onClick={() => pedir({ acao: "trocar", chave })}
          >
            Trocar
          </button>
        ) : null}
        {ESTADOS_QUE_REVOGAM.has(chave.estado) ? (
          <button
            type="button"
            className="botao pequeno"
            disabled={ocupada}
            aria-label={`Revogar a chave ${chave.prefixo}`}
            onClick={() => pedir({ acao: "revogar", chave })}
          >
            Revogar
          </button>
        ) : null}
      </span>
    ),
  };
  return [...COLUNAS_DOS_DADOS_DA_CHAVE, acoes];
}

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
      {`Suspensa em ${formatarData(painel.suspensa_em)}. `}
      {painel.motivo_da_suspensao
        ? `Motivo: ${motivoDaSuspensao(painel.motivo_da_suspensao)}.`
        : "Sem motivo registrado."}
    </p>
  );
}

interface PropriedadesDasChaves {
  painel: PainelDaOrganizacaoV1;
  acoes: AcoesDoPainel;
  pendente: Pendente;
  pedir(pendente: Pendente): void;
}

function Chaves({ painel, acoes, pendente, pedir }: PropriedadesDasChaves) {
  const daChave = pendente?.acao === "trocar" || pendente?.acao === "revogar" ? pendente : null;
  function confirmar() {
    if (daChave === null) return;
    pedir(null);
    if (daChave.acao === "trocar") acoes.trocar(daChave.chave);
    else acoes.revogar(daChave.chave);
  }
  const semChaveNova = acoes.ocupada || acoes.chaveNaTela;
  return (
    <Secao titulo="Chaves">
      <div className="acoes-da-administracao">
        <button type="button" className="botao" disabled={semChaveNova} onClick={acoes.emitir}>
          Emitir chave nova
        </button>
      </div>
      {acoes.chaveNaTela ? (
        <p className="apagado">Tire a chave nova da tela para emitir ou trocar outra: uma chave por vez.</p>
      ) : null}
      <Tabela
        legenda="Chaves da organização"
        legendaEscondida
        colunas={colunasDasChaves(acoes.ocupada, semChaveNova, pedir)}
        linhas={painel.chaves}
        chaveDaLinha={(chave) => chave.id}
        vazio="Nenhuma chave emitida."
      />
      {daChave?.acao === "trocar" ? (
        <Confirmacao
          pergunta={`Trocar a chave ${daChave.chave.prefixo}? Sai uma chave nova, e a antiga continua valendo por alguns dias, para o cliente fazer a troca.`}
          sim="Trocar mesmo"
          ocupada={semChaveNova}
          aoConfirmar={confirmar}
          aoCancelar={() => pedir(null)}
        />
      ) : null}
      {daChave?.acao === "revogar" ? (
        <Confirmacao
          pergunta={`Revogar a chave ${daChave.chave.prefixo}? Ela para de entrar na hora, e não dá para desfazer.`}
          sim="Revogar mesmo"
          ocupada={acoes.ocupada}
          aoConfirmar={confirmar}
          aoCancelar={() => pedir(null)}
        />
      ) : null}
      <p className="apagado">
        O valor de uma chave aparece uma única vez, para quem a emite ou troca. Aqui fica só o prefixo.
      </p>
    </Secao>
  );
}

interface PropriedadesDaSuspensao {
  painel: PainelDaOrganizacaoV1;
  motivos: string[];
  acoes: AcoesDoPainel;
  pendente: Pendente;
  pedir(pendente: Pendente): void;
}

function Suspensao({ painel, motivos, acoes, pendente, pedir }: PropriedadesDaSuspensao) {
  const [motivo, setMotivo] = useState(motivos[0] ?? "");
  if (painel.suspensa_em !== null) {
    return (
      <Secao titulo="Suspensão">
        <p>A organização está suspensa: nenhuma chave dela entra.</p>
        <div className="acoes-da-administracao">
          <button type="button" className="botao" disabled={acoes.ocupada} onClick={() => pedir({ acao: "reativar" })}>
            Reativar organização
          </button>
        </div>
        {pendente?.acao === "reativar" ? (
          <Confirmacao
            pergunta={`Reativar ${painel.nome}? As chaves dela voltam a entrar.`}
            sim="Reativar mesmo"
            ocupada={acoes.ocupada}
            aoConfirmar={() => {
              pedir(null);
              acoes.reativar();
            }}
            aoCancelar={() => pedir(null)}
          />
        ) : null}
      </Secao>
    );
  }
  return (
    <Secao titulo="Suspensão">
      <p>Suspender bloqueia todas as chaves da organização até ela ser reativada. Nada é apagado.</p>
      <div className="formulario-do-app">
        <div className="campos-do-formulario">
          <label>
            <span>Motivo</span>
            <select value={motivo} onChange={(ev) => setMotivo(ev.target.value)}>
              {motivos.map((codigo) => (
                <option key={codigo} value={codigo}>
                  {motivoDaSuspensao(codigo)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="botao"
            disabled={acoes.ocupada}
            onClick={() => pedir({ acao: "suspender", motivo })}
          >
            Suspender organização
          </button>
        </div>
      </div>
      {pendente?.acao === "suspender" ? (
        <Confirmacao
          pergunta={`Suspender ${painel.nome}? Nenhuma chave dela entra até a organização ser reativada.`}
          sim="Suspender mesmo"
          ocupada={acoes.ocupada}
          aoConfirmar={() => {
            const escolhido = pendente.motivo;
            pedir(null);
            acoes.suspender(escolhido);
          }}
          aoCancelar={() => pedir(null)}
        />
      ) : null}
    </Secao>
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

interface PropriedadesDoPainel {
  painel: PainelDaOrganizacaoV1;
  motivos: string[];
  acoes: AcoesDoPainel;
}

function PainelPronto({ painel, motivos, acoes }: PropriedadesDoPainel) {
  const id = useId();
  const [pendente, setPendente] = useState<Pendente>(null);
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
      <Chaves painel={painel} acoes={acoes} pendente={pendente} pedir={setPendente} />
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
      <Suspensao painel={painel} motivos={motivos} acoes={acoes} pendente={pendente} pedir={setPendente} />
    </section>
  );
}

interface PropriedadesDoPainelPedido {
  id: string;
  motivos: string[];
  /** Algo mudou que a lista mostra (a suspensão), ou o servidor deixou de achar o que a tela mostrava. */
  aoMudarALista(): void;
  /** A chave nova desta organização que está à vista. Quem a guarda é a tela, não o painel: o valor não
   * dá para ver de novo, então ele não pode depender de o painel continuar montado nem de uma releitura. */
  chaveNova: ChaveNovaV1 | null;
  /** O servidor respondeu com uma chave nova (pode ser depois de a pessoa ter deixado este painel). */
  aoChegarAChave(nova: ChaveNovaV1): void;
  aoTirarAChave(): void;
}

function Painel(propriedades: PropriedadesDoPainelPedido) {
  const { id, motivos, aoMudarALista, chaveNova, aoChegarAChave, aoTirarAChave } = propriedades;
  const { pedido, recarregar } = usarLeitura<PainelDaOrganizacaoV1>(ROTA_DA_ORGANIZACAO, { id });
  const temChaveNova = chaveNova !== null;
  const [aviso, setAviso] = useState<string | null>(null);
  const { ocupada, falha, executar } = useAcao(() => {
    recarregar();
    aoMudarALista();
  });
  function agir<T>(rota: string, corpo: unknown, aoDarCerto: (resposta: T) => void) {
    setAviso(null);
    executar((token) => mudar<T>("POST", rota, token, corpo), aoDarCerto);
  }
  function mostrarAChave(nova: ChaveNovaV1) {
    aoChegarAChave(nova);
    recarregar();
  }
  function feito(texto: string) {
    setAviso(texto);
    recarregar();
  }
  function mudouASuspensao(resposta: MudouV1, texto: string) {
    feito(resposta.mudou ? texto : NADA_MUDOU);
    aoMudarALista();
  }
  // uma chave por vez na tela: a segunda apagaria, sem aviso, o valor da primeira, que não dá para ver de novo
  function pedirChave(rota: string, corpo: unknown) {
    if (temChaveNova) return;
    agir<ChaveNovaV1>(rota, corpo, mostrarAChave);
  }
  const acoes: AcoesDoPainel = {
    ocupada,
    chaveNaTela: temChaveNova,
    emitir: () => pedirChave(ROTA_DE_EMITIR, { organizacao_id: id }),
    trocar: (chave) => pedirChave(ROTA_DE_TROCAR, { organizacao_id: id, chave_id: chave.id }),
    revogar: (chave) =>
      agir<MudouV1>(ROTA_DE_REVOGAR, { organizacao_id: id, chave_id: chave.id }, () =>
        feito("Chave revogada: ela não entra mais."),
      ),
    suspender: (motivo) =>
      agir<MudouV1>(ROTA_DE_SUSPENDER, { id, motivo }, (resposta) =>
        mudouASuspensao(resposta, "Organização suspensa: nenhuma chave entra."),
      ),
    reativar: () =>
      agir<MudouV1>(ROTA_DE_REATIVAR, { id }, (resposta) =>
        mudouASuspensao(resposta, "Organização reativada: as chaves voltam."),
      ),
  };
  return (
    <>
      {chaveNova ? <ChaveNova key={chaveNova.id} chave={chaveNova} aoTirar={aoTirarAChave} /> : null}
      <Aviso texto={aviso} />
      <Falha texto={falha} />
      {pedido.estado === "carregando" && <Carregando tipo="painel" rotulo="Carregando a organização…" />}
      {pedido.estado === "erro" && (
        <Erro
          erro={pedido.erro.tipo === "nao-encontrado" ? ORGANIZACAO_NAO_ENCONTRADA : pedido.erro}
          tentarDeNovo={recarregar}
        />
      )}
      {pedido.estado === "pronto" && <PainelPronto painel={pedido.dados} motivos={motivos} acoes={acoes} />}
    </>
  );
}

// --- a tela -----------------------------------------------------------------------------------

const A_CRIADA_ESPERA = " Ela abre quando você tirar a chave nova da tela.";
const OUTRA_CHAVE_ESPERA = "Há outra chave nova esperando: ela aparece quando você tirar esta da tela.";

interface ChaveDaOrganizacao {
  organizacao: string;
  nova: ChaveNovaV1;
}

function Organizacoes({ lista, recarregar }: { lista: OrganizacoesV1; recarregar(): void }) {
  const { organizacoes } = lista;
  const [pedida, setPedida] = useState<string | null>(null);
  const [criando, setCriando] = useState(organizacoes.length === 0);
  const [criada, setCriada] = useState<OrganizacaoDaListaV1 | null>(null);
  // as chaves novas que o servidor devolveu e a pessoa ainda não tirou da tela, na ordem de chegada; a
  // primeira é a que está à vista, com a organização dela. O valor não dá para ver de novo, então só a
  // própria pessoa tira esse painel (escolhendo outra organização ou tirando a chave); a tela, sozinha, não
  // troca. Fica aqui, mudado na mesma hora que o resto da escolha: um aviso do painel por efeito chegaria
  // depois do desenho e podia desfazer a troca de organização feita nesse intervalo
  const [chaves, setChaves] = useState<ChaveDaOrganizacao[]>([]);
  const chaveNova = chaves[0] ?? null;
  const tirarAChave = () => setChaves((atuais) => atuais.slice(1));
  const naLista = (id: string | null) => organizacoes.find((organizacao) => organizacao.id === id)?.id;
  const comChave = naLista(chaveNova?.organizacao ?? null) ?? null;
  // a pedida vale enquanto estiver na lista (a recém-criada entra quando a lista recarrega); senão, a primeira
  const escolhida = comChave ?? naLista(pedida) ?? organizacoes[0]?.id ?? null;
  function escolher(id: string) {
    setPedida(id);
    tirarAChave();
    setCriada(null);
  }
  // a resposta pode chegar depois de a pessoa trocar de organização: a chave já existe no servidor, então o
  // painel dela volta com o valor. Com outra chave à vista, a que chegou espera a vez (uma não apaga a outra,
  // e nenhuma fica ativa no servidor sem ninguém ter visto o valor)
  function aoChegarAChave(organizacao: string, nova: ChaveNovaV1) {
    setChaves((atuais) => [...atuais, { organizacao, nova }]);
  }
  // a resposta de um criar pode chegar depois de uma chave aparecer (o pedido saiu antes): aqui só se anota
  // a criada; quem decide o painel é o `escolhida` acima, com o estado de agora
  function aoCriar(nova: OrganizacaoDaListaV1) {
    setPedida(nova.id);
    setCriando(false);
    setCriada(nova);
    recarregar();
  }
  const esperaAChaveSair = criada !== null && comChave !== null && criada.id !== comChave;
  const aviso = criada ? `Organização criada: ${criada.nome}.${esperaAChaveSair ? A_CRIADA_ESPERA : ""}` : null;
  return (
    <>
      {organizacoes.length > 1 && escolhida !== null ? (
        <div className="formulario-do-app">
          <div className="campos-do-formulario">
            <label>
              <span>Organização</span>
              <select value={escolhida} onChange={(ev) => escolher(ev.target.value)}>
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
      <div className="acoes-da-administracao">
        <button type="button" className="botao" aria-expanded={criando} onClick={() => setCriando(!criando)}>
          Nova organização
        </button>
      </div>
      {criando ? (
        <NovaOrganizacao
          planos={lista.planos_da_api}
          chaveNaTela={comChave !== null}
          aoCriar={aoCriar}
          aoNaoAchar={recarregar}
        />
      ) : null}
      <Aviso texto={aviso} />
      <Aviso texto={chaves.length > 1 ? OUTRA_CHAVE_ESPERA : null} />
      {escolhida === null ? (
        <Vazio frase="Nenhuma organização cadastrada. Crie a primeira no formulário acima." />
      ) : (
        <Painel
          key={escolhida}
          id={escolhida}
          motivos={lista.motivos_da_suspensao}
          aoMudarALista={recarregar}
          chaveNova={chaveNova !== null && chaveNova.organizacao === escolhida ? chaveNova.nova : null}
          aoChegarAChave={(nova) => aoChegarAChave(escolhida, nova)}
          aoTirarAChave={tirarAChave}
        />
      )}
    </>
  );
}

function AdministracaoAberta() {
  const { pedido: lista, ultimos, recarregar } = usarLeitura<OrganizacoesV1>(ROTA_DAS_ORGANIZACOES, SEM_PARAMETROS);
  // o servidor disse que este endereço não existe para esta conta: a tela diz o mesmo
  if (lista.estado === "erro" && lista.erro.tipo === "nao-encontrado") return <NaoEncontrada />;
  return (
    <section>
      <Cabecalho
        titulo={TITULO_DA_ADMINISTRACAO}
        descricao="As organizações da API por chave: situação, consumo do mês, chaves e o que o contrato liga."
        acoes={
          <a className="botao pequeno" href={linkDoClassico(ENDERECO_DA_ADMINISTRACAO)}>
            Abrir a Administração antiga
          </a>
        }
      />
      <p className="apagado">
        As contas do app, o registro de ações, os eventos de cobrança e o acervo continuam na Administração antiga.
      </p>
      {lista.estado === "carregando" && <Carregando tipo="lista" rotulo="Carregando as organizações…" />}
      {lista.estado === "erro" && <Erro erro={lista.erro} tentarDeNovo={recarregar} />}
      {/* a releitura que falha não tira a tela: fica a última lista, com a falha acima (uma chave nova à vista
          não some por um tropeço do servidor) */}
      {ultimos !== null && <Organizacoes lista={ultimos} recarregar={recarregar} />}
    </section>
  );
}

export function Administracao() {
  const conta = useConta();
  // só poupa o pedido: quem recusa de verdade é o servidor, a cada pedido
  if (!conta?.eu?.administrador) return <NaoEncontrada />;
  return <AdministracaoAberta />;
}
