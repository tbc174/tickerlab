// Sair do app: para um site de fora (a página de pagamento ou o portal do Stripe) ou para a versão
// clássica. Num objeto para os testes trocarem a ida por uma conferência (o jsdom não navega).
export const navegador = {
  ir(url: string): void {
    window.location.assign(url);
  },
  /** Como `ir`, mas sem deixar a página atual no histórico: o Voltar não cai no mesmo desvio. */
  trocar(url: string): void {
    window.location.replace(url);
  },
};

// os únicos destinos de fora que o app abre: o Checkout e o portal do Stripe
const DESTINOS_DO_STRIPE = ["https://checkout.stripe.com/", "https://billing.stripe.com/"];

/** O endereço veio da nossa API, mas só vale se for do Stripe (segunda barreira). */
export const eDoStripe = (url: string) => DESTINOS_DO_STRIPE.some((inicio) => url.startsWith(inicio));
