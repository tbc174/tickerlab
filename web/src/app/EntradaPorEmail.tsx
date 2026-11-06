// Entrar com o e-mail e um código de 6 dígitos (sem senha): a pessoa digita o e-mail, recebe o código
// e digita de volta. A API responde igual com ou sem conta, então a tela também (não diz se existe).
import { type FormEvent, useEffect, useState } from "react";
import { useConta } from "./conta";

const ESPERA_PARA_REENVIAR_EM_SEGUNDOS = 60;
const DIGITOS = 6;
const SEGUNDO = 1000;

function mensagemDe(erro: unknown): string {
  return erro instanceof Error ? erro.message : String(erro);
}

export function EntradaPorEmail() {
  const conta = useConta();
  const [email, setEmail] = useState("");
  const [codigo, setCodigo] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [falha, setFalha] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [espera, setEspera] = useState(0);

  useEffect(() => {
    if (espera <= 0) return;
    const relogio = setTimeout(() => setEspera((s) => s - 1), SEGUNDO);
    return () => clearTimeout(relogio);
  }, [espera]);

  if (!conta) return null;
  const { pedirCodigo, confirmarCodigo } = conta;

  const mandar = async (ev?: FormEvent) => {
    ev?.preventDefault();
    setOcupado(true);
    setFalha(null);
    try {
      setAviso(await pedirCodigo(email.trim()));
      setEnviado(true);
      setEspera(ESPERA_PARA_REENVIAR_EM_SEGUNDOS);
    } catch (erro: unknown) {
      setFalha(mensagemDe(erro));
    } finally {
      setOcupado(false);
    }
  };

  const confirmar = async (ev: FormEvent) => {
    ev.preventDefault();
    setOcupado(true);
    setFalha(null);
    try {
      await confirmarCodigo(email.trim(), codigo.trim());
    } catch (erro: unknown) {
      setFalha(mensagemDe(erro));
      setOcupado(false);
    }
  };

  return (
    <div className="entrada-por-email">
      <p className="apagado">ou entre com o seu e-mail</p>
      {enviado ? (
        <form onSubmit={confirmar}>
          {aviso ? <p role="status">{aviso}</p> : null}
          <label>
            Código de {DIGITOS} dígitos
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={DIGITOS}
              value={codigo}
              onChange={(ev) => setCodigo(ev.target.value)}
            />
          </label>
          <button type="submit" className="botao primario" disabled={ocupado || codigo.trim().length < DIGITOS}>
            Entrar
          </button>
          <button type="button" className="botao" disabled={ocupado || espera > 0} onClick={() => mandar()}>
            {espera > 0 ? `Mandar de novo (${espera} s)` : "Mandar de novo"}
          </button>
        </form>
      ) : (
        <form onSubmit={mandar}>
          <label>
            E-mail
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
            />
          </label>
          <button type="submit" className="botao" disabled={ocupado || email.trim() === ""}>
            Enviar código
          </button>
        </form>
      )}
      {falha ? (
        <p className="erro-do-app" role="alert">
          {falha}
        </p>
      ) : null}
    </div>
  );
}
