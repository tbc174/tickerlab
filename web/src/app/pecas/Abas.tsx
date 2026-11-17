// Peça única: as abas de uma tela (a ficha da empresa: Resumo, Cadastro, Quem controla...). Segue o padrão
// de abas do WAI-ARIA: as setas, Home e End trocam de aba; o Tab vai da aba para o conteúdo. Com `parametro`,
// a aba aberta fica no endereço (`?aba=cadastro`): o link copiado abre na mesma aba e o "voltar" do navegador
// funciona. Só o conteúdo da aba aberta é montado: a aba que busca dado só busca quando a pessoa a abre.
// A exceção é a aba marcada com `sempreMontada`, que fica no documento, escondida, quando outra abre.
import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";
import { useSearchParams } from "react-router";

export interface Aba {
  /** Estável e sem acento: vai para o endereço. */
  chave: string;
  rotulo: string;
  conteudo: ReactNode;
  /** Um número pequeno ao lado do rótulo (quantos eventos, quantos sinais). */
  contagem?: number;
  /** O conteúdo continua montado, escondido, quando outra aba abre: para a aba que guarda o que a pessoa
   * não pode perder ao trocar de aba (um valor que só aparece uma vez). */
  sempreMontada?: boolean;
}

interface Propriedades {
  /** O que as abas dividem, para o leitor de tela ("Partes da ficha"). */
  rotulo: string;
  abas: Aba[];
  /** Nome do parâmetro do endereço que guarda a aba aberta; sem ele, a aba vale só enquanto a tela vive. */
  parametro?: string;
  /** A aba aberta, quando quem manda nela é quem usa a peça (junto com `aoAbrir`): a tela que precisa
   * trocar de aba sozinha. Sem isto, a peça guarda a aba (ou o endereço, com `parametro`). */
  aberta?: string;
  aoAbrir?(chave: string): void;
}

const TECLAS: Record<string, (atual: number, total: number) => number> = {
  ArrowRight: (atual, total) => (atual + 1) % total,
  ArrowLeft: (atual, total) => (atual - 1 + total) % total,
  Home: () => 0,
  End: (_, total) => total - 1,
};

export function Abas({ rotulo, abas, parametro, aberta: mandada, aoAbrir }: Propriedades) {
  const prefixo = useId();
  const botoes = useRef<(HTMLButtonElement | null)[]>([]);
  const [consulta, setConsulta] = useSearchParams();
  const [local, setLocal] = useState(abas[0]?.chave);
  const pedida = mandada ?? (parametro ? consulta.get(parametro) : local);
  // chave desconhecida no endereço (link antigo, aba que não existe para esta empresa): a primeira
  const aberta = abas.find((aba) => aba.chave === pedida) ?? abas[0];
  if (!aberta) return null;

  const abrir = (chave: string) => {
    if (aoAbrir) return aoAbrir(chave);
    if (!parametro) return setLocal(chave);
    const nova = new URLSearchParams(consulta);
    nova.set(parametro, chave);
    setConsulta(nova, { replace: false, preventScrollReset: true });
  };
  const aoTeclar = (evento: KeyboardEvent, indice: number) => {
    const proxima = TECLAS[evento.key]?.(indice, abas.length);
    if (proxima === undefined) return;
    evento.preventDefault();
    abrir(abas[proxima]!.chave);
    botoes.current[proxima]?.focus();
  };

  const doPainel = (aba: Aba) => ({
    className: "aba-painel",
    role: "tabpanel",
    id: `${prefixo}-painel-${aba.chave}`,
    "aria-labelledby": `${prefixo}-aba-${aba.chave}`,
    tabIndex: 0,
  });

  return (
    <div className="abas-da-tela">
      <div className="abas-lista" role="tablist" aria-label={rotulo}>
        {abas.map((aba, indice) => {
          const marcada = aba.chave === aberta.chave;
          return (
            <button
              key={aba.chave}
              ref={(botao) => {
                botoes.current[indice] = botao;
              }}
              type="button"
              role="tab"
              id={`${prefixo}-aba-${aba.chave}`}
              aria-selected={marcada}
              aria-controls={`${prefixo}-painel-${aba.chave}`}
              tabIndex={marcada ? 0 : -1}
              onClick={() => abrir(aba.chave)}
              onKeyDown={(evento) => aoTeclar(evento, indice)}
            >
              {aba.rotulo}
              {aba.contagem !== undefined ? <span className="aba-contagem">{aba.contagem}</span> : null}
            </button>
          );
        })}
      </div>
      {abas
        .filter((aba) => aba.sempreMontada)
        .map((aba) => (
          <div key={aba.chave} {...doPainel(aba)} hidden={aba.chave !== aberta.chave}>
            {aba.conteudo}
          </div>
        ))}
      {/* sem `key`: o painel das outras abas é um só, como sempre foi */}
      {aberta.sempreMontada ? null : <div {...doPainel(aberta)}>{aberta.conteudo}</div>}
    </div>
  );
}
