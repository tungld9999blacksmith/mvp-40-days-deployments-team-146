from pathlib import Path
import os

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth

load_dotenv(Path(__file__).resolve().parents[5] / ".env")

cred_path = Path(__file__).parent.parent.parent.parent / "assets" / "secrets" / os.getenv("FIREBASE_CREDENTIAL")

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

