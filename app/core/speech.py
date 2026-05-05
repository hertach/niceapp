import os
import json
import urllib.request
import zipfile
import tempfile
import asyncio
from faster_whisper import WhisperModel
import vosk

VOSK_MODEL_NAME = "vosk-model-small-de-0.15"

class SpeechManager:
    _whisper_model = None
    _vosk_model = None
    _lock = asyncio.Lock()

    @classmethod
    def ensure_models(cls):
        """Stellt sicher, dass alle Modell-Dateien vorhanden sind."""
        # Vosk Download
        if not os.path.exists(VOSK_MODEL_NAME):
            print(f"Lade Vosk-Modell {VOSK_MODEL_NAME} herunter (ca. 45MB)...")
            url = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"
            zip_path = "vosk_tmp.zip"
            try:
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(".")
                os.remove(zip_path)
                print("Vosk-Modell erfolgreich installiert.")
            except Exception as e:
                print(f"Fehler beim Vosk-Download: {e}")

        # Whisper Initialisierung (triggert Download bei Bedarf)
        if cls._whisper_model is None:
            print("Initialisiere Whisper (Modell: small)...")
            try:
                cls._whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
                print("Whisper bereit.")
            except Exception as e:
                print(f"Whisper Fehler: {e}")

        if cls._vosk_model is None and os.path.exists(VOSK_MODEL_NAME):
            vosk.SetLogLevel(-1)
            cls._vosk_model = vosk.Model(VOSK_MODEL_NAME)
            print("Vosk bereit.")

    @classmethod
    def get_whisper(cls):
        if cls._whisper_model is None:
            cls.ensure_models()
        return cls._whisper_model

    @classmethod
    def get_vosk(cls):
        if cls._vosk_model is None:
            cls.ensure_models()
        return cls._vosk_model