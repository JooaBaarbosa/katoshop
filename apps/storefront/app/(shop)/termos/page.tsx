import type { Metadata } from "next";
import { LegalPage } from "../../../components/legal-page";
import { renderContent } from "../../../lib/markdown";

export const metadata: Metadata = {
  title: "Termos e condições",
  description: "Termos de uso da KatoShop, loja demonstrativa.",
  alternates: { canonical: "/termos" },
};

export default function TermsPage() {
  return <LegalPage title="Termos e condições" html={renderContent("termos")} />;
}
