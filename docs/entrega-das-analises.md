# Entrega das análises aprovadas ao app

O lote fica no acervo de casa; o app lê `dados_locais/analises/<cnpj>.json` nos dois
contêineres. A linha 376 era a ligação ausente entre esses lugares.

`scripts/transferir_analises.py` usa apenas a biblioteca padrão do Python. No emissor:

```sh
python3 transferir_analises.py empacotar --origem analises/v1/analises --entradas analises/entradas > pacote.tar
```

O pacote contém só análises com `publicavel: true` e veredito humano `aprovado`.
Textos do primeiro lote não tinham `corte`: esse metadado só é recuperado de uma
entrada original cujo SHA-256 seja igual a `hash_da_entrada_atual`. O texto, os
gráficos, a aprovação e o original permanecem iguais. Nenhuma chamada de IA ocorre.

No recebedor, sob trava exclusiva (`flock`) e comando SSH restrito:

```sh
python3 transferir_analises.py receber --dados dados_locais < pacote.tar
```

Antes de gravar, confere nomes, tipos, tamanhos, duplicatas, manifesto, hashes,
CNPJ, data de corte e aprovação. Não extrai caminhos do tar no sistema de arquivos.
Publica uma pasta nova em `dados_locais/.analises-publicadas/` e troca atomicamente
o link relativo `dados_locais/analises`. Repetir o mesmo pacote não cria outra pasta.
O pacote é a lista completa de aprovações: revogar uma aprovação retira o arquivo
na próxima entrega. Origem inexistente ou vazia aborta, sem retirar textos do app.

As fotografias anteriores ficam guardadas para reversão. O operador pode voltar
o link para a fotografia anterior; a limpeza não faz parte deste comando.
Pasta real preexistente em `analises` não é sobrescrita automaticamente.

A rotina operacional e sua agenda ficam no registro privado dos servidores.
Usar a chave restrita já existente, sem abrir shell nem alterar `authorized_keys`.
O comando forçado encaminha `receber-analises` ao recebedor com destino fixo.
Envio deve usar a mesma trava do lote, para não ler durante uma gravação.

Conferência depois da entrega: contar arquivos dentro dos dois contêineres e chamar
o mesmo montador usado pela API. Arquivo entregue não significa texto atualizado:
o leitor mantém as travas de aprovação, plano e hash da ficha. Se a ficha mudou,
revalidar/reescrever a análise; nunca trocar o hash só para liberar a exibição.
