#!/usr/bin/env python3
"""Check whether the local environment is ready for Feishu audio delivery."""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("~/.openclaw-autoclaw/openclaw.json").expanduser()


def main() -> int:
    rows: list[tuple[str, bool, str]] = []
    system = platform.system().lower()

    brew_path = shutil.which("brew") if system == "darwin" else None
    if system == "darwin":
        rows.append(
            (
                "homebrew",
                brew_path is not None,
                brew_path or "not found in PATH",
            )
        )

    python3_path = shutil.which("python3")
    rows.append(
        (
            "python3",
            python3_path is not None,
            python3_path or "not found in PATH",
        )
    )

    ffmpeg_path = shutil.which("ffmpeg")
    rows.append(
        (
            "ffmpeg",
            ffmpeg_path is not None,
            ffmpeg_path or "not found in PATH",
        )
    )

    config_exists = DEFAULT_CONFIG_PATH.is_file()
    rows.append(
        (
            "openclaw config",
            config_exists,
            str(DEFAULT_CONFIG_PATH) if config_exists else f"missing: {DEFAULT_CONFIG_PATH}",
        )
    )

    env_names = [
        "FEISHU_TENANT_ACCESS_TOKEN",
        "LARK_TENANT_ACCESS_TOKEN",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "LARK_APP_ID",
        "LARK_APP_SECRET",
    ]
    for name in env_names:
        rows.append((name, bool(os.environ.get(name)), "set" if os.environ.get(name) else "not set"))

    config_summary = inspect_config(DEFAULT_CONFIG_PATH) if config_exists else None

    print("Feishu TTS environment check")
    print("")
    for name, ok, detail in rows:
        status = "OK" if ok else "MISSING"
        print(f"[{status}] {name}: {detail}")

    if config_summary:
        print("")
        print("Config details")
        print(config_summary)

    missing_core = [name for name, ok, _ in rows if name in {"python3", "ffmpeg"} and not ok]
    if missing_core:
        print("")
        print("Core dependencies are missing:", ", ".join(missing_core))
        print("")
        print("Suggested install commands")
        for line in install_suggestions(missing_core, brew_installed=brew_path is not None):
            print(line)
        return 1

    print("")
    print("Core runtime looks usable.")

    if not config_exists and not has_any_feishu_env():
        print("")
        print("Feishu credentials are not ready yet.")
        print(f"- Add app credentials to {DEFAULT_CONFIG_PATH}")
        print("- Or export FEISHU_APP_ID and FEISHU_APP_SECRET")
        print("- Or export FEISHU_TENANT_ACCESS_TOKEN directly")

    return 0


def inspect_config(config_path: Path) -> str:
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return "openclaw.json exists but is not valid JSON"

    feishu = config.get("channels", {}).get("feishu", {})
    if not isinstance(feishu, dict):
        return "openclaw.json exists but channels.feishu is missing"

    app_id = "present" if feishu.get("appId") else "missing"
    app_secret = "present" if feishu.get("appSecret") else "missing"
    return f"channels.feishu.appId={app_id}, channels.feishu.appSecret={app_secret}"


def has_any_feishu_env() -> bool:
    env_names = {
        "FEISHU_TENANT_ACCESS_TOKEN",
        "LARK_TENANT_ACCESS_TOKEN",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "LARK_APP_ID",
        "LARK_APP_SECRET",
    }
    return any(os.environ.get(name) for name in env_names)


def install_suggestions(missing_core: list[str], *, brew_installed: bool) -> list[str]:
    system = platform.system().lower()
    suggestions: list[str] = []

    if system == "darwin":
        if not brew_installed:
            suggestions.append("- macOS: install Homebrew first: `https://brew.sh`")
        if "python3" in missing_core:
            suggestions.append("- macOS: `brew install python`")
        if "ffmpeg" in missing_core:
            suggestions.append("- macOS: `brew install ffmpeg`")
        return suggestions

    if system == "linux":
        if "python3" in missing_core or "ffmpeg" in missing_core:
            pkg_names = []
            if "python3" in missing_core:
                pkg_names.append("python3")
            if "ffmpeg" in missing_core:
                pkg_names.append("ffmpeg")
            joined = " ".join(pkg_names)
            suggestions.append(f"- Debian/Ubuntu: `sudo apt update && sudo apt install -y {joined}`")
            suggestions.append(f"- Fedora: `sudo dnf install -y {joined}`")
            suggestions.append(f"- Arch: `sudo pacman -S --needed {joined}`")
        return suggestions

    if system == "windows":
        if "python3" in missing_core:
            suggestions.append("- Windows: `winget install Python.Python.3`")
        if "ffmpeg" in missing_core:
            suggestions.append("- Windows: `winget install Gyan.FFmpeg`")
        suggestions.append("- If winget is unavailable, install Python and FFmpeg manually and restart the terminal.")
        return suggestions

    suggestions.append("- Install Python 3 and FFmpeg with your system package manager, then rerun this check.")
    return suggestions


if __name__ == "__main__":
    raise SystemExit(main())
