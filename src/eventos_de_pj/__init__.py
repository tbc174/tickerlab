"""Eventos de pessoa jurídica com três estados: mudou, não observado e fonte falhou (N5, C-PR03).

`evento.py` tem o tipo e o motor; cada fonte do primeiro corte tem o seu adaptador (`fidc.py`,
`cadastro_receita.py`, `cadastro_cvm.py`), e `registro.py` lê do registro de coletas quando cada
fonte foi lida.
"""
