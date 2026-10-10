import { auth } from "@/lib/auth";
import { generateSasUrl } from "@/lib/blob";
import { prisma } from "@/lib/prisma";
import { escapeHtml, sanitizeHref } from "@/lib/sanitize-href";
import { marked } from "marked";
import { randomBytes } from "crypto";
import { NextResponse } from "next/server";

// SEC-005: Content-Security-Policy for served deliverable HTML. `default-src
// 'none'` denies everything not explicitly allowed; the document needs only
// inline <style> (style-src 'unsafe-inline'), same-origin + data:/https: images
// (the encyclopedia embeds inline SVG diagrams and a same-origin CBTS logo),
// and same-origin/data: fonts (the encyclopedia @font-face). Scripts are denied
// outright except a single per-response nonce used by the Markdown renderer's
// print button — the legacy encyclopedia HTML carries no scripts, so it gets no
// script-src at all (SEC-006's SVG <foreignObject> scripts are thereby inert).
function cspHeader(nonce?: string): string {
  const scriptSrc = nonce ? ` script-src 'nonce-${nonce}';` : "";
  return (
    "default-src 'none';" +
    " style-src 'unsafe-inline';" +
    " img-src 'self' data: https:;" +
    " font-src 'self' data:;" +
    scriptSrc +
    " base-uri 'none'; form-action 'none'"
  );
}

// ─── Dual-mode document renderer ──────────────────────────────────────────────
// Renders a Markdown deliverable as one artifact that works both ways:
//  • interactive web report — sticky TOC sidebar built from section headings
//  • print-ready document — cover block, page-break per section, light print CSS
// Raw HTML embedded in the markdown is escaped before rendering (defense in
// depth: deliverable content is AI-generated).

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

