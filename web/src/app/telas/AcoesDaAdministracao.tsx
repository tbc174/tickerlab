// As peças das ações da Administração (linha 955, PR 3): o pedido que recarrega sem apagar a tela, a ação
// com a frase do servidor, a confirmação na própria página, o formulário de criar organização e a caixa da
// chave nova. O valor de uma chave vive só no estado da tela de quem a emitiu: não vai para o armazenamento
// do navegador, para o endereço nem para o console, e some ao ser tirado, ao trocar de organização ou ao
// sair da tela. Quem autoriza cada ação é o servidor, a cada pedido (src/api_v1/administracao.py).
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ErroDaApi, type Parametros, mudar, pedir } from "../api";
import { useConta } from "../conta";
import type { ChaveNovaV1, OrganizacaoDaListaV1, PlanoDaApiV1 } from "../tiposDaAdministracao";
import type { Pedido } from "../usarPedido";

export const ROTA_DAS_ORGANIZACOES = "/v1/admin/organizacoes";

const NAO_DEU_AGORA = "Não deu agora. Tente de novo em instantes.";
// o 404 sem frase é o de um endereço que não existe: o que o servidor responde a quem não é administrador
const RECUSA_SEM_FRASE = "Not Found";
const PEDIDO_NAO_RECONHECIDO =
  "O servidor não reconheceu o pedido: a organização pode ter saído, ou a sua conta deixou de ser administradora.";

function fraseDaFalha(erro: unknown): string {
  if (!(erro instanceof ErroDaApi)) return NAO_DEU_AGORA;
  if (erro.tipo === "nao-encontrado" && erro.message === RECUSA_SEM_FRASE) return PEDIDO_NAO_RECONHECIDO;
  return erro.message;
}

/** Como `usarPedido`, com `recarregar`: refaz o pedido deixando na tela o que já estava, até a resposta nova
 * chegar (o aviso de uma ação e a chave recém-emitida não piscam). Os parâmetros são os da primeira vez: quem
 * muda de organização monta a peça de novo. */
export function usarLeitura<T>(rota: string, parametros: Parametros): { pedido: Pedido<T>; recarregar(): void } {
  const token = useConta()?.token ?? null;
  const [pedido, setPedido] = useState<Pedido<T>>({ estado: "carregando" });
  const [versao, setVersao] = useState(0);
  const chave = JSON.stringify(parametros);
  // `versao` entra na lista só para o pedido ser refeito quando alguém chama `recarregar`
  useEffect(() => {
    if (token === null) return;
    let valendo = true;
    pedir<T>(rota, token, JSON.parse(chave) as Parametros)
      .then((dados) => {
        if (valendo) setPedido({ estado: "pronto", dados });
      })
      .catch((falha: unknown) => {
        if (!valendo) return;
        const erro = falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha));
        setPedido({ estado: "erro", erro });
      });
    return () => {
      valendo = false;
    };
  }, [rota, token, chave, versao]);
  const recarregar = useCallback(() => setVersao((atual) => atual + 1), []);
  return { pedido, recarregar };
}

/** Roda uma ação da Administração, uma por vez: guarda a frase da recusa e, quando o servidor não acha mais
 * o que a tela mostrava (404), avisa para a tela reler o que ele diz agora. */
export function useAcao(aoNaoAchar: () => void) {
  const token = useConta()?.token ?? null;
  const [ocupada, setOcupada] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  // dois cliques seguidos chegam antes de o botão desligar: a trava não pode esperar o próximo desenho
  const emCurso = useRef(false);
  function executar<T>(fazer: (token: string) => Promise<T>, aoDarCerto: (resposta: T) => void) {
    if (token === null || emCurso.current) return;
    emCurso.current = true;
    setOcupada(true);
    setFalha(null);
    fazer(token)
      .then(aoDarCerto)
      .catch((erro: unknown) => {
        setFalha(fraseDaFalha(erro));
        if (erro instanceof ErroDaApi && erro.tipo === "nao-encontrado") aoNaoAchar();
      })
      .finally(() => {
        emCurso.current = false;
        setOcupada(false);
      });
  }
  return { ocupada, falha, executar };
}

export function Falha({ texto }: { texto: string | null }) {
  return texto ? (
    <p className="erro-do-app" role="alert">
      {texto}
    </p>
  ) : null;
}

export function Aviso({ texto }: { texto: string | null }) {
  return texto ? <p role="status">{texto}</p> : null;
}

interface PropriedadesDaConfirmacao {
  pergunta: string;
  /** O texto do botão que faz (ex.: "Revogar mesmo"). */
  sim: string;
  ocupada: boolean;
  aoConfirmar(): void;
  aoCancelar(): void;
}

