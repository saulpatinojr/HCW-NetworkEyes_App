import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// CBTS brand typeface. Only the Regular weight is licensed/available;
// heavier weights render via browser synthetic bolding.
const aeonik = localFont({
  src: "./fonts/Aeonik-Regular.ttf",
  weight: "400",
  variable: "--font-sans",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
});

export const metadata: Metadata = {
  title: "CNA Platform — CBTS",
  description:
    "CBTS Cloud Network Assessment — multi-user assessment, analysis, and delivery platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={aeonik.variable}>
      <head>
        <meta name="color-scheme" content="light dark" />
      </head>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
