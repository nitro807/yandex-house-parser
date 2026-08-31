from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse, urlunparse

from .models import Organization


SPACE_RE = re.compile(r"\s+")
ORG_PATH_RE = re.compile(r"/(?:maps/)?org/(?:[^/]+/)?(\d+)/?")


def inside_url_for_house(url: str) -> str | None:
    """Return the canonical `inside` URL only for a real Yandex house page."""
    parsed = urlparse(url)
    if "/house/" not in parsed.path:
        return None
    path = parsed.path.rstrip("/") + "/inside/"
    return urlunparse(parsed._replace(path=path, fragment=""))


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = SPACE_RE.sub(" ", value).strip(" \n\t,;")
    return value or None


def normalize_address(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold().replace("ё", "е")
    value = re.sub(r"\b(?:город|г\.)\s*", "", value)
    value = re.sub(r"\b(?:улица|ул\.)\s*", "", value)
    value = re.sub(r"\b(?:дом|д\.)\s*", "", value)
    value = re.sub(r"[^0-9a-zа-я/]+", " ", value)
    return SPACE_RE.sub(" ", value).strip()


def address_matches(
    candidate: str | None,
    house: str | None,
    *,
    allow_missing_candidate: bool = False,
) -> bool:
    left = normalize_address(candidate)
    right = normalize_address(house)
    if not right:
        return True
    if not left:
        return allow_missing_candidate
    left_numbers = re.findall(r"\b\d+[a-zа-я]?(?:[/кстр.-]\d+[a-zа-я]?)?\b", left)
    right_numbers = re.findall(r"\b\d+[a-zа-я]?(?:[/кстр.-]\d+[a-zа-я]?)?\b", right)
    if left_numbers and right_numbers and left_numbers[-1] != right_numbers[-1]:
        return False
    if left.split() == right.split():
        return True
    left_tokens, right_tokens = set(left.split()), set(right.split())
    shared = left_tokens & right_tokens
    return len(shared) >= min(4, max(2, len(right_tokens) - 1))


def walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def _phone_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            phone = clean_text(item)
        elif isinstance(item, dict):
            phone = clean_text(item.get("formatted") or item.get("value") or item.get("number"))
        else:
            phone = None
        if phone and phone not in result:
            result.append(phone)
    return result


def _email_value(value: Any) -> str | None:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, dict):
            item = item.get("value") or item.get("email") or item.get("address")
        email = clean_text(item)
        if email and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return email
    return None


def _categories(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for item in value:
        name = clean_text(item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None)
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or None


def _rating(node: dict[str, Any]) -> float | None:
    rating_data = node.get("ratingData") if isinstance(node.get("ratingData"), dict) else {}
    value = node.get("rating") or node.get("ratingValue") or rating_data.get("ratingValue")
    try:
        return float(str(value).replace(",", ".")) if value is not None else None
    except ValueError:
        return None


def organization_from_node(node: dict[str, Any]) -> Organization | None:
    properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    company = properties.get("CompanyMetaData") if isinstance(properties.get("CompanyMetaData"), dict) else None
    source = company or node

    node_type = str(node.get("type") or source.get("type") or "").casefold()
    has_business_shape = bool(company) or node_type == "business" or any(
        key in source for key in ("categories", "Categories", "phones", "Phones", "businessLinks", "ratingData")
    )
    if not has_business_shape:
        return None

    name = clean_text(source.get("title") or source.get("name") or properties.get("name"))
    if not name:
        return None

    company_id = clean_text(source.get("id") or source.get("oid"))
    address_obj = source.get("Address") if isinstance(source.get("Address"), dict) else {}
    address = clean_text(
        source.get("fullAddress")
        or source.get("address")
        or address_obj.get("formatted")
        or properties.get("description")
    )
    categories = _categories(source.get("categories") or source.get("Categories"))
    phones = _phone_values(source.get("phones") or source.get("Phones"))

    links = source.get("businessLinks") if isinstance(source.get("businessLinks"), list) else []
    email = _email_value(source.get("email") or source.get("emails") or source.get("Email"))
    website = clean_text(source.get("url") or source.get("website"))
    for link in links:
        if not isinstance(link, dict):
            continue
        link_type = str(link.get("type", "")).casefold()
        link_value = clean_text(link.get("link") or link.get("url") or link.get("value"))
        if not website and link_type in {"website", "site"}:
            website = link_value
        elif not email and link_type in {"email", "mail"}:
            email = _email_value(link_value)

    uri = clean_text(source.get("uri") or properties.get("uri"))
    yandex_url = clean_text(source.get("urlForYandexMaps") or source.get("yandexUrl"))
    if not yandex_url and company_id:
        yandex_url = f"https://yandex.ru/maps/org/{company_id}/"
    elif not yandex_url and uri and "oid=" in uri:
        yandex_url = f"https://yandex.ru/maps/org/{uri.rsplit('oid=', 1)[-1]}/"

    return Organization(
        id=company_id,
        name=name,
        category=categories,
        address=address,
        phones=phones,
        email=email,
        website=website,
        rating=_rating(source),
        yandex_url=yandex_url,
    )


def organizations_from_payloads(
    payloads: Iterable[Any],
    house_address: str | None = None,
    *,
    allow_missing_address: bool = False,
) -> list[Organization]:
    found: list[Organization] = []
    seen: set[str] = set()
    for payload in payloads:
        for node in walk_json(payload):
            organization = organization_from_node(node)
            if not organization or not address_matches(
                organization.address,
                house_address,
                allow_missing_candidate=allow_missing_address,
            ):
                continue
            key = organization.id or f"{normalize_address(organization.name)}|{normalize_address(organization.address)}"
            if key in seen:
                continue
            seen.add(key)
            found.append(organization)
    return found


def probable_house_address(values: Iterable[str | None]) -> str | None:
    cleaned = [clean_text(value) for value in values]
    candidates = [value for value in cleaned if value and any(char.isdigit() for char in value)]
    if not candidates:
        return None
    normalized_counts = Counter(normalize_address(value) for value in candidates)
    winner = normalized_counts.most_common(1)[0][0]
    return next(value for value in candidates if normalize_address(value) == winner)


def organization_from_dom(
    name: str,
    href: str,
    text: str,
    *,
    category: str | None = None,
    address: str | None = None,
) -> Organization | None:
    name = clean_text(name)
    match = ORG_PATH_RE.fullmatch(urlparse(href).path)
    if not name or name.casefold() in {"фото", "галерея", "отзывы", "карта"} or not match:
        return None
    lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line and line != name]
    rating = None
    category = clean_text(category)
    address = clean_text(address)
    for line in lines:
        if rating is None and re.fullmatch(r"[0-5](?:[.,]\d)?", line):
            rating = float(line.replace(",", "."))
        elif category is None and len(line) < 120:
            category = line
    company_id = match.group(1)
    return Organization(
        id=company_id,
        name=name,
        category=category,
        address=address,
        rating=rating,
        yandex_url=urljoin("https://yandex.ru", href),
    )
