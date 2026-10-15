from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any

YEN_RE = re.compile(r"([0-9０-９][0-9０-９,，]*)\s*(?:円|JPY)", re.IGNORECASE)
YEN_MARK_RE = re.compile(r"[¥￥]\s*([0-9０-９][0-9０-９,，]*)")
DATE_RE = re.compile(r"(20\d{2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?(?:\s*[（(]?[月火水木金土日][）)]?)?(?:\s+(\d{1,2})[:：時](\d{2})?)?")
MONTH_DAY_RE = re.compile(r"(\d{1,2})[月/\-.](\d{1,2})日?(?:\s+(\d{1,2})[:：時](\d{2})?)?")
AMAZON_ORDER_NUMBER_RE = re.compile(r"(?:注文番号|注文No\.?|Order\s*#?)\s*[:：]?\s*([0-9０-９]{3}-[0-9０-９]{7}-[0-9０-９]{7})", re.IGNORECASE)

AMOUNT_KEYWORDS = [
    "ご利用金額",
    "利用金額",
    "ご請求金額",
    "請求金額",
    "決済金額",
    "お支払い金額",
    "金額",
]

MERCHANT_KEYWORDS = [
    "ご利用先",
    "利用先",
    "ご利用店名",
    "利用店名",
    "加盟店名",
    "加盟店",
    "店舗名",
    "店名",
    "ショップ",
]

SUBJECT_NOISE = ["【PayPayカード】", "PayPayカード", "ご利用", "のお知らせ", "利用速報", "カード利用速報"]

AMAZON_CONFIRM_SUBJECT_KEYWORDS = [
    "注文済み",
    "注文を確定しました",
    "ご注文の確認",
    "注文確認",
    "注文内容の確認",
    "ご注文内容",
]
AMAZON_CONFIRM_BODY_AMOUNT_KEYWORDS = [
    "注文合計",
    "ご請求額",
    "お支払い金額",
    "請求額",
]
AMAZON_SHIPPING_STATUS_SUBJECT_KEYWORDS = [
    "発送しました",
    "発送のお知らせ",
    "出荷",
    "配送中",
    "配達完了",
    "お届け完了",
]
AMAZON_CANCEL_REFUND_RETURN_KEYWORDS = [
    "キャンセル",
    "返金",
    "返品",
]
AMAZON_NON_ORDER_SUBJECT_KEYWORDS = [
    "セール",
    "おすすめ",
    "タイムセール",
    "Prime",
    "prime",
    "プライム会員",
    "会員特典",
    "プライムデー",
]
AMAZON_AMOUNT_KEYWORDS = [
    "注文合計",
    "合計",
    "ご請求額",
    "お支払い金額",
    "請求額",
]
AMAZON_AMOUNT_EXCLUDE_KEYWORDS = [
    "送料",
    "配送料",
    "獲得ポイント",
    "ポイント",
    "値引き",
    "クーポン",
    "割引",
    "税",
]
AMAZON_ORDER_DATE_KEYWORDS = [
    "注文日",
    "ご注文日",
    "注文日時",
    "注文時刻",
]


@dataclass
class ParsedTransaction:
    occurred_at: str
    merchant: str
    amount_yen: int
    raw_description: str
    direction: str = "expense"
    external_id_hint: str | None = None


class ParseError(Exception):
    pass


class ParseSkip(ParseError):
    pass


def normalize_text(text: str) -> str:
    text = unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # HTMLメールを雑にテキスト化する保険
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u3000", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return "\n".join([line for line in lines if line])


def z2h_digits(value: str) -> str:
    return value.translate(str.maketrans("０１２３４５６７８９，", "0123456789,"))


def parse_yen(value: str) -> int:
    return int(z2h_digits(value).replace(",", ""))


def parse_header_date(headers: dict[str, str]) -> datetime | None:
    date_raw = headers.get("date") or headers.get("Date")
    if not date_raw:
        return None
    try:
        dt = parsedate_to_datetime(date_raw)
        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        return None


