import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";

/** Small single-stroke line icons for the "day" details grid. */
const PATHS: Record<string, React.ReactNode> = {
  cal: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2.5" />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21s7-6.4 7-11a7 7 0 1 0-14 0c0 4.6 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  car: (
    <>
      <path d="M5 16l1.5-6h11L19 16M3 16h18v3H3z" />
      <circle cx="7.5" cy="19.5" r="1.5" />
      <circle cx="16.5" cy="19.5" r="1.5" />
    </>
  ),
  hourglass: (
    <>
      <path d="M6 3h12M6 21h12" />
      <path d="M7 3c0 5 5 5 5 9s-5 4-5 9M17 3c0 5-5 5-5 9s5 4 5 9" />
    </>
  ),
  dress: (
    <>
      <path d="M12 4.5a1.6 1.6 0 1 1 1.4 1.6" />
      <path d="M13.4 6.1 21 11H3l4.5-2.9" />
      <path d="M4 11h16a1 1 0 0 1 0 2H4a1 1 0 0 1 0-2z" />
    </>
  ),
  ring: (
    <>
      <circle cx="12" cy="14.5" r="4.5" />
      <path d="M9.2 7 12 3.5 14.8 7l-2.8 3z" />
    </>
  ),
  gift: (
    <>
      <rect x="3" y="8" width="18" height="13" rx="1.5" />
      <path d="M3 12.5h18M12 8v13" />
      <path d="M12 8S11 4 9 4a2 2 0 0 0 0 4zM12 8s1-4 3-4a2 2 0 0 1 0 4z" />
    </>
  ),
  cup: (
    <>
      <path d="M8 3h8l-1 6.5a3 3 0 0 1-6 0z" />
      <path d="M12 12.5V18M9 21h6" />
    </>
  ),
  music: (
    <>
      <path d="M9 18V5l11-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="17" cy="16" r="3" />
    </>
  ),
  heart: <path d="M12 20s-7-4.6-7-10a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 5.4-7 10-7 10z" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 7.5h.01" />
    </>
  ),
  sparkle: <path d="M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z" />,
};

export type IcoName = keyof typeof PATHS;

/** Ordered icon names for admin pickers. */
export const ICO_NAMES = Object.keys(PATHS) as IcoName[];

export default function Ico({ name, size = 26, sx }: { name: IcoName; size?: number; sx?: SxProps<Theme> }) {
  return (
    <Box
      component="svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      sx={[{ width: size, height: size, display: "block" }, ...(Array.isArray(sx) ? sx : [sx])]}
    >
      {PATHS[name]}
    </Box>
  );
}
