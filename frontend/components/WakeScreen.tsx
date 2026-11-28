"use client";

// The "Waking up AI braincells..." screen (T-028, DESIGN.md "Server waking up", approved
// 2026-11-28). Wraps the site in app/layout.tsx: while the shared health check (lib/serverInfo)
// is waking the free API host, or has given up, a full-page cover sits on top and the site behind
// it is `inert`. Fades in and out; stays at least MIN_SHOWN_MS so a just-late answer never
// flickers. Announcements go through one polite live region that outlives the cover.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { secondaryButton } from "@/components/buttonStyles";
import { ExternalLinkIcon } from "@/components/icons";
import { formatElapsed } from "@/lib/formatElapsed";
import { useServerInfo, useServerWake } from "@/lib/serverInfo";

export const MIN_SHOWN_MS = 800;
const FADE_OUT_MS = 300;
const ISSUES_URL = "https://github.com/Oralino/gradpath-ai/issues";

// Seven cells and their links (DESIGN.md): positions in a 120x72 box, edges drawn first.
const NODES: [number, number][] = [[14, 40], [38, 18], [44, 54], [66, 32], [86, 12], [92, 52], [108, 30]];
const EDGES: [number, number][] = [[1, 2], [1, 3], [2, 4], [3, 4], [2, 5], [4, 5], [4, 6], [5, 7], [6, 7]];
// Firing order 1, 2, 4, 5, 7, 6, 3 at 0.4 s steps: exactly one cell lit at a time.
const DELAY_S: Record<number, number> = { 1: 0, 2: 0.4, 4: 0.8, 5: 1.2, 7: 1.6, 6: 2.0, 3: 2.4 };
const CENTRE = 4;

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** The nerve-cell drawing. Asleep (stopped): every cell hollow and nothing moves. */
function Braincells({ asleep }: { asleep: boolean }) {
  return (
    <svg viewBox="0 0 120 72" aria-hidden="true" focusable="false" className="h-auto w-40" data-testid="braincells">
      {EDGES.map(([a, b]) => {
        const [x1, y1] = NODES[a - 1];
        const [x2, y2] = NODES[b - 1];
        return (
          <line key={`${a}-${b}`} x1={x1} y1={y1} x2={x2} y2={y2} className="stroke-rule" strokeWidth={1.5} strokeLinecap="round" />
        );
      })}
      {NODES.map(([cx, cy], i) => {
        const id = i + 1;
        const lit = asleep
          ? "opacity-0"
          : `opacity-0 motion-safe:animate-fire ${id === CENTRE ? "motion-reduce:opacity-100" : ""}`;
        return (
          <g key={id}>
            <circle cx={cx} cy={cy} r={4} className="fill-paper stroke-line" strokeWidth={1.5} />
            <circle
              cx={cx}
              cy={cy}
              r={4}
              className={`fill-link ${lit}`}
              style={asleep ? undefined : { animationDelay: `${DELAY_S[id]}s` }}
              data-cell={id}
            />
          </g>
        );
      })}
    </svg>
  );
}

