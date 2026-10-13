// A moldura de toda página do site: <head>, topo com o menu do tema, rodapé.
// Era a função `pagina()` de scripts/gerar_site.py; o HTML sai com a mesma estrutura.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { marca } from "../conteudo";
import { css } from "../estilo";
import { Bruto } from "./Bruto";
import {
  ASSINATURA,
  AVISO,
  EMAIL_DE_CONTATO,
  URL_DO_CODIGO,
  URL_DO_SITE,
  linkDoApp,
} from "./textos";

// O build roda dentro de web/ (npm run build): os arquivos do repositório ficam um nível acima.
const RAIZ_DO_REPOSITORIO = join(process.cwd(), "..");
// LF sempre (o Git no Windows pode tirar o arquivo com CRLF): o mesmo hash em todo lugar
const lerTexto = (caminho: string) => readFileSync(caminho, "utf8").replace(/\r\n/g, "\n");
export const SOL_JS = lerTexto(join(RAIZ_DO_REPOSITORIO, "static", "tema", "sol.js"));
export const SITE_JS = lerTexto(join(process.cwd(), "publico", "site.js"));

/** Um pedaço do hash do arquivo, no endereço: a Cloudflare e o navegador guardam o CSS e o JS por
 * horas, e um endereço novo a cada mudança faz todos buscarem a versão nova na hora. */
export function versao(conteudo: string): string {
  return createHash("sha256").update(conteudo, "utf8").digest("hex").slice(0, 12);
}

// Roda no <head>, antes de pintar a página (o sol.js vem antes, sem defer): decide o tema pela
// escolha guardada; quem nunca escolheu fica no Automático (claro de dia, escuro à noite, pelo fuso
// do aparelho). Também avisa o CSS que há JavaScript.
const TEMA_SALVO =
  '<script>(function () { var raiz = document.documentElement, escolha = "auto";' +
  ' raiz.classList.add("com-js");' +
  ' try { escolha = localStorage.getItem("tema") || "auto"; } catch (e) {}' +
  " var sol = window.TickerLabSol;" +
  ' var tema = escolha !== "auto" ? escolha' +
  ' : sol ? sol.temaDoMomento(new Date(), sol.fusoDoAparelho()) : "claro";' +
  " raiz.dataset.escolha = escolha;" +
  ' if (tema === "escuro") raiz.dataset.tema = "escuro"; })();</script>';

const ICONES_E_FONTE =
  '<link rel="icon" href="/marca/simbolo.svg" type="image/svg+xml">' +
  '<link rel="icon" href="/marca/icone.png" type="image/png">' +
  '<link rel="preload" href="/fontes/Manrope-VariableFont_wght.ttf" as="font" type="font/ttf" crossorigin>';

// ícones do Material ("light_mode", "dark_mode" e "contrast"); o botão mostra o da escolha atual
const ICONE_SOL =
  "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM2 13h2a1 1 0 0 0 0-2H2a1 1 0 0 0 0 2zm18 0h2a1" +
  " 1 0 0 0 0-2h-2a1 1 0 0 0 0 2zM11 2v2a1 1 0 0 0 2 0V2a1 1 0 0 0-2 0zm0 18v2a1 1 0 0 0 2 0v-2a1" +
  " 1 0 0 0-2 0zM5.99 4.58a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41L5.99 4.58zm12.37" +
  " 12.37a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41l-1.06-1.06zm1.06-10.96a1 1 0 0 0-1.41" +
  "-1.41l-1.06 1.06a1 1 0 0 0 1.41 1.41l1.06-1.06zM7.05 18.36a1 1 0 0 0-1.41-1.41l-1.06 1.06a1 1" +
  " 0 0 0 1.41 1.41l1.06-1.06z";
const ICONE_LUA =
  "M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 0 1-4.4 2.26 5.4 5.4 0 0 1" +
  "-3.14-9.8c-.44-.06-.9-.1-1.36-.1z";
const ICONE_AUTOMATICO =
  "M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10zm1-17.93c3.94.49" +
  " 7 3.85 7 7.93s-3.06 7.44-7 7.93V4.07z";

// (valor guardado, nome, ícone, explicação curta)
const OPCOES_DO_TEMA: [string, string, string, string][] = [
  ["claro", "Claro", ICONE_SOL, ""],
  ["escuro", "Escuro", ICONE_LUA, ""],
  ["auto", "Automático", ICONE_AUTOMATICO, "Claro de dia, escuro à noite"],
];

function Icone({ classe, desenho }: { classe: string; desenho: string }) {
  return (
    <svg className={classe} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d={desenho} />
    </svg>
  );
}

