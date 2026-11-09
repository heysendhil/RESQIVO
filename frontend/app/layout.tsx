import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { THEME_SCRIPT } from "@/lib/theme";

import { InlineScript } from "./components/inline-script";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "RESQIVO — Emergency Operations",
  description:
    "Agentic AI disaster-response planning with deterministic resource validation. Every Second. Every Life.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Browser extensions add attributes to <html> (e.g. data-ube-extension) before
    // hydration. This only ignores attribute mismatches on this element, not its children.
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* Applies a saved dark theme before the first paint. */}
        <InlineScript html={THEME_SCRIPT} />
      </head>
      <body className="min-h-full bg-canvas font-sans text-ink">{children}</body>
    </html>
  );
}
