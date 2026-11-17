// O registro de ações e os eventos do Stripe na Administração (linha 962, PR 5): duas leituras, as mesmas
// da página antiga. Quem autoriza cada pedido é o servidor, a cada vez
// (src/api_v1/administracao_registro.py); a tela só mostra o que ele devolve. O registro guarda só ids: o
// e-mail de quem fez e de quem sofreu a ação vem na resposta, só para o administrador, e fica só no
// estado desta tela (nada no endereço, no armazenamento do navegador nem no console).
import { useEffect, useState } from "react";
import type { ErroDaApi } from "../api";
import { Carregando } from "../pecas/Carregando";
import { Erro } from "../pecas/Erro";
import { type Coluna, Tabela } from "../pecas/Tabela";
import type { AcaoV1, EventoDoStripeV1, EventosDoStripeV1, RegistroV1 } from "../tiposDaAdministracao";
import { Secao, inteiro, usarLeitura } from "./AcoesDaAdministracao";

const SEM_PARAMETROS = {};
const ROTA_DO_REGISTRO = "/v1/admin/registro";
const ROTA_DOS_EVENTOS = "/v1/admin/eventos-do-stripe";
const TODAS_AS_ACOES = "";
const SEM_VALOR = "—";
// quantos caracteres de um id cabem na tabela; o id inteiro fica na dica do campo
const TAMANHO_DO_ID_CURTO = 8;
// o 404 de uma leitura: o servidor deixou de reconhecer a conta como administradora
const LEITURA_NAO_RECONHECIDA =
  "O servidor não reconheceu o pedido: a sua conta pode ter deixado de ser administradora.";

// os rótulos do que a auditoria grava em código (os `ACAO_...` de src/auditoria.py e o de
// src/exportacao_do_acervo.py; há teste em tests/ que cobra um rótulo para cada um); código que a tela
// ainda não conhece aparece como veio
const ACOES: Record<string, string> = {
  plano_alterado: "Plano alterado",
  papel_alterado: "Papel alterado",
  conta_bloqueada: "Conta bloqueada",
  conta_desbloqueada: "Conta desbloqueada",
  termos_aceitos: "Termos aceitos",
  conta_apagada: "Conta apagada",
  dados_exportados: "Dados da conta exportados",
  acervo_exportado: "Acervo exportado",
  organizacao_criada: "Organização criada",
  organizacao_suspensa: "Organização suspensa",
  organizacao_reativada: "Organização reativada",
  chave_emitida: "Chave emitida",
  chave_rotacionada: "Chave trocada",
  chave_revogada: "Chave revogada",
  direito_concedido: "Direito concedido",
  direito_suspenso: "Direito suspenso",
  direito_reativado: "Direito reativado",
  conjunto_suspenso: "Conjunto suspenso",
  conjunto_reativado: "Conjunto reativado",
  membro_vinculado: "Conta vinculada à organização",
  membro_desvinculado: "Conta desvinculada da organização",
  pessoa_vista: "Pessoa vista na tela",
  newsletter_inscrita: "Newsletter: inscrição",
  newsletter_cancelada: "Newsletter: cancelamento",
  novidades_inscrita: "Novidades: inscrição",
  novidades_cancelada: "Novidades: cancelamento",
  carteira_consentida: "Carteira: consentimento",
  carteira_revogada: "Carteira: consentimento revogado",
  operacao_criada: "Sala: operação criada",
  operacao_encerrada: "Sala: operação encerrada",
  operacao_prorrogada: "Sala: prazo prorrogado",
  operacao_apagada: "Sala: operação apagada",
  operacao_expirada: "Sala: operação expirada",
  documento_enviado: "Sala: documento enviado",
  documento_recusado: "Sala: documento recusado",
  documento_baixado: "Sala: documento baixado",
  documento_apagado: "Sala: documento apagado",
  sala_baixada: "Sala: todos os documentos baixados",
  negocio_aberto: "Negócio aberto",
  negocio_fase_mudada: "Negócio: fase mudada",
  negocio_atualizado: "Negócio atualizado",
  contato_registrado: "Negócio: contato registrado",
  contato_apagado: "Negócio: contato apagado",
  exposicao_registrada: "Exposição registrada",
  exposicao_apagada: "Exposição apagada",
  garantia_registrada: "Garantia registrada",
  garantia_apagada: "Garantia apagada",
};

