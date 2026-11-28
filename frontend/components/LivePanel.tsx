"use client";

// Live mode entry (DESIGN.md "Live mode panel"; T-018, T-026; always-hard area). LivePanel
// replaces the submit row on Ask/Job/Plan (and sits inside the resume import on Profile) while the
// server is in live mode and this tab isn't both signed in with GitHub and holding a key;
// LiveStrip is what shows once both hold. Signing in is a full-page link to
// /api/auth/github/login (the server keeps the session in an HttpOnly cookie). The key lives ONLY
// in this panel's input state: it goes to api.liveCheck, then to lib/liveSession.ts, and the input
// is emptied. Never put it in a URL, storage, a log, an error text or a prop. Not a <form> (no
// submit event, fewer password-manager prompts); Enter in the key field runs "Use live mode".

import { useEffect, useRef, useState } from "react";
import { OctagonIcon, KeyIcon } from "@/components/icons";
import { primaryButton, secondaryButton, textButton } from "@/components/buttonStyles";
import { api, ApiError } from "@/lib/api";
import {
  clearAll,
  clearKey,
  clearRefusal,
  liveState,
  setKey as setLiveKey,
  useLiveSession,
} from "@/lib/liveSession";
import { RetryAfter } from "@/components/RetryAfter";
import { useCountdown } from "@/lib/useCountdown";

export const KEY_PREFIX = "sk-ant-";
export const SIGNIN_URL = "/api/auth/github/login";
const MSG_KEY_FORMAT = "This doesn't look like an Anthropic API key: they start with sk-ant-.";
// Header values must be printable ASCII: anything else makes fetch throw before sending.
const HEADER_SAFE = /^[!-~]+$/;
const MSG_KEY_REFUSED = "Anthropic refused this API key. Check that it is active and has credit.";
const MSG_SIGNIN_ENDED = "Your GitHub sign-in has ended. Sign in again to use live mode.";
const MSG_SIGNIN_UNAVAILABLE = "GitHub sign-in isn't available on this server right now.";
const MSG_SIGNOUT_FAILED = "Signed out in this tab, but the server didn't confirm it. Reload the page to check.";
const PRIVACY_LINE =
  "We keep only your GitHub username and id, in a cookie that expires after a day. Nothing is logged.";
const INPUT = "h-11 min-w-0 flex-1 rounded-md border bg-surface px-3 text-body sm:h-10";
const SHOW_BUTTON =
  "inline-flex h-11 items-center justify-center rounded-md border border-line bg-surface px-4 text-label text-ink transition-colors duration-150 hover:bg-sunken sm:h-10";

// One-shot hand-offs between the panel and the strip, which never exist together. They hold no
// secret: only "move focus here once" and what to announce.
let stripFocusPending = false;
let panelClearedPending: string | null = null;

interface Outcome {
  status: number | null; // a model request's refusal is always a 401
  code: string | null;
  message: string;
  retryAfter?: number | null;
}

// POST /api/auth/logout; true when the server confirmed (the cookie is HttpOnly, so only the
// server can clear it). Callers then forget the key and sign-in here either way (clearAll).
async function logout(): Promise<boolean> {
  try {
    await api.logout();
    return true;
  } catch {
    return false;
  }
}

/** The collapsed state: signed in and key held (DESIGN.md, "Key set"). Used by Assistant,
 * JobAnalysisView, PlanView and ResumeImport. */
export function LiveStrip() {
  const live = useLiveSession();
  const ref = useRef<HTMLDivElement>(null);
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    if (!stripFocusPending) return;
    stripFocusPending = false;
    ref.current?.focus();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnnounce("Live mode on");
  }, []);
  return (
    <div
      ref={ref}
      tabIndex={-1}
      className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-md border-l-4 border-info bg-info-bg p-3 text-small"
    >
      <p className="flex min-w-0 flex-1 items-start gap-2">
        <KeyIcon size={16} />
        <span>
          Live mode on{live.login ? `, signed in as @${live.login}` : ""}. Your key is in this tab&apos;s memory
          only and clears on reload; the GitHub sign-in lasts a day.
        </span>
      </p>
      <button
        type="button"
        className={textButton}
        onClick={() => {
          panelClearedPending = "Key cleared";
          clearKey();
        }}
      >
        Clear key
      </button>
      <button
        type="button"
        className={textButton}
        onClick={() => {
          void logout().then((ok) => {
            panelClearedPending = ok ? "Signed out" : MSG_SIGNOUT_FAILED;
            clearAll();
          });
        }}
      >
        Sign out
      </button>
      <span role="status" className="sr-only">
        {announce}
      </span>
    </div>
  );
}

