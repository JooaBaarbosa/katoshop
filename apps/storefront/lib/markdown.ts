import { readFileSync } from "node:fs";
import path from "node:path";
import { Marked, type Tokens } from "marked";

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const SAFE_HREF = /^(https?:\/\/|mailto:|\/(?![/\\]))/i;

const marked = new Marked({
  async: false,
  gfm: true,
  renderer: {
    // Sem HTML bruto: tags viram texto.
    html: ({ text }: Tokens.HTML | Tokens.Tag) => escapeHtml(text),
    // Só http(s), mailto e caminhos internos viram link; o resto vira texto.
    link({ href, tokens }: Tokens.Link) {
      const label = this.parser.parseInline(tokens);
      return SAFE_HREF.test(href) ? `<a href="${escapeHtml(href)}">${label}</a>` : label;
    },
    image: ({ text }: Tokens.Image) => escapeHtml(text),
  },
});

/** Markdown de conteúdo próprio para HTML, sem HTML bruto nem links perigosos. */
export function renderMarkdown(source: string): string {
  return marked.parse(source, { async: false });
}

/** Lê `content/<name>.md` (relativo à raiz do app, que é o cwd do Next) e renderiza. */
export function renderContent(name: "privacidade" | "termos"): string {
  return renderMarkdown(readFileSync(path.join(process.cwd(), "content", `${name}.md`), "utf8"));
}
