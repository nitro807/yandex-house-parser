"use client";

import { FormEvent, useMemo, useState } from "react";
import { ArrowUpRight, Building2, Download, Link2, MapPin, Search, TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Organization = { id?: string | null; name: string; category?: string | null; address?: string | null; phones: string[]; email?: string | null; website?: string | null; rating?: number | null; yandex_url?: string | null };
type ParseResult = { source_url: string; resolved_url: string; address?: string | null; organizations: Organization[]; warnings: string[] };

const csvCell = (value: string | number | null | undefined) => `"${String(value ?? "").replaceAll('"', '""')}"`;
const websiteUrl = (value: string | null | undefined) => !value ? null : /^https?:\/\//i.test(value) ? value : `https://${value}`;

export function ParserApp() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<ParseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const canSubmit = /^https:\/\/(?:www\.)?yandex\.(?:ru|com|kz|by|com\.tr)\//i.test(url.trim());

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit || loading) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const response = await fetch("/api/parse", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url: url.trim() }) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Не удалось обработать ссылку");
      setResult(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Неизвестная ошибка");
    } finally { setLoading(false); }
  }

  const csv = useMemo(() => {
    if (!result) return "";
    const rows = result.organizations.map((item) => [item.name, item.category, item.address, item.phones.join(", "), item.email, item.website, item.rating, item.yandex_url].map(csvCell).join(";"));
    return [["Название", "Категория", "Адрес", "Телефоны", "Email", "Сайт", "Рейтинг", "Яндекс Карты"].map(csvCell).join(";"), ...rows].join("\n");
  }, [result]);

  function downloadCsv() {
    const blobUrl = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = blobUrl; anchor.download = "organizations.csv"; anchor.click(); URL.revokeObjectURL(blobUrl);
  }

  return (
    <main className="min-h-screen bg-[#f4f2ec] text-[#17211f]">
      <div className="mx-auto max-w-[1480px] px-4 py-4 sm:px-8 sm:py-8">
        <header className="mb-5 flex items-center justify-between border-b border-[#17211f]/15 pb-4">
          <div className="flex items-center gap-3"><div className="grid size-10 place-items-center rounded-full bg-[#e64f2e] text-white"><Building2 className="size-5" /></div><div><p className="text-sm font-semibold tracking-tight">Организации в доме</p><p className="text-xs text-[#53615e]">Парсер Яндекс Карт</p></div></div>
          <Badge variant="outline" className="border-[#17211f]/20 bg-white/55 text-[#53615e]">Playwright</Badge>
        </header>
        <section className="grid min-h-[calc(100vh-125px)] gap-5 lg:grid-cols-[minmax(320px,430px)_1fr]">
          <aside className="flex flex-col rounded-[28px] bg-[#17211f] p-6 text-white sm:p-8">
            <div className="mb-12 inline-flex size-12 items-center justify-center rounded-2xl bg-white/10"><MapPin className="size-6 text-[#f5b44a]" /></div>
            <h1 className="max-w-sm text-4xl font-semibold leading-[1.05] tracking-[-0.04em] sm:text-5xl">Один дом.<br />Все компании.</h1>
            <p className="mt-5 max-w-sm text-sm leading-6 text-white/60">Вставьте ссылку на карточку здания. Сервис откроет раздел организаций, соберёт карточки и подготовит таблицу.</p>
            <form onSubmit={submit} className="mt-10 space-y-3">
              <label htmlFor="yandex-url" className="text-xs font-medium uppercase tracking-[0.16em] text-white/45">Ссылка на дом</label>
              <div className="relative"><Link2 className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-white/35" /><Input id="yandex-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://yandex.ru/maps/..." autoComplete="off" className="h-14 rounded-2xl border-white/10 bg-white/8 pl-11 text-white placeholder:text-white/25 focus-visible:border-[#f5b44a] focus-visible:ring-[#f5b44a]/30" /></div>
              <Button type="submit" disabled={!canSubmit || loading} className="h-14 w-full rounded-2xl bg-[#f5b44a] text-[#17211f] hover:bg-[#ffc466]"><Search className="size-4" />{loading ? "Собираю организации…" : "Найти организации"}</Button>
            </form>
            <div className="mt-auto border-t border-white/10 pt-6 text-xs leading-5 text-white/40">Сервис собирает список, затем открывает карточку каждой организации, чтобы найти опубликованные контакты. Для большого здания это может занять несколько минут.</div>
          </aside>
          <section className="min-w-0 rounded-[28px] border border-[#17211f]/10 bg-[#fbfaf6] p-5 sm:p-8">
            {!loading && !result && !error && <EmptyState />}
            {loading && <LoadingState />}
            {error && <Alert variant="destructive" className="rounded-2xl"><TriangleAlert className="size-4" /><AlertTitle>Парсинг не завершён</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
            {result && <Results result={result} onDownload={downloadCsv} />}
          </section>
        </section>
      </div>
    </main>
  );
}

