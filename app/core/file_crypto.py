import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

_MASTER_KEY: bytes | None = None  # In-Memory-Cache für die Laufzeit


def _load_master_key() -> bytes:
    global _MASTER_KEY
    if _MASTER_KEY is not None:
        return _MASTER_KEY

    raw = os.environ.get("ENCRYPTION_MASTER_KEY", "")
    if not raw:
        raise RuntimeError(
            "ENCRYPTION_MASTER_KEY nicht in .env gesetzt. "
            "Generiere einen Key mit: "
            "python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError("ENCRYPTION_MASTER_KEY muss exakt 32 Bytes (256 Bit) sein.")

    _MASTER_KEY = key
    return _MASTER_KEY


def derive_patient_key(storage_uuid: str) -> bytes:
    """
    Leitet einen deterministischen 256-Bit-Key pro Patient ab.
    Jeder Patient hat einen einzigartigen Key — Kompromittierung isoliert.
    """
    master = _load_master_key()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        # storage_uuid als Salt: bindet den Key an diesen spezifischen Patienten
        salt=storage_uuid.encode("utf-8"),
        info=b"niceapp-v1-patient-file-key",
    )
    return hkdf.derive(master)


def encrypt_bytes(storage_uuid: str, plaintext: bytes) -> bytes:
    """
    AES-256-GCM Verschlüsselung.
    Rückgabeformat: [12 Byte Nonce] + [Ciphertext + 16 Byte Auth-Tag]
    """
    key = derive_patient_key(storage_uuid)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-Bit-Nonce — pro Datei einmalig
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext  # Nonce mitschicken (kein Geheimnis)


def decrypt_bytes(storage_uuid: str, cipherdata: bytes) -> bytes:
    """
    Entschlüsselt und verifiziert die Integrität (GCM-Tag).
    Wirft InvalidTag wenn Daten manipuliert wurden.
    Niemals auf Disk schreiben — nur im RAM verwenden!
    """
    if len(cipherdata) < 28:  # 12 Nonce + min 16 Tag
        raise ValueError("Ungültiges verschlüsseltes Datenformat.")

    key = derive_patient_key(storage_uuid)
    aesgcm = AESGCM(key)
    nonce, ciphertext = cipherdata[:12], cipherdata[12:]

    try:
        return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    except InvalidTag:
        # Logging ohne Details — keine Infos über Schlüssel nach außen
        raise InvalidTag("Datei konnte nicht entschlüsselt werden — Integrität verletzt.")