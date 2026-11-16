"""O conector remoto do TickerLab (linha 570): um servidor MCP por HTTPS para os analistas da casa de M&A.

Um servidor só para o Claude e o ChatGPT (Streamable HTTP, sem estado). Ele não lê a base nem o banco:
cada ferramenta chama a API externa (`/data/v1`) com a chave do analista, e o que a chave não pode ver a
API já nega. Por cima dela, o conector recusa a resposta inteira que traga campo de pessoa física, limpa os
caracteres de controle do texto e corta a resposta grande demais para a IA.

Roda num contêiner próprio (`tickerlab-mcp`), sem acervo, banco nem o `.env` do app; por isso nada aqui
importa `src/`, `base/` ou `telas/` (há teste que confere). Plano: pasta privada,
`planos/2026-11-10-servidor-mcp-570.md`.
"""
