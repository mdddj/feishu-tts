#!/usr/bin/env python3
"""Generate speech from text and send it to Feishu as a voice bubble."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

from send_feishu_audio import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_REQUEST_TIMEOUT,
    DeliveryOptions,
    FeishuAudioError,
    deliver_audio_file,
)


DEFAULT_TTS_API_URL = "https://api.openai.com/v1/audio/speech"
DEFAULT_TTS_MODEL = "tts-1"
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_CHATTTS_URL = "http://127.0.0.1:8080"
DEFAULT_CHATTTS_PATH = "/tts"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate speech from text and send it as a Feishu audio message."
    )
    parser.add_argument(
        "--mode",
        choices=["api", "local"],
        default="api",
        help="Speech generation mode: remote API or local ChatTTS service.",
    )
    text_group = parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("--text", help="Text to convert into speech.")
    text_group.add_argument(
        "--text-file",
        help="UTF-8 text file to read before generating speech.",
    )
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
        help="Uploaded OPUS file name. Defaults to a generated name.",
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
        "--source-audio-path",
        help="Write the generated source audio to this path instead of a temp file.",
    )
    parser.add_argument(
        "--keep-source-audio",
        action="store_true",
        help="Keep the generated source audio instead of deleting temp output.",
    )
    parser.add_argument(
        "--base-url",
        default="https://open.feishu.cn",
        help="Override the Feishu API base URL if required.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="HTTP timeout in seconds for TTS and Feishu API requests.",
    )

    parser.add_argument(
        "--tts-api-url",
        default=os.environ.get("TTS_API_URL") or DEFAULT_TTS_API_URL,
        help="Remote TTS endpoint for --mode api.",
    )
    parser.add_argument(
        "--tts-api-key",
        help="Bearer token for --mode api. Falls back to TTS_API_KEY or OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--tts-model",
        default=os.environ.get("TTS_MODEL") or DEFAULT_TTS_MODEL,
        help="Model name for --mode api.",
    )
    parser.add_argument(
        "--voice",
        default=os.environ.get("TTS_VOICE") or DEFAULT_TTS_VOICE,
        help="Voice name for --mode api.",
    )
    parser.add_argument(
        "--response-format",
        choices=["mp3", "wav", "opus", "aac", "flac", "pcm"],
        default=os.environ.get("TTS_RESPONSE_FORMAT") or "mp3",
        help="Requested response format for --mode api.",
    )

    parser.add_argument(
        "--chattts-url",
        default=os.environ.get("CHATTTS_URL") or DEFAULT_CHATTTS_URL,
        help="Base URL of the local ChatTTS service for --mode local.",
    )
    parser.add_argument(
        "--chattts-path",
        default=DEFAULT_CHATTTS_PATH,
        help="Path appended to --chattts-url for --mode local.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=500,
        help="Random seed for the local ChatTTS request.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    text = resolve_text(args)

    if args.mode == "api":
        audio_bytes, source_suffix = generate_voice_api(text=text, args=args)
    else:
        audio_bytes, source_suffix = generate_voice_local(text=text, args=args)

    source_audio_path, cleanup_source_audio = resolve_source_audio_path(
        requested_path=args.source_audio_path,
        keep_source_audio=args.keep_source_audio,
        suffix=source_suffix,
    )
    source_audio_path.write_bytes(audio_bytes)

    options = DeliveryOptions(
        receive_id=args.receive_id,
        receive_id_type=args.receive_id_type,
        tenant_access_token=args.tenant_access_token,
        app_id=args.app_id,
        app_secret=args.app_secret,
        config_path=args.config,
        file_name=args.file_name or f"tts-{uuid.uuid4().hex}.opus",
        opus_path=Path(args.opus_path).expanduser().resolve() if args.opus_path else None,
        keep_opus=args.keep_opus,
        base_url=args.base_url,
        request_timeout=args.request_timeout,
    )

    try:
        response = deliver_audio_file(input_path=source_audio_path, options=options)
    finally:
        if cleanup_source_audio and source_audio_path.exists():
            source_audio_path.unlink()

    output: dict[str, Any] = {"feishu": response}
    if not cleanup_source_audio and source_audio_path.exists():
        output["generated_audio_path"] = str(source_audio_path)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def resolve_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        text = args.text
    else:
        text_path = Path(args.text_file).expanduser().resolve()
        if not text_path.is_file():
            raise FeishuAudioError(f"Text file not found: {text_path}")
        text = text_path.read_text(encoding="utf-8")

    if not text.strip():
        raise FeishuAudioError("Input text is empty.")
    return text


def resolve_source_audio_path(
    *,
    requested_path: str | None,
    keep_source_audio: bool,
    suffix: str,
) -> tuple[Path, bool]:
    normalized_suffix = suffix.lstrip(".") or "mp3"
    if requested_path:
        path = Path(requested_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path, False
    temp_path = Path(tempfile.gettempdir()) / f"feishu-tts-{uuid.uuid4().hex}.{normalized_suffix}"
    return temp_path, not keep_source_audio


def generate_voice_api(*, text: str, args: argparse.Namespace) -> tuple[bytes, str]:
    api_key = args.tts_api_key or os.environ.get("TTS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise FeishuAudioError(
            "API mode requires --tts-api-key, TTS_API_KEY, or OPENAI_API_KEY."
        )

    payload = {
        "model": args.tts_model,
        "input": text,
        "voice": args.voice,
        "response_format": args.response_format,
    }
    req = request.Request(
        args.tts_api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    audio_bytes, content_type = request_binary(req, timeout=args.request_timeout)
    if content_type.startswith("application/json"):
        return decode_json_audio_response(audio_bytes, timeout=args.request_timeout)
    return audio_bytes, guess_audio_suffix(content_type, fallback=args.response_format)


def generate_voice_local(*, text: str, args: argparse.Namespace) -> tuple[bytes, str]:
    url = build_url(args.chattts_url, args.chattts_path)
    payload = {"text": text, "seed": args.seed}
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    audio_bytes, content_type = request_binary(req, timeout=args.request_timeout)
    if content_type.startswith("application/json"):
        return decode_json_audio_response(audio_bytes, timeout=args.request_timeout)
    return audio_bytes, guess_audio_suffix(content_type, fallback="wav")


def build_url(base_url: str, path: str) -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalized_base}{normalized_path}"


def request_binary(req: request.Request, *, timeout: float) -> tuple[bytes, str]:
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            return body, content_type
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise FeishuAudioError(f"HTTP {exc.code} calling {req.full_url}:\n{raw}") from exc
    except error.URLError as exc:
        raise FeishuAudioError(f"Network error calling {req.full_url}: {exc}") from exc


def decode_json_audio_response(
    body: bytes,
    *,
    timeout: float,
) -> tuple[bytes, str]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FeishuAudioError("ChatTTS returned JSON content that could not be parsed.") from exc

    audio_base64 = first_string(
        payload.get("audio_base64"),
        payload.get("audioBase64"),
        nested_get(payload, "data", "audio_base64"),
        nested_get(payload, "data", "audioBase64"),
    )
    if audio_base64:
        try:
            decoded = base64.b64decode(audio_base64)
        except ValueError as exc:
            raise FeishuAudioError("ChatTTS returned invalid base64 audio content.") from exc
        return decoded, guess_audio_suffix_from_payload(payload, fallback="wav")

    audio_url = first_string(
        payload.get("audio_url"),
        payload.get("audioUrl"),
        payload.get("url"),
        nested_get(payload, "data", "audio_url"),
        nested_get(payload, "data", "audioUrl"),
        nested_get(payload, "data", "url"),
    )
    if audio_url:
        req = request.Request(audio_url, method="GET")
        audio_bytes, content_type = request_binary(req, timeout=timeout)
        return audio_bytes, guess_audio_suffix(
            content_type,
            fallback=guess_audio_suffix_from_payload(payload, fallback="wav"),
        )

    raise FeishuAudioError(
        "ChatTTS returned JSON, but no supported audio payload was found. "
        "Expected audio bytes, audio_base64, or audio_url."
    )


def nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def guess_audio_suffix_from_payload(payload: dict[str, Any], *, fallback: str) -> str:
    format_name = first_string(
        payload.get("format"),
        nested_get(payload, "data", "format"),
        payload.get("audio_format"),
        nested_get(payload, "data", "audio_format"),
    )
    if format_name:
        return format_name.lower().lstrip(".")
    return fallback


def guess_audio_suffix(content_type: str, *, fallback: str) -> str:
    content_type = content_type.split(";", 1)[0].strip().lower()
    mapping = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/wave": "wav",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
        "audio/flac": "flac",
        "audio/aac": "aac",
        "audio/pcm": "pcm",
        "audio/linear16": "wav",
    }
    return mapping.get(content_type, fallback)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FeishuAudioError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
