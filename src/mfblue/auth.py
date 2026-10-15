from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .paths import project_path

SERVICE_NAME = "mfblue-local-budget"
TOKEN_USERNAME = "gmail-readonly-token"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_SECRET_PATH = project_path("secrets", "google_oauth_client.json")


def _get_token_json() -> str | None:
    return keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)


def _set_token_json(token_json: str) -> None:
    keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, token_json)


def _delete_token_json() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, TOKEN_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass


def load_credentials() -> Credentials | None:
    token_json = _get_token_json()
    if not token_json:
        return None
    try:
        info: dict[str, Any] = json.loads(token_json)
        return Credentials.from_authorized_user_info(info, scopes=SCOPES)
    except Exception:
        return None


def save_credentials(creds: Credentials) -> None:
    _set_token_json(creds.to_json())


def get_credentials(allow_interactive: bool = False) -> Credentials:
    creds = load_credentials()
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
        return creds
    if not allow_interactive:
        raise RuntimeError(
            "Gmail認証が未設定です。先に scripts/02_authorize_gmail.ps1 を実行してください。"
        )
    return authorize_interactive()


def authorize_interactive() -> Credentials:
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"Google OAuthクライアントJSONがありません: {CLIENT_SECRET_PATH}\n"
            "Google Cloudからダウンロードし、secrets/google_oauth_client.json として保存してください。"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    save_credentials(creds)
    return creds


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else "status"
    if cmd == "authorize":
        creds = authorize_interactive()
        print("Gmail read-only OAuthトークンをOSの資格情報保管領域に保存しました。")
        print(f"scopes: {', '.join(creds.scopes or SCOPES)}")
        return 0
    if cmd == "status":
        creds = load_credentials()
        if not creds:
            print("Gmail認証: 未設定")
            return 1
        print(f"Gmail認証: 保存済み / valid={creds.valid} / expired={creds.expired}")
        return 0
    if cmd == "reset":
        _delete_token_json()
        print("Gmail OAuthトークンを削除しました。")
        return 0
    print("Usage: python -m mfblue.auth [authorize|status|reset]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
