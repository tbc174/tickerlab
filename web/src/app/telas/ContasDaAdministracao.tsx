// As contas do app na Administração (linha 962, PR 4): os números do serviço, a busca de contas e as
// mudanças de plano, de papel e de bloqueio. Quem autoriza cada pedido é o servidor, a cada vez
// (src/api_v1/administracao_contas.py); a tela só mostra o que ele devolve e manda o que ele confere.
// O e-mail e o nome das contas ficam só no estado desta tela: o termo da busca vai no corpo do pedido,
// nunca no endereço, e nada disto vai para o armazenamento do navegador nem para o console.
import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import { ErroDaApi, mudar } from "../api";
import { useConta } from "../conta";
import { formatarData } from "../formatar";
import { Carregando } from "../pecas/Carregando";
import { CartaoDeNumero } from "../pecas/CartaoDeNumero";
import { Erro } from "../pecas/Erro";
import { Selo } from "../pecas/Selo";
import { type Coluna, Tabela } from "../pecas/Tabela";
import type { BloqueadaV1, ContaV1, ContasV1, ResumoV1 } from "../tiposDaAdministracao";
import { Aviso, Confirmacao, Falha, Secao, inteiro, plural, useAcao, usarLeitura } from "./AcoesDaAdministracao";

const SEM_PARAMETROS = {};
const ROTA_DO_RESUMO = "/v1/admin/resumo";
const ROTA_DE_BUSCAR = "/v1/admin/contas/buscar";
const ROTA_DO_PLANO = "/v1/admin/conta/plano";
const ROTA_DO_PAPEL = "/v1/admin/conta/papel";
const ROTA_DE_BLOQUEAR = "/v1/admin/conta/bloquear";
const ROTA_DE_DESBLOQUEAR = "/v1/admin/conta/desbloquear";
// o mesmo teto do servidor: termo maior ele recusa
const TAMANHO_MAXIMO_DA_BUSCA = 200;
const PAPEL_DE_ADMINISTRADOR = "admin";
// o 404 de uma leitura: o servidor deixou de reconhecer a conta como administradora
const LEITURA_NAO_RECONHECIDA =
  "O servidor não reconheceu o pedido: a sua conta pode ter deixado de ser administradora.";

// os rótulos do que a API manda em código; código que a tela ainda não conhece aparece como veio
const PLANOS: Record<string, string> = { gratuito: "Gratuito", plus: "Plus", pro: "Pro" };
const PAPEIS: Record<string, string> = { usuario: "Usuário", admin: "Administrador" };
const MOTIVOS_DO_BLOQUEIO: Record<string, string> = {
  abuso: "Abuso",
  acesso_de_terceiro: "Acesso de terceiro",
  incidente: "Incidente",
  pedido_do_titular: "Pedido do titular",
};
// os estados de uma assinatura no Stripe
const ASSINATURAS: Record<string, string> = {
  active: "Ativa",
  trialing: "Em teste",
  past_due: "Em atraso",
  unpaid: "Não paga",
  canceled: "Cancelada",
  incomplete: "Incompleta",
  incomplete_expired: "Expirada",
  paused: "Pausada",
};

const oPlano = (codigo: string) => PLANOS[codigo] ?? codigo;
const oPapel = (codigo: string) => PAPEIS[codigo] ?? codigo;
const oMotivo = (codigo: string) => MOTIVOS_DO_BLOQUEIO[codigo] ?? codigo;
const aAssinatura = (codigo: string | null) => (codigo === null ? "Sem assinatura" : (ASSINATURAS[codigo] ?? codigo));

const erroDaLeitura = (erro: ErroDaApi) => (erro.tipo === "nao-encontrado" ? LEITURA_NAO_RECONHECIDA : erro);

// --- os números do serviço --------------------------------------------------------------------

