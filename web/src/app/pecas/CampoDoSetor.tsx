// O campo de setor das ferramentas do analista: uma caixa de busca nas atividades do CNAE (o combobox com lista
// do WAI-ARIA, como o campo Ativo). Digita-se o nome ("farmácia", "transporte de carga") ou o código; as setas
// andam na lista, Enter escolhe e Esc fecha; no celular, toca-se na sugestão. Cada sugestão mostra o nome e o
// código. Quem sabe o código digita os 5 ou 7 dígitos e segue sem escolher na lista.
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { type AtividadeDoCnae, carregarCnaes, cnaeComPontuacao, sugestoesDeCnae } from "../buscaDeCnaes";

/** As atividades do CNAE, carregadas quando a tela abre (null enquanto não chegam). */
export function useAtividadesDoCnae(): AtividadeDoCnae[] | null {
  const [atividades, setAtividades] = useState<AtividadeDoCnae[] | null>(null);
  useEffect(() => {
    let viva = true;
    void carregarCnaes().then((lista) => {
      if (viva) setAtividades(lista);
    });
    return () => {
      viva = false;
    };
  }, []);
  return atividades;
}

interface Propriedades {
  rotulo: string;
  texto: string;
  atividades: AtividadeDoCnae[] | null;
  dica?: string; // a linha de baixo (o código escolhido, ou como usar o campo)
  aoDigitar(texto: string): void;
  aoEscolher(atividade: AtividadeDoCnae): void;
}

export function CampoDoSetor({ rotulo, texto, atividades, dica, aoDigitar, aoEscolher }: Propriedades) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  const [marcada, setMarcada] = useState(-1); // a sugestão em destaque (setas), -1 = nenhuma
  const lista = useRef<HTMLUListElement>(null);

  const opcoes = aberta && atividades ? sugestoesDeCnae(atividades, texto) : [];
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
  const escolher = (atividade: AtividadeDoCnae) => {
    fechar();
    aoEscolher(atividade);
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
          onChange={(ev) => digitar(ev.target.value)}
          onKeyDown={teclar}
          onBlur={fechar}
          maxLength={120}
          placeholder="Ex.: farmácia, transporte de carga ou 4771-7/01"
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <ul
        className="sugestoes-do-ativo"
        id={`${id}-lista`}
        role="listbox"
        aria-label="Atividades do CNAE"
        ref={lista}
        hidden={opcoes.length === 0}
      >
        {opcoes.map((a, i) => (
          <li
            key={a.codigo}
            id={idDaOpcao(i)}
            role="option"
            aria-selected={i === marcada}
            // o mousedown tiraria o foco do campo (e fecharia a lista) antes do clique
            onMouseDown={(ev) => ev.preventDefault()}
            onClick={() => escolher(a)}
          >
            <span>{a.nome}</span>
            <span className="codigo-da-sugestao">{cnaeComPontuacao(a.codigo)}</span>
          </li>
        ))}
      </ul>
      <span className="so-para-leitor" aria-live="polite">
        {aberta && texto.trim() !== "" && atividades ? `${opcoes.length} sugestões` : ""}
      </span>
      {dica ? (
        <small className="dica-do-setor" id={`${id}-dica`}>
          {dica}
        </small>
      ) : null}
    </div>
  );
}
