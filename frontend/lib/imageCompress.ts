/**
 * Downscale + re-encode an image File in the browser BEFORE upload.
 *
 * Vercel serverless functions reject request bodies larger than ~4.5 MB (a hard,
 * non-configurable platform limit), so the raw 8-14 MB comic panels must be
 * shrunk client-side first or they 413 before ever reaching the backend. We
 * resize the longest edge to <= MAX_DIM and re-encode to WebP — which keeps
 * transparency (for icons) and compresses photos hard, typically to a few
 * hundred KB. The backend compresses again server-side; doing it here first is
 * purely to slip under Vercel's body limit.
 *
 * Best-effort: if anything fails, or the result isn't actually smaller, the
 * original File is returned unchanged.
 */
const MAX_DIM = 1600; // matches the backend's MAX_DIM (app/storage.py)
const QUALITY = 0.85;

export async function compressImage(file: File): Promise<File> {
  if (typeof document === "undefined" || !file.type.startsWith("image/")) return file;
  try {
    const bitmap = await loadBitmap(file);
    const scale = Math.min(1, MAX_DIM / Math.max(bitmap.width, bitmap.height));
    const w = Math.round(bitmap.width * scale);
    const h = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);
    if (typeof ImageBitmap !== "undefined" && bitmap instanceof ImageBitmap) bitmap.close();

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/webp", QUALITY),
    );
    if (!blob || blob.size >= file.size) return file; // didn't help → keep original

    const name = file.name.replace(/\.[^.]+$/, "") + ".webp";
    return new File([blob], name, { type: "image/webp" });
  } catch {
    return file;
  }
}

async function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === "function") {
    try {
      return await createImageBitmap(file);
    } catch {
      // fall through to the <img> path (e.g. unsupported in some browsers)
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}