function markdownToHtml(title: string, markdown: string, nonce: string): string {
  // Neutralize embedded raw HTML while preserving Markdown semantics.
  const safeSource = markdown.replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Collect headings for the TOC while assigning stable IDs.
  const toc: Array<{ depth: number; text: string; id: string }> = [];
  const seen = new Map<string, number>();
  const renderer = new marked.Renderer();
  renderer.heading = ({ tokens, depth }) => {
    const text = tokens.map((t) => ("text" in t ? (t as { text: string }).text : "")).join("");
    let id = slugify(text) || "section";
    const n = seen.get(id) ?? 0;
    seen.set(id, n + 1);
    if (n > 0) id = `${id}-${n}`;
    if (depth === 2 || depth === 3) toc.push({ depth, text, id });
    return `<h${depth} id="${id}">${text}</h${depth}>\n`;
  };
  // SEC-005: neutralise dangerous link schemes (javascript:, data:text/html, …)
  // that an LLM could emit from untrusted customer input. The inner text is
  // re-rendered so inline formatting (bold, code) inside links is preserved.
  renderer.link = ({ href, title: linkTitle, tokens }) => {
    const safe = escapeHtml(sanitizeHref(href));
    const text = renderer.parser.parseInline(tokens);
    const titleAttr = linkTitle ? ` title="${escapeHtml(linkTitle)}"` : "";
    return `<a href="${safe}"${titleAttr} rel="noopener noreferrer">${text}</a>`;
  };

  const body = marked.parse(safeSource, { renderer, gfm: true, breaks: false }) as string;

  const needsReview = /\[(VERIFY|REVIEW REQUIRED)\]/.test(markdown);
  const tocHtml = toc
    .map(
      (t) =>
        `<a class="toc-${t.depth === 2 ? "section" : "sub"}" href="#${t.id}">${escapeHtml(t.text)}</a>`,
    )
    .join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(title)}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --navy-900:#0f172a; --navy-800:#1e293b; --navy-700:#334155; --navy-300:#cbd5e1; --teal:#0d9488; }
  html { scroll-behavior: smooth; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--navy-900); color: var(--navy-300); line-height: 1.65;
  }
  .toolbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: var(--navy-800); border-bottom: 1px solid var(--navy-700);
    padding: 0.75rem 1.5rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  }
  .toolbar h1 { font-size: 0.875rem; font-weight: 600; color: #f1f5f9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .btn-print {
    background: var(--teal); color: #fff; border: none; flex: none;
    padding: 0.4rem 1rem; border-radius: 0.5rem; font-size: 0.8rem; font-weight: 600; cursor: pointer;
  }
  .btn-print:hover { background: #0f766e; }
  .review-banner {
    margin-top: 3.4rem; padding: 0.6rem 1.5rem; font-size: 0.8rem;
    background: #451a03; color: #fdba74; border-bottom: 1px solid #7c2d12;
  }
  .layout { display: flex; max-width: 1400px; margin: 0 auto; gap: 2rem; padding: 1.5rem; }
  .review-banner + .layout { margin-top: 0; }
  body > .layout:first-of-type { margin-top: 3.4rem; }
  nav.toc {
    position: sticky; top: 4.5rem; align-self: flex-start; flex: 0 0 280px;
    max-height: calc(100vh - 6rem); overflow-y: auto;
    background: var(--navy-800); border: 1px solid var(--navy-700); border-radius: 0.75rem;
    padding: 1rem; font-size: 0.8rem;
  }
  nav.toc .toc-title { font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; margin-bottom: 0.5rem; }
  nav.toc a { display: block; color: var(--navy-300); text-decoration: none; padding: 0.2rem 0.4rem; border-radius: 0.35rem; }
  nav.toc a:hover { background: var(--navy-700); color: #fff; }
  nav.toc a.toc-sub { padding-left: 1.2rem; color: #94a3b8; font-size: 0.75rem; }
  main.doc {
    flex: 1; min-width: 0; background: var(--navy-800); border: 1px solid var(--navy-700);
    border-radius: 0.75rem; padding: 2.5rem 3rem;
  }
  main.doc h1 { color: #f8fafc; font-size: 1.7rem; margin-bottom: 1rem; letter-spacing: -0.01em; }
  main.doc h2 { color: #f1f5f9; font-size: 1.3rem; margin: 2.2rem 0 0.8rem; padding-top: 1rem; border-top: 1px solid var(--navy-700); }
  main.doc h3 { color: #e2e8f0; font-size: 1.05rem; margin: 1.5rem 0 0.5rem; }
  main.doc p { margin: 0.6rem 0; }
  main.doc ul, main.doc ol { margin: 0.6rem 0 0.6rem 1.4rem; }
  main.doc blockquote { border-left: 3px solid var(--teal); padding: 0.4rem 1rem; margin: 0.8rem 0; color: #94a3b8; background: rgba(13,148,136,0.06); border-radius: 0 0.4rem 0.4rem 0; }
  main.doc code { font-family: Consolas, Monaco, "Courier New", monospace; font-size: 0.85em; background: var(--navy-900); padding: 0.1em 0.35em; border-radius: 0.3em; color: #5eead4; }
  main.doc pre { background: var(--navy-900); border: 1px solid var(--navy-700); border-radius: 0.5rem; padding: 1rem; overflow-x: auto; margin: 0.8rem 0; }
  main.doc pre code { background: none; padding: 0; color: #e2e8f0; }
  main.doc table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.85rem; }
  main.doc th, main.doc td { border: 1px solid var(--navy-700); padding: 0.45rem 0.7rem; text-align: left; vertical-align: top; }
  main.doc th { background: var(--navy-900); color: #f1f5f9; }
  main.doc a { color: #2dd4bf; }
  main.doc hr { border: none; border-top: 1px solid var(--navy-700); margin: 2rem 0; }
  @media (max-width: 900px) { nav.toc { display: none; } main.doc { padding: 1.5rem; } }
  @media print {
    @page { size: A4; margin: 2cm 1.8cm; }
    .toolbar, nav.toc, .review-banner { display: none !important; }
    body { background: #fff; color: #1e293b; }
    .layout { display: block; padding: 0; margin-top: 0 !important; max-width: none; }
    main.doc { background: transparent; border: none; padding: 0; border-radius: 0; }
    main.doc h1 { color: #0f172a; font-size: 22pt; margin-top: 30vh; text-align: center; }
    main.doc h1 + p { text-align: center; }
    main.doc h2 { color: #0f172a; border-top: none; page-break-before: always; break-before: page; }
    main.doc h3 { color: #1e293b; }
    main.doc table, main.doc pre, main.doc blockquote { page-break-inside: avoid; break-inside: avoid; }
    main.doc th { background: #f1f5f9; color: #0f172a; }
    main.doc th, main.doc td { border-color: #cbd5e1; }
    main.doc code, main.doc pre { background: #f8fafc; color: #0f172a; border-color: #cbd5e1; }
    main.doc pre code { color: #0f172a; }
    main.doc a { color: #0f766e; text-decoration: none; }
    main.doc blockquote { background: #f8fafc; color: #475569; }
  }
</style>
</head>
<body>
<div class="toolbar">
  <h1>${escapeHtml(title)}</h1>
  <button class="btn-print" id="btn-print" type="button">Print / Save as PDF</button>
</div>
${needsReview ? `<div class="review-banner">⚠ This document contains [VERIFY] and/or [REVIEW REQUIRED] flags — it must be reviewed and approved by the engagement team before client delivery.</div>` : ""}
<div class="layout">
  <nav class="toc"><div class="toc-title">Contents</div>${tocHtml}</nav>
  <main class="doc">${body}</main>
</div>
<script nonce="${nonce}">document.getElementById("btn-print").addEventListener("click",function(){window.print();});</script>
</body>
</html>`;
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (!session?.user?.id) {
    return new NextResponse("Unauthorized", { status: 401 });
  }

  const { id } = await params;

  const deliverable = await prisma.deliverable.findUnique({
    where: { id },
    include: {
      engagement: {
        select: {
          members: { select: { userId: true } },
        },
      },
    },
  });

  if (!deliverable) {
    return new NextResponse("Not found", { status: 404 });
  }

  const isMember = deliverable.engagement.members.some(
    (m) => m.userId === session.user!.id,
  );
  if (!isMember) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  if (deliverable.status === "RUNNING" || deliverable.status === "QUEUED") {
    return new NextResponse("This assessment is still being generated. Check its progress on the Deliverables page.", { status: 409 });
  }
  if (deliverable.status === "FAILED") {
    return new NextResponse("Generation of this assessment failed. Regenerate it from the Deliverables page.", { status: 409 });
  }

  if (!deliverable.content) {
    if (!deliverable.blobPath) {
      return new NextResponse("No content available for this deliverable.", {
        status: 404,
      });
    }
    const sasUrl = await generateSasUrl(deliverable.blobPath, 1);
    return NextResponse.redirect(sasUrl, { status: 302 });
  }

  const content = deliverable.content;
  // Legacy deliverables (pre-sectioned Comprehensive, encyclopedia editions)
  // stored complete HTML documents — serve those as-is.
  const isHtml =
    content.trimStart().startsWith("<!DOCTYPE") ||
    content.trimStart().startsWith("<html");

  if (isHtml) {
    // Legacy/encyclopedia HTML documents carry no scripts — deny script-src
    // entirely (no nonce) so any embedded/injected script (SEC-006) is inert.
    return new NextResponse(content, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": cspHeader(),
      },
    });
  }

  const nonce = randomBytes(16).toString("base64");
  const html = markdownToHtml(deliverable.title, content, nonce);
  return new NextResponse(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Disposition": "inline",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": cspHeader(nonce),
    },
  });
}
