import { redirect } from "next/navigation";

/**
 * The pre-platform single-wedding dashboard lived here. Admin is now
 * wedding-scoped at /{weddingSlug}/admin; the post-login home lists your
 * weddings and takes you there.
 */
export default function AdminRedirect() {
  redirect("/dashboard");
}
