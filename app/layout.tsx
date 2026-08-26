import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Организации в доме",
  description: "Сбор организаций из карточки дома на Яндекс Картах",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
