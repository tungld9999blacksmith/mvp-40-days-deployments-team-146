import json
import os
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials

load_dotenv(Path(__file__).resolve().parents[5] / ".env")


def _load_credential() -> credentials.Certificate:
    # Local: JSON file in assets/secrets/ (FIREBASE_CREDENTIAL = file name).
    # Deploy (Railway/CI): no file -> JSON content in FIREBASE_CREDENTIAL_JSON.
    file_name = os.getenv("FIREBASE_CREDENTIAL")
    if file_name:
        cred_path = Path(__file__).parent.parent.parent.parent / "assets" / "secrets" / file_name
        if cred_path.is_file():
            return credentials.Certificate(cred_path)

    cred_json = os.getenv("FIREBASE_CREDENTIAL_JSON")
    if cred_json:
        return credentials.Certificate(json.loads(cred_json))

    raise RuntimeError(
        "Firebase credential not found: put the JSON file in assets/secrets/ "
        "(FIREBASE_CREDENTIAL=<file name>) or set FIREBASE_CREDENTIAL_JSON"
    )


if not firebase_admin._apps:
    firebase_admin.initialize_app(_load_credential())
