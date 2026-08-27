from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from .extract import address_matches, organization_from_dom, organizations_from_payloads, probable_house_address
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

    async def parse(self, source_url: str, max_organizations: int = 100) -> ParseResult:
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
                return await self._parse_in_context(context, source_url, max_organizations)
            finally:
                await context.close()

    async def _parse_in_context(self, context: BrowserContext, source_url: str, max_items: int) -> ParseResult:
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

        address = probable_house_address(await self._address_candidates(page))
        payload_count_before_section = len(payloads)
        section_opened = await self._open_organizations(page)
        if not section_opened:
            warnings.append("Не удалось открыть раздел «Организации внутри»")

        await self._scroll_results(page, max_items)
        await page.wait_for_timeout(1_000)
        if await self._captcha_visible(page):
            raise ParserError("Во время сбора Яндекс показал капчу")

        section_payloads = payloads[payload_count_before_section:] if section_opened else []
        organizations = organizations_from_payloads(
            section_payloads,
            address,
            allow_missing_address=True,
        )
        if not organizations and not section_opened:
            organizations = organizations_from_payloads(payloads, address)
        if not organizations and section_opened:
            organizations = await self._organizations_from_dom(page, address)
            if organizations:
                warnings.append("Организации извлечены из страницы; телефоны и сайты могут отсутствовать")

        if not address:
            address = probable_house_address([item.address for item in organizations])
            if not address:
                warnings.append("Адрес дома не распознан; проверь результаты вручную")

        organizations = organizations[:max_items]
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
        locator = page.locator("a[href*='/inside/']").first
        try:
            href = await locator.get_attribute("href", timeout=3_000)
            if not href:
                return False
            await page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1_000)
            return "/inside/" in urlparse(page.url).path
        except Exception:
            return False

    @staticmethod
    async def _scroll_results(page: Page, max_items: int) -> None:
        previous = 0
        stable = 0
        for _ in range(min(40, max(8, max_items // 3))):
            count = await page.locator("li a[href*='/org/']").count()
            stable = stable + 1 if count == previous else 0
            previous = count
            if count >= max_items or stable >= 3:
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
            if not organization or not address_matches(
                organization.address,
                house_address,
                allow_missing_candidate=True,
            ):
                continue
            key = organization.id or organization.yandex_url or organization.name
            if key in seen:
                continue
            seen.add(key)
            result.append(organization)
        return result
