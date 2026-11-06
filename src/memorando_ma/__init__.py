"""O memorando de M&A com fonte em cada frase (B-26 do dossiê da plataforma; protótipo A, M&A).

Junta o que o protótipo A já calcula (perfil e grupo pelo CNPJ, pares, DCF reverso e múltiplos, comps
por transação, LBO com as premissas do usuário e os red flags dos cruzamentos) num texto em que cada
frase aponta para as evidências de onde saiu (`evidencia.py`). A conferência (`conferencia.py`) passa
cada frase pela porta 1 da ADR 0100 e pelas regras próprias do memorando antes de qualquer tela: frase
sem fonte, evidência incompleta ou de depois da data, preço-alvo e "vale X" reprovam.

Tipos simples, sem Streamlit: a API e o app novo leem o mesmo `como_dict`. Nada é recomendação.
"""
