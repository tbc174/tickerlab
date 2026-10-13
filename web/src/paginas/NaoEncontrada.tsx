// A página 404. Era `nao_encontrada()` de scripts/gerar_site.py.

export const DADOS = {
  caminho: "/404.html",
  titulo: "Página não encontrada",
  descricao: "Página não encontrada.",
};

export function NaoEncontrada() {
  return (
    <section className="faixa secao estreita">
      <p className="olho">Erro 404</p>
      <h1>Esta página não existe</h1>
      <p className="subtitulo">O endereço pode ter mudado. Volte para o início ou abra o app.</p>
      <p>
        <a className="botao primario" href="/">
          Ir para o início
        </a>
      </p>
    </section>
  );
}