const aAcao = (codigo: string) => ACOES[codigo] ?? codigo;

const RELOGIO = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** O momento da API (UTC) na hora de Brasília: "16/11/2026 20:57". */
export function dataEHora(iso: string): string {
  const partes = new Map<string, string>(
    RELOGIO.formatToParts(new Date(iso)).map((parte) => [parte.type, parte.value]),
  );
  const de = (tipo: string) => partes.get(tipo) ?? "";
  return `${de("day")}/${de("month")}/${de("year")} ${de("hour")}:${de("minute")}`;
}

function IdCurto({ id }: { id: string }) {
  return <code title={id}>{id.slice(0, TAMANHO_DO_ID_CURTO)}</code>;
}

function QuemFez({ acao }: { acao: AcaoV1 }) {
  if (acao.foi_voce) return <>Você</>;
  if (acao.ator_email !== null) return <>{acao.ator_email}</>;
  // sem conta: ela foi apagada, ou foi o próprio serviço que gravou
  return acao.ator_id === null ? <>{SEM_VALOR}</> : <IdCurto id={acao.ator_id} />;
}

function Alvo({ acao }: { acao: AcaoV1 }) {
  if (acao.alvo_id === null) return <>{SEM_VALOR}</>;
  if (acao.alvo_id === acao.ator_id) return <>A própria conta</>;
  // o alvo que não é uma conta (organização, chave, operação) ou é de conta apagada: só o id
  return acao.alvo_email !== null ? <>{acao.alvo_email}</> : <IdCurto id={acao.alvo_id} />;
}

const umValor = (valor: unknown) => (typeof valor === "string" ? valor : JSON.stringify(valor));

/** Os detalhes como a auditoria gravou (ids e dados técnicos), em "chave: valor". */
function detalhesDe(acao: AcaoV1): string {
  const pares = Object.entries(acao.detalhes);
  if (pares.length === 0) return SEM_VALOR;
  return pares.map(([chave, valor]) => `${chave}: ${umValor(valor)}`).join(" · ");
}

const COLUNAS_DAS_ACOES: Coluna<AcaoV1>[] = [
  { chave: "quando", titulo: "Quando", celula: (acao) => dataEHora(acao.quando) },
  { chave: "acao", titulo: "Ação", celula: (acao) => aAcao(acao.acao) },
  { chave: "ator", titulo: "Quem fez", celula: (acao) => <QuemFez acao={acao} /> },
  { chave: "alvo", titulo: "Sobre quem ou o quê", celula: (acao) => <Alvo acao={acao} /> },
  { chave: "detalhes", titulo: "Detalhes", celula: detalhesDe },
];

const COLUNAS_DOS_EVENTOS: Coluna<EventoDoStripeV1>[] = [
  { chave: "quando", titulo: "Quando", celula: (evento) => dataEHora(evento.processado_em) },
  { chave: "tipo", titulo: "Tipo", celula: (evento) => evento.tipo },
  { chave: "evento", titulo: "Evento", celula: (evento) => <code>{evento.id}</code> },
];

const recusada = (erro: ErroDaApi) => erro.tipo === "nao-encontrado";
const erroDaLeitura = (erro: ErroDaApi) => (recusada(erro) ? LEITURA_NAO_RECONHECIDA : erro);

// --- o registro de ações ----------------------------------------------------------------------

