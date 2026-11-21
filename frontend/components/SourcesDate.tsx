"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Day = { iso: string; label: string };

// "Sources as of {date} · " at the start of the footer (DESIGN.md, footer copy; T-018 step 3).
// The date comes from /api/health (the oldest page fetch in the index). Fetched after mount, so
// the static footer renders at once; if the API is down or has no date, nothing is shown.
export function SourcesDate() {
  const [asOf, setAsOf] = useState<Day | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then((h) => setAsOf(formatDay(h.sources_as_of)))
      .catch(() => undefined); // the footer simply leaves the date out
    return () => controller.abort();
  }, []);

  if (asOf === null) return null;
  return (
    <>
      Sources as of <time dateTime={asOf.iso}>{asOf.label}</time> ·{" "}
    </>
  );
}

// "2026-11-18" -> { iso, label: "18 Nov 2026" }; anything else -> null. Read as UTC, so the day
// never shifts with the visitor's time zone.
export function formatDay(value: string | null | undefined): Day | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const day = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(day.getTime()) || day.toISOString().slice(0, 10) !== value) return null;
  const label = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(day);
  return { iso: value, label };
}
