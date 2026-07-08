# Invite images — swap by bullet number

These are the guest invite's pictures. They are **referenced as data**, not
hardcoded in components: each story beat in the wedding's `content.story.beats[]`
(seeded in `backend/app/seed_data.py`) carries a stable bullet number and an
`image` path.

## To change the picture for story bullet _N_

Replace the file at:

```
public/invite/story/0N.png      # e.g. bullet 3 -> public/invite/story/03.png
```

That's it — the beat keeps its number, narration, and onomatopoeia; only the
picture changes. No code edit needed.

If you'd rather host the image elsewhere (e.g. Supabase Storage), set that beat's
`image` field in `seed_data.py` to the full URL instead of the `/invite/story/0N.png`
path — the component renders whatever the field points at, no code change required.

| File | Used by |
|------|---------|
| `story/01.png` … `story/06.png` | story beats 1–6 (the manga strip) |
| `wordmark.png` | (reserved) raster wordmark fallback; the live wordmark is drawn as SVG |

Originals (the 8–14 MB comic exports) are **not** committed. The optimizer that
produced these lives at `frontend/scripts/optimize-invite-images.mjs`.