function Acoes({ registro }: { registro: RegistroV1 }) {
  const [filtro, setFiltro] = useState(TODAS_AS_ACOES);
  const tipos = [...new Set(registro.acoes.map((acao) => acao.acao))].sort((a, b) =>
    aAcao(a).localeCompare(aAcao(b), "pt-BR"),
  );
  // o tipo escolhido que saiu da lista numa releitura deixa de filtrar, em vez de esconder tudo
  const valendo = tipos.includes(filtro) ? filtro : TODAS_AS_ACOES;
  const linhas = valendo === TODAS_AS_ACOES ? registro.acoes : registro.acoes.filter((acao) => acao.acao === valendo);
  return (
    <>
      {tipos.length > 1 ? (
        <div className="formulario-do-app">
          <div className="campos-do-formulario">
            <label>
              <span>Mostrar</span>
              <select value={valendo} onChange={(ev) => setFiltro(ev.target.value)}>
                <option value={TODAS_AS_ACOES}>Todas as ações</option>
                {tipos.map((codigo) => (
                  <option key={codigo} value={codigo}>
                    {aAcao(codigo)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      ) : null}
      <Tabela
        legenda="Ações registradas"
        legendaEscondida
        colunas={COLUNAS_DAS_ACOES}
        linhas={linhas}
        chaveDaLinha={(acao) => acao.id}
        vazio="Nada registrado ainda."
      />
      {registro.cortado ? (
        <p className="apagado">
          {`Estas são as ${inteiro(registro.acoes.length)} ações mais novas. As mais antigas continuam guardadas; o filtro acima vale só para as que estão na tela.`}
        </p>
      ) : null}
    </>
  );
}

// --- a aba ------------------------------------------------------------------------------------

interface PropriedadesDoRegistro {
  /** O servidor deixou de reconhecer esta conta como administradora (404): a tela relê o que ele diz. */
  aoNaoAchar(): void;
}

export function RegistroDaAdministracao({ aoNaoAchar }: PropriedadesDoRegistro) {
  const registro = usarLeitura<RegistroV1>(ROTA_DO_REGISTRO, SEM_PARAMETROS);
  const eventos = usarLeitura<EventosDoStripeV1>(ROTA_DOS_EVENTOS, SEM_PARAMETROS);
  const semAcesso =
    (registro.pedido.estado === "erro" && recusada(registro.pedido.erro)) ||
    (eventos.pedido.estado === "erro" && recusada(eventos.pedido.erro));
  useEffect(() => {
    if (semAcesso) aoNaoAchar();
  }, [semAcesso, aoNaoAchar]);
  function atualizar() {
    registro.recarregar();
    eventos.recarregar();
  }
  // o servidor não reconhece mais o administrador: o que já tinha vindo sai da tela
  const acoes = semAcesso ? null : registro.ultimos;
  const recebidos = semAcesso ? null : eventos.ultimos;

  return (
    <>
      <Secao titulo="Registro de ações">
        <p className="apagado">
          O que foi feito, quando, por qual conta e sobre o quê: mudança de plano e de papel, bloqueio, chave emitida,
          aceite dos termos. O registro guarda só identificadores; o e-mail aparece aqui enquanto a conta existe. Os
          horários são de Brasília.
        </p>
        <div className="acoes-da-administracao">
          <button type="button" className="botao pequeno" onClick={atualizar}>
            Atualizar
          </button>
        </div>
        {registro.pedido.estado === "carregando" && acoes === null && (
          <Carregando tipo="lista" rotulo="Carregando o registro…" />
        )}
        {registro.pedido.estado === "erro" && (
          <Erro erro={erroDaLeitura(registro.pedido.erro)} tentarDeNovo={registro.recarregar} />
        )}
        {acoes !== null && <Acoes registro={acoes} />}
      </Secao>
      <Secao titulo="Eventos do Stripe">
        <p className="apagado">
          Os últimos eventos de cobrança que o webhook recebeu e processou: servem para conferir se ele está recebendo.
        </p>
        {eventos.pedido.estado === "carregando" && recebidos === null && (
          <Carregando tipo="lista" rotulo="Carregando os eventos…" />
        )}
        {eventos.pedido.estado === "erro" && (
          <Erro erro={erroDaLeitura(eventos.pedido.erro)} tentarDeNovo={eventos.recarregar} />
        )}
        {recebidos !== null && (
          <>
            <Tabela
              legenda="Eventos do Stripe processados"
              legendaEscondida
              colunas={COLUNAS_DOS_EVENTOS}
              linhas={recebidos.eventos}
              chaveDaLinha={(evento) => evento.id}
              vazio="Nenhum evento recebido ainda."
            />
            {recebidos.cortado ? (
              <p className="apagado">{`Estes são os ${inteiro(recebidos.eventos.length)} eventos mais novos.`}</p>
            ) : null}
          </>
        )}
      </Secao>
    </>
  );
}
