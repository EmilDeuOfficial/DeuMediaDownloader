"""Regenerate frontend/mock/bootstrap.json from the real backend definitions.

The mock bridge (?mock=1) serves this file as the result of api.bootstrap() so the
browser preview shows the real strings, format lists and default config.
Run from the project root:  python tools/gen_mock_data.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api import Api  # noqa: E402
import config  # noqa: E402


class _Silent:
    def emit(self, *_a, **_k):
        pass


def main() -> None:
    for lang, name in (("en", "bootstrap.json"), ("de", "bootstrap.de.json")):
        write(lang, name)


def write(lang: str, name: str) -> None:
    config._lang = lang
    config.CONFIG_FILE = ROOT / "frontend" / "mock" / "_unused_config.json"
    api = Api(_Silent(), {}, ffmpeg_ok=True, spawn=lambda fn: None)
    api._load = lambda: dict(config.DEFAULT_CONFIG)  # never touch the real config file
    res = api.bootstrap()
    assert res["ok"], res
    # Keep the local user name out of the committed file.
    home = str(Path.home())
    for key, value in res["data"]["config"].items():
        if isinstance(value, str) and value.startswith(home):
            res["data"]["config"][key] = "C:/Users/Demo" + value[len(home):].replace("\\", "/")
    out = ROOT / "frontend" / "mock" / name
    out.write_text(json.dumps(res["data"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
