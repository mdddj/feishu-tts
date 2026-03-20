#!/usr/bin/env python3
"""Convert audio to OPUS and send it as a Feishu audio message."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request


FEISHU_BASE_URL = "https://open.feishu.cn"
DEFAULT_CONFIG_PATH = "~/.openclaw-autoclaw/openclaw.json"


class FeishuAudioError(RuntimeError):
    """Raised when the Feishu audio flow fails."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert audio to OPUS and send it as a Feishu audio message."
    )
    parser.add_argument("--input", required=True, help="Path to the source audio file.")
    parser.add_argument(
        "--receive-id",
        required=True,
        help="Target Feishu receive_id, such as a chat_id or open_id.",
    )
    parser.add_argument(
        "--receive-id-type",
        default="chat_id",
        choices=["chat_id", "open_id", "user_id", "union_id", "email"],
        help="Feishu receive_id_type used by the send message API.",
    )
    parser.add_argument(
        "--tenant-access-token",
        help="Use an existing tenant access token instead of requesting one.",
    )
    parser.add_argument("--app-id", help="Feishu app ID used to fetch tenant token.")
    parser.add_argument(
        "--app-secret", help="Feishu app secret used to fetch tenant token."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Config file that may contain channels.feishu.appId/appSecret.",
    )
    parser.add_argument(
        "--file-name",
        help="Uploaded file name. Defaults to the input stem with .opus suffix.",
    )
    parser.add_argument(
        "--opus-path",
        help="Write the converted OPUS file to this path instead of a temp file.",
    )
    parser.add_argument(
        "--keep-opus",
        action="store_true",
        help="Keep the converted OPUS file instead of deleting temp output.",
    )
    parser.add_argument(
        "--base-url",
        default=FEISHU_BASE_URL,
        help="Override the Feishu API base URL if required.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise FeishuAudioError(f"Input audio file not found: {input_path}")
    if shutil.which("ffmpeg") is None:
        raise FeishuAudioError("ffmpeg is required but was not found in PATH.")

    cleanup_opus = False
    opus_path = resolve_opus_path(args, input_path)
    if not args.opus_path:
        cleanup_opus = not args.keep_opus

    convert_to_opus(input_path, opus_path)

    try:
        tenant_access_token = resolve_tenant_access_token(args)
        file_name = normalize_opus_file_name(args.file_name or input_path.name)
        file_key = upload_opus(
            base_url=args.base_url,
            tenant_access_token=tenant_access_token,
            opus_path=opus_path,
            file_name=file_name,
        )
        response = send_audio_message(
            base_url=args.base_url,
            tenant_access_token=tenant_access_token,
            receive_id=args.receive_id,
            receive_id_type=args.receive_id_type,
            file_key=file_key,
        )
    finally:
        if cleanup_opus and opus_path.exists():
            opus_path.unlink()

    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def resolve_opus_path(args: argparse.Namespace, input_path: Path) -> Path:
    if args.opus_path:
        opus_path = Path(args.opus_path).expanduser().resolve()
        opus_path.parent.mkdir(parents=True, exist_ok=True)
        return opus_path
    return Path(tempfile.gettempdir()) / f"{input_path.stem}-{uuid.uuid4().hex}.opus"


def convert_to_opus(input_path: Path, opus_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-acodec",
        "libopus",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(opus_path),
    ]
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise FeishuAudioError(
            "ffmpeg conversion failed:\n"
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )


def normalize_opus_file_name(file_name: str) -> str:
    path = Path(file_name)
    if path.suffix.lower() == ".opus":
        return path.name
    return f"{path.stem}.opus"


def resolve_tenant_access_token(args: argparse.Namespace) -> str:
    direct_token = (
        args.tenant_access_token
        or os.environ.get("FEISHU_TENANT_ACCESS_TOKEN")
        or os.environ.get("LARK_TENANT_ACCESS_TOKEN")
    )
    if direct_token:
        return direct_token

    app_id = args.app_id or os.environ.get("FEISHU_APP_ID") or os.environ.get("LARK_APP_ID")
    app_secret = (
        args.app_secret
        or os.environ.get("FEISHU_APP_SECRET")
        or os.environ.get("LARK_APP_SECRET")
    )

    if not app_id or not app_secret:
        config_path = Path(args.config).expanduser()
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text())
            except json.JSONDecodeError as exc:
                raise FeishuAudioError(
                    f"Invalid JSON in config file: {config_path}"
                ) from exc
            feishu = config.get("channels", {}).get("feishu", {})
            app_id = app_id or feishu.get("appId")
            app_secret = app_secret or feishu.get("appSecret")

    if not app_id or not app_secret:
        raise FeishuAudioError(
            "Could not resolve Feishu credentials. Provide --tenant-access-token, "
            "set FEISHU_TENANT_ACCESS_TOKEN, pass --app-id/--app-secret, or ensure "
            "~/.openclaw-autoclaw/openclaw.json contains channels.feishu credentials."
        )

    token_response = post_json(
        f"{args.base_url}/open-apis/auth/v3/tenant_access_token/internal",
        payload={"app_id": app_id, "app_secret": app_secret},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    return get_ok_data(token_response, "tenant token").get("tenant_access_token") or fail(
        "Feishu token response did not include tenant_access_token."
    )


def upload_opus(
    *,
    base_url: str,
    tenant_access_token: str,
    opus_path: Path,
    file_name: str,
) -> str:
    response = post_multipart(
        f"{base_url}/open-apis/im/v1/files",
        fields={
            "file_type": "opus",
            "file_name": file_name,
        },
        file_field_name="file",
        file_path=opus_path,
        upload_file_name=file_name,
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    return get_ok_data(response, "file upload").get("file_key") or fail(
        "Feishu upload response did not include data.file_key."
    )


def send_audio_message(
    *,
    base_url: str,
    tenant_access_token: str,
    receive_id: str,
    receive_id_type: str,
    file_key: str,
) -> dict[str, Any]:
    url = (
        f"{base_url}/open-apis/im/v1/messages?"
        f"{parse.urlencode({'receive_id_type': receive_id_type})}"
    )
    payload = {
        "receive_id": receive_id,
        "msg_type": "audio",
        "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
    }
    response = post_json(
        url,
        payload=payload,
        headers={
            "Authorization": f"Bearer {tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    get_ok_data(response, "send audio message")
    return response


def post_json(url: str, *, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    return load_json(req)


def post_multipart(
    url: str,
    *,
    fields: dict[str, str],
    file_field_name: str,
    file_path: Path,
    upload_file_name: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    body = bytearray()

    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode(
                "utf-8"
            )
        )

    mime_type = "audio/ogg"
    file_bytes = file_path.read_bytes()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field_name}"; '
            f'filename="{upload_file_name}"\r\n'
        ).encode("utf-8")
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req_headers = {
        **headers,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = request.Request(url, data=bytes(body), headers=req_headers, method="POST")
    return load_json(req)


def load_json(req: request.Request) -> dict[str, Any]:
    try:
        with request.urlopen(req) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise FeishuAudioError(
            f"HTTP {exc.code} calling {req.full_url}:\n{raw}"
        ) from exc
    except error.URLError as exc:
        raise FeishuAudioError(f"Network error calling {req.full_url}: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FeishuAudioError(
            f"Expected JSON response from {req.full_url}, got:\n{raw}"
        ) from exc


def get_ok_data(response: dict[str, Any], action: str) -> dict[str, Any]:
    code = response.get("code", 0)
    if code not in (0, "0", None):
        msg = response.get("msg") or response.get("message") or "unknown error"
        raise FeishuAudioError(f"Feishu {action} failed with code {code}: {msg}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise FeishuAudioError(f"Feishu {action} response did not include a data object.")
    return data


def fail(message: str) -> None:
    raise FeishuAudioError(message)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FeishuAudioError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
