// A conta de quem está usando o app novo. O ID token do Google fica só na memória (estado do React):
// nada em localStorage, sessionStorage ou cookie. Recarregar a página pede o login de novo (o Google
// entra sozinho se a pessoa já autorizou: auto_select).
import { type ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { planos } from "../conteudo";
import { linkDoApp } from "../site/textos";
import { ErroDaApi, pedir } from "./api";
import { FundoDoApp } from "./FundoDoApp";
import { type GoogleId, carregarGoogle } from "./login";
import type { EuV1 } from "./tipos";

interface Conta {
  token: string | null;
  eu: EuV1 | null;
  erro: ErroDaApi | null;
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
      .then((lida) => {
        if (valendo) setEu(lida);
      })
      .catch((falha: unknown) => {
        if (!valendo) return;
        setToken(null);
        setEu(null);
        setErro(falha instanceof ErroDaApi ? falha : new ErroDaApi("indisponivel", String(falha)));
      });
    return () => {
      valendo = false;
    };
  }, [token]);

  const sair = useCallback(() => {
    google.current?.disableAutoSelect();
    setToken(null);
    setEu(null);
    setErro(null);
  }, []);

  return (
    <ContextoDaConta.Provider value={{ token, eu, erro, sair }}>{children}</ContextoDaConta.Provider>
  );
}

const SAIDA_DE_CADA_ERRO: Partial<Record<ErroDaApi["tipo"], [string, string]>> = {
  "sessao-vencida": ["Sua sessão terminou. Entre de novo para continuar.", ""],
  "conta-nova": [
    "Esta conta ainda não existe no TickerLab. Crie a conta no app atual (é o mesmo login) e volte aqui.",
    "Criar a conta no app",
  ],
  termos: ["Os termos de uso mudaram. Aceite os termos no app atual e volte aqui.", "Aceitar os termos no app"],
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
    </section>
  );
}

/** Mostra as telas só para quem entrou e foi aceito pela API. */
export function ExigeLogin({ children }: { children: ReactNode }) {
  const conta = useConta();
  if (conta?.eu) return <>{children}</>;
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
