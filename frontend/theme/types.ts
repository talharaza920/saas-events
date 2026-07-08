/**
 * The shape of a wedding's theme tokens.
 *
 * This is the ONE source of truth for what is themeable. A wedding stores a
 * (possibly partial) `ThemeTokens` object in the DB (`weddings.theme_tokens`);
 * `buildTheme` deep-merges it onto `defaultThemeConfig` and produces an MUI
 * theme. A future in-app theme editor edits exactly this object — no component
 * changes required. Components must reference theme tokens, never raw hex/px.
 */
export interface ThemeColors {
  /** Page background — the comic's cream paper. */
  paper: string;
  /** Slightly deeper cream for panels/cards. */
  paperAlt: string;
  /** Edge / hairline cream for borders and dividers. */
  paperEdge: string;
  /** Near-black ink for line art and text. */
  ink: string;
  /** Muted ink for secondary text. */
  inkSoft: string;
  /** Warm sunset peach/terracotta. */
  primary: string;
  /** Deeper terracotta for hover / emphasis. */
  primaryDeep: string;
  /** Dusty periwinkle (sky). */
  secondary: string;
  accentSage: string;
  accentLav: string;
  /** Affirmative RSVP / success. */
  yes: string;
  /** Decline RSVP. */
  no: string;
  /** Warm ochre for "awaiting / pending" + MUI warning. */
  amber: string;
  /** Dreamy pastel hero wash (cover blobs + panel glow). */
  dream1: string;
  dream2: string;
  dream3: string;
  dream4: string;
}

export interface ThemeTypography {
  /** Friendly rounded/comic face for the wordmark + brand. */
  logo: string;
  /** Friendly rounded/comic face for headings. */
  display: string;
  /** Warm serif for "Once upon a time" narrator captions. */
  story: string;
  /** Clean humanist sans for body, forms, details. */
  body: string;
}

export interface ThemeShadows {
  /** Resting card elevation. */
  soft: string;
  /** Hover / popped elevation. */
  pop: string;
}

export interface ThemeTokens {
  colors: ThemeColors;
  typography: ThemeTypography;
  shadows: ThemeShadows;
  /** Base border radius in px. */
  radius: number;
  /** Larger radius for cards/panels in px. */
  radiusLg: number;
  /** MUI spacing unit in px. */
  spacingUnit: number;
  /**
   * How far (in %) each story-panel image edge feathers into the page. 0 = hard
   * edge; ~4 = subtle softening; higher = dreamier dissolve (eats into the
   * image). Used by the story manga strip's edge mask.
   */
  storyFeather: number;
}

/** A partial override as stored per-wedding (any subset of tokens). */
export type ThemeTokensOverride = {
  colors?: Partial<ThemeColors>;
  typography?: Partial<ThemeTypography>;
  shadows?: Partial<ThemeShadows>;
  radius?: number;
  radiusLg?: number;
  spacingUnit?: number;
  storyFeather?: number;
};
