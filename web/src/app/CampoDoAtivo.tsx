// O campo Ativo: uma caixa de busca no catálogo (o combobox com lista do WAI-ARIA), como o selectbox da
// versão clássica. Digita-se o código ou o nome, as setas andam na lista, Enter escolhe e Esc fecha; no
// celular, toca-se na sugestão. Um código fora da lista continua valendo, e a linha de baixo diz qual ativo
// vai ser analisado (ou que ele está fora do catálogo): nada troca de ativo sem a pessoa ver (SEARCH-03).
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { type Ativo, ativoExato, carregarAtivos, resolverAtivo, sugestoes } from "./buscaDeAtivos";

interface Propriedades {
  rotulo: string;
  descricao: string;
  obrigatorio: boolean;
  valor: string; // o símbolo (PETR4.SA) ou o que veio no endereço
  aoMudar(valor: string): void;
}

/** O ativo que vai ser analisado, dito embaixo do campo (com a lista aberta, só o que já bate exato). */
function textoDaDica(ativos: Ativo[] | null, texto: string, listaAberta: boolean): string {
  if (ativos === null || texto.trim() === "") return "";
  const ativo = ativoExato(ativos, texto);
  if (ativo) return ativo.rotulo;
  if (listaAberta) return "";
  return `“${texto.trim().toUpperCase()}” está fora do catálogo: o app procura assim mesmo e avisa se não achar dados.`;
}

export function CampoDoAtivo({ rotulo, descricao, obrigatorio, valor, aoMudar }: Propriedades) {
  const id = useId();
  const [ativos, setAtivos] = useState<Ativo[] | null>(null);
  const [texto, setTexto] = useState(valor);
  const [aberta, setAberta] = useState(false);
  const [marcada, setMarcada] = useState(-1); // a sugestão em destaque (setas), -1 = nenhuma
  const lista = useRef<HTMLUListElement>(null);
  const textoAtual = useRef(valor); // o texto na hora em que o catálogo chega (o estado ficaria velho ali)

  // só na montagem: aoMudar grava no rascunho do formulário, que não muda de lugar
  useEffect(() => {
    let vivo = true;
    void carregarAtivos().then((carregados) => {
      if (!vivo) return;
      setAtivos(carregados);
      // quem digitou antes de o catálogo chegar: o código exato passa a valer como o do catálogo, já
      // (depois, cada tecla resolve em digitar)
      aoMudar(resolverAtivo(carregados, textoAtual.current));
    });
    return () => {
      vivo = false;
    };
  }, []);

  const opcoes = aberta && ativos ? sugestoes(ativos, texto) : [];
  const idDaOpcao = (i: number) => `${id}-opcao-${i}`;

  useEffect(() => {
    if (marcada >= 0) lista.current?.children[marcada]?.scrollIntoView?.({ block: "nearest" });
  }, [marcada]);

  const digitar = (novo: string) => {
    textoAtual.current = novo;
    setTexto(novo);
    setAberta(true);
    setMarcada(-1);
    aoMudar(ativos ? resolverAtivo(ativos, novo) : novo.trim().toUpperCase());
  };
  const escolher = (ativo: Ativo) => {
    textoAtual.current = ativo.codigo;
    setTexto(ativo.codigo);
    setAberta(false);
    setMarcada(-1);
    aoMudar(ativo.simbolo);
  };
  const fechar = () => {
    setAberta(false);
    setMarcada(-1);
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

  const dica = textoDaDica(ativos, texto, opcoes.length > 0);
  // a dica é uma linha inteira no fim da grade de campos (fora da caixa do campo): assim o campo do ativo
  // fica alinhado com os vizinhos, com dica ou sem
  return (
    <>
      <div className="campo-do-ativo">
        <label title={descricao}>
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
            required={obrigatorio}
            maxLength={60}
            placeholder="Código ou empresa"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
          />
        </label>
        <ul
          className="sugestoes-do-ativo"
          id={`${id}-lista`}
          role="listbox"
          aria-label="Ativos do catálogo"
          ref={lista}
          hidden={opcoes.length === 0}
        >
          {opcoes.map((a, i) => (
            <li
              key={a.simbolo}
              id={idDaOpcao(i)}
              role="option"
              aria-selected={i === marcada}
              // o mousedown tiraria o foco do campo (e fecharia a lista) antes do clique
              onMouseDown={(ev) => ev.preventDefault()}
              onClick={() => escolher(a)}
            >
              {a.rotulo}
            </li>
          ))}
        </ul>
        <span className="so-para-leitor" aria-live="polite">
          {aberta && texto.trim() !== "" && ativos ? `${opcoes.length} sugestões` : ""}
        </span>
      </div>
      {dica ? (
        <small className="dica-do-ativo" id={`${id}-dica`}>
          {dica}
        </small>
      ) : null}
    </>
  );
}
