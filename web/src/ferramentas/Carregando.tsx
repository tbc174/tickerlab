// O que a ferramenta com dados do Banco Central mostra antes de ter os dados, se eles faltarem, e a
// data e a fonte de cada número (com o aviso quando o dado é velho).
import type { ReactNode } from "react";
import { type Carga, type DadosDoBc, dataBrasileira, estaVelho } from "./dados";

export function ComDadosDoBc({
  carga,
  children,
}: {
  carga: Carga;
  children: (dados: DadosDoBc) => ReactNode;
}) {
  if (carga.estado === "carregando") {
    return <p className="ferramenta-espera apagado">Carregando os dados do Banco Central…</p>;
  }
  if (carga.estado === "indisponivel") {
    return (
      <p className="ferramenta-erro" role="alert">
        Os dados do Banco Central estão indisponíveis agora. Tente de novo mais tarde.
      </p>
    );
  }
  return <>{children(carga.dados)}</>;
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** "Banco Central, IPCA até set/2026." O IPCA é mensal (sai perto do dia 10 do mês seguinte):
 * sem o aviso de dado velho, que acenderia sempre. */
export function MesDoIpca({ ultimo }: { ultimo: string }) {
  const [ano, mes] = ultimo.split("-");
  return (
    <p className="ferramenta-data apagado">
      Banco Central, IPCA até {MESES[Number(mes) - 1]}/{ano}.
    </p>
  );
}

/** "Banco Central, dado de 13/10/2026", e o aviso se ele passou de 4 dias úteis. */
export function DataDoDado({ data, rotulo = "dado de" }: { data: string; rotulo?: string }) {
  const velho = estaVelho(data, new Date());
  return (
    <p className="ferramenta-data apagado">
      Banco Central, {rotulo} {dataBrasileira(data)}.
      {velho ? (
        <strong className="ferramenta-velho"> Atenção: dado de vários dias atrás; a atualização pode ter falhado.</strong>
      ) : null}
    </p>
  );
}