function Numeros({ resumo }: { resumo: ResumoV1 }) {
  return (
    <div className="numeros">
      <CartaoDeNumero
        rotulo="Contas"
        valor={inteiro(resumo.usuarios)}
        detalhe={plural(resumo.administradores, "administrador", "administradores")}
        principal
      />
      <CartaoDeNumero rotulo="Plano Gratuito" valor={inteiro(resumo.gratuito)} />
      <CartaoDeNumero rotulo="Plano Plus" valor={inteiro(resumo.plus)} />
      <CartaoDeNumero rotulo="Plano Pro" valor={inteiro(resumo.pro)} />
      <CartaoDeNumero rotulo="Novas na semana" valor={inteiro(resumo.novos_na_semana)} detalhe="criadas em 7 dias" />
      <CartaoDeNumero
        rotulo="Ativas na semana"
        valor={inteiro(resumo.ativos_na_semana)}
        detalhe="entraram em 7 dias"
      />
      <CartaoDeNumero rotulo="Assinaturas ativas" valor={inteiro(resumo.assinaturas_ativas)} detalhe="no Stripe" />
      <CartaoDeNumero rotulo="Simulações salvas" valor={inteiro(resumo.simulacoes)} />
      <CartaoDeNumero
        rotulo="Eventos do Stripe"
        valor={inteiro(resumo.eventos_do_stripe)}
        detalhe="recebidos pelo webhook"
      />
    </div>
  );
}

// --- a busca ----------------------------------------------------------------------------------

type EstadoDaBusca = { estado: "carregando" } | { estado: "pronta" } | { estado: "erro"; erro: ErroDaApi };

/** A busca de contas. É `POST` com o termo no corpo: o termo costuma ser um e-mail, e endereço fica no
 * histórico do navegador e nos registros do caminho. `buscar` troca o termo e limpa a lista; `recarregar`
 * refaz a mesma busca deixando a lista na tela até a resposta nova chegar. */
function usarContas(aoNaoAchar: () => void) {
  const token = useConta()?.token ?? null;
  const [termo, setTermo] = useState("");
  const [versao, setVersao] = useState(0);
  const [busca, setBusca] = useState<EstadoDaBusca>({ estado: "carregando" });
  const [ultimas, setUltimas] = useState<ContasV1 | null>(null);
  // `versao` entra na lista só para o pedido ser refeito quando alguém busca de novo ou recarrega
  useEffect(() => {
    if (token === null) return;
    let valendo = true;
    mudar<ContasV1>("POST", ROTA_DE_BUSCAR, token, { busca: termo })
      .then((dados) => {
        if (!valendo) return;
        setUltimas(dados);
        setBusca({ estado: "pronta" });
      })
      .catch((falha: unknown) => {
        if (!valendo) return;
        const erro = falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha));
        setBusca({ estado: "erro", erro });
        if (erro.tipo !== "nao-encontrado") return;
        // o servidor não reconhece mais o administrador: as contas saem da tela, e ela relê o que ele diz
        setUltimas(null);
        aoNaoAchar();
      });
    return () => {
      valendo = false;
    };
  }, [token, termo, versao, aoNaoAchar]);
  function buscar(novo: string) {
    setTermo(novo);
    setUltimas(null);
    setBusca({ estado: "carregando" });
    setVersao((atual) => atual + 1);
  }
  const recarregar = useCallback(() => setVersao((atual) => atual + 1), []);
  return { termo, busca, ultimas, buscar, recarregar };
}

function FormularioDaBusca({ aoBuscar }: { aoBuscar(termo: string): void }) {
  const [digitado, setDigitado] = useState("");
  function enviar(evento: FormEvent) {
    evento.preventDefault();
    aoBuscar(digitado.trim());
  }
  return (
    <form className="formulario-do-app" role="search" aria-label="Buscar contas" autoComplete="off" onSubmit={enviar}>
      <div className="campos-do-formulario">
        <label>
          <span>Buscar por e-mail ou nome</span>
          <input
            value={digitado}
            maxLength={TAMANHO_MAXIMO_DA_BUSCA}
            onChange={(ev) => setDigitado(ev.target.value)}
          />
        </label>
        <button type="submit" className="botao">
          Buscar
        </button>
      </div>
    </form>
  );
}

// --- a lista ----------------------------------------------------------------------------------

function Situacao({ conta }: { conta: ContaV1 }) {
  if (conta.bloqueada_em === null) return <Selo tom="bom">Liberada</Selo>;
  const quando = formatarData(conta.bloqueada_em);
  return (
    <>
      <Selo tom="alerta">Bloqueada</Selo>{" "}
      <span className="apagado">
        {conta.motivo_do_bloqueio ? `${quando} · ${oMotivo(conta.motivo_do_bloqueio)}` : quando}
      </span>
    </>
  );
}

