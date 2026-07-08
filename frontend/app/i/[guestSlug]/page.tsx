import Box from "@mui/material/Box";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import Cover from "@/components/invite/Cover";
import DressCode from "@/components/invite/DressCode";
import EventDetails from "@/components/invite/EventDetails";
import Faq from "@/components/invite/Faq";
import Footer from "@/components/invite/Footer";
import InviteThemeProvider from "@/components/invite/InviteThemeProvider";
import Nav from "@/components/invite/Nav";
import PetTheCat from "@/components/invite/PetTheCat";
import RsvpForm from "@/components/invite/RsvpForm";
import ScrollProgress from "@/components/invite/ScrollProgress";
import Story from "@/components/invite/Story";
import Wishes from "@/components/invite/Wishes";
import { fetchInvite, fetchWishes, InviteNotFound } from "@/lib/api";
import { parseContent, parseStoryContent, toPlainText } from "@/lib/content";
import type { ThemeTokensOverride } from "@/theme/types";

/**
 * The invitation. Resolves the guest slug server-side (the slug carries the
 * tenant), renders the wedding's stored content under its own theme. The RSVP
 * form is wired in M5 — capabilities are already on the payload but the tier is
 * never exposed here. Always dynamic: RSVP state must be fresh.
 */
export const dynamic = "force-dynamic";

/**
 * Cache the fetch within a request so `generateMetadata` and the page share one
 * backend call (fetchInvite is `no-store`, so React's per-request `cache` is what
 * dedupes them — not the fetch cache).
 */
const getInvite = cache(fetchInvite);

/**
 * Per-wedding page metadata (browser tab + link/social preview). Derived from the
 * wedding's own stored content so it's never hardcoded to one couple — and kept at
 * couple level (no guest name) since link previews can be cached/shared.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ guestSlug: string }>;
}): Promise<Metadata> {
  const { guestSlug } = await params;
  try {
    const { wedding } = await getInvite(guestSlug);
    const content = parseContent(wedding);
    const title =
      [toPlainText(content.cover.kicker), wedding.couple_names].filter(Boolean).join(" — ") ||
      "Wedding invitation";
    const description =
      toPlainText(content.cover.tagline) ||
      toPlainText(content.cover.invite_line) ||
      "You’re invited.";
    return { title, description };
  } catch {
    // Unknown/inactive link: fall back to the generic layout metadata.
    return {};
  }
}

export default async function InvitePage({
  params,
}: {
  params: Promise<{ guestSlug: string }>;
}) {
  const { guestSlug } = await params;

  let invite;
  try {
    invite = await getInvite(guestSlug);
  } catch (err) {
    if (err instanceof InviteNotFound) notFound();
    throw err;
  }

  const wishes = await fetchWishes(guestSlug);

  const { wedding, guest } = invite;
  const content = parseContent(wedding);
  // Story comes from the arcs this guest is allowed to see (resolved server-side
  // per-guest). Fall back to the legacy embedded content.story if none. >1 arc
  // renders as a carousel inside <Story>.
  const arcs = invite.story_arcs ?? [];
  const stories = arcs.length
    ? arcs.map((a) => parseStoryContent(a.content))
    : [content.story];
  const tokens = (wedding.theme_tokens ?? null) as ThemeTokensOverride | null;

  return (
    <InviteThemeProvider tokens={tokens}>
      <ScrollProgress />
      <Nav nav={content.nav} />
      <PetTheCat />
      <Box sx={{ bgcolor: "background.default", color: "text.primary" }}>
        <Cover
          firstName={guest.first_name}
          greetingName={guest.greeting_name}
          coupleNames={wedding.couple_names}
          cover={content.cover}
          brand={content.brand}
          event={content.event}
        />
        <Story stories={stories} sectionLabel={content.storySection} />
        <EventDetails day={content.day} event={content.event} />
        <DressCode dressCode={content.dressCode} />
        <Faq faq={content.faq} />

        <RsvpForm
          guestSlug={guestSlug}
          fullName={guest.name}
          greetingName={guest.greeting_name}
          partyMembers={guest.party_members}
          initialEmail={guest.email}
          initialPhone={guest.phone}
          capabilities={invite.capabilities}
          questions={invite.questions}
          initialRsvp={invite.rsvp ?? null}
          rsvp={content.rsvp}
          guideIconUrl={content.brand.rsvp_icon_url || undefined}
          wishes={{
            guestSlug,
            defaultName: guest.greeting_name || guest.first_name,
            initialWishes: wishes,
            copy: content.wishes,
          }}
        />

        <Wishes
          guestSlug={guestSlug}
          defaultName={guest.greeting_name || guest.first_name}
          initialWishes={wishes}
          copy={content.wishes}
        />

        <Footer footer={content.footer} />
      </Box>
    </InviteThemeProvider>
  );
}
