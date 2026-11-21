"use client";

// Live mode entry (DESIGN.md "Live mode panel", decisions 10-12; always-hard area). LivePanel
// replaces the submit row on Ask/Job/Plan (and sits inside the resume import on Profile) while the
// server is in live mode and this tab has no key and token; LiveStrip is what shows once both are
// held. The passcode and key live ONLY in this panel's input state: they go to api.liveCheck, then
// the token and key go to lib/liveSession.ts and the inputs are emptied. Never put them in a URL,
// storage, a log, an error text or a prop. Not a <form> (no submit event, fewer password-manager
// prompts); Enter in either field runs "Use live mode". With a remembered token (after a reload)
// only the key is asked and checked locally: the first real request verifies it (the token is
// bound to the key it was issued with, so another key comes back as a 401 passcode_required).

import { useEffect, useRef, useState } from "react";
import { OctagonIcon, KeyIcon } from "@/components/icons";
import { primaryButton, textButton } from "@/components/buttonStyles";
import { api, ApiError } from "@/lib/api";
import {
  clearAll,
  clearRefusal,
  clearToken,
  liveState,
  setKey as setLiveKey,
  setToken,
  useLiveSession,
} from "@/lib/liveSession";
import { RetryAfter } from "@/components/RetryAfter";
import { useCountdown } from "@/lib/useCountdown";

export const KEY_PREFIX = "sk-ant-";
const MSG_KEY_FORMAT = "This doesn't look like an Anthropic API key: they start with sk-ant-.";
const MSG_PASSCODE_EMPTY = "Enter the passcode.";
const MSG_PASSCODE_CHARS = "A passcode uses only letters, digits and keyboard symbols, with no spaces.";
// Header values must be printable ASCII: anything else makes fetch throw before sending.
const HEADER_SAFE = /^[!-~]+$/;
const MSG_PASSCODE_WRONG = "That passcode didn't work. Check it with the person who gave it to you.";
const MSG_PASSCODE_BOUND = "The remembered passcode no longer works with this key (it works only with the key first used with it, until the server restarts). Enter the passcode again.";
const MSG_KEY_REFUSED = "Anthropic refused this API key. Check that it is active and has credit.";
const INPUT = "h-11 min-w-0 flex-1 rounded-md border bg-surface px-3 text-body sm:h-10";
const SHOW_BUTTON =
  "inline-flex h-11 items-center justify-center rounded-md border border-line bg-surface px-4 text-label text-ink transition-colors duration-150 hover:bg-sunken sm:h-10";

// One-shot hand-offs between the panel and the strip, which never exist together. They hold no
// secret: only "move focus here once".
let stripFocusPending = false;
let panelClearedPending = false;

type Field = "passcode" | "key";
interface Outcome {
  code: string | null;
  message: string;
  retryAfter?: number | null;
}

