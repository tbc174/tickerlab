"""A tela do analista (linha 798): a leitura da API externa para quem entra no app com login e plano.

Nada aqui lê a base por outro caminho: cada função chama o mesmo leitor da API externa
(`src/api_externa/conjuntos/`) com o mesmo portão, para a tela mostrar exatamente o que a API mostraria.
As funções não dependem da tela (um conector, como o da linha 570, pode chamá-las).
"""
