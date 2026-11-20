// A caixa de busca com sugestões das ferramentas do analista (o combobox com lista do WAI-ARIA, como o campo Ativo):
// digita-se, as setas andam na lista, Enter escolhe e Esc fecha; no celular, toca-se na sugestão. Quem decide o que
// sugerir é quem usa a caixa (as atividades do CNAE em "Quem já se mexeu", as seções em "Encontrar empresas").
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

/** Uma sugestão: o nome, uma linha de detalhe embaixo (opcional) e o código à direita (opcional). */
export interface Sugestao {
  chave: string;
  nome: string;
  detalhe?: string;
  codigo?: string;
}

interface Propriedades {
  rotulo: string;
  texto: string;
  sugestoes: (texto: string) => Sugestao[];
  rotuloDaLista: string;
  placeholder: string;
  dica?: string; // a linha de baixo (o que foi escolhido, ou como usar o campo)
  desligada?: boolean;
  aoDigitar(texto: string): void;
  aoEscolher(chave: string): void;
}

export function CaixaDeSugestoes({
  rotulo,
  texto,
  sugestoes,
  rotuloDaLista,
  placeholder,
  dica,
  desligada = false,
  aoDigitar,
  aoEscolher,
}: Propriedades) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  const [marcada, setMarcada] = useState(-1); // a sugestão em destaque (setas), -1 = nenhuma
  const lista = useRef<HTMLUListElement>(null);

  const opcoes = aberta && !desligada ? sugestoes(texto) : [];
  const idDaOpcao = (i: number) => `${id}-opcao-${i}`;

  useEffect(() => {
    if (marcada >= 0) lista.current?.children[marcada]?.scrollIntoView?.({ block: "nearest" });
  }, [marcada]);

  const fechar = () => {
    setAberta(false);
    setMarcada(-1);
  };
  const digitar = (novo: string) => {
    setAberta(true);
    setMarcada(-1);
    aoDigitar(novo);
  };
  const escolher = (sugestao: Sugestao) => {
    fechar();
    aoEscolher(sugestao.chave);
  };
  const teclar = (evento: KeyboardEvent<HTMLInputElement>) => {
    const total = opcoes.length;
    if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
      evento.preventDefault();
      if (!aberta) return setAberta(true);
      if (total === 0) return;
      const passo = evento.key === "ArrowDown" ? 1 : -1;
      setMarcada((m) => (m < 0 ? (passo > 0 ? 0 : total - 1) : (m + passo + total) % total));
    } else if (evento.key === "Enter" && marcada >= 0 && marcada < total) {
      evento.preventDefault(); // escolhe na lista sem enviar o formulário
      escolher(opcoes[marcada]);
    } else if (evento.key === "Escape" && total > 0) {
      evento.preventDefault();
      fechar();
    }
  };

  return (
    <div className="campo-do-ativo campo-do-setor">
      <label>
        <span>{rotulo}</span>
        <input
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={opcoes.length > 0}
          aria-controls={`${id}-lista`}
          aria-activedescendant={marcada >= 0 && marcada < opcoes.length ? idDaOpcao(marcada) : undefined}
          aria-describedby={dica ? `${id}-dica` : undefined}
          value={texto}
          disabled={desligada}
          onChange={(ev) => digitar(ev.target.value)}
          onKeyDown={teclar}
          onFocus={() => setAberta(true)}
          onBlur={fechar}
          maxLength={120}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <ul
        className="sugestoes-do-ativo"
        id={`${id}-lista`}
        role="listbox"
        aria-label={rotuloDaLista}
        ref={lista}
        hidden={opcoes.length === 0}
      >
        {opcoes.map((s, i) => (
          <li
            key={s.chave}
            id={idDaOpcao(i)}
            role="option"
            aria-selected={i === marcada}
            // o mousedown tiraria o foco do campo (e fecharia a lista) antes do clique
            onMouseDown={(ev) => ev.preventDefault()}
            onClick={() => escolher(s)}
          >
            <span>
              {s.nome}
              {s.detalhe ? <small className="detalhe-da-sugestao">{s.detalhe}</small> : null}
            </span>
            {s.codigo ? <span className="codigo-da-sugestao">{s.codigo}</span> : null}
          </li>
        ))}
      </ul>
      <span className="so-para-leitor" aria-live="polite">
        {aberta && texto.trim() !== "" ? `${opcoes.length} sugestões` : ""}
      </span>
      {dica ? (
        <small className="dica-do-setor" id={`${id}-dica`}>
          {dica}
        </small>
      ) : null}
    </div>
  );
}