function colunasDasContas(abrir: (id: string) => void): Coluna<ContaV1>[] {
  return [
    {
      chave: "email",
      titulo: "E-mail",
      celula: (conta) => (
        <>
          {conta.email}
          {conta.e_voce ? (
            <>
              {" "}
              <Selo tom="destaque">Sua conta</Selo>
            </>
          ) : null}
        </>
      ),
    },
    { chave: "nome", titulo: "Nome", celula: (conta) => conta.nome ?? "—" },
    { chave: "plano", titulo: "Plano", celula: (conta) => oPlano(conta.plano) },
    { chave: "papel", titulo: "Papel", celula: (conta) => oPapel(conta.papel) },
    { chave: "situacao", titulo: "Situação", celula: (conta) => <Situacao conta={conta} /> },
    { chave: "assinatura", titulo: "Assinatura", celula: (conta) => aAssinatura(conta.status_da_assinatura) },
    { chave: "simulacoes", titulo: "Simulações", numero: true, celula: (conta) => inteiro(conta.simulacoes) },
    { chave: "criada", titulo: "Criada em", celula: (conta) => formatarData(conta.criado_em) },
    {
      chave: "acesso",
      titulo: "Último acesso",
      celula: (conta) => (conta.ultimo_acesso ? formatarData(conta.ultimo_acesso) : "Nunca entrou"),
    },
    {
      chave: "acoes",
      titulo: "Ações",
      celula: (conta) => (
        <button
          type="button"
          className="botao pequeno"
          aria-label={`Gerenciar a conta ${conta.email}`}
          onClick={() => abrir(conta.id)}
        >
          Gerenciar
        </button>
      ),
    },
  ];
}

// --- o painel de uma conta --------------------------------------------------------------------

/** O que o painel sabe fazer; cada uma vira um pedido que o servidor confere de novo. */
interface AcoesDaConta {
  ocupada: boolean;
  mudarOPlano(plano: string): void;
  mudarOPapel(papel: string): void;
  bloquear(motivo: string): void;
  desbloquear(): void;
}

/** A mudança que espera o "sim" de quem clicou. */
type Pendente =
  | { acao: "plano"; plano: string }
  | { acao: "papel"; papel: string }
  | { acao: "bloquear"; motivo: string }
  | { acao: "desbloquear" }
  | null;

function perguntaDe(pendente: Exclude<Pendente, null>, conta: ContaV1): { pergunta: string; sim: string } {
  if (pendente.acao === "plano")
    return {
      pergunta: `Mudar o plano de ${oPlano(conta.plano)} para ${oPlano(pendente.plano)}? Isso não cria nem cancela assinatura no Stripe.`,
      sim: "Mudar o plano mesmo",
    };
  if (pendente.acao === "papel")
    return {
      pergunta:
        pendente.papel === PAPEL_DE_ADMINISTRADOR
          ? "Tornar esta conta administradora? Ela passa a ver e a mudar tudo o que esta Administração mostra."
          : `Mudar o papel desta conta para ${oPapel(pendente.papel)}? Ela deixa de abrir a Administração.`,
      sim: "Mudar o papel mesmo",
    };
  if (pendente.acao === "bloquear")
    return {
      pergunta: `Bloquear esta conta (motivo: ${oMotivo(pendente.motivo)})? As sessões da conta são encerradas na hora e o login para. Nada é apagado.`,
      sim: "Bloquear mesmo",
    };
  return { pergunta: "Desbloquear esta conta? O login volta a funcionar.", sim: "Desbloquear mesmo" };
}

interface PropriedadesDoPainel {
  conta: ContaV1;
  /** O que o servidor aceita em cada mudança (veio com a lista). */
  opcoes: ContasV1;
  acoes: AcoesDaConta;
  aoFechar(): void;
}

