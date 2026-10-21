"""Esquema `pessoas` da base (ADR 0106): o único lugar onde o nome de uma pessoa natural pode existir.

Fora dele só o `id_pessoa` (pseudônimo por HMAC com a chave do servidor). O nome só sai de casa pelo portão
(`portao.py`), por fonte e com quatro condições escritas.
"""
