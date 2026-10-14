// A conta de quem está usando o app novo. O ID token do Google fica só na memória (estado do React):
// nada em localStorage, sessionStorage ou cookie. Recarregar a página pede o login de novo (o Google
// entra sozinho se a pessoa já autorizou: auto_select).
import { type ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { conteudoDoApp, planos } from "../conteudo";
import { URL_DO_SITE, linkDoApp } from "../site/textos";
import { ErroDaApi, pedir } from "./api";
import { FundoDoApp } from "./FundoDoApp";
import { type GoogleId, carregarGoogle } from "./login";
import type { EuV1 } from "./tipos";

interface Conta {
  token: string | null;
  eu: EuV1 | null;
  erro: ErroDaApi | null;
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
  const google = useRef<GoogleId | null>(null);

  useEffect(() => {
    let valendo = true;
    carregarGoogle()
      .then((id) => {
        if (!valendo) return;
        google.current = id;
        id.initialize({
          client_id: clientId,
          callback: (resposta) => {
            setErro(null);
            setToken(resposta.credential);
          },
          auto_select: true,
          use_fedcm_for_prompt: true,
        });
        id.prompt();
      })
      .catch(() => {
        if (valendo) setErro(new ErroDaApi("rede", "Não deu para carregar o login do Google."));
      });
    return () => {
      valendo = false;
    };
  }, [clientId]);

  useEffect(() => {
    if (token === null) return;
    let valendo = true;
    pedir<EuV1>("/v1/eu", token)
      .catch((falha: unknown) => {
        // primeiro login: a API cria a conta com o mesmo token (as regras do app atual) e lê de novo
        if (!(falha instanceof ErroDaApi) || falha.tipo !== "conta-nova") throw falha;
        return pedir<EuV1>("/v1/conta", token, {}, {}).then(() => pedir<EuV1>("/v1/eu", token));
      })
      .then((lida) => {
        if (valendo) setEu(lida);
      })
      .catch((falha: unknown) => {
        if (!valendo) return;
        if (falha instanceof ErroDaApi && falha.tipo === "termos") {
          setPrecisaAceitar(true); // o token continua: a tela do aceite usa
          return;
        }
        setToken(null);
        setEu(null);
        setErro(falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha)));
      });
    return () => {
      valendo = false;
    };
  }, [token]);

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
    google.current?.disableAutoSelect();
    setToken(null);
    setEu(null);
    setErro(null);
    setPrecisaAceitar(false);
  }, []);

  return (
    <ContextoDaConta.Provider value={{ token, eu, erro, precisaAceitar, aceitar, pedirAceite, sair }}>
      {children}
    </ContextoDaConta.Provider>
  );
}

const SAIDA_DE_CADA_ERRO: Partial<Record<ErroDaApi["tipo"], [string, string]>> = {
  "sessao-vencida": ["Sua sessão terminou. Entre de novo para continuar.", ""],
  "conta-nova": ["Não deu para criar a sua conta agora. Tente entrar de novo em instantes.", ""],
};

/** O botão do Google e, se a API recusou a conta, o motivo e o caminho para resolver. */
function Entrada({ erro }: { erro: ErroDaApi | null }) {
  const botao = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let valendo = true;
    void carregarGoogle().then((id) => {
      if (valendo && botao.current) {
        id.renderButton(botao.current, { theme: "outline", size: "large", text: "signin_with", locale: "pt-BR" });
      }
    });
    return () => {
      valendo = false;
    };
  }, []);
  const saida = erro ? SAIDA_DE_CADA_ERRO[erro.tipo] : undefined;
  return (
    <section className="aviso-do-app">
      <h1>Entre com o Google</h1>
      <p>Use a mesma conta do Google do app de sempre. Os números são os mesmos.</p>
      {erro ? (
        <p className="erro-do-app" role="alert">
          {saida ? saida[0] : erro.message}
        </p>
      ) : null}
      {saida?.[1] ? (
        <a className="botao primario" href={linkDoApp()}>
          {saida[1]}
        </a>
      ) : null}
      <div ref={botao} className="botao-do-google" />
      <p className="apagado">{conteudoDoApp.entrada.aviso}</p>
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
  const { titulo, introducao, caixa, novidades } = conteudoDoApp.aceite;
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
    </section>
  );
}

/** Mostra as telas só para quem entrou e foi aceito pela API. */
export function ExigeLogin({ children }: { children: ReactNode }) {
  const conta = useConta();
  if (conta?.eu) return <>{children}</>;
  if (conta?.token && conta.precisaAceitar) return <AceiteDosTermos conta={conta} />;
  if (conta?.token) return <p className="apagado" role="status">Entrando…</p>;
  return (
    <FundoDoApp>
      <Entrada erro={conta?.erro ?? null} />
    </FundoDoApp>
  );
}

/** O nome e o plano no topo, com o botão de sair. */
export function ContaNoTopo() {
  const conta = useConta();
  if (!conta?.eu) return null;
  const nome = conta.eu.nome ?? "Sua conta";
  return (
    <span className="conta-no-topo">
      <span>
        {nome} · {nomeDoPlano(conta.eu.plano)}
      </span>
      <button type="button" className="botao pequeno" onClick={conta.sair}>
        Sair
      </button>
    </span>
  );
}
