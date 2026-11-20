// Counter under long inputs, "312 / 2,000" (DESIGN.md, Field): caution from 90%, stopped when
// over. Used by the message and job posting fields.

export function CharCount({ id, value, max }: { id?: string; value: number; max: number }) {
  const tone = value > max ? "text-stopped" : value >= max * 0.9 ? "text-caution" : "text-ink-muted";
  return (
    <p id={id} className={`text-meta tabular-nums ${tone}`}>
      {value.toLocaleString("en-US")} / {max.toLocaleString("en-US")}
    </p>
  );
}