def find_amount(text: str) -> int:
    lines = text.split("\n")
    for line in lines:
        if any(key in line for key in AMOUNT_KEYWORDS):
            m = YEN_RE.search(line)
            if m:
                return parse_yen(m.group(1))
    # キーワード行の次の行に金額があるパターン
    for i, line in enumerate(lines[:-1]):
        if any(key in line for key in AMOUNT_KEYWORDS):
            m = YEN_RE.search(lines[i + 1])
            if m:
                return parse_yen(m.group(1))
    amounts = [parse_yen(m.group(1)) for m in YEN_RE.finditer(text)]
    if not amounts:
        raise ParseError("金額を見つけられませんでした")
    # カード下4桁などを拾う事故を避けるため、小さすぎる値は最後の手段では除外する。
    candidates = [a for a in amounts if a >= 3]
    if not candidates:
        raise ParseError("有効な金額候補を見つけられませんでした")
    return max(candidates)


def clean_merchant(value: str) -> str:
    value = re.sub(r"^[：:\-\s]+", "", value).strip()
    value = re.sub(r"\s+", " ", value)
    value = YEN_RE.sub("", value).strip()
    for word in MERCHANT_KEYWORDS:
        value = value.replace(word, "")
    value = re.sub(r"^[：:\-\s]+", "", value).strip()
    return value[:120]


def find_merchant(text: str, subject: str) -> str:
    lines = text.split("\n")
    for line in lines:
        if any(key in line for key in MERCHANT_KEYWORDS):
            # 例: ご利用先：セブンイレブン
            parts = re.split(r"[:：]", line, maxsplit=1)
            candidate = parts[1] if len(parts) == 2 else line
            candidate = clean_merchant(candidate)
            if candidate and not YEN_RE.fullmatch(candidate):
                return candidate
    # キーワード行の次の行に店舗名があるパターン
    for i, line in enumerate(lines[:-1]):
        if any(key in line for key in MERCHANT_KEYWORDS):
            candidate = clean_merchant(lines[i + 1])
            if candidate:
                return candidate
    # 件名から最低限の説明を作る
    merchant = subject or "PayPayカード利用"
    for noise in SUBJECT_NOISE:
        merchant = merchant.replace(noise, "")
    merchant = merchant.strip(" ｜|:：-　")
    return merchant or "PayPayカード利用"


def find_occurred_date(text: str, headers: dict[str, str]) -> str:
    # 本文に利用日時があれば優先する。
    lines = text.split("\n")
    keyword_lines = [line for line in lines if any(k in line for k in ["利用日時", "ご利用日時", "利用日", "ご利用日", "日時", "日付"])]
    haystacks = keyword_lines + lines
    for line in haystacks:
        m = DATE_RE.search(line)
        if m:
            y, mo, d, hh, mm = m.groups()
            return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0)).date().isoformat()
    header_dt = parse_header_date(headers)
    if header_dt:
        for line in haystacks:
            m = MONTH_DAY_RE.search(line)
            if m:
                mo, d, hh, mm = m.groups()
                return datetime(header_dt.year, int(mo), int(d), int(hh or 0), int(mm or 0)).date().isoformat()
        return header_dt.date().isoformat()
    raise ParseError("利用日を見つけられませんでした")


def _extract_amount_candidates(line: str) -> list[int]:
    yen_plain = [parse_yen(m.group(1)) for m in YEN_RE.finditer(line)]
    yen_marked = [parse_yen(m.group(1)) for m in YEN_MARK_RE.finditer(line)]
    return [*yen_plain, *yen_marked]


def _parse_japanese_date_in_line(line: str) -> datetime | None:
    m = DATE_RE.search(line)
    if not m:
        return None
    y, mo, d, hh, mm = m.groups()
    return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0))


def _is_amazon_sender(headers: dict[str, str]) -> bool:
    from_raw = (headers.get("from") or headers.get("From") or "").lower()
    return "amazon.co.jp" in from_raw or "amazon.co" in from_raw