export function LivePanel({
  firstLine,
  examplesHref = "#recorded-examples",
}: {
  firstLine?: string | null;
  examplesHref?: string;
}) {
  const live = useLiveSession();
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  // The last answer of this panel's own check; while null, a refusal recorded by lib/api.ts (a
  // model request's 401) is what the panel explains.
  const [own, setOwn] = useState<Outcome | null>(null);
  const [attempted, setAttempted] = useState(false); // once this panel has checked, a stale refusal is history
  const [focusTarget, setFocusTarget] = useState<{ target: "signin" | "key"; n: number } | null>(null);
  const [announce, setAnnounce] = useState("");
  const [signOutNote, setSignOutNote] = useState<string | null>(null);
  const wait = useCountdown();

  const headingRef = useRef<HTMLHeadingElement>(null);
  const signInRef = useRef<HTMLAnchorElement>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const signedIn = live.signedIn;
  const outcome: Outcome | null =
    own ?? (attempted || live.refusal === null ? null : { status: 401, ...live.refusal });

  // What the panel shows: the local check first, then the server's answer by code.
  let keyError = localError;
  let signInLine: string | null = null;
  let stoppedLine: string | null = null;
  if (outcome && !keyError) {
    if (outcome.code === "signin_required") signInLine = MSG_SIGNIN_ENDED;
    else if (outcome.code === "key_refused") keyError = MSG_KEY_REFUSED;
    else if (outcome.status === 401 && outcome.code?.startsWith("key_")) keyError = outcome.message;
    else stoppedLine = outcome.message;
  }

  // Focus the control a refusal or a failed check points at.
  useEffect(() => {
    if (focusTarget?.target === "signin") signInRef.current?.focus();
    else if (focusTarget?.target === "key") keyRef.current?.focus();
  }, [focusTarget]);

  // After "Clear key" or "Sign out" in the strip: focus the heading and say so.
  useEffect(() => {
    if (panelClearedPending === null) return;
    const said = panelClearedPending;
    panelClearedPending = null;
    headingRef.current?.focus();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnnounce(said);
  }, []);

  // A model request's 401 reopened this panel: focus the control it is about.
  const refusalCode = live.refusal?.code ?? null;
  useEffect(() => {
    // Read the store, not this render: a refusal the previous page's panel already cleared on
    // unmount must not pull focus here.
    if (refusalCode === null || liveState().refusal === null) return;
    const target = refusalCode === "signin_required" || !liveState().signedIn ? "signin" : "key";
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFocusTarget((f) => ({ target, n: (f?.n ?? 0) + 1 }));
  }, [refusalCode]);

  // On unmount: stop a pending check, and forget the refusal this panel explained, so another
  // page doesn't open with a stale error.
  useEffect(
    () => () => {
      controllerRef.current?.abort();
      clearRefusal();
    },
    [],
  );

  function focus(target: "signin" | "key") {
    setFocusTarget((f) => ({ target, n: (f?.n ?? 0) + 1 }));
  }

  // "Use live mode": the local shape check, then one POST /api/live/check. On success the input
  // is emptied and the key goes to lib/liveSession.ts (the screen then swaps in the strip).
  async function submitLive() {
    if (checking || !signedIn) return;
    const trimmedKey = key.trim();
    setShowKey(false);
    if (!trimmedKey.startsWith(KEY_PREFIX) || !HEADER_SAFE.test(trimmedKey)) {
      setLocalError(MSG_KEY_FORMAT);
      focus("key");
      return;
    }
    setLocalError(null);
    const controller = new AbortController();
    controllerRef.current = controller;
    setOwn(null);
    setAttempted(true);
    setChecking(true);
    try {
      await api.liveCheck(trimmedKey, controller.signal);
      if (controller.signal.aborted) return;
      setKey("");
      setOwn(null);
      stripFocusPending = true;
      setLiveKey(trimmedKey);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const error =
        caught instanceof ApiError ? caught : new ApiError("server", null, "Something went wrong on the server.");
      setOwn({ status: error.status, code: error.code, message: error.message, retryAfter: error.retryAfter });
      if (error.retryAfter !== null) wait.start(error.retryAfter);
      if (error.code === "key_refused") setKey("");
      if (error.code === "signin_required") focus("signin");
      else if (error.status === 401 && error.code?.startsWith("key_")) focus("key");
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setChecking(false);
      }
    }
  }

  async function onSignOut() {
    setSigningOut(true);
    setKey("");
    setOwn(null);
    const ok = await logout();
    clearAll();
    setSigningOut(false);
    setSignOutNote(ok ? null : MSG_SIGNOUT_FAILED);
    setAnnounce(ok ? "Signed out" : "");
    headingRef.current?.focus();
  }

  function onEnter(e: React.KeyboardEvent) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    void submitLive();
  }

  const describedKey = ["live-key-help", keyError ? "live-key-error" : ""].filter(Boolean).join(" ");
  const waiting = wait.remaining !== null && wait.remaining > 0;

  return (
    <div
      role="group"
      aria-labelledby="live-title"
      className="space-y-4 rounded-md border border-rule bg-surface p-4 sm:p-6"
    >
      {firstLine && <p className="text-small">{firstLine}</p>}
      <h2 id="live-title" ref={headingRef} tabIndex={-1} className="text-heading">
        Use live mode
      </h2>
      <p className="text-small text-ink-muted">
        Runs the real app with your own Anthropic API key. Requests use your Anthropic credit; a plan makes many more
        calls than an answer.
      </p>

      <div className="space-y-1">
        {signedIn ? (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            <span>Signed in as @{live.login}</span>
            <button
              type="button"
              className={textButton}
              disabled={signingOut}
              onClick={() => void onSignOut()}
            >
              {signingOut ? "Signing out..." : "Sign out"}
            </button>
          </p>
        ) : live.signIn === "unavailable" ? (
          <p className="text-small">{MSG_SIGNIN_UNAVAILABLE}</p>
        ) : (
          <>
            <a
              ref={signInRef}
              href={SIGNIN_URL}
              className={`${secondaryButton} w-full no-underline sm:w-auto`}
              aria-describedby="live-signin-help"
            >
              Sign in with GitHub
            </a>
            <p id="live-signin-help" className="text-meta text-ink-muted">
              Your GitHub account must be at least 30 days old.
            </p>
          </>
        )}
        {signInLine && !signedIn && (
          <p role="alert" className="flex items-center gap-1 text-meta text-stopped">
            <OctagonIcon size={14} />
            {signInLine}
          </p>
        )}
        {signOutNote && !signedIn && <p className="text-meta text-ink-muted">{signOutNote}</p>}
        <p className="text-meta text-ink-muted">{PRIVACY_LINE}</p>
      </div>

      <div className="space-y-1">
        <label htmlFor="live-key" className="text-label">
          Anthropic API key
        </label>
        <div className="flex gap-2">
          <input
            id="live-key"
            ref={keyRef}
            type={showKey ? "text" : "password"}
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="none"
            autoCorrect="off"
            value={key}
            disabled={!signedIn}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={onEnter}
            aria-invalid={keyError ? true : undefined}
            aria-describedby={describedKey}
            className={`${INPUT} ${keyError ? "border-stopped" : "border-line"} disabled:opacity-50`}
          />
          <button
            type="button"
            className={`${SHOW_BUTTON} disabled:opacity-50`}
            disabled={!signedIn}
            aria-label={showKey ? "Hide API key" : "Show API key"}
            onClick={() => setShowKey((v) => !v)}
          >
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
        <p id="live-key-help" className="text-meta text-ink-muted">
          {signedIn ? "" : "Sign in with GitHub first. "}Sent to the GradPath server with each request, which passes it
          to Anthropic for that request only. Never stored, logged or shown back. Kept in this tab&apos;s memory:
          reloading or closing the page clears it.
        </p>
        {keyError && (
          <p id="live-key-error" className="flex items-center gap-1 text-meta text-stopped">
            <OctagonIcon size={14} />
            {keyError}
          </p>
        )}
      </div>

      {stoppedLine && (
        <div role="alert" className="flex items-start gap-2 rounded-md border-l-4 border-stopped bg-stopped-bg p-3 text-small">
          <OctagonIcon size={16} />
          <div>
            <p>{stoppedLine}</p>
            {outcome?.retryAfter != null && (
              <RetryAfter retryAfter={outcome.retryAfter} remaining={wait.remaining} action="try again" />
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          className={`${primaryButton} w-full sm:w-auto`}
          disabled={!signedIn || checking || waiting}
          onClick={() => void submitLive()}
        >
          {checking ? "Checking..." : "Use live mode"}
        </button>
        <a href={examplesHref} className={`${textButton} text-small`}>
          No key? Browse the examples
        </a>
      </div>
      <span role="status" className="sr-only">
        {announce}
      </span>
    </div>
  );
}
