import type { Metadata } from "next";
import { Baloo_2, Lora, Plus_Jakarta_Sans } from "next/font/google";

import Providers from "./providers";

// Fonts → CSS variables consumed by the theme tokens (see theme/defaultThemeConfig.ts).
// Baloo 2 = display/logo, Lora (italic) = storybook narrator, Plus Jakarta Sans = body.
const display = Baloo_2({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const story = Lora({ subsets: ["latin"], style: ["italic", "normal"], variable: "--font-story", display: "swap" });
const body = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-body", display: "swap" });

export const metadata: Metadata = {
  title: "Ever after — Alex & Sam",
  description: "You are invited.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${display.variable} ${story.variable} ${body.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
