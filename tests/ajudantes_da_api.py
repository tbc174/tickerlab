"""Ajudantes dos testes da API v1: tokens no formato do Google, assinados com chaves do próprio teste."""

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

CLIENT_ID = "tickerlab-teste.apps.googleusercontent.com"
AGORA = 1_800_000_000


def gerar_chave(kid: str = "chave-1") -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": kid})


def chaves_publicas(chave: RSAKey) -> KeySet:
    return KeySet.import_key_set({"keys": [chave.as_dict(private=False)]})


def token(chave: RSAKey, **mudancas) -> str:
    """Um ID token como o do Google para a conta "ana"; `mudancas` troca (ou, com None, tira) campos."""
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "ana",
        "email": "ana@exemplo.com",
        "email_verified": True,
        "name": "Ana",
        "iat": AGORA - 60,
        "exp": AGORA + 3600,
    }
    claims.update(mudancas)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode({"alg": "RS256", "kid": "chave-1"}, claims, chave)


def com_token(valor: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {valor}"}
