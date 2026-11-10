import os
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import bcrypt
from jose import jwt, JWTError
from cryptography.fernet import Fernet, InvalidToken

DEFAULT_INSECURE_SECRET = "Ruvexi-enterprise-secret-key-production-ready-2026"
SECRET_KEY = os.getenv("JWT_SECRET", DEFAULT_INSECURE_SECRET)

if os.getenv("ENVIRONMENT") == "production" and SECRET_KEY == DEFAULT_INSECURE_SECRET:
    print("[CRITICAL SECURITY WARNING] JWT_SECRET environment variable is not configured! Please set a unique 64-character secret on Railway.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with automatic salt."""
    if not password:
        return ""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against the stored bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Encodes session claims into a signed JSON Web Token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates signature and expiration of a JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _get_fernet() -> Fernet:
    raw_secret = os.getenv("WHATSAPP_ENCRYPTION_KEY") or SECRET_KEY
    digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypts sensitive integration secrets (e.g. Meta access tokens) at rest using Fernet."""
    if not plaintext:
        return plaintext
    if plaintext.startswith("enc::"):
        return plaintext
    token_bytes = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return f"enc::{token_bytes.decode('utf-8')}"


def decrypt_secret(stored_value: Optional[str]) -> Optional[str]:
    """Decrypts secrets stored with encrypt_secret; passes through legacy plaintext values cleanly."""
    if not stored_value:
        return stored_value
    if not stored_value.startswith("enc::"):
        return stored_value
    try:
        raw_ciphertext = stored_value[5:].encode("utf-8")
        return _get_fernet().decrypt(raw_ciphertext).decode("utf-8")
    except (InvalidToken, Exception):
        return ""
