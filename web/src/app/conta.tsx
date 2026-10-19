// A conta de quem está usando o app novo. Ao abrir, o app pergunta à API se já há uma sessão (o cookie
// HttpOnly `__Host-tl_sessao`, que vale 30 dias e que o app não vê). Sem sessão, entra pelo Google: o
// ID token vai uma vez só, no `POST /v1/conta`, que abre a sessão; daí em diante nenhum pedido leva
// token. Nada fica em localStorage nem em sessionStorage.
import { type ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { NavLink } from "react-router";
import { conteudoDoApp, paginasDoApp, planos } from "../conteudo";
import { URL_DO_SITE } from "../site/textos";
import { linkDoClassico } from "./classico";
import { ErroDaApi, SESSAO, pedir } from "./api";
import { BaixarMeusDados } from "./BaixarMeusDados";
import { Icone } from "./Icone";
import { type GoogleId, carregarGoogle } from "./login";
import { PaginaDeEntrada } from "./PaginaDeEntrada";
import type { EuV1 } from "./tipos";

interface Conta {
  token: string | null; // `SESSAO` depois de entrar (o que as telas passam ao `pedir`), null antes
  eu: EuV1 | null;
  entrando: boolean; // conferindo a sessão ao abrir, ou abrindo a sessão depois do Google
  erro: ErroDaApi | null;
  google: GoogleId | null; // o Google já iniciado (initialize): só então dá para desenhar o botão
  precisaAceitar: boolean; // a conta existe, mas ainda não aceitou os termos atuais
  aceitar(querNovidades: boolean): Promise<void>;
  pedirAceite(): void; // os termos mudaram no meio do uso: volta para a tela do aceite
  sair(): void;
}

const ContextoDaConta = createContext<Conta | null>(null);

/** A conta logada (dentro do `ProvedorDaConta`), ou null fora dele (API desligada). */
export function useConta(): Conta | null {
  return useContext(ContextoDaConta);
}

export function nomeDoPlano(plano: string): string {
  return planos.nomes.find((nome) => nome.toLowerCase() === plano.toLowerCase()) ?? plano;
}

export function ProvedorDaConta({ clientId, children }: { clientId: string; children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [eu, setEu] = useState<EuV1 | null>(null);
  const [erro, setErro] = useState<ErroDaApi | null>(null);
  const [precisaAceitar, setPrecisaAceitar] = useState(false);
  const [google, setGoogle] = useState<GoogleId | null>(null);
  const [entrando, setEntrando] = useState(true);
  const [sessaoConferida, setSessaoConferida] = useState(false);
  const jaPediuAoGoogle = useRef(false);

  // lê a conta da sessão; `acabouDeEntrar`: a sessão foi aberta agora, então uma recusa é erro a
  // mostrar (ao abrir a página, a falta de sessão é o normal: segue para o login, sem aviso)
  const lerAConta = useCallback(async (acabouDeEntrar: boolean) => {
    try {
      const lida = await pedir<EuV1>("/v1/eu", SESSAO);
      setToken(SESSAO);
      setEu(lida);
    } catch (falha: unknown) {
      if (falha instanceof ErroDaApi && falha.tipo === "termos") {
        setToken(SESSAO); // a sessão continua: a tela do aceite usa
        setPrecisaAceitar(true);
        return;
      }
      setToken(null);
      setEu(null);
      if (acabouDeEntrar) setErro(comoErroDaApi(falha));
    }
  }, []);

  useEffect(() => {
    lerAConta(false).finally(() => {
      setEntrando(false);
      setSessaoConferida(true);
    });
  }, [lerAConta]);

  useEffect(() => {
    let valendo = true;
    carregarGoogle()
      .then((id) => {
        if (!valendo) return;
        id.initialize({
          client_id: clientId,
          callback: (resposta) => {
            setErro(null);
            setEntrando(true);
            // cria a conta na primeira vez (as regras do app atual) e abre a sessão (o cookie)
            pedir<unknown>("/v1/conta", resposta.credential, {}, {})
              .then(() => lerAConta(true))
              .catch((falha: unknown) => setErro(comoErroDaApi(falha)))
              .finally(() => setEntrando(false));
          },
          auto_select: true,
          use_fedcm_for_prompt: true,
        });
        setGoogle(id);
      })
      .catch(() => {
        if (valendo) setErro(new ErroDaApi("rede", "Não deu para carregar o login do Google."));
      });
    return () => {
      valendo = false;
    };
  }, [clientId, lerAConta]);

  // o login automático do Google só quando não há sessão (e uma vez: depois do Sair, não volta sozinho)
  useEffect(() => {
    if (google === null || !sessaoConferida || token !== null || jaPediuAoGoogle.current) return;
    jaPediuAoGoogle.current = true;
    google.prompt();
  }, [google, sessaoConferida, token]);

  const aceitar = useCallback(
    async (querNovidades: boolean) => {
      if (token === null) return;
      const { versao, novidades } = conteudoDoApp.aceite;
      const lida = await pedir<EuV1>("/v1/aceite-dos-termos", token, {}, {
        versao,
        novidades: querNovidades,
        versao_das_novidades: novidades.versao,
      });
      setEu(lida);
      setPrecisaAceitar(false);
    },
    [token],
  );

  const pedirAceite = useCallback(() => {
    setEu(null);
    setPrecisaAceitar(true);
  }, []);

  const sair = useCallback(() => {
    // encerra a sessão no servidor (e o cookie); se a rede falhar, a tela sai do mesmo jeito
    if (token !== null) pedir<undefined>("/v1/sair", token, {}, {}).catch(() => undefined);
    google?.disableAutoSelect();
    setToken(null);
    setEu(null);
    setErro(null);
    setPrecisaAceitar(false);
  }, [google, token]);

  return (
    <ContextoDaConta.Provider
      value={{ token, eu, entrando, erro, google, precisaAceitar, aceitar, pedirAceite, sair }}
    >
      {children}
    </ContextoDaConta.Provider>
  );
}

function comoErroDaApi(falha: unknown): ErroDaApi {
  return falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha));
}

