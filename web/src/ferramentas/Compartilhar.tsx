// "Copiar link" e "Copiar resultado": o link já guarda a simulação (endereco.ts). Sem botões de redes
// sociais nem script de terceiros. Sem a área de transferência (navegador antigo, página sem https),
// mostra o link num campo para copiar à mão.
import { useEffect, useState } from "react";

type Estado = "parado" | "copiado" | "manual";

export function Compartilhar({ resultado }: { resultado: string }) {
  const [estado, setEstado] = useState<Estado>("parado");
  const [link, setLink] = useState("");
  useEffect(() => {
    if (estado !== "copiado") return;
    const relogio = setTimeout(() => setEstado("parado"), 2500);
    return () => clearTimeout(relogio);
  }, [estado]);

  const copiar = async (comResultado: boolean) => {
    const endereco = window.location.href;
    setLink(endereco);
    const texto = comResultado ? `${resultado} — ${endereco}` : endereco;
    try {
      if (!navigator.clipboard) throw new Error("sem área de transferência");
      await navigator.clipboard.writeText(texto);
      setEstado("copiado");
    } catch {
      setEstado("manual");
    }
  };

  return (
    <div className="ferramenta-compartilhar">
      <button type="button" className="botao secundario pequeno" onClick={() => copiar(false)}>
        Copiar link
      </button>
      <button type="button" className="botao secundario pequeno" onClick={() => copiar(true)}>
        Copiar resultado
      </button>
      <span role="status" className="apagado">
        {estado === "copiado" ? "Copiado! O link abre esta mesma simulação." : ""}
      </span>
      {estado === "manual" ? (
        <label className="ferramenta-link-manual">
          Link desta simulação
          <input type="text" readOnly value={link} onFocus={(evento) => evento.target.select()} />
        </label>
      ) : null}
    </div>
  );
}
