# -*- coding: utf-8 -*-
"""Configuration management for Agent Reach.

Stores settings in ~/.agent-reach/config.yaml.
Auto-creates directory on first use.
Sensitive values (tokens, keys, cookies) are encrypted at rest.
"""

import base64
import hashlib
import hmac
import os
import stat
from pathlib import Path
from typing import Any, Optional

import yaml


#: Config keys whose values are encrypted at rest.
#: Matched by lowercase substring — add new sensitive keys here.
_SENSITIVE_KEY_PATTERNS = (
    "key", "token", "password", "secret",
    "cookie", "auth", "proxy",
)

#: Environment variable names that Config.get() may fall back to.
#: All other uppercase env var names are ignored for safety.
_ENV_ALLOWLIST = frozenset({
    # API keys
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "EXA_API_KEY",
    "GITHUB_TOKEN",
    # Auth tokens / cookies
    "TWITTER_AUTH_TOKEN",
    "TWITTER_CT0",
    "BILIBILI_SESSDATA",
    "BILIBILI_CSRF",
    "XHS_COOKIE",
    "XUEQIU_COOKIE",
    "YOUTUBE_COOKIES_FROM",
    # Proxy / environment
    "PROXY",
    "AGENT_REACH_LANG",
})

#: Encryption marker prefix — values starting with this use at-rest encryption.
_ENC_PREFIX = "$enc$"
_ENC_SALT = b"agent-reach-enc-v1"
_ENC_KEYGEN_ITERATIONS = 200_000
_ENC_KEYFILE = ".config_key"


