/** Página de texto legal. O HTML vem do Markdown próprio do repositório (sem HTML bruto). */
export function LegalPage({ title, html }: { title: string; html: string }) {
  return (
    <article className="space-y-6">
      <h1 className="text-5xl">{title}</h1>
      <p className="inline-block border border-ks-border bg-ks-surface px-3 py-1 font-mono text-xs uppercase tracking-wide text-ks-muted">
        Modelo para loja demonstrativa
      </p>
      <div className="legal-text" dangerouslySetInnerHTML={{ __html: html }} />
    </article>
  );
}
