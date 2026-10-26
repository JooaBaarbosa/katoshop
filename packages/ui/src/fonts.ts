import { Anton, Inter, JetBrains_Mono } from "next/font/google";

/**
 * next/font baixa e auto-hospeda as fontes no build. As apps colocam
 * `${anton.variable} ${inter.variable} ${jetbrainsMono.variable}` na className do <html>;
 * tokens.css mapeia as variáveis para font-display, font-sans e font-mono.
 */
export const anton = Anton({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-anton-nf",
  display: "swap",
});

export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter-nf",
  display: "swap",
});

export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-nf",
  display: "swap",
});
