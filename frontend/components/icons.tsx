// Small inline SVG icons (DESIGN.md, Component library: no icon package). One glyph means one
// thing everywhere (see Status badge). All are aria-hidden: the words next to them carry meaning.
// Used by StatusBadge, StatusPanel, CitationList and the Ask screen.

import type { ReactNode } from "react";

function Svg({ size, children }: { size: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      {children}
    </svg>
  );
}

type IconProps = { size?: number };

export function CheckIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M3 8.5l3.2 3L13 4.5" />
    </Svg>
  );
}

export function TriangleIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M8 2.2l6 10.8H2z" />
      <path d="M8 6.5v3M8 11.3v.1" />
    </Svg>
  );
}

export function HalfCircleIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" />
    </Svg>
  );
}

export function HollowCircleIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="8" cy="8" r="5.5" />
    </Svg>
  );
}

export function OctagonIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M5.3 2h5.4L14 5.3v5.4L10.7 14H5.3L2 10.7V5.3z" />
      <path d="M8 5v3.5M8 10.8v.1" />
    </Svg>
  );
}

export function InfoIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 7.3v3.4M8 5.2v.1" />
    </Svg>
  );
}

export function ExternalLinkIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M9 2.5h4.5V7M13.5 2.5L7.5 8.5M12 9.5v3a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3" />
    </Svg>
  );
}

// The dash glyph: "not assessed" / sample marker (DESIGN.md, Status badge).
export function DashIcon({ size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M3 8h10" />
    </Svg>
  );
}
