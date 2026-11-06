// O selo da data da base: cada página pública é um retrato gerado num dia, então a data aparece
// à vista, no mesmo lugar e do mesmo jeito (data-data-da-base é o que o teste confere).
export function SeloDaBase({ data }: { data: string }) {
  return (
    <p className="v2-selo-base" data-data-da-base={data}>
      <strong>Retrato de {data}.</strong> Cada número abaixo traz a data do próprio dado. Páginas
      diferentes são geradas em dias diferentes, por isso este retrato pode ser mais antigo que o de
      outra página; a busca por empresa consulta a base na hora.
    </p>
  );
}
