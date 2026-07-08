"use client";

import { useState } from "react";

import FormatBoldIcon from "@mui/icons-material/FormatBold";
import FormatItalicIcon from "@mui/icons-material/FormatItalic";
import FormatUnderlinedIcon from "@mui/icons-material/FormatUnderlined";
import LinkIcon from "@mui/icons-material/Link";
import LinkOffIcon from "@mui/icons-material/LinkOff";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormHelperText from "@mui/material/FormHelperText";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import Tooltip from "@mui/material/Tooltip";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

type Variant = "inline" | "block";

/** Turn a user-typed URL into a safe, scheme-qualified href, or null if unusable.
 * Bare domains become https://…, an "x@y" becomes mailto:. Only http(s)/mailto pass. */
function normalizeHref(raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  let href = v;
  if (!/^(https?:|mailto:)/i.test(href)) {
    href = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(href) ? `mailto:${href}` : `https://${href}`;
  }
  return /^(https?:\/\/|mailto:)/i.test(href) ? href : null;
}

/** Strip the editor's HTML to "is there any text?" — so a field that only contains
 * empty paragraphs / stray formatting saves as "" (matching the plain-field behavior
 * the parsers/filters already expect). */
function isBlank(html: string): boolean {
  return !html
    .replace(/<br\s*\/?>/gi, "")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/gi, " ")
    .trim();
}

/** Normalize editor output for storage. Inline drops the paragraph wrapper so the
 * value stays a single line; block keeps paragraphs/line breaks. Empty → "". */
function toStored(editor: Editor, variant: Variant): string {
  const html = editor.getHTML();
  if (isBlank(html)) return "";
  return variant === "inline" ? html.replace(/<\/?p[^>]*>/gi, "").trim() : html;
}

function ToolbarButton({
  active,
  onClick,
  title,
  children,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Tooltip title={title}>
      <ToggleButton
        value={title}
        selected={active}
        size="small"
        onMouseDown={(e) => e.preventDefault()} // keep the editor selection
        onClick={onClick}
        sx={{ border: 0, borderRadius: 1, px: 1, py: 0.5 }}
      >
        {children}
      </ToggleButton>
    </Tooltip>
  );
}

/**
 * A Word-like rich-text field for the admin. Built on TipTap (open-source, MIT) with
 * a small MUI toolbar; drops in where a `TextField` was. Emits the same HTML allow-list
 * that `components/invite/RichText.tsx` renders.
 *
 * - `variant="block"` (default): bold / italic / underline / link + new lines — for
 *   generous body copy (FAQ answers, section intros, confirmations).
 * - `variant="inline"`: bold / italic / link only, Enter is suppressed (no new lines) —
 *   for limited-space display copy (FAQ question, headings, kickers, labels).
 *
 * TipTap loads only here in the admin bundle; the guest invite never imports it.
 */
export default function RichTextField({
  label,
  value,
  onChange,
  variant = "block",
  helperText,
}: {
  label: string;
  value: string;
  onChange: (html: string) => void;
  variant?: Variant;
  helperText?: string;
}) {
  const inline = variant === "inline";
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");

  const editor = useEditor({
    immediatelyRender: false, // Next.js SSR: render the editor after mount
    extensions: [
      StarterKit.configure({
        heading: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        blockquote: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        strike: false,
        // Inline fields stay on one line: no hard breaks, no underline.
        hardBreak: inline ? false : undefined,
        underline: inline ? false : undefined,
        link: {
          openOnClick: false,
          autolink: true,
          protocols: ["https", "mailto"],
          HTMLAttributes: { rel: "noopener noreferrer", target: "_blank" },
        },
      }),
    ],
    content: value || "",
    editorProps: {
      // Inline variant: swallow Enter so a limited-space field can't grow new lines.
      handleKeyDown: inline ? (_view, e) => e.key === "Enter" : undefined,
    },
    onUpdate: ({ editor: ed }) => onChange(toStored(ed, variant)),
  });

  function applyLink() {
    if (!editor) return;
    const href = normalizeHref(linkUrl);
    const chain = editor.chain().focus().extendMarkRange("link");
    if (href) chain.setLink({ href }).run();
    else chain.unsetLink().run();
    setLinkOpen(false);
    setLinkUrl("");
  }

  function openLinkDialog() {
    if (!editor) return;
    setLinkUrl(editor.getAttributes("link").href ?? "");
    setLinkOpen(true);
  }

  return (
    <Box sx={{ position: "relative", width: "100%" }}>
      {/* Notch-style floating label, so the field reads like the other outlined inputs. */}
      <Box
        component="span"
        sx={{
          position: "absolute",
          top: -8,
          left: 10,
          px: 0.5,
          fontSize: 12,
          lineHeight: 1,
          bgcolor: "background.paper",
          color: "text.secondary",
          zIndex: 1,
          pointerEvents: "none",
        }}
      >
        {label}
      </Box>
      <Box
        sx={{
          border: "1px solid",
          borderColor: "rgba(0,0,0,0.23)",
          borderRadius: 1,
          transition: "border-color .15s ease",
          "&:focus-within": { borderColor: "primary.main", boxShadow: (t) => `0 0 0 1px ${t.palette.primary.main}` },
        }}
      >
        <Stack direction="row" spacing={0.5} sx={{ p: 0.5, flexWrap: "wrap" }}>
          <ToolbarButton
            title="Bold"
            active={!!editor?.isActive("bold")}
            onClick={() => editor?.chain().focus().toggleBold().run()}
          >
            <FormatBoldIcon fontSize="small" />
          </ToolbarButton>
          <ToolbarButton
            title="Italic"
            active={!!editor?.isActive("italic")}
            onClick={() => editor?.chain().focus().toggleItalic().run()}
          >
            <FormatItalicIcon fontSize="small" />
          </ToolbarButton>
          {!inline && (
            <ToolbarButton
              title="Underline"
              active={!!editor?.isActive("underline")}
              onClick={() => editor?.chain().focus().toggleUnderline().run()}
            >
              <FormatUnderlinedIcon fontSize="small" />
            </ToolbarButton>
          )}
          <ToolbarButton title="Link" active={!!editor?.isActive("link")} onClick={openLinkDialog}>
            <LinkIcon fontSize="small" />
          </ToolbarButton>
          {!!editor?.isActive("link") && (
            <ToolbarButton
              title="Remove link"
              active={false}
              onClick={() => editor?.chain().focus().extendMarkRange("link").unsetLink().run()}
            >
              <LinkOffIcon fontSize="small" />
            </ToolbarButton>
          )}
        </Stack>
        <Divider />
        <Box
          sx={{
            px: 1.5,
            py: 1,
            cursor: "text",
            "& .ProseMirror": { outline: "none", minHeight: inline ? 24 : 64 },
            "& .ProseMirror p": { m: 0 },
            "& .ProseMirror p + p": { mt: 1 },
            "& .ProseMirror a": { color: "primary.main", textDecoration: "underline" },
          }}
          onClick={() => editor?.chain().focus().run()}
        >
          <EditorContent editor={editor} />
        </Box>
      </Box>
      {helperText && <FormHelperText sx={{ mx: 1.5 }}>{helperText}</FormHelperText>}

      <Dialog open={linkOpen} onClose={() => setLinkOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Add a link</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            margin="dense"
            label="Web address"
            placeholder="https://example.com or name@email.com"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyLink();
              }
            }}
            helperText="Select some text first, then add the link. Links open in a new tab."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLinkOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={applyLink}>
            {normalizeHref(linkUrl) ? "Apply" : "Remove"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
