import { anton, inter, jetbrainsMono } from "@katoshop/ui/fonts";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { siteUrl } from "../lib/env";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: { default: "KatoShop | Streetwear em tecido pesado", template: "%s | KatoShop" },
  description: "Loja demonstrativa de streetwear: camisetas, moletons e calças em tecido pesado.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" className={`${anton.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="flex min-h-dvh flex-col bg-ks-bg text-ks-fg antialiased">
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:bg-ks-surface focus:px-3 focus:py-2"
        >
          Pular para o conteúdo
        </a>
        {children}
      </body>
    </html>
  );
}
