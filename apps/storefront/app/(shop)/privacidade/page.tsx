import type { Metadata } from "next";
import { LegalPage } from "../../../components/legal-page";
import { renderContent } from "../../../lib/markdown";

export const metadata: Metadata = {
  title: "Política de privacidade",
  description: "Como a KatoShop (loja demonstrativa) trata dados pessoais, conforme a LGPD.",
  alternates: { canonical: "/privacidade" },
};

export default function PrivacyPage() {
  return <LegalPage title="Política de privacidade" html={renderContent("privacidade")} />;
}
