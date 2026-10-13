import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import "./app.css";

const raiz = document.getElementById("raiz");
if (raiz) {
  createRoot(raiz).render(
    <StrictMode>
      <BrowserRouter basename="/novo">
        <App />
      </BrowserRouter>
    </StrictMode>,
  );
}
