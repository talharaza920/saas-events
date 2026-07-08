import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import parse, { domToReact, type DOMNode, type HTMLReactParserOptions, Element } from "html-react-parser";
import { Fragment } from "react";

/**
 * Renders wedding-authored copy. Two input shapes are accepted, auto-detected:
 *
 *  1. **HTML** (from the admin's TipTap editor) — a tiny allow-list of inline
 *     formatting tags: <strong>/<b>, <em>/<i>, <u>, <a href>, <br>, <p>. Parsed
 *     with `html-react-parser` (SSR-safe, NOT dangerouslySetInnerHTML): any tag
 *     outside the allow-list collapses to its text, and links keep only
 *     http(s)/mailto hrefs and always open in a new tab. So owner-authored copy
 *     can never inject markup or script.
 *  2. **Legacy markup** — the original `**bold**` + `\n` mini-format still used by
 *     older stored content (e.g. story narration). Rendered exactly as before.
 *
 * `variant="inline"` strips block breaks (<p>, <br>, `\n` → spaces) so the copy
 * sits on a single line — used for headings, kickers, labels and other
 * limited-space fields. The default "block" keeps line breaks and paragraphs.
 */
const ALLOWED_TAGS = new Set(["strong", "b", "em", "i", "u", "a", "br", "p"]);
const HTML_RE = /<(?:strong|b|em|i|u|a|br|p)\b[^>]*>/i;
const SAFE_HREF_RE = /^(?:https?:|mailto:)/i;

function safeHref(href: string | undefined): string | null {
  if (!href) return null;
  const trimmed = href.trim();
  return SAFE_HREF_RE.test(trimmed) ? trimmed : null;
}

/** Render an allow-listed HTML string to React elements. */
function renderHtml(html: string, inline: boolean) {
  // For inline fields, drop block-level breaks up front so nothing wraps.
  const src = inline
    ? html
        .replace(/<br\s*\/?>/gi, " ")
        .replace(/<\/p\s*>/gi, " ")
        .replace(/<p\b[^>]*>/gi, "")
    : html;

  const options: HTMLReactParserOptions = {
    replace: (node) => {
      if (!(node instanceof Element)) return undefined; // text nodes render as-is
      const name = node.name.toLowerCase();
      const kids = () => domToReact(node.children as DOMNode[], options);

      if (!ALLOWED_TAGS.has(name)) return <Fragment>{kids()}</Fragment>; // drop tag, keep text

      switch (name) {
        case "strong":
        case "b":
          return <strong>{kids()}</strong>;
        case "em":
        case "i":
          return <em>{kids()}</em>;
        case "u":
          return <u>{kids()}</u>;
        case "br":
          return <br />;
        case "p":
          // Avoid an invalid <p> inside the surrounding <Typography> (also a <p>):
          // render each paragraph as a block-level span with a little spacing.
          return (
            <Box component="span" sx={{ display: "block", "&:not(:last-child)": { mb: 1 } }}>
              {kids()}
            </Box>
          );
        case "a": {
          const href = safeHref(node.attribs?.href);
          if (!href) return <Fragment>{kids()}</Fragment>;
          return (
            <Link href={href} target="_blank" rel="noopener noreferrer" sx={{ color: "primary.main" }}>
              {kids()}
            </Link>
          );
        }
        default:
          return <Fragment>{kids()}</Fragment>;
      }
    },
  };

  return <>{parse(src, options)}</>;
}

/** Render the legacy `**bold**` + `\n` mini-format. */
function renderLegacy(text: string, inline: boolean) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, li) => (
        <Fragment key={li}>
          {li > 0 && (inline ? " " : <br />)}
          {line.split(/(\*\*[^*]+\*\*)/g).map((seg, si) =>
            seg.startsWith("**") && seg.endsWith("**") ? (
              <strong key={si}>{seg.slice(2, -2)}</strong>
            ) : (
              <Fragment key={si}>{seg}</Fragment>
            ),
          )}
        </Fragment>
      ))}
    </>
  );
}

export default function RichText({
  text,
  variant = "block",
}: {
  text?: string;
  variant?: "inline" | "block";
}) {
  if (!text) return null;
  const inline = variant === "inline";
  return HTML_RE.test(text) ? renderHtml(text, inline) : renderLegacy(text, inline);
}
