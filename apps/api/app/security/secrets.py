import base64
import hashlib
import json
import os
import platform
from pathlib import Path

import keyring
from app.config import settings
from cryptography.fernet import Fernet
from keyring.errors import KeyringError, PasswordDeleteError


class SecretStore:
    service = "yingzhang"

    def __init__(self, vault_path=None):
        self.vault_path = vault_path or Path(".yingzhang/secrets.enc")

    def _fernet(self):
        seed = (
            settings.vault_key
            or f"{platform.node()}:{os.environ.get('USERNAME', 'user')}:yingzhang"
        )
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))

    def _read(self):
        return (
            {}
            if not self.vault_path.exists()
            else json.loads(self._fernet().decrypt(self.vault_path.read_bytes()).decode())
        )

    def _write(self, data):
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_bytes(self._fernet().encrypt(json.dumps(data).encode()))

    def set(self, ref, value):
        try:
            keyring.set_password(self.service, ref, value)
            return
        except KeyringError:
            data = self._read()
            data[ref] = value
            self._write(data)

    def get(self, ref):
        if not ref:
            return None
        try:
            value = keyring.get_password(self.service, ref)
            if value is not None:
                return value
        except KeyringError:
            pass
        return self._read().get(ref)

    def delete(self, ref):
        if not ref:
            return
        try:
            keyring.delete_password(self.service, ref)
        except (KeyringError, PasswordDeleteError):
            pass
        data = self._read()
        if ref in data:
            data.pop(ref, None)
            self._write(data)


secret_store = SecretStore()
