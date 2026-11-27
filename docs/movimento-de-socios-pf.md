# Movimento mensal de sócios PF: contagem sem identificação

`movimento_de_socios_pf` conta, por raiz empresarial e mês do retrato da
Receita, quantos sócios do tipo 2 entraram, saíram e estavam presentes no fim.
A saída não tem nome, CPF, pseudônimo nem outro identificador de pessoa.
Não é uma tabela de pessoas: é uma contagem sem identificação por empresa.

O cálculo lê o QSA vigente e suas diferenças mensais já pseudonimizadas.
Desfaz as diferenças em memória para recuperar a presença de cada chave
nos dois retratos consecutivos. Duplicatas não contam duas vezes; mudança
de qualificação ou de data de entrada não vira movimento. Sair e voltar
em meses diferentes conta como saída e nova entrada.

O saldo inicial, em maio de 2023, tem `tem_retrato_anterior = false`.
Seus movimentos são zero por convenção: não se observam entradas nem saídas
anteriores ao início da série. Só existe linha quando havia PF em pelo
menos um dos dois retratos. Ausência de linha, isoladamente, não prova
ausência de sócios: é preciso conferir a cobertura do acervo e do recorte.

O mês indica quando a diferença apareceu no cadastro, não quando ocorreu
um negócio. Em sociedades anônimas, o QSA pode listar administradores.
O campo `disponivel_em` usa o dia 21 do retrato, como o molde PJ; a porta
arredonda `publico_em` para o último dia do mês. Não existe data de aquisição.
Herda a regra do molde PJ para setembro de 2024, pois são os mesmos arquivos
`Socios*.zip`: setembro não sai e outubro compara diretamente com agosto.
A Diretoria medirá PF no ensaio antes da primeira carga; se PF não apresentar
o defeito, a regra será retirada em PR próprio. Os totais do ensaio mostram
os movimentos com e sem a correção, permitindo conferir esse efeito.

O contrato mantém `historico_desde = 2026-10-14` (`_GOVERNO`), como toda a
família: foi quando essas fontes passaram a ser guardadas na hora. A existência
de retratos desde 2023-05 não prova que cada arquivo foi preservado naquela
data; os meses de 2023-05 a 2026-06 foram recarregados em bloco pela Receita.

Somente raízes de `cnpj_estabelecimentos_pj` entram, com a lista do mesmo
mês do vigente. Como no molde PJ, uma raiz retirada dessa lista é retirada
da série inteira. MEI, empresário individual e grupo 4 ficam fora. Chave PF
vazia em M (inclusive após oposição) omite a comparação inteira daquela empresa
em M e M+1, sem travar as demais. Lacuna de mês, diferenças incompletas ou saldo
inconsistente interrompem a montagem; não se inventa uma identidade.
Uma correção da identidade na origem pode aparecer como saída e entrada:
não se tenta ligar pessoas além da chave pseudonimizada que a base já tem.

Depois de `atender` uma oposição no QSA, é necessário remontar esta tabela
e reenviar o recorte quando ele estiver autorizado. O atendimento no QSA
não atualiza automaticamente cópias agregadas já montadas ou enviadas.

Risco aceito pela Diretoria em 27/11/2026 (`decisoes-delegadas`): em uma
sociedade unipessoal, a série pode mostrar o mês da troca do único sócio PF.
A tabela não publica identificador, nome ou qualificação, e a Receita já
publica o QSA com nome em CC BY. Esse risco das contagens pequenas foi aceito
para esta entrega; MEI, empresário individual e grupo 4 continuam excluídos.

## Montagem no servidor de casa

```text
python -m scripts.montar_movimento_socios_pf --cnpj <base do CNPJ> --destino <acervo>/base --ensaio
python -m scripts.montar_movimento_socios_pf --cnpj <base do CNPJ> --destino <acervo>/base
```

O script não usa rede nem lê ZIP, diretório restrito ou segredo. Lê uma
partição de raiz por vez, sem gravar as chaves intermediárias. Confere o
total de mudanças do QSA contra o manifesto de cada mês antes de publicar.
O freio do acervo exige pelo menos 50 GB livres e no máximo 70% de uso.
`--ensaio` conta sem gravar e imprime somente totais mensais de entradas,
saídas e saldo, com e sem a correção do retrato defeituoso. A guarda de faixa
é aplicada depois desse relatório: mês novo (exceto o saldo inicial) com
mais de 30.000 entradas ou 10.000 saídas impede a publicação. São os limites
provisórios conservadores do molde PJ, **não uma faixa medida para PF**;
a Diretoria deve medir e calibrar por PR antes da primeira carga. O ensaio
ainda imprime todos os totais se a guarda reprovar. Meses já publicados
não passam de novo pela guarda, como no molde.

A montagem com gravação prepara somente agregados temporários com manifesto;
a tabela publicada é substituída somente depois da conferência de faixa.
O freio é conferido antes de cada gravação, inclusive temporários.
Código sem commit conhecido ou com alterações não commitadas é recusado.
Repetir o retrato preserva arquivos iguais;
correções guardam a versão anterior agregada pelo gravador padrão da base.
Cada Parquet recebe manifesto com os hashes dos ZIPs e versão do código.

## Catálogo e acesso

Família `rfb-cnpj`, licença CC BY e atribuição à Receita com o mês. A ADR
0088 trata da posição jurídica interna e das restrições sobre pessoas;
a ADR 0106 especifica o histórico mensal do CNPJ e a licença. Esta entrega
aplica a restrição mais estreita: somente contagens empresariais, sem
identificação individual, e as mesmas portas de `entradas_de_socio_pj`.

A porta local lê o Parquet e respeita o corte de publicação. A consulta
aberta não serve a tabela. Ela **ainda não integra o degrau 2** do recorte:
isso depende da primeira carga conferida e de um PR próprio com o pode
datado da Diretoria. A guarda já exige a lista de empresas sem pessoa e
confere cada raiz caso a montagem seja solicitada explicitamente. A API externa segue
exigindo autorização e prontidão; nenhuma prova de carga ou qualidade real
foi declarada. A tabela não entra na lista de tabelas já montadas até a
carga e a conferência pela Diretoria. Não há nova rota, concessão por
organização, cron ou carga real nesta entrega.