function PainelDaConta({ conta, opcoes, acoes, aoFechar }: PropriedadesDoPainel) {
  const id = useId();
  const caixa = useRef<HTMLElement>(null);
  // o painel abre longe do botão que o chamou: quem usa teclado ou leitor de tela chega direto nele
  useEffect(() => caixa.current?.focus(), []);
  const [pendente, setPendente] = useState<Pendente>(null);
  // o que a pessoa escolheu; sem escolha, vale o que a conta tem agora (a lista relida conta a verdade)
  const [planoEscolhido, setPlanoEscolhido] = useState<string | null>(null);
  const [papelEscolhido, setPapelEscolhido] = useState<string | null>(null);
  const [motivo, setMotivo] = useState(opcoes.motivos_do_bloqueio[0] ?? "");
  const plano = planoEscolhido ?? conta.plano;
  const papel = papelEscolhido ?? conta.papel;
  const bloqueada = conta.bloqueada_em !== null;
  // a pergunta some com o botão que tinha o foco: o foco volta ao painel, em vez de cair no topo da página
  function fecharAPergunta() {
    setPendente(null);
    caixa.current?.focus();
  }
  function confirmar() {
    if (pendente === null) return;
    fecharAPergunta();
    if (pendente.acao === "plano") acoes.mudarOPlano(pendente.plano);
    else if (pendente.acao === "papel") acoes.mudarOPapel(pendente.papel);
    else if (pendente.acao === "bloquear") acoes.bloquear(pendente.motivo);
    else acoes.desbloquear();
  }
  // trocar a escolha desfaz a pergunta aberta: o "sim" nunca vale para o que não está mais escolhido
  function escolher(guardar: (valor: string) => void, valor: string) {
    setPendente(null);
    guardar(valor);
  }
  return (
    <section className="secao-do-relatorio" aria-labelledby={id} tabIndex={-1} ref={caixa}>
      <div className="cabecalho-titulo">
        <h3 id={id}>{conta.email}</h3>
        {conta.e_voce ? <Selo tom="destaque">Sua conta</Selo> : null}
        <Selo tom={bloqueada ? "alerta" : "bom"}>{bloqueada ? "Bloqueada" : "Liberada"}</Selo>
      </div>
      <p className="apagado">
        {`${conta.nome ?? "Sem nome"} · criada em ${formatarData(conta.criado_em)} · `}
        {conta.ultimo_acesso ? `último acesso em ${formatarData(conta.ultimo_acesso)}` : "nunca entrou"}
      </p>
      {conta.bloqueada_em !== null ? (
        <p role="note">
          {`Bloqueada em ${formatarData(conta.bloqueada_em)}. `}
          {conta.motivo_do_bloqueio ? `Motivo: ${oMotivo(conta.motivo_do_bloqueio)}.` : "Sem motivo registrado."}
        </p>
      ) : null}
      <div className="formulario-do-app">
        <div className="campos-do-formulario">
          <label>
            <span>Plano</span>
            <select value={plano} onChange={(ev) => escolher(setPlanoEscolhido, ev.target.value)}>
              {opcoes.planos.map((codigo) => (
                <option key={codigo} value={codigo}>
                  {oPlano(codigo)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="botao"
            disabled={acoes.ocupada || plano === conta.plano}
            onClick={() => setPendente({ acao: "plano", plano })}
          >
            Mudar o plano
          </button>
        </div>
        {conta.e_voce ? null : (
          <div className="campos-do-formulario">
            <label>
              <span>Papel</span>
              <select value={papel} onChange={(ev) => escolher(setPapelEscolhido, ev.target.value)}>
                {opcoes.papeis.map((codigo) => (
                  <option key={codigo} value={codigo}>
                    {oPapel(codigo)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="botao"
              disabled={acoes.ocupada || papel === conta.papel}
              onClick={() => setPendente({ acao: "papel", papel })}
            >
              Mudar o papel
            </button>
          </div>
        )}
        {conta.e_voce || bloqueada ? null : (
          <div className="campos-do-formulario">
            <label>
              <span>Motivo do bloqueio</span>
              <select value={motivo} onChange={(ev) => escolher(setMotivo, ev.target.value)}>
                {opcoes.motivos_do_bloqueio.map((codigo) => (
                  <option key={codigo} value={codigo}>
                    {oMotivo(codigo)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="botao"
              disabled={acoes.ocupada}
              onClick={() => setPendente({ acao: "bloquear", motivo })}
            >
              Bloquear conta
            </button>
          </div>
        )}
      </div>
      {conta.e_voce ? (
        <p className="apagado">
          Esta é a sua conta: o papel e o bloqueio não aparecem aqui, para você não tirar o próprio acesso. O servidor
          também recusa.
        </p>
      ) : null}
      {pendente !== null ? (
        <Confirmacao
          {...perguntaDe(pendente, conta)}
          ocupada={acoes.ocupada}
          aoConfirmar={confirmar}
          aoCancelar={fecharAPergunta}
        />
      ) : null}
      <div className="acoes-da-administracao">
        {!conta.e_voce && bloqueada ? (
          <button
            type="button"
            className="botao"
            disabled={acoes.ocupada}
            onClick={() => setPendente({ acao: "desbloquear" })}
          >
            Desbloquear conta
          </button>
        ) : null}
        <button type="button" className="botao pequeno" onClick={aoFechar}>
          Fechar
        </button>
      </div>
    </section>
  );
}

// --- a aba ------------------------------------------------------------------------------------

interface PropriedadesDasContas {
  /** O servidor deixou de reconhecer esta conta como administradora (404): a tela relê o que ele diz. */
  aoNaoAchar(): void;
}

export function ContasDoApp({ aoNaoAchar }: PropriedadesDasContas) {
  const resumo = usarLeitura<ResumoV1>(ROTA_DO_RESUMO, SEM_PARAMETROS);
  const contas = usarContas(aoNaoAchar);
  const [aberta, setAberta] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const { ocupada, falha, executar } = useAcao(() => {
    contas.recarregar();
    aoNaoAchar();
  });
  const lista = contas.ultimas;
  // o painel é desenhado da lista de agora: a conta que saiu dela (outra busca, conta apagada) fecha sozinha
  const escolhida = lista?.contas.find((conta) => conta.id === aberta) ?? null;

  function agir<T>(rota: string, corpo: unknown, feito: (resposta: T) => string) {
    setAviso(null);
    executar(
      (token) => mudar<T>("POST", rota, token, corpo),
      (resposta) => {
        setAviso(feito(resposta));
        contas.recarregar();
        resumo.recarregar();
      },
    );
  }
  function acoesDe(conta: ContaV1): AcoesDaConta {
    const { id, email } = conta;
    return {
      ocupada,
      mudarOPlano: (plano) =>
        agir<void>(ROTA_DO_PLANO, { id, plano }, () => `Plano de ${email} mudado para ${oPlano(plano)}.`),
      mudarOPapel: (papel) =>
        agir<void>(ROTA_DO_PAPEL, { id, papel }, () => `Papel de ${email} mudado para ${oPapel(papel)}.`),
      bloquear: (motivo) =>
        agir<BloqueadaV1>(
          ROTA_DE_BLOQUEAR,
          { id, motivo },
          (resposta) =>
            `Conta ${email} bloqueada: ${plural(resposta.sessoes_encerradas, "sessão encerrada", "sessões encerradas")}.`,
        ),
      desbloquear: () => agir<void>(ROTA_DE_DESBLOQUEAR, { id }, () => `Conta ${email} desbloqueada: o login volta.`),
    };
  }
  function buscar(termo: string) {
    setAviso(null);
    contas.buscar(termo);
  }

  return (
    <>
      <Secao titulo="Números do serviço">
        {resumo.pedido.estado === "carregando" && resumo.ultimos === null && (
          <Carregando tipo="painel" rotulo="Carregando os números…" />
        )}
        {resumo.pedido.estado === "erro" && (
          <Erro erro={erroDaLeitura(resumo.pedido.erro)} tentarDeNovo={resumo.recarregar} />
        )}
        {resumo.ultimos !== null && <Numeros resumo={resumo.ultimos} />}
      </Secao>
      <Secao titulo="Contas">
        <FormularioDaBusca aoBuscar={buscar} />
        <Aviso texto={aviso} />
        <Falha texto={falha} />
        {escolhida !== null && lista !== null ? (
          <PainelDaConta
            key={escolhida.id}
            conta={escolhida}
            opcoes={lista}
            acoes={acoesDe(escolhida)}
            aoFechar={() => setAberta(null)}
          />
        ) : null}
        {contas.busca.estado === "carregando" && lista === null && (
          <Carregando tipo="lista" rotulo="Carregando as contas…" />
        )}
        {contas.busca.estado === "erro" && (
          <Erro erro={erroDaLeitura(contas.busca.erro)} tentarDeNovo={() => contas.buscar(contas.termo)} />
        )}
        {lista !== null && (
          <>
            <Tabela
              legenda="Contas encontradas"
              legendaEscondida
              colunas={colunasDasContas(setAberta)}
              linhas={lista.contas}
              chaveDaLinha={(conta) => conta.id}
              vazio="Nenhuma conta encontrada."
            />
            {lista.cortada ? (
              <p className="apagado">
                {`Estas são as ${inteiro(lista.contas.length)} contas mais novas que batem com a busca. Há mais: afine a busca para achar as outras.`}
              </p>
            ) : null}
          </>
        )}
        <p className="apagado">
          Mudar o plano aqui não cria nem cancela assinatura no Stripe. Bloquear encerra as sessões da conta na hora e
          para o login; não apaga nada. Toda mudança fica no registro de ações, na aba Registro.
        </p>
      </Secao>
    </>
  );
}
