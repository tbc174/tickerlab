"""A análise escrita pelo modelo de linguagem, com fonte em cada frase (ADR 0100, regras da 0093).

O modelo recebe a ficha da empresa (`relatorio_empresa.montar`) com um id por número e devolve a
análise em 8 partes, frase por frase, cada frase com as notas que apontam para a entrada. O código
confere cada número, data e nome contra a entrada (porta 1); um segundo modelo lê às cegas (porta
2); a parte que não passa volta ao molde por regras. Nada aqui importa o Streamlit nem chama a API
nos testes.
"""
