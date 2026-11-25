"""Eventos de pessoa jurídica com três estados: mudou, não observado e fonte falhou (N5, C-PR03).

`evento.py` tem o tipo e o motor; cada fonte do primeiro corte tem o seu adaptador (`fidc.py`,
`cadastro_receita.py`, `cadastro_cvm.py`), e `registro.py` lê do registro de coletas quando cada
fonte foi lida. `acervo.py` é a cola: lê as versões guardadas e as tentativas e entrega aos adaptadores
do FIDC e do cadastro da CVM.
"""
