// O aviso no fim de toda ferramenta: não é recomendação, e o que a conta deixa de fora.

export function AvisoDaFerramenta({ foraDaConta, fonte }: { foraDaConta: string[]; fonte?: string }) {
  return (
    <div className="ferramenta-aviso apagado">
      <p>
        <strong>O que a conta deixa de fora:</strong> {foraDaConta.join("; ")}.
      </p>
      {fonte ? <p>Fonte dos dados: {fonte}.</p> : null}
      <p>
        É uma simulação para entender os números e não é recomendação de investimento. Rentabilidade
        passada não garante resultado futuro.
      </p>
    </div>
  );
}