const SAIDA_DE_CADA_ERRO: Partial<Record<ErroDaApi["tipo"], [string, string]>> = {
  "sessao-vencida": ["Sua sessão terminou. Entre de novo para continuar.", ""],
  "conta-nova": ["Não deu para criar a sua conta agora. Tente entrar de novo em instantes.", ""],
};

// o Google desenha o botão com largura fixa, entre 200 e 400 px: o do cartão ocupa a largura dele
const LARGURA_DO_BOTAO = { minima: 200, maxima: 400 };

/** O botão do Google e, se a API recusou a conta, o motivo e o caminho para resolver. */
function Entrada({ erro }: { erro: ErroDaApi | null }) {
  const botao = useRef<HTMLDivElement>(null);
  const google = useConta()?.google ?? null;
  const { titulo, explicacao, lembrete_da_versao_classica, aviso } = conteudoDoApp.entrada;
  useEffect(() => {
    // só depois do initialize do Provedor (os efeitos do React rodam do filho para o pai): antes
    // disso o Google recusa o botão e não desenha nada; quem não tinha o login automático ficava sem entrar
    if (google && botao.current) {
      const largura = Math.min(
        LARGURA_DO_BOTAO.maxima,
        Math.max(LARGURA_DO_BOTAO.minima, botao.current.offsetWidth),
      );
      google.renderButton(botao.current, {
        theme: "outline",
        size: "large",
        text: "signin_with",
        locale: "pt-BR",
        width: largura,
      });
    }
  }, [google]);
  const saida = erro ? SAIDA_DE_CADA_ERRO[erro.tipo] : undefined;
  return (
    <section className="cartao-de-entrada">
      <h1>{titulo}</h1>
      <p className="apagado">{explicacao}</p>
      {erro ? (
        <p className="erro-do-app" role="alert">
          {saida ? saida[0] : erro.message}
        </p>
      ) : null}
      {saida?.[1] ? (
        <a className="botao primario" href={linkDoClassico()}>
          {saida[1]}
        </a>
      ) : null}
      {/* vazio até o Google desenhar o botão: o CSS mostra um esqueleto do mesmo tamanho (sem buraco) */}
      <div ref={botao} className="botao-do-google" aria-busy={google === null} />
      <p className="lembrete-da-entrada">{lembrete_da_versao_classica}</p>
      <p className="apagado aviso-da-entrada">{aviso}</p>
      <p className="textos-legais">
        <TextoLegal titulo="Termos de uso" pagina="termos" />
        <TextoLegal titulo="Política de privacidade" pagina="privacidade" />
      </p>
    </section>
  );
}

/** Um texto legal, aberto noutra aba na página do site (o mesmo texto: as duas saem de conteudo/ no
 * mesmo build). O app não põe HTML pronto na tela (testes/app/esqueleto.test.tsx). */
function TextoLegal({ titulo, pagina }: { titulo: string; pagina: string }) {
  return (
    <a className="texto-legal" href={`${URL_DO_SITE}/${pagina}.html`} target="_blank" rel="noopener">
      {titulo}
    </a>
  );
}

