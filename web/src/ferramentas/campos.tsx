// Os campos das ferramentas: número em texto (aceita "1.000,50"), escolha entre opções e o bloco do
// resultado. Saem prontos no HTML do build com os valores de exemplo e voltam a responder quando o
// ferramentas.js liga a ferramenta no navegador.
import { type ReactNode, useId } from "react";

export function CampoDeNumero({
  rotulo,
  valor,
  aoMudar,
  antes,
  depois,
  dica,
}: {
  rotulo: string;
  valor: string;
  aoMudar: (valor: string) => void;
  antes?: string; // "R$"
  depois?: ReactNode; // "%" ou uma Escolha de unidade
  dica?: string;
}) {
  const id = useId();
  return (
    <div className="ferramenta-campo">
      <label htmlFor={id}>{rotulo}</label>
      <div className="ferramenta-entrada">
        {antes ? <span aria-hidden="true">{antes}</span> : null}
        <input
          id={id}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          value={valor}
          onChange={(evento) => aoMudar(evento.target.value)}
        />
        {depois}
      </div>
      {dica ? <small className="apagado">{dica}</small> : null}
    </div>
  );
}

export function Escolha<T extends string>({
  rotulo,
  valor,
  opcoes,
  aoMudar,
}: {
  rotulo: string;
  valor: T;
  opcoes: [T, string][];
  aoMudar: (valor: T) => void;
}) {
  return (
    <select aria-label={rotulo} value={valor} onChange={(evento) => aoMudar(evento.target.value as T)}>
      {opcoes.map(([chave, nome]) => (
        <option key={chave} value={chave}>
          {nome}
        </option>
      ))}
    </select>
  );
}

export function Alternativas<T extends string>({
  rotulo,
  valor,
  opcoes,
  aoMudar,
}: {
  rotulo: string;
  valor: T;
  opcoes: [T, string][];
  aoMudar: (valor: T) => void;
}) {
  const nome = useId();
  return (
    <fieldset className="ferramenta-campo ferramenta-alternativas">
      <legend>{rotulo}</legend>
      {opcoes.map(([chave, texto]) => (
        <label key={chave}>
          <input
            type="radio"
            name={nome}
            value={chave}
            checked={valor === chave}
            onChange={() => aoMudar(chave)}
          />
          {texto}
        </label>
      ))}
    </fieldset>
  );
}

/** O resultado principal e os números de apoio. Só o número principal (ou o erro) é anunciado a quem
 * usa leitor de tela: a tabela da evolução seria lida inteira a cada tecla. */
export function Resultado({
  rotulo,
  principal,
  erro,
  children,
}: {
  rotulo: string;
  principal: string;
  erro: string | null;
  children?: ReactNode;
}) {
  return (
    <div className="ferramenta-resultado">
      <div aria-live="polite">
        {erro ? (
          <p className="ferramenta-erro">{erro}</p>
        ) : (
          <>
            <p className="olho">{rotulo}</p>
            <p className="ferramenta-principal" data-resultado="">
              {principal}
            </p>
          </>
        )}
      </div>
      {erro ? null : children}
    </div>
  );
}
