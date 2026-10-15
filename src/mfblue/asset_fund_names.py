from __future__ import annotations

import re
import unicodedata

_DASH_PATTERN = re.compile(r"[‐‑‒–—―ーｰ−]")
_SPACE_PATTERN = re.compile(r"\s+")
_TRIM_AROUND_SYMBOLS = re.compile(r"\s*([()\[\]{}&/+,\.-])\s*")


def normalize_asset_fund_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", str(name or ""))
    text = text.replace("\u3000", " ").replace("\u00a0", " ")
    text = _DASH_PATTERN.sub("-", text)
    text = _SPACE_PATTERN.sub(" ", text).strip().casefold()
    text = _TRIM_AROUND_SYMBOLS.sub(r"\1", text)
    return text.replace(" ", "")