/** O botão do topo abre as três opções (o site.js cuida do teclado e de marcar a escolhida). */
function MenuDoTema() {
  return (
    <div className="tema-menu">
      <button
        className="tema"
        type="button"
        data-tema-botao=""
        aria-haspopup="menu"
        aria-expanded="false"
        aria-controls="opcoes-do-tema"
        aria-label="Tema: Automático"
      >
        {OPCOES_DO_TEMA.map(([valor, , desenho]) => (
          <Icone key={valor} classe={valor} desenho={desenho} />
        ))}
      </button>
      <div className="tema-opcoes" id="opcoes-do-tema" role="menu" aria-label="Tema" hidden>
        {OPCOES_DO_TEMA.map(([valor, nome, desenho, dica]) => (
          <button
            key={valor}
            type="button"
            role="menuitemradio"
            aria-checked="false"
            data-tema-escolha={valor}
          >
            <Icone classe="" desenho={desenho} />
            <span>
              {nome}
              {dica ? <small>{dica}</small> : null}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// o topo do símbolo segue o tema (marinho no claro, claro no escuro); a haste é sempre elétrica
function Logo() {
  return (
    <a className="marca" href="/" aria-label="TickerLab, página inicial">
      <Bruto html={marca.simbolo_svg} />
      <span>
        Ticker<b>Lab</b>
      </span>
    </a>
  );
}

const ITENS_DO_TOPO: [string, string][] = [
  ["/produto.html", "Produto"],
  ["/como-funciona.html", "Como funciona"],
  ["/#relatorios", "Relatórios"],
  ["/precos.html", "Planos"],
  ["/aprender.html", "Aprender"],
  ["/sobre.html", "Sobre"],
];

function Topo({ atual }: { atual: string }) {
  return (
    <header className="topo">
      <div className="faixa">
        <Logo />
        <nav aria-label="Principal">
          {ITENS_DO_TOPO.map(([href, nome]) => (
            <a key={href} href={href} aria-current={href === atual ? "page" : undefined}>
              {nome}
            </a>
          ))}
        </nav>
        <MenuDoTema />
        <a className="botao primario pequeno" href={linkDoApp()}>
          Abrir o app
        </a>
      </div>
    </header>
  );
}

function Rodape() {
  return (
    <footer className="rodape escura">
      <div className="faixa">
        <div>
          <Logo />
          <p className="apagado">{ASSINATURA}</p>
        </div>
        <nav aria-label="Rodapé">
          <a href="/sobre.html">Sobre</a>
          <a href="/metodologia.html">Fontes e metodologia</a>
          <a href="/precos.html">Planos</a>
          <a href="/termos.html">Termos de uso</a>
          <a href="/privacidade.html">Privacidade</a>
          <a href={URL_DO_CODIGO} rel="noopener">
            Código no GitHub
          </a>
          <a href={`mailto:${EMAIL_DE_CONTATO}`}>{EMAIL_DE_CONTATO}</a>
        </nav>
        <p className="aviso">{AVISO}</p>
      </div>
    </footer>
  );
}

export interface DadosDaPagina {
  caminho: string; // "/", "/produto.html"...
  titulo: string;
  descricao: string;
  atual?: string; // o item do topo marcado como página atual
}

export function Documento({
  caminho,
  titulo,
  descricao,
  atual = "",
  children,
}: DadosDaPagina & { children: ReactNode }) {
  const tituloCompleto = caminho === "/" ? "TickerLab" : `${titulo} · TickerLab`;
  const endereco = `${URL_DO_SITE}${caminho}`;
  return (
    <html lang="pt-BR">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{tituloCompleto}</title>
        <meta name="description" content={descricao} />
        <link rel="canonical" href={endereco} />
        <meta property="og:title" content={tituloCompleto} />
        <meta property="og:description" content={descricao} />
        <meta property="og:type" content="website" />
        <meta property="og:url" content={endereco} />
        <meta property="og:image" content={`${URL_DO_SITE}/marca/compartilhamento.png`} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content={`TickerLab: ${ASSINATURA}`} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="theme-color" content={marca.claro} />
        <script src={`/tema/sol.js?v=${versao(SOL_JS)}`} />
        <Bruto html={TEMA_SALVO} />
        {/* HTML pronto: com <link> do React, o React 19 sobe estes para antes dos scripts do tema */}
        <Bruto html={ICONES_E_FONTE} />
        <link rel="stylesheet" href={`/estilo.css?v=${versao(css())}`} />
        <script src={`/site.js?v=${versao(SITE_JS)}`} defer />
      </head>
      <body>
        <a className="pular" href="#conteudo">
          Pular para o conteúdo
        </a>
        <Topo atual={atual} />
        <main id="conteudo">{children}</main>
        <Rodape />
      </body>
    </html>
  );
}