/** Primeiro acesso ou termos novos: a pessoa lê e confirma antes de abrir qualquer tela. */
function AceiteDosTermos({ conta }: { conta: Conta }) {
  const { titulo, introducao, caixa, novidades, sem_o_aceite } = conteudoDoApp.aceite;
  const [aceitou, setAceitou] = useState(false);
  const [querNovidades, setQuerNovidades] = useState(false); // opt-in: começa desmarcada
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const continuar = () => {
    setEnviando(true);
    setFalha(null);
    conta
      .aceitar(querNovidades)
      .catch((erro: unknown) => setFalha(erro instanceof Error ? erro.message : String(erro)))
      .finally(() => setEnviando(false));
  };
  return (
    <section className="aviso-do-app">
      <h1>{titulo}</h1>
      <p>{introducao}</p>
      <p className="textos-legais">
        <TextoLegal titulo="Termos de uso" pagina="termos" />
        <TextoLegal titulo="Política de privacidade" pagina="privacidade" />
      </p>
      <label className="marcar">
        <input type="checkbox" checked={aceitou} onChange={(ev) => setAceitou(ev.target.checked)} />
        {caixa}
      </label>
      <label className="marcar">
        <input type="checkbox" checked={querNovidades} onChange={(ev) => setQuerNovidades(ev.target.checked)} />
        {novidades.texto}
      </label>
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
      <div className="botoes-do-aceite">
        <button type="button" className="botao primario" disabled={!aceitou || enviando} onClick={continuar}>
          Continuar
        </button>
        <button type="button" className="botao" onClick={conta.sair}>
          Sair
        </button>
      </div>
      {/* LGPD: termos novos sem aceite não prendem os dados de quem já tem conta */}
      <details className="sem-o-aceite">
        <summary>{sem_o_aceite.titulo}</summary>
        <p className="apagado">{sem_o_aceite.explicacao}</p>
        <BaixarMeusDados token={conta.token} />
        <a className="botao" href={linkDoClassico("meus-dados")}>
          Apagar a conta (na versão clássica)
        </a>
      </details>
    </section>
  );
}

/** Mostra as telas só para quem entrou e foi aceito pela API. Antes disso, a página de entrada, sem a
 * moldura do app: o login, o "Entrando…" e o aceite dos termos. */
export function ExigeLogin({ children }: { children: ReactNode }) {
  const conta = useConta();
  if (conta?.eu) return <>{children}</>;
  let cartao: ReactNode;
  if (conta?.token && conta.precisaAceitar) cartao = <AceiteDosTermos conta={conta} />;
  else if (conta?.token || conta?.entrando)
    cartao = (
      <p className="apagado" role="status">
        Entrando…
      </p>
    );
  else cartao = <Entrada erro={conta?.erro ?? null} />;
  return <PaginaDeEntrada>{cartao}</PaginaDeEntrada>;
}

// as telas da área Conta (ADR 0096), na ordem de src/paginas.py: ficam no menu da pessoa, não no lateral
const TELAS_DA_CONTA = (conteudoDoApp.areas.find((a) => a.chave === "conta")?.paginas ?? []).flatMap((chave) =>
  paginasDoApp.filter((p) => p.chave === chave && p.no_menu && p.contrato !== null),
);

/** O nome e o plano no topo: abre o menu da pessoa (simulações, dados, plano). O Sair fica à vista. */
export function ContaNoTopo() {
  const conta = useConta();
  const menu = useRef<HTMLDetailsElement>(null);
  if (!conta?.eu) return null;
  const nome = conta.eu.nome ?? "Sua conta";
  // escolher uma tela fecha o menu (a moldura continua na página; sem isso ele ficaria aberto)
  const fechar = () => {
    if (menu.current) menu.current.open = false;
  };
  return (
    <span className="conta-no-topo">
      <details ref={menu} className="menu-da-conta">
        <summary title="Sua conta">
          <Icone nome="conta" />
          <span className="nome-da-conta">
            {nome} · {nomeDoPlano(conta.eu.plano)}
          </span>
        </summary>
        <div className="lista-da-conta">
          {TELAS_DA_CONTA.map((pagina) => (
            <NavLink key={pagina.chave} to={`/${pagina.url}`} onClick={fechar}>
              {pagina.titulo}
            </NavLink>
          ))}
        </div>
      </details>
      <button type="button" className="botao pequeno" onClick={conta.sair}>
        Sair
      </button>
    </span>
  );
}