/** A pergunta antes de uma ação que pesa. O foco vai para o "Cancelar": o Enter distraído não confirma. */
export function Confirmacao({ pergunta, sim, ocupada, aoConfirmar, aoCancelar }: PropriedadesDaConfirmacao) {
  const cancelar = useRef<HTMLButtonElement>(null);
  useEffect(() => cancelar.current?.focus(), []);
  return (
    <div className="confirmacao-da-administracao" role="group" aria-label="Confirmar a ação">
      <p>{pergunta}</p>
      <div className="acoes-da-administracao">
        <button type="button" className="botao primario" disabled={ocupada} onClick={aoConfirmar}>
          {sim}
        </button>
        <button type="button" className="botao" ref={cancelar} onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

const dias = (n: number) => `${n} ${n === 1 ? "dia" : "dias"}`;

/** A chave recém-emitida ou trocada: o único lugar em que o valor aparece, até a pessoa tirar. */
export function ChaveNova({ chave, aoTirar }: { chave: ChaveNovaV1; aoTirar(): void }) {
  const [copiada, setCopiada] = useState<"sim" | "nao" | null>(null);
  const caixa = useRef<HTMLElement>(null);
  // quem usa leitor de tela ou teclado chega direto na chave, que apareceu longe do botão
  useEffect(() => caixa.current?.focus(), []);
  async function copiar() {
    try {
      if (!navigator.clipboard) throw new Error("sem área de transferência");
      await navigator.clipboard.writeText(chave.valor);
      setCopiada("sim");
    } catch {
      setCopiada("nao");
    }
  }
  const oQueHouve =
    chave.antiga_vale_por_dias === null
      ? "Chave emitida"
      : `Chave rotacionada: a antiga vale mais ${dias(chave.antiga_vale_por_dias)}`;
  return (
    <section className="chave-nova" aria-label="Chave nova" tabIndex={-1} ref={caixa}>
      <p>
        <strong>{`${oQueHouve} (prefixo ${chave.prefixo})`}</strong>
      </p>
      <pre>{chave.valor}</pre>
      <p>
        Esta chave aparece só agora: copie e entregue ao cliente. Ela não fica guardada em lugar nenhum e não dá para
        ver de novo: some se você trocar de organização ou sair desta tela.
      </p>
      <div className="acoes-da-administracao">
        <button type="button" className="botao primario" onClick={copiar}>
          Copiar a chave
        </button>
        <button type="button" className="botao" onClick={aoTirar}>
          Já copiei: tirar da tela
        </button>
        {copiada === "sim" && <span role="status">Copiada.</span>}
        {copiada === "nao" && <span role="status">Não deu para copiar; selecione o texto acima.</span>}
      </div>
    </section>
  );
}

interface PropriedadesDaNovaOrganizacao {
  planos: PlanoDaApiV1[];
  aoCriar(criada: OrganizacaoDaListaV1): void;
  aoNaoAchar(): void;
}

export function NovaOrganizacao({ planos, aoCriar, aoNaoAchar }: PropriedadesDaNovaOrganizacao) {
  const [nome, setNome] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [plano, setPlano] = useState(planos[0]?.plano_da_api ?? "");
  const { ocupada, falha, executar } = useAcao(aoNaoAchar);
  const semNome = nome.trim() === "";
  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (semNome) return;
    const corpo = { nome: nome.trim(), cnpj: cnpj.trim() === "" ? null : cnpj.trim(), plano_da_api: plano };
    executar((token) => mudar<OrganizacaoDaListaV1>("POST", ROTA_DAS_ORGANIZACOES, token, corpo), aoCriar);
  }
  return (
    <form className="formulario-do-app" aria-label="Nova organização" autoComplete="off" onSubmit={enviar}>
      <div className="campos-do-formulario">
        <label>
          <span>Nome</span>
          <input value={nome} onChange={(ev) => setNome(ev.target.value)} />
        </label>
        <label>
          <span>CNPJ (opcional)</span>
          <input value={cnpj} inputMode="numeric" onChange={(ev) => setCnpj(ev.target.value)} />
        </label>
        <label>
          <span>Plano da API</span>
          <select value={plano} onChange={(ev) => setPlano(ev.target.value)}>
            {planos.map((opcao) => (
              <option key={opcao.plano_da_api} value={opcao.plano_da_api}>
                {opcao.nome_do_plano}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="botao primario" disabled={ocupada || semNome}>
          Criar organização
        </button>
      </div>
      <Falha texto={falha} />
    </form>
  );
}