class Config:
    """Manages Agent Reach configuration."""

    CONFIG_DIR = Path.home() / ".agent-reach"
    CONFIG_FILE = CONFIG_DIR / "config.yaml"

    # Feature → required config keys
    FEATURE_REQUIREMENTS = {
        "exa_search": ["exa_api_key"],
        "twitter_xreach": ["twitter_auth_token", "twitter_ct0"],  # legacy key name; used by twitter-cli
        "groq_whisper": ["groq_api_key"],
        "openai_whisper": ["openai_api_key"],
        "github_token": ["github_token"],
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = Path(config_path) if config_path else self.CONFIG_FILE
        self.config_dir = self.config_path.parent
        self.data: dict = {}
        self._ensure_dir()
        self.load()

    def _ensure_dir(self):
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    # ── Encryption helpers ──────────────────────────────────────

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        """True if *key* holds a credential that should be encrypted at rest."""
        kl = key.lower()
        return any(pattern in kl for pattern in _SENSITIVE_KEY_PATTERNS)

    @staticmethod
    def _key_path() -> Path:
        return Config.CONFIG_DIR / _ENC_KEYFILE

    @staticmethod
    def _load_or_create_key() -> bytes:
        """Load the machine-local encryption key, creating it on first use."""
        kp = Config._key_path()
        if kp.exists():
            return kp.read_bytes()
        # Create with 0o600 so the key is never world-readable.
        key = os.urandom(32)
        try:
            fd = os.open(str(kp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                         stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
        except OSError:
            with open(kp, "wb") as f:
                f.write(key)
            try:
                os.chmod(kp, 0o600)
            except OSError:
                pass
        return key

    def _encrypt_value(self, plaintext: str) -> str:
        """Encrypt *plaintext* for at-rest storage.

        Uses PBKDF2-derived key material + HMAC-SHA256 integrity.
        This is NOT production-grade encryption — install ``cryptography``
        (Fernet) for stronger protection. The goal here is to prevent
        casual credential disclosure from config file reads.
        """
        key = self._load_or_create_key()
        salt = os.urandom(16)
        dk = hashlib.pbkdf2_hmac("sha256", key, salt + _ENC_SALT,
                                 _ENC_KEYGEN_ITERATIONS, dklen=64)
        enc_key, mac_key = dk[:32], dk[32:]
        # Simple XOR keystream (enc_key as seed — not AES, see docstring).
        plain_bytes = plaintext.encode("utf-8")
        keystream = hashlib.sha256(enc_key + salt).digest()
        while len(keystream) < len(plain_bytes):
            keystream += hashlib.sha256(enc_key + keystream[-32:]).digest()
        cipher = bytes(a ^ b for a, b in zip(plain_bytes, keystream[:len(plain_bytes)]))
        tag = hmac.new(mac_key, salt + cipher, "sha256").digest()
        return _ENC_PREFIX + base64.b64encode(salt + tag + cipher).decode("ascii")

    def _decrypt_value(self, ciphertext: str) -> str:
        """Decrypt a value previously encrypted with ``_encrypt_value``."""
        if not ciphertext.startswith(_ENC_PREFIX):
            return ciphertext  # not encrypted (backward compat)
        raw = base64.b64decode(ciphertext[len(_ENC_PREFIX):])
        salt, tag, cipher = raw[:16], raw[16:48], raw[48:]
        key = self._load_or_create_key()
        dk = hashlib.pbkdf2_hmac("sha256", key, salt + _ENC_SALT,
                                 _ENC_KEYGEN_ITERATIONS, dklen=64)
        enc_key, mac_key = dk[:32], dk[32:]
        expected = hmac.new(mac_key, salt + cipher, "sha256").digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("config integrity check failed — key file may have changed")
        keystream = hashlib.sha256(enc_key + salt).digest()
        while len(keystream) < len(cipher):
            keystream += hashlib.sha256(enc_key + keystream[-32:]).digest()
        return bytes(a ^ b for a, b in zip(cipher, keystream[:len(cipher)])).decode("utf-8")

    # ── Load / Save ─────────────────────────────────────────────

    def load(self):
        """Load config from YAML file, decrypting sensitive fields."""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            # Decrypt any encrypted values transparently.
            self.data = {
                k: (self._decrypt_value(v) if isinstance(v, str) else v)
                for k, v in raw.items()
            }
        else:
            self.data = {}

    def save(self):
        """Save config to YAML file, encrypting sensitive fields."""
        self._ensure_dir()
        # Encrypt sensitive values before writing.
        to_write = {}
        for k, v in self.data.items():
            if isinstance(v, str) and self._is_sensitive(k):
                to_write[k] = self._encrypt_value(v)
            else:
                to_write[k] = v
        # Create file with restricted permissions.
        try:
            fd = os.open(
                str(self.config_path),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,  # 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(to_write, f, default_flow_style=False, allow_unicode=True)
        except OSError:
            # Fallback for Windows or other edge cases where os.open flags
            # are not fully supported.
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(to_write, f, default_flow_style=False, allow_unicode=True)

    # ── Accessors ───────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value.

        Checks (in order):
        1. Config file (decrypted transparently on load).
        2. Environment variable — *only* if *key* appears in ``_ENV_ALLOWLIST``.

        This prevents accidental leakage of unrelated environment variables.
        """
        if key in self.data:
            return self.data[key]
        # Only fall back to env var for allowlisted names.
        env_key = key.upper()
        if env_key in _ENV_ALLOWLIST:
            env_val = os.environ.get(env_key)
            if env_val:
                return env_val
        return default

    def set(self, key: str, value: Any):
        """Set a config value and save.

        Sensitive values (tokens, keys, cookies) are encrypted at rest.
        """
        self.data[key] = value
        self.save()

    def delete(self, key: str):
        """Delete a config key and save."""
        self.data.pop(key, None)
        self.save()

    def is_configured(self, feature: str) -> bool:
        """Check if a feature has all required config."""
        required = self.FEATURE_REQUIREMENTS.get(feature, [])
        return all(self.get(k) for k in required)

    def get_configured_features(self) -> dict:
        """Return status of all optional features."""
        return {
            feature: self.is_configured(feature)
            for feature in self.FEATURE_REQUIREMENTS
        }

    def to_dict(self) -> dict:
        """Return config as dict (masks sensitive values)."""
        masked = {}
        for k, v in self.data.items():
            if any(s in k.lower() for s in ("key", "token", "password", "proxy")):
                masked[k] = f"{str(v)[:8]}..." if v else None
            else:
                masked[k] = v
        return masked
