import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const backend = process.env.PARSER_API_URL;
  if (!backend) return NextResponse.json({ detail: "Сервис парсинга не подключён. Укажи PARSER_API_URL или запусти приложение через Docker Compose." }, { status: 503 });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const response = await fetch(`${backend.replace(/\/$/, "")}/api/parse`, { method: "POST", headers: { "content-type": "application/json" }, body: await request.text(), signal: controller.signal });
    return new NextResponse(await response.text(), { status: response.status, headers: { "content-type": response.headers.get("content-type") || "application/json" } });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof Error && error.name === "AbortError" ? "Парсинг занял больше двух минут" : "Сервис парсинга недоступен" }, { status: 502 });
  } finally { clearTimeout(timeout); }
}
