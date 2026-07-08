"use client";

import { useRef, useState } from "react";

import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { adminApi } from "@/lib/adminApi";
import { compressImage } from "@/lib/imageCompress";

/**
 * Pick an image → upload via the admin API → return the stored URL through
 * `onChange`. Shows a preview of the current value. A plain <img> is used (not
 * next/image) since this is the owner dashboard, not the themed guest site.
 */
export default function ImageUpload({
  value,
  onChange,
  label = "image",
  aspect = "4 / 3",
  fit = "cover",
}: {
  value?: string | null;
  onChange: (url: string) => void;
  label?: string;
  /** CSS aspect-ratio for the preview box (e.g. "1 / 1" for a square icon). */
  aspect?: string;
  /** object-fit for the preview image ("contain" keeps a transparent icon whole). */
  fit?: "cover" | "contain";
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      // Shrink client-side first: Vercel rejects request bodies over ~4.5 MB,
      // so big originals must be downscaled before they reach the backend.
      const prepared = await compressImage(file);
      const url = await adminApi.uploadImage(prepared);
      onChange(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <Stack spacing={1}>
      <Box
        sx={{
          position: "relative",
          width: "100%",
          aspectRatio: aspect,
          borderRadius: 1,
          border: 1,
          borderColor: "divider",
          bgcolor: "action.hover",
          overflow: "hidden",
          display: "grid",
          placeItems: "center",
        }}
      >
        {value ? (
          <Box
            component="img"
            src={value}
            alt={`${label} preview`}
            sx={{ width: "100%", height: "100%", objectFit: fit }}
          />
        ) : (
          <Typography variant="caption" color="text.secondary">
            No {label} yet
          </Typography>
        )}
        {busy && (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "grid",
              placeItems: "center",
              bgcolor: "rgba(255,255,255,0.6)",
            }}
          >
            <CircularProgress size={28} />
          </Box>
        )}
      </Box>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      <Button
        size="small"
        startIcon={<PhotoCameraIcon />}
        onClick={() => inputRef.current?.click()}
        disabled={busy}
      >
        {value ? `Replace ${label}` : `Upload ${label}`}
      </Button>
      {error && (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      )}
    </Stack>
  );
}
