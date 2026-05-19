import base64
import io
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pypdf import PdfReader, PdfWriter

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


# ── PDF-Passwort-Verschlüsselung ─────────────────────────────────────────────

def derive_patient_password(storage_uuid: str) -> str:
    """
    Leitet ein deterministisches, lesbares Passwort für die PDF-Verschlüsselung ab.
    Format: ABCD-1234-EFGH-5678  (Base32, 4×4 Zeichen, 80 Bit Entropie)

    Das Passwort ist immer gleich für denselben Patienten und kann im UI
    angezeigt werden, wenn der User eine Datei außerhalb der App öffnen möchte
    (z.B. Finder / Adobe Reader).
    """
    key = derive_patient_key(storage_uuid)   # 32 Bytes HKDF-Output
    # 10 Bytes → Base32 = exakt 16 Zeichen (keine Padding-Zeichen)
    raw = base64.b32encode(key[:10]).decode()   # nur A–Z und 2–7, gut tippbar
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def encrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """
    Erzeugt ein AES-256-passwortgeschütztes PDF (PDF-Standard, R=6 / PDF 2.0).
    Die Datei bleibt ein gültiges PDF — jeder Viewer kann sie mit dem Passwort öffnen.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt(
        user_password=password,
        owner_password=password,
        algorithm="AES-256",
    )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def decrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """
    Entschlüsselt ein passwortgeschütztes PDF und gibt die Klartextbytes zurück.
    Wirft pypdf.errors.FileNotDecryptedError wenn das Passwort falsch ist.
    Niemals auf Disk schreiben — nur im RAM verwenden.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        reader.decrypt(password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def encrypt_pdf_with_transfer_password(pdf_bytes: bytes, transfer_password: str) -> bytes:
    """
    Verschlüsselt ein Klartext-PDF mit einem frei wählbaren Transfer-Passwort.
    Verwendung: E-Mail-Versand, Patientendaten-Export.
    Das transfer_password wird NICHT aus dem Master-Key abgeleitet —
    es ist ein vom User definierter Wert (z.B. Geburtsdatum des Patienten).
    """
    return encrypt_pdf(pdf_bytes, transfer_password)