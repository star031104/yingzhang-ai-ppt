import type { ReactNode, SVGProps } from "react";

/* Small hand-drawn stroke icon set (24px grid, 1.75 stroke). No icon dependency. */
const PATHS = {
  plus: <path d="M12 5v14M5 12h14" />,
  folder: <path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2h7.4a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />,
  chip: <><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M10 3.5v3M14 3.5v3M10 17.5v3M14 17.5v3M3.5 10h3M3.5 14h3M17.5 10h3M17.5 14h3" /></>,
  sparkles: <><path d="M11 4.5l1.6 4.2 4.2 1.6-4.2 1.6L11 16.1l-1.6-4.2-4.2-1.6 4.2-1.6z" /><path d="M18 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></>,
  user: <><circle cx="12" cy="8.5" r="3.75" /><path d="M4.75 19.5c1.4-3.2 4.1-4.75 7.25-4.75s5.85 1.55 7.25 4.75" /></>,
  sliders: <><path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="17" cy="17" r="2" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.75v2M12 19.25v2M4.75 12h-2M21.25 12h-2M6.9 6.9 5.5 5.5M18.5 18.5l-1.4-1.4M6.9 17.1l-1.4 1.4M18.5 5.5l-1.4 1.4" /></>,
  moon: <path d="M19.5 14.6A7.75 7.75 0 0 1 9.4 4.5a7.75 7.75 0 1 0 10.1 10.1z" />,
  monitor: <><rect x="3.5" y="4.5" width="17" height="11.5" rx="2" /><path d="M8.5 20h7M12 16v4" /></>,
  arrowLeft: <path d="M19 12H5M11 6l-6 6 6 6" />,
  arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
  chevronRight: <path d="M9.5 6l6 6-6 6" />,
  chevronLeft: <path d="M14.5 6l-6 6 6 6" />,
  chevronDown: <path d="M6 9.5l6 6 6-6" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  alert: <><circle cx="12" cy="12" r="8.75" /><path d="M12 7.75v5M12 16.25v.01" /></>,
  info: <><circle cx="12" cy="12" r="8.75" /><path d="M12 11v5.25M12 7.75v.01" /></>,
  x: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  download: <path d="M12 4v11M7 10.5l5 5 5-5M5 20h14" />,
  upload: <path d="M12 20V9M7 13.5l5-5 5 5M5 4h14" />,
  file: <><path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z" /><path d="M14 3.5V8h4.5" /></>,
  layers: <><path d="M12 3.75l8.25 4.5-8.25 4.5-8.25-4.5z" /><path d="M3.75 12.5 12 17l8.25-4.5" /><path d="M3.75 16.25 12 20.75l8.25-4.5" /></>,
  history: <><path d="M3.75 12a8.25 8.25 0 1 0 2.4-5.85" /><path d="M3.75 4.5v4.25H8" /><path d="M12 7.75V12l3 2" /></>,
  zoomIn: <><circle cx="10.75" cy="10.75" r="6.75" /><path d="M20 20l-4.25-4.25M10.75 8v5.5M8 10.75h5.5" /></>,
  zoomOut: <><circle cx="10.75" cy="10.75" r="6.75" /><path d="M20 20l-4.25-4.25M8 10.75h5.5" /></>,
  fit: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  select: <><path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M12 4h0M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 12v0M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M12 20h0M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16M4 12v0" /></>,
  wand: <><path d="M5 19 15.5 8.5" /><path d="M14 7l3 3" /><path d="M18 3.5v2M21 7h-2M19.5 4.5 18 6" /><path d="M9.5 3.5v1.5M8.75 4.25h1.5" /></>,
  refresh: <><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M19.5 4.5v4h-4" /></>,
  play: <path d="M8 5.5v13l10.5-6.5z" />,
  logout: <><path d="M14.5 4.5h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3" /><path d="M9.5 16.5 5 12l4.5-4.5M5 12h10.5" /></>,
  shield: <><path d="M12 3.5l7.5 2.75v5.5c0 4.6-3.2 7.8-7.5 8.75-4.3-.95-7.5-4.15-7.5-8.75v-5.5z" /><path d="M9 12l2 2 4-4.25" /></>,
  book: <><path d="M5 5.25a2 2 0 0 1 2-2h12v15.5H7a2 2 0 0 0-2 2z" /><path d="M5 20.75a2 2 0 0 1 2-2h12" /></>,
  list: <path d="M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01" />,
  pen: <><path d="M4.5 19.5h3.75L19 8.75 15.25 5 4.5 15.75z" /><path d="M13.5 6.75l3.75 3.75" /></>,
  image: <><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><circle cx="9" cy="10" r="1.75" /><path d="M20.5 15.5 15.5 11 6 19.5" /></>,
  sidebar: <><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M9.5 4.5v15" /></>,
  layout: <><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M3.5 9.5h17M9.5 9.5v10" /></>,
  message: <path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8.5a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5V7A1.5 1.5 0 0 1 5 5.5z" />,
  users: <><circle cx="9" cy="8.5" r="3.25" /><path d="M3.5 19c1-2.8 3.1-4.25 5.5-4.25s4.5 1.45 5.5 4.25" /><path d="M15.5 5.5a3.25 3.25 0 0 1 0 6.25M17.25 14.9c1.5.6 2.6 1.9 3.25 4.1" /></>,
  trash: <path d="M4.5 7h15M10 4h4M6.5 7l.9 11.6a2 2 0 0 0 2 1.9h5.2a2 2 0 0 0 2-1.9L17.5 7M10 11v5.5M14 11v5.5" />,
  external: <path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2V8.5a2 2 0 0 1 2-2H10" />,
  lock: <><rect x="5" y="10.5" width="14" height="9.5" rx="2" /><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" /></>,
  grid: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
  slides: <><rect x="3.5" y="5" width="17" height="11" rx="1.75" /><path d="M8 20h8M12 16v4" /></>,
  link: <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" />,
  eye: <><path d="M2.75 12S6.25 5.5 12 5.5 21.25 12 21.25 12 17.75 18.5 12 18.5 2.75 12 2.75 12z" /><circle cx="12" cy="12" r="2.75" /></>,
  dot: <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16, ...props }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {PATHS[name]}
    </svg>
  );
}
