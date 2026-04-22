import type { Metadata } from "next";
import Link from "next/link";
import { Inter, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { ClerkProvider } from "@clerk/nextjs";

import { NavAuth } from "@/components/NavAuth";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans"
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono"
});

export const metadata: Metadata = {
  title: "ExperimentIQ",
  description: "AI-powered experimentation intelligence platform."
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans`}>
          <div className="h-0.5 w-full bg-gradient-to-r from-[var(--primary)] via-[var(--secondary)] to-transparent" />
          <div className="min-h-screen">
            <header className="border-b border-[var(--border)] bg-[#0c0c13]/90 backdrop-blur-xl">
              <nav className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-4">
                <div className="flex items-center gap-8">
                  <Link
                    href="/"
                    className="text-lg font-semibold tracking-[-0.03em] text-[var(--primary)]"
                  >
                    ExperimentIQ
                  </Link>
                  <div className="hidden items-center gap-6 text-sm text-[var(--text-muted)] md:flex">
                    <Link href="/">Dashboard</Link>
                    <Link href="/experiments/new">Framing</Link>
                  </div>
                </div>
                <NavAuth />
              </nav>
            </header>
            <main className="mx-auto max-w-[1440px] px-6 py-10">{children}</main>
          </div>
        </body>
      </html>
    </ClerkProvider>
  );
}
