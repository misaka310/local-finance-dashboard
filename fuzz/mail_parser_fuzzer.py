from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from mfblue.parser import ParseError, normalize_text, parse_amazon_order_email, parse_paypay_card_email


def TestOneInput(data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    normalized = normalize_text(text)
    headers = {"Date": text[:256], "From": text[:256]}
    for parser in (parse_amazon_order_email, parse_paypay_card_email):
        try:
            parser(text[:512], normalized[:20000], headers)
        except (ParseError, ValueError, OverflowError):
            pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
