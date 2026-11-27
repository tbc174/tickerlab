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
A exceção de setembro de 2024 do molde PJ não foi aplicada a PF sem uma
medição própria: esta série compara os retratos disponíveis como publicados.

Somente raízes de `cnpj_estabelecimentos_pj` entram, com a lista do mesmo
mês do vigente. Como no molde PJ, uma raiz retirada dessa lista é retirada
da série inteira. MEI, empresário individual e grupo 4 ficam fora. Chave PF
vazia (inclusive após oposição) omite a comparação inteira daquela empresa
e mês, sem travar as demais. Lacuna de mês, diferenças incompletas ou saldo
inconsistente interrompem a montagem; não se inventa uma identidade.
Uma correção da identidade na origem pode aparecer como saída e entrada:
não se tenta ligar pessoas além da chave pseudonimizada que a base já tem.

## Montagem no servidor de casa

```text
python -m scripts.montar_movimento_socios_pf --cnpj <base do CNPJ> --destino <acervo>/base --ensaio
python -m scripts.montar_movimento_socios_pf --cnpj <base do CNPJ> --destino <acervo>/base
```

O script não usa rede nem lê ZIP, diretório restrito ou segredo. Lê uma
partição de raiz por vez, sem gravar as chaves intermediárias. Confere o
total de mudanças do QSA contra o manifesto de cada mês antes de publicar.
O freio do acervo exige pelo menos 50 GB livres e no máximo 70% de uso.
`--ensaio` conta sem gravar. Repetir o retrato preserva arquivos iguais;
correções guardam a versão anterior agregada pelo gravador padrão da base.
Cada Parquet recebe manifesto com os hashes dos ZIPs e versão do código.

## Catálogo e acesso

Família `rfb-cnpj`, licença CC BY e atribuição à Receita com o mês. A ADR
0088 trata da posição jurídica interna e das restrições sobre pessoas;
a ADR 0106 especifica o histórico mensal do CNPJ e a licença. Esta entrega
aplica a restrição mais estreita: somente contagens empresariais, sem
identificação individual, e as mesmas portas de `entradas_de_socio_pj`.

A porta local lê o Parquet e respeita o corte de publicação. A consulta
aberta não serve a tabela. O recorte do degrau 2 só a leva junto da lista
de empresas sem pessoa e confere cada raiz na saída. A API externa segue
exigindo autorização e prontidão; nenhuma prova de carga ou qualidade real
foi declarada. A tabela não entra na lista de tabelas já montadas até a
carga e a conferência pela Diretoria. Não há nova rota, concessão por
organização, cron ou carga real nesta entrega.
