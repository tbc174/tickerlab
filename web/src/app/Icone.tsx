// Os ícones do menu do app novo: só traço, na cor do texto (currentColor), 24 × 24. O nome de cada área
// vem de src/paginas.py (Area.icone); o desenho fica aqui.
const DESENHOS: Record<string, string> = {
  inicio: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  ativo: "M3 3v18h18M7 15l4-4 3 3 5-6",
  estrategias: "M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M7.5 14h9",
  acompanhar: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  conta: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  ajuda: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01",
  mais: "M5 12h.01M12 12h.01M19 12h.01",
  estrela: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3l-5.5 2.9 1-6.2L3 9.6l6.2-.9z",
};

/** Um ícone decorativo (o nome vem do texto ao lado ou do aria-label do botão). */
export function Icone({ nome }: { nome: string }) {
  const desenho = DESENHOS[nome];
  if (!desenho) return null;
  return (
    <svg
      className={`icone icone-${nome}`}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth={nome === "mais" ? 3 : 2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={desenho} />
    </svg>
  );
}
