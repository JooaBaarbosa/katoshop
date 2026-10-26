import { Anton, Inter, JetBrains_Mono } from "next/font/google";

// next/font baixa e auto-hospeda as fontes no build; nenhuma requisição ao Google em runtime.
export const anton = Anton({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-display",
  display: "swap",
});

export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});
