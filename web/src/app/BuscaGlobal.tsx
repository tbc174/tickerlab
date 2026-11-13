// A busca do topo (linha 903): abre com o botão ou com Ctrl K (Cmd K no Mac) em qualquer tela. Acha uma tela
// pelo nome e abre a ficha de um CNPJ digitado inteiro. O CNPJ vai pelo estado da navegação, nunca pelo
// endereço. Empresa pelo nome não se busca aqui, e a busca diz: por setor e estado, a tela é "Encontrar empresas".
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import type { PaginaDoApp } from "../conteudo";
import { useDialogo } from "./dialogo";
import { Icone } from "./Icone";
import { TELAS_DO_APP, temTelaPronta } from "./rotas";

const ROTULO = "Buscar tela ou abrir um CNPJ";
const MAXIMO_DE_TELAS = 8;
const TAMANHO_MAXIMO = 40;
// o CNPJ como o analista digita ou cola: 14 posições (letras nas 12 primeiras desde 2026), com ou sem pontuação
const PONTUACAO_DO_CNPJ = /[./\-\s]/g;
const CNPJ = /^[0-9A-Z]{12}\d{2}$/;

export interface Destino {
  chave: string;
  titulo: string;
  descricao: string;
  endereco: string;
}

const INICIO: Destino = { chave: "inicio", titulo: "Início", descricao: "A página inicial do app.", endereco: "/" };
const paraDestino = (pagina: PaginaDoApp): Destino => ({
  chave: pagina.chave,
  titulo: pagina.titulo,
  descricao: pagina.descricao,
  endereco: `/${pagina.url}`,
});
// o Pulse é o próprio Início
const TELAS: Destino[] = [
  INICIO,
  ...TELAS_DO_APP.filter((p) => p.no_menu && p.chave !== "pulse" && temTelaPronta(p.chave)).map(paraDestino),
];
const FICHA = TELAS.find((tela) => tela.chave === "ficha_da_empresa");
const ENCONTRAR = TELAS.find((tela) => tela.chave === "encontrar_empresas");

/** Sem acento e em minúsculas: "inicio" acha "Início". */
const simples = (texto: string) =>
  texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

/** O CNPJ digitado inteiro, sem a pontuação; outro texto, null. */
export function cnpjDigitado(texto: string): string | null {
  const limpo = texto.replace(PONTUACAO_DO_CNPJ, "").toUpperCase();
  return CNPJ.test(limpo) ? limpo : null;
}

/** As telas cujo nome (ou, depois, a descrição) contém o texto; sem texto, as primeiras do app. */
export function telasDaBusca(texto: string): Destino[] {
  const procurado = simples(texto.trim());
  if (procurado === "") return TELAS.slice(0, MAXIMO_DE_TELAS);
  const peloNome = TELAS.filter((tela) => simples(tela.titulo).includes(procurado));
  const pelaDescricao = TELAS.filter(
    (tela) => !peloNome.includes(tela) && simples(tela.descricao).includes(procurado),
  );
  return [...peloNome, ...pelaDescricao].slice(0, MAXIMO_DE_TELAS);
}

const eMac = () => /Mac|iPhone|iPad/.test(navigator.platform ?? "");

/** O campo e o que a busca achou: o CNPJ digitado inteiro, as telas pelo nome ou o aviso de que não há. */
function Achados({ texto, mudarTexto, sair }: { texto: string; mudarTexto(texto: string): void; sair(): void }) {
  const navegar = useNavigate();
  const cnpj = FICHA ? cnpjDigitado(texto) : null;
  const telas = useMemo(() => (cnpj ? [] : telasDaBusca(texto)), [cnpj, texto]);
  const abrirAFicha = () => {
    if (!FICHA || !cnpj) return;
    navegar(FICHA.endereco, { state: { cnpj } });
    sair();
  };
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (cnpj) abrirAFicha();
    else if (telas.length > 0) {
      navegar(telas[0].endereco);
      sair();
    }
  };
  return (
    <>
      <form onSubmit={enviar}>
        <label>
          <span className="pular-leitura">{ROTULO}</span>
          <input
            type="search"
            value={texto}
            onChange={(evento) => mudarTexto(evento.target.value)}
            placeholder="Nome de uma tela ou um CNPJ inteiro"
            autoComplete="off"
            maxLength={TAMANHO_MAXIMO}
            autoFocus
          />
        </label>
      </form>
      {cnpj ? (
        <button type="button" className="resultado-da-busca" onClick={abrirAFicha}>
          <strong>Abrir a ficha deste CNPJ</strong>
          <span className="apagado">Abre a tela "{FICHA?.titulo}" com o CNPJ digitado.</span>
        </button>
      ) : telas.length > 0 ? (
        <ul className="resultados-da-busca" aria-label="Telas encontradas">
          {telas.map((tela) => (
            <li key={tela.chave}>
              <Link className="resultado-da-busca" to={tela.endereco} onClick={sair}>
                <strong>{tela.titulo}</strong>
                <span className="apagado">{tela.descricao}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="apagado" role="status">
          Nenhuma tela com esse nome.
        </p>
      )}
      <p className="apagado nota-da-busca">
        A busca abre telas e a ficha de um CNPJ digitado inteiro.
        {ENCONTRAR ? (
          <>
            {" "}
            Para achar empresas pelo setor e pelo estado, use{" "}
            <Link to={ENCONTRAR.endereco} onClick={sair}>
              {ENCONTRAR.titulo}
            </Link>
            .
          </>
        ) : null}
      </p>
    </>
  );
}

export function BuscaGlobal() {
  const dialogo = useDialogo();
  const [texto, setTexto] = useState("");
  const { abrir, fechar, aberto } = dialogo;

  useEffect(() => {
    const atalho = (evento: KeyboardEvent) => {
      if ((evento.ctrlKey || evento.metaKey) && !evento.altKey && evento.key.toLowerCase() === "k") {
        evento.preventDefault(); // o navegador usa Ctrl K para a barra de endereço
        abrir();
      }
    };
    window.addEventListener("keydown", atalho);
    return () => window.removeEventListener("keydown", atalho);
  }, [abrir]);

  const sair = () => {
    fechar();
    setTexto("");
  };
  return (
    <>
      <button
        type="button"
        className="busca-do-topo"
        aria-haspopup="dialog"
        aria-expanded={aberto}
        aria-keyshortcuts="Control+K Meta+K"
        onClick={abrir}
      >
        <Icone nome="busca" />
        <span className="rotulo-da-busca">{ROTULO}</span>
        <kbd aria-hidden="true">{eMac() ? "⌘ K" : "Ctrl K"}</kbd>
      </button>
      <dialog
        ref={dialogo.ref}
        className="busca-global"
        aria-label="Busca"
        onClose={() => {
          dialogo.aoFechar();
          setTexto("");
        }}
        onClick={dialogo.aoClicarNoFundo}
      >
        {/* o miolo só existe com a busca aberta: fechada, ela não deixa texto nem link perdido na página */}
        {aberto ? <Achados texto={texto} mudarTexto={setTexto} sair={sair} /> : null}
      </dialog>
    </>
  );
}
