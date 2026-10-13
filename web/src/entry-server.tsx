// Monta o HTML de uma página no build (sem navegador): é o que a busca do Google lê.
import { renderToString } from "react-dom/server";
import { ROTAS, rotaDoArquivo } from "./rotas";

export const arquivos = ROTAS.map((r) => r.arquivo);

export function renderizar(arquivo: string, script: string): string {
  const rota = rotaDoArquivo(arquivo);
  const corpo = renderToString(rota.pagina());
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapar(rota.titulo)}</title>
<meta name="description" content="${escapar(rota.descricao)}">
</head>
<body data-pagina="${escapar(arquivo)}">
<div id="raiz">${corpo}</div>
<script type="module" src="${escapar(script)}"></script>
</body>
</html>
`;
}

function escapar(texto: string): string {
  return texto
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
