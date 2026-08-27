from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from .extract import inside_url_for_house, organization_from_dom, organizations_from_payloads, probable_house_address
from .models import Organization, ParseResult


ALLOWED_HOSTS = {
    "yandex.ru", "www.yandex.ru", "yandex.com", "www.yandex.com",
    "yandex.kz", "www.yandex.kz", "yandex.by", "www.yandex.by",
    "yandex.com.tr", "www.yandex.com.tr",
}


class ParserError(RuntimeError):
    pass


def validate_yandex_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ParserError("Нужна HTTPS-ссылка на Яндекс Карты")
    if not parsed.path.startswith(("/maps", "/-/")):
        raise ParserError("Ссылка не похожа на ссылку Яндекс Карт")
    return url


class YandexHouseParser:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def parse(self, source_url: str) -> ParseResult:
        validate_yandex_url(source_url)
        async with self._lock:
            await self.start()
            assert self._browser
            context = await self._browser.new_context(
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
                ),
            )
            try:
                return await self._parse_in_context(context, source_url)
            finally:
                await context.close()

    async def _parse_in_context(self, context: BrowserContext, source_url: str) -> ParseResult:
        page = await context.new_page()
        payloads: list[object] = []
        warnings: list[str] = []

        async def capture_response(response) -> None:
            try:
                hostname = urlparse(response.url).hostname or ""
                if "yandex" not in hostname:
                    return
                content_type = (await response.header_value("content-type") or "").casefold()
                resource_type = response.request.resource_type
                if "json" not in content_type and resource_type not in {"xhr", "fetch"}:
                    return
                body = await response.body()
                if len(body) > 8_000_000:
                    return
                text = body.decode("utf-8-sig").lstrip()
                if text.startswith(")]}'"):
                    text = text.split("\n", 1)[-1]
                payloads.append(json.loads(text))
            except Exception:
                return

        page.on("response", capture_response)
        try:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(2_000)
        except Exception as exc:
            raise ParserError(f"Яндекс Карты не открылись: {exc}") from exc

        resolved_url = page.url
        validate_yandex_url(resolved_url)
        if await self._captcha_visible(page):
            raise ParserError("Яндекс показал капчу. Повтори запрос позже или запусти сервис с обычного IP")

        # A shared short link may point to an organization card rather than a
        # house card. Follow the address link to the containing house first.
        if "/org/" in urlparse(page.url).path:
            if not await self._open_house_from_organization(page):
                raise ParserError("Ссылка ведёт на организацию, но адрес дома в карточке не найден")

        address = probable_house_address(await self._address_candidates(page))
        section_opened = await self._open_organizations(page)
        if not section_opened:
            warnings.append("Не удалось открыть раздел «Организации внутри»")

        organizations: list[Organization] = []
        organization_pages = 0
        if section_opened:
            organizations, organization_pages, fully_enriched = await self._collect_organization_pages(
                page, address, payloads
            )
            if organizations and not fully_enriched:
                warnings.append("Часть организаций извлечена из страницы; телефоны и сайты могут отсутствовать")

        if not address:
            address = probable_house_address([item.address for item in organizations])
            if not address:
                warnings.append("Адрес дома не распознан; проверь результаты вручную")

        if not organizations:
            warnings.append("Организации не найдены. Возможно, в карточке дома их нет или Яндекс изменил интерфейс")

        return ParseResult(
            source_url=source_url,
            resolved_url=page.url,
            address=address,
            organizations=organizations,
            warnings=warnings,
            diagnostics={
                "captured_payloads": len(payloads),
                "organization_section_opened": section_opened,
                "organization_pages": organization_pages,
            },
        )

    @staticmethod
    async def _captcha_visible(page: Page) -> bool:
        return await page.locator(".CheckboxCaptcha, .AdvancedCaptcha, [data-testid='captcha']").count() > 0

    @staticmethod
    async def _address_candidates(page: Page) -> list[str]:
        selectors = [
            "[itemprop='address']", "[class*='card-title'] h1",
            "[class*='card-title']", "h1", "[aria-label*='адрес' i]",
        ]
        values: list[str] = []
        for selector in selectors:
            with suppress(Exception):
                values.extend((await page.locator(selector).all_inner_texts())[:10])
        return values

    @staticmethod
    async def _open_organizations(page: Page) -> bool:
        if "/inside/" in urlparse(page.url).path:
            return True
        try:
            target = inside_url_for_house(page.url)
            if not target:
                locator = page.locator("a[href*='/inside/']").first
                href = await locator.get_attribute("href", timeout=3_000)
                if not href:
                    return False
                target = urljoin(page.url, href)
            await page.goto(target, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1_000)
            return "/inside/" in urlparse(page.url).path
        except Exception:
            return False

    @staticmethod
    async def _open_house_from_organization(page: Page) -> bool:
        try:
            locator = page.locator("a[href*='/house/']").first
            href = await locator.get_attribute("href", timeout=5_000)
            if not href:
                return False
            await page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1_000)
            return "/house/" in urlparse(page.url).path
        except Exception:
            return False

    @staticmethod
    async def _scroll_results(page: Page) -> None:
        previous = 0
        stable = 0
        for _ in range(60):
            count = await page.locator("li a[href*='/org/']").count()
            stable = stable + 1 if count == previous else 0
            previous = count
            if stable >= 4:
                break
            await page.evaluate(
                """() => {
                  const candidates = [...document.querySelectorAll('*')]
                    .filter((node) => node.scrollHeight > node.clientHeight + 200);
                  const target = candidates.sort((a, b) => b.clientHeight - a.clientHeight)[0];
                  if (target) target.scrollTop = target.scrollHeight;
                  window.scrollTo(0, document.body.scrollHeight);
                }"""
            )
            await page.wait_for_timeout(500)

    async def _collect_organization_pages(
        self,
        page: Page,
        house_address: str | None,
        payloads: list[object],
    ) -> tuple[list[Organization], int, bool]:
        pending = [page.url]
        queued = {self._inside_page_number(page.url)}
        visited: set[int] = set()
        found: dict[str, Organization] = {}
        fully_enriched = True

        while pending:
            target = pending.pop(0)
            page_number = self._inside_page_number(target)
            if page_number in visited:
                continue
            visited.add(page_number)

            if self._inside_page_number(page.url) != page_number:
                await page.goto(target, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(1_000)

            await self._scroll_results(page)
            await page.wait_for_timeout(500)
            if await self._captcha_visible(page):
                raise ParserError("Во время сбора Яндекс показал капчу")

            dom_organizations = await self._organizations_from_dom(page, house_address)
            allowed_ids = {item.id for item in dom_organizations if item.id}
            payload_organizations = organizations_from_payloads(
                payloads,
                house_address,
                allow_missing_address=True,
            )
            enriched = {item.id: item for item in payload_organizations if item.id in allowed_ids}
            fully_enriched = fully_enriched and len(enriched) >= len(dom_organizations)

            for item in dom_organizations:
                organization = enriched.get(item.id, item)
                key = organization.id or organization.yandex_url or organization.name
                found.setdefault(key, organization)

            hrefs = await page.locator("a[href*='/inside/'][href*='page=']").evaluate_all(
                "(links) => links.map((link) => link.getAttribute('href')).filter(Boolean)"
            )
            for href in hrefs:
                target_url = urljoin(page.url, href)
                target_number = self._inside_page_number(target_url)
                if target_number not in visited and target_number not in queued:
                    queued.add(target_number)
                    pending.append(target_url)

        return list(found.values()), len(visited), fully_enriched

    @staticmethod
    def _inside_page_number(url: str) -> int:
        from urllib.parse import parse_qs

        value = parse_qs(urlparse(url).query).get("page", ["1"])[0]
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    async def _organizations_from_dom(page: Page, house_address: str | None) -> list[Organization]:
        raw = await page.locator("li a[href*='/org/']").evaluate_all(
            """(links) => links.map((link) => {
              const href = link.getAttribute('href') || '';
              const path = new URL(href, location.href).pathname;
              if (!/^\\/maps\\/org\\/(?:[^/]+\\/)?\\d+\\/?$/.test(path)) return null;
              const card = link.closest('li') || link.closest('article') || link.parentElement;
              const category = card?.querySelector("a[href*='/category/']")?.textContent || '';
              const address = card?.querySelector("a[href*='/house/']")?.textContent || '';
              return {name: link.textContent || '', href, text: card?.innerText || '', category, address};
            }).filter(Boolean)"""
        )
        result: list[Organization] = []
        seen: set[str] = set()
        for item in raw:
            organization = organization_from_dom(
                item["name"], item["href"], item["text"],
                category=item.get("category"), address=item.get("address"),
            )
            if not organization or not self_address_matches(
                organization.address, house_address, allow_missing_candidate=True
            ):
                continue
            key = organization.id or organization.yandex_url or organization.name
            if key in seen:
                continue
            seen.add(key)
            result.append(organization)
        return result


def self_address_matches(candidate: str | None, house: str | None, *, allow_missing_candidate: bool = False) -> bool:
    from .extract import address_matches

    return address_matches(candidate, house, allow_missing_candidate=allow_missing_candidate)