export function WakeScreen({ children }: { children: ReactNode }) {
  const info = useServerInfo();
  const { waking, startedAt, retry } = useServerWake();
  const stopped = info.status === "error" && !waking;
  const wanted = waking || stopped;

  const [shown, setShown] = useState(false); // the cover is mounted
  const [opaque, setOpaque] = useState(false); // faded in (false while fading in or out)
  const [now, setNow] = useState(() => Date.now());
  const [message, setMessage] = useState("");
  const shownAt = useRef(0);
  const minutesAnnounced = useRef(0);
  const stoppedHeading = useRef<HTMLParagraphElement>(null);
  const wakingHeading = useRef<HTMLParagraphElement>(null);
  const focusWaking = useRef(false);

  // Show on the next frame, then fade in; hide after the minimum time, fading out unless motion
  // is reduced. State changes run in frame and timer callbacks, never directly in the effect.
  useEffect(() => {
    if (wanted) {
      const frame = requestAnimationFrame(() => {
        if (!shown) {
          shownAt.current = Date.now();
          minutesAnnounced.current = 0;
          setShown(true);
          setMessage("Waking up AI braincells");
          requestAnimationFrame(() => setOpaque(true));
        } else {
          setOpaque(true);
        }
      });
      return () => cancelAnimationFrame(frame);
    }
    if (!shown) return;
    const hold = Math.max(0, MIN_SHOWN_MS - (Date.now() - shownAt.current));
    const fade = reducedMotion() ? 0 : FADE_OUT_MS;
    const start = setTimeout(() => {
      setOpaque(false);
      if (info.status === "ready") setMessage("Server ready");
    }, hold);
    const end = setTimeout(() => setShown(false), hold + fade);
    return () => {
      clearTimeout(start);
      clearTimeout(end);
    };
  }, [wanted, shown, info.status]);

  // The timer ticks while waking and freezes when the check gives up. Once a minute the live
  // region says "Still waking up, N minute(s)"; the timer itself is never announced.
  useEffect(() => {
    if (!waking) return;
    const tick = setInterval(() => {
      const t = Date.now();
      setNow(t);
      const minutes = Math.floor((t - startedAt) / 60_000);
      if (minutes > minutesAnnounced.current) {
        minutesAnnounced.current = minutes;
        setMessage(`Still waking up, ${minutes} minute${minutes === 1 ? "" : "s"}`);
      }
    }, 1000);
    return () => clearInterval(tick);
  }, [waking, startedAt]);

  const elapsedS = Math.max(0, Math.floor((now - startedAt) / 1000));
  const announcement = stopped ? "The braincells didn't wake up. The backend might be down." : message;

  // Stopped: move focus to the first line so keyboard users land on it. After "Try again" (whose
  // button disappears) focus goes to the waking line instead of falling to the page body.
  useEffect(() => {
    if (!shown) return;
    if (stopped) stoppedHeading.current?.focus();
    else if (focusWaking.current) {
      focusWaking.current = false;
      wakingHeading.current?.focus();
    }
  }, [stopped, shown]);

  /** "Try again": start the announcements over and keep focus on the screen. */
  function tryAgain() {
    minutesAnnounced.current = 0;
    focusWaking.current = true;
    setMessage("Waking up AI braincells");
    retry();
  }

  return (
    <>
      <div className="contents" inert={shown}>
        {children}
      </div>
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>
      {shown && (
        <div
          data-testid="wake-screen"
          className={`fixed inset-0 z-50 flex flex-col bg-paper text-ink motion-safe:transition-opacity ${
            opaque ? "opacity-100 duration-150" : "opacity-0 duration-300 ease-out"
          }`}
        >
          <div className="mx-auto flex h-14 w-full max-w-5xl flex-none items-center px-4 text-label sm:px-6 lg:px-8">
            GradPath
          </div>
          <div className="m-auto flex flex-col items-center gap-6 px-4 pb-14 text-center">
            <Braincells asleep={stopped} />
            {stopped ? (
              <>
                <div className="flex flex-col items-center gap-2">
                  <p ref={stoppedHeading} tabIndex={-1} className="text-title text-ink outline-none">
                    The braincells didn&apos;t wake up.
                  </p>
                  <p className="text-heading tabular-nums text-ink-muted">{formatElapsed(elapsedS)}</p>
                  <p className="max-w-xs text-small text-ink-muted">
                    The backend might be down. Please{" "}
                    <a href={ISSUES_URL} target="_blank" rel="noopener noreferrer" className="text-link underline underline-offset-4">
                      let the owner know{" "}
                      <span className="inline-block align-[-1px]">
                        <ExternalLinkIcon size={12} />
                      </span>
                      <span className="sr-only">(opens in new tab)</span>
                    </a>
                    .
                  </p>
                </div>
                <button type="button" onClick={tryAgain} className={`${secondaryButton} w-full sm:w-auto`}>
                  Try again
                </button>
              </>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <p ref={wakingHeading} tabIndex={-1} className="text-title text-ink outline-none">
                  Waking up AI braincells...
                </p>
                <p className="text-heading tabular-nums text-ink-muted">{formatElapsed(elapsedS)}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
