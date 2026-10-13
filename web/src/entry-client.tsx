// No navegador: o React assume o HTML que já veio pronto (hidratação), para as partes interativas.
import { hydrateRoot } from "react-dom/client";
import { rotaDoArquivo } from "./rotas";

const raiz = document.getElementById("raiz");
const arquivo = document.body.dataset.pagina;
if (raiz && arquivo) {
  hydrateRoot(raiz, rotaDoArquivo(arquivo).pagina());
}
