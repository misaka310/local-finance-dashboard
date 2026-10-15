from __future__ import annotations

from typing import Iterable


ACCOUNT_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "amazon": ("amazon-order-history", "amazon-order"),
}


def normalize_account_group(value: str | None) -> str | None:
    group = (value or "").strip().lower()
    return group or None


def resolve_account_filter(
    *,
    account_id: str | None,
    account_group: str | None,
) -> tuple[str, list[str] | None]:
    group = normalize_account_group(account_group)
    if group:
        members = ACCOUNT_GROUP_MEMBERS.get(group)
        if not members:
            raise ValueError(f"unsupported account_group: {group}")
        return f"group:{group}", list(members)

    normalized = (account_id or "").strip()
    if not normalized or normalized == "all":
        return "all", None

    if normalized in {"amazon", "group:amazon"}:
        return "group:amazon", list(ACCOUNT_GROUP_MEMBERS["amazon"])

    return normalized, [normalized]


def is_group_member(account_id: str, group: str) -> bool:
    members: Iterable[str] = ACCOUNT_GROUP_MEMBERS.get(group, ())
    return account_id in members
