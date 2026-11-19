"""Bot de pesquisa do TickerLab (linha 697 da fila): buscar página, baixar documento com proveniência
e hash, extrair texto ou tabela, validar fato por evidência. Serve ao Claude, ao Codex e ao Gemini
(`agy`) por um servidor MCP (`pesquisa/servidor_mcp.py`).

Fica fora do app, da imagem Docker e da cobertura do CI: roda no PC, nas rodadas de pesquisa. O
núcleo usa só o `requirements.txt`; os motores pesados (Crawl4AI para HTML renderizado, Docling para
PDF e planilha) são opcionais e entram só se estiverem instalados (`pesquisa/requirements.txt`).
Não edita o arquivista: usa o `ClienteHttp` de `base/arquivo/cliente_http.py` como está (robots.txt,
ritmo por domínio, bloqueio da Cloudflare registrado e nunca contornado).
"""