/** The collapsed state: key held (DESIGN.md, "Key set"). Used by Assistant, JobAnalysisView, PlanView. */
export function LiveStrip() {
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
          Live mode on. Your key is in this tab&apos;s memory only and clears on reload; the passcode is remembered
          for this tab for up to 12 hours.
        </span>
      </p>
      <button
        type="button"
        className={textButton}
        onClick={() => {
          panelClearedPending = true;
          clearAll();
        }}
      >
        Clear key and passcode
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
  const [passcode, setPasscode] = useState("");
  const [key, setKey] = useState("");
  const [showPasscode, setShowPasscode] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [local, setLocal] = useState<{ passcode?: string; key?: string }>({});
  const [checking, setChecking] = useState(false);
  // The last answer of this panel's own check; while null, a refusal recorded by lib/api.ts (a
  // model request's 401) is what the panel explains.
  const [own, setOwn] = useState<Outcome | null>(null);
  const [attempted, setAttempted] = useState(false); // once this panel has checked, a stale refusal is history
  const [focusField, setFocusField] = useState<{ field: Field; n: number } | null>(null);
  const [announce, setAnnounce] = useState("");
  const lockWait = useCountdown();

  const headingRef = useRef<HTMLHeadingElement>(null);
  const passcodeRef = useRef<HTMLInputElement>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const keyOnly = live.hasToken; // a remembered passcode: ask for the key only
  const outcome: Outcome | null = own ?? (attempted ? null : live.refusal);
  const fromRefusal = own === null && !attempted && live.refusal !== null;

  // What each field shows: local checks first, then the server's answer by code.
  let passcodeError = local.passcode ?? null;
  let keyError = local.key ?? null;
  let stoppedLine: string | null = null;
  if (outcome && !passcodeError && !keyError) {
    if (outcome.code === "passcode_required") {
      passcodeError = fromRefusal ? MSG_PASSCODE_BOUND : MSG_PASSCODE_WRONG;
    } else if (outcome.code === "key_refused") {
      keyError = MSG_KEY_REFUSED;
    } else if (outcome.code === "key_required") {
      keyError = outcome.message;
    } else {
      stoppedLine = outcome.message;
    }
  }

  // Focus the field a refusal or a failed check points at.
  useEffect(() => {
    if (focusField?.field === "passcode") passcodeRef.current?.focus();
    else if (focusField?.field === "key") keyRef.current?.focus();
  }, [focusField]);

  // After "Clear key and passcode": focus the heading and say so.
  useEffect(() => {
    if (!panelClearedPending) return;
    panelClearedPending = false;
    headingRef.current?.focus();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnnounce("Key cleared");
  }, []);

  // A model request's 401 reopened this panel: focus the field it is about.
  const refusalCode = live.refusal?.code ?? null;
  useEffect(() => {
    // Read the store, not this render: a refusal the previous page's panel already cleared on
    // unmount must not pull focus here.
    if (refusalCode === null || liveState().refusal === null) return;
    const field: Field = refusalCode === "passcode_required" ? "passcode" : "key";
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFocusField((f) => ({ field, n: (f?.n ?? 0) + 1 }));
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

  function focus(field: Field) {
    setFocusField((f) => ({ field, n: (f?.n ?? 0) + 1 }));
  }

  // "Use live mode": local checks, then (with no remembered token) one POST /api/live/check. On
  // success the inputs are emptied and the token and key go to lib/liveSession.ts.
  async function submitLive() {
    if (checking) return;
    const trimmedKey = key.trim();
    const trimmedPasscode = passcode.trim();
    const errors: { passcode?: string; key?: string } = {};
    if (!keyOnly && trimmedPasscode === "") errors.passcode = MSG_PASSCODE_EMPTY;
    else if (!keyOnly && !HEADER_SAFE.test(trimmedPasscode)) errors.passcode = MSG_PASSCODE_CHARS;
    if (!trimmedKey.startsWith(KEY_PREFIX) || !HEADER_SAFE.test(trimmedKey)) errors.key = MSG_KEY_FORMAT;
    setLocal(errors);
    setShowPasscode(false);
    setShowKey(false);
    if (errors.passcode || errors.key) {
      focus(errors.passcode ? "passcode" : "key");
      return;
    }
    if (keyOnly) {
      finish(trimmedKey);
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setOwn(null);
    setAttempted(true);
    setChecking(true);
    try {
      const result = await api.liveCheck(trimmedPasscode, trimmedKey, controller.signal);
      if (controller.signal.aborted) return;
      setToken(result.token, result.expires_at);
      finish(trimmedKey);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const error =
        caught instanceof ApiError ? caught : new ApiError("server", null, "Something went wrong on the server.");
      setOwn({ code: error.code, message: error.message, retryAfter: error.retryAfter });
      if (error.code === "passcode_locked") lockWait.start(error.retryAfter);
      if (error.code === "key_refused") setKey("");
      if (error.code === "passcode_required") focus("passcode");
      else if (error.code === "key_required" || error.code === "key_refused") focus("key");
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setChecking(false);
      }
    }
  }

  // Empty the inputs, then hand the key to memory; the screen swaps this panel for the strip.
  function finish(value: string) {
    setKey("");
    setPasscode("");
    setLocal({});
    setOwn(null);
    stripFocusPending = true;
    setLiveKey(value);
  }

  function onEnter(e: React.KeyboardEvent) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    void submitLive();
  }

  const describedPasscode = ["live-passcode-help", passcodeError ? "live-passcode-error" : ""].filter(Boolean).join(" ");
  const describedKey = ["live-key-help", keyError ? "live-key-error" : ""].filter(Boolean).join(" ");

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

      {keyOnly ? (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
          <span>Passcode remembered for this tab.</span>
          <button
            type="button"
            className={textButton}
            onClick={() => {
              clearToken();
              focus("passcode");
            }}
          >
            Use a different passcode
          </button>
        </p>
      ) : (
        <div className="space-y-1">
          <label htmlFor="live-passcode" className="text-label">
            Passcode
          </label>
          <div className="flex gap-2">
            <input
              id="live-passcode"
              ref={passcodeRef}
              type={showPasscode ? "text" : "password"}
              autoComplete="off"
              spellCheck={false}
              autoCapitalize="none"
              autoCorrect="off"
              value={passcode}
              onChange={(e) => setPasscode(e.target.value)}
              onKeyDown={onEnter}
              aria-invalid={passcodeError ? true : undefined}
              aria-describedby={describedPasscode}
              className={`${INPUT} ${passcodeError ? "border-stopped" : "border-line"}`}
            />
            <button
              type="button"
              className={SHOW_BUTTON}
              aria-label={showPasscode ? "Hide passcode" : "Show passcode"}
              onClick={() => setShowPasscode((v) => !v)}
            >
              {showPasscode ? "Hide" : "Show"}
            </button>
          </div>
          <p id="live-passcode-help" className="text-meta text-ink-muted">
            From the site owner.
          </p>
          {passcodeError && (
            <p id="live-passcode-error" className="flex items-center gap-1 text-meta text-stopped">
              <OctagonIcon size={14} />
              {passcodeError}
            </p>
          )}
        </div>
      )}

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
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={onEnter}
            aria-invalid={keyError ? true : undefined}
            aria-describedby={describedKey}
            className={`${INPUT} ${keyError ? "border-stopped" : "border-line"}`}
          />
          <button
            type="button"
            className={SHOW_BUTTON}
            aria-label={showKey ? "Hide API key" : "Show API key"}
            onClick={() => setShowKey((v) => !v)}
          >
            {showKey ? "Hide" : "Show"}
          </button>
        </div>
        <p id="live-key-help" className="text-meta text-ink-muted">
          Sent to the GradPath server with each request, which passes it to Anthropic for that request only. Never
          stored, logged or shown back. Kept in this tab&apos;s memory: reloading or closing the page clears it.
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
            {outcome?.code === "passcode_locked" && (
              <RetryAfter retryAfter={outcome.retryAfter ?? null} remaining={lockWait.remaining} action="try again" />
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          className={`${primaryButton} w-full sm:w-auto`}
          disabled={checking || (lockWait.remaining !== null && lockWait.remaining > 0)}
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
