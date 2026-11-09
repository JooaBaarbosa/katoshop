import { anton, inter, jetbrainsMono } from "@katoshop/ui/fonts";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Painel KatoShop", template: "%s | Painel KatoShop" },
  description: "Painel administrativo da loja demonstrativa KatoShop.",
  // área restrita: fora dos buscadores
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="pt-BR"
      data-theme="admin"
      className={`${anton.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body className="min-h-dvh bg-ks-bg text-ks-fg antialiased">
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:bg-ks-surface focus:px-3 focus:py-2"
        >
          Pular para o conteúdo
        </a>
        {children}
      </body>
    </html>
  );
}
