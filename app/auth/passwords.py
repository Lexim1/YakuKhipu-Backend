"""Contraseñas scrypt con sal aleatoria; nunca almacenar texto plano."""
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    if len(password)<12:
        raise ValueError('La contraseña debe tener al menos 12 caracteres.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        algorithm,salt,digest = (encoded or '').split('$')
        if algorithm!='scrypt': return False
        value = hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
        return hmac.compare_digest(value,digest)
    except (ValueError,TypeError): return False
