# Организации в доме

Веб-приложение принимает ссылку на карточку дома в Яндекс Картах и возвращает организации в здании. Парсер работает через Chromium/Playwright, собирает JSON-ответы интерфейса и использует DOM как резервный источник.

## Быстрый запуск

Требуются Docker и Docker Compose.

```bash
docker compose up --build -d
```

Откройте `http://localhost:18473`. Для остановки: `docker compose down`.

## Разработка без Docker

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

В другом терминале из корня проекта:

```bash
PARSER_API_URL=http://localhost:8000 npm run dev
```

## API

`POST /api/parse`

```json
{
  "url": "https://yandex.ru/maps/.../house/.../"
}
```

`GET /health` возвращает состояние сервиса.

## Особенности

- Разрешены только HTTPS-ссылки доменов Яндекса, чтобы входная ссылка не превратилась в SSRF.
- Запросы выполняются последовательно: это уменьшает вероятность капчи.
- Раздел «Организации внутри» обходится по всем страницам без ограничения количества компаний.
- Короткие ссылки раскрываются браузером.
- Результаты удаляются по ID и фильтруются по адресу дома.
- Интерфейс сохраняет результат в CSV с UTF-8 BOM.
- При массовом использовании понадобятся прокси, очередь и мониторинг ошибок.

## Проверки

```bash
npm test
PYTHONPATH=backend python -m unittest discover -s backend/tests
```