export function Results({ result, onDownload }: { result: ParseResult; onDownload: () => void }) {
  return <div className="space-y-6">
    <div className="flex flex-col gap-4 border-b border-[#17211f]/10 pb-6 sm:flex-row sm:items-end sm:justify-between"><div><p className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-[#73807d]">Найдено</p><div className="flex items-baseline gap-3"><strong className="text-5xl font-semibold tracking-[-0.05em]">{result.organizations.length}</strong><span className="text-sm text-[#66736f]">организаций</span></div>{result.address && <p className="mt-3 text-sm text-[#3d4b47]">{result.address}</p>}</div><Button variant="outline" onClick={onDownload} disabled={!result.organizations.length} className="rounded-xl bg-white"><Download className="size-4" /> Скачать CSV</Button></div>
    {result.warnings.length > 0 && <Alert className="rounded-2xl border-[#f5b44a]/50 bg-[#fff8e7]"><TriangleAlert className="size-4 text-[#9b6717]" /><AlertTitle>Обрати внимание</AlertTitle><AlertDescription>{result.warnings.join(" ")}</AlertDescription></Alert>}
    <div className="overflow-hidden rounded-2xl border border-[#17211f]/10 bg-white"><div className="max-h-[calc(100vh-320px)] overflow-auto"><Table className="table-fixed"><TableHeader className="sticky top-0 z-10 bg-[#f0eee7]"><TableRow><TableHead className="w-12">№</TableHead><TableHead className="w-[30%]">Организация</TableHead><TableHead className="w-[30%]">Категория</TableHead><TableHead className="w-[30%]">Контакты</TableHead><TableHead className="w-16">Карта</TableHead></TableRow></TableHeader><TableBody>
      {result.organizations.map((item, index) => { const website = websiteUrl(item.website); return <TableRow key={item.id || `${item.name}-${index}`} className="[&_td]:whitespace-normal [&_td]:[overflow-wrap:anywhere]"><TableCell className="align-top text-[#8a9592]">{String(index + 1).padStart(2, "0")}</TableCell><TableCell className="align-top"><p className="font-medium">{item.name}</p>{item.address && <p className="mt-1 text-xs leading-5 text-[#72807c]">{item.address}</p>}{item.rating != null && <Badge className="mt-2 bg-[#e9f5dd] text-[#365b21]">★ {item.rating}</Badge>}</TableCell><TableCell className="align-top text-sm text-[#53615e]">{item.category || "—"}</TableCell><TableCell className="align-top text-sm">{item.phones.map((phone) => <a key={phone} href={`tel:${phone}`} className="block hover:underline">{phone}</a>)}{item.email && <a href={`mailto:${item.email}`} className="mt-1 block break-all text-[#c34127] hover:underline">{item.email}</a>}{website && <a href={website} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[#c34127] hover:underline">Сайт <ArrowUpRight className="size-3" /></a>}{!item.phones.length && !item.email && !website && "—"}</TableCell><TableCell className="align-top">{item.yandex_url ? <Button asChild variant="ghost" size="icon" className="rounded-full"><a href={item.yandex_url} target="_blank" rel="noreferrer" aria-label={`Открыть ${item.name} на Яндекс Картах`}><ArrowUpRight className="size-4" /></a></Button> : "—"}</TableCell></TableRow>; })}
    </TableBody></Table></div></div>
  </div>;
}

function EmptyState() { return <div className="grid min-h-[620px] place-items-center text-center"><div className="max-w-sm"><div className="mx-auto mb-6 grid size-20 place-items-center rounded-full border border-dashed border-[#17211f]/25 bg-[#f4f2ec]"><Building2 className="size-8 text-[#66736f]" /></div><h2 className="text-xl font-semibold tracking-tight">Здесь появится таблица</h2><p className="mt-2 text-sm leading-6 text-[#72807c]">Подойдёт полная ссылка на карточку здания или короткая ссылка Яндекс Карт.</p></div></div>; }
function LoadingState() { return <div className="space-y-6" aria-label="Загрузка"><div className="flex items-end justify-between border-b border-[#17211f]/10 pb-6"><div className="space-y-3"><Skeleton className="h-3 w-20" /><Skeleton className="h-12 w-48" /><Skeleton className="h-4 w-72" /></div><Skeleton className="h-10 w-32" /></div><div className="space-y-2">{Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} className="h-16 w-full rounded-xl" />)}</div></div>; }