def _is_amazon_order_mail(subject: str, text: str, headers: dict[str, str]) -> bool:
    compact_subject = subject.strip()
    compact_text = text
    is_amazon_context = _is_amazon_sender(headers) or "amazon.co.jp" in compact_text.lower() or "amazon.co.jp" in compact_subject.lower()
    if not is_amazon_context:
        return False

    # キャンセル・返金・返品は注文支出として取り込まない。
    if any(keyword in compact_subject for keyword in AMAZON_CANCEL_REFUND_RETURN_KEYWORDS):
        return False
    if any(keyword in compact_text for keyword in AMAZON_CANCEL_REFUND_RETURN_KEYWORDS):
        return False

    # 発送/配達ステータスメールは件名ベースで除外する。
    if any(keyword in compact_subject for keyword in AMAZON_SHIPPING_STATUS_SUBJECT_KEYWORDS):
        return False
    if any(keyword in compact_subject for keyword in AMAZON_NON_ORDER_SUBJECT_KEYWORDS):
        return False

    # 肯定条件優先: 件名が注文確認系、または本文に注文番号+金額系キーワードがある。
    has_subject_confirmation = any(keyword in compact_subject for keyword in AMAZON_CONFIRM_SUBJECT_KEYWORDS)
    has_body_order_number = "注文番号" in compact_text
    has_body_amount_hint = any(keyword in compact_text for keyword in AMAZON_CONFIRM_BODY_AMOUNT_KEYWORDS)
    return has_subject_confirmation or (has_body_order_number and has_body_amount_hint)


def _find_amazon_amount(text: str) -> int:
    lines = text.split("\n")
    for line in lines:
        if any(key in line for key in AMAZON_AMOUNT_KEYWORDS):
            if any(ng in line for ng in AMAZON_AMOUNT_EXCLUDE_KEYWORDS):
                continue
            candidates = _extract_amount_candidates(line)
            if candidates:
                return max(candidates)
    for i, line in enumerate(lines[:-1]):
        if any(key in line for key in AMAZON_AMOUNT_KEYWORDS):
            if any(ng in line for ng in AMAZON_AMOUNT_EXCLUDE_KEYWORDS):
                continue
            candidates = _extract_amount_candidates(lines[i + 1])
            if candidates:
                return max(candidates)
    raise ParseError("Amazon注文メールから注文合計を見つけられませんでした")


def _find_amazon_occurred_date(text: str, headers: dict[str, str]) -> str:
    lines = text.split("\n")
    candidates = [line for line in lines if any(k in line for k in AMAZON_ORDER_DATE_KEYWORDS)]
    for line in [*candidates, *lines]:
        dt = _parse_japanese_date_in_line(line)
        if dt:
            return dt.date().isoformat()
    header_dt = parse_header_date(headers)
    if header_dt:
        return header_dt.date().isoformat()
    raise ParseError("Amazon注文メールの日付を見つけられませんでした")


def _extract_amazon_order_number(subject: str, text: str) -> str | None:
    match = AMAZON_ORDER_NUMBER_RE.search(text) or AMAZON_ORDER_NUMBER_RE.search(subject)
    if not match:
        return None
    return z2h_digits(match.group(1)).replace("，", ",")


def parse_paypay_card_email(subject: str, body_text: str, headers: dict[str, str]) -> ParsedTransaction:
    text = normalize_text(body_text)
    amount = find_amount(text)
    merchant = find_merchant(text, subject)
    occurred_at = find_occurred_date(text, headers)
    description_parts = [subject.strip(), merchant]
    return ParsedTransaction(
        occurred_at=occurred_at,
        merchant=merchant,
        amount_yen=amount,
        raw_description=" / ".join([p for p in description_parts if p]),
    )


def parse_amazon_order_email(subject: str, body_text: str, headers: dict[str, str]) -> ParsedTransaction:
    text = normalize_text(body_text)
    if not _is_amazon_order_mail(subject, text, headers):
        raise ParseSkip("Amazon注文確定/確認メールではないため取り込み対象外です")

    amount = _find_amazon_amount(text)
    occurred_at = _find_amazon_occurred_date(text, headers)
    order_number = _extract_amazon_order_number(subject, text)
    raw_description = subject.strip()
    if order_number:
        raw_description = f"{raw_description} / 注文番号:{order_number}" if raw_description else f"注文番号:{order_number}"

    return ParsedTransaction(
        occurred_at=occurred_at,
        merchant="Amazon.co.jp",
        amount_yen=amount,
        raw_description=raw_description[:200],
        direction="expense",
        external_id_hint=order_number,
    )
