"use client";

// The visitor's live-mode state (T-018 step 9, T-026; DESIGN.md "Live mode panel"; always-hard
// area). Two things: the Anthropic key, which lives ONLY in this module's memory (never in
// localStorage, sessionStorage, the URL or a log, so a reload or a closed tab drops it), and
// whether the visitor is signed in with GitHub. The sign-in itself is an HttpOnly cookie the
// browser sends on its own; this module only mirrors GET /api/auth/me (login and expiry), loaded
// by components/SignInNotice.tsx. lib/api.ts reads `authHeaders()` for the model routes only;
// screens subscribe with `useLiveSession()`.

import { useSyncExternalStore } from "react";

/** Why the server last refused live credentials (fixed server text), so the panel can say so. */
export interface AuthRefusal {
  code: string;
  message: string;
}

/** "unknown" until /api/auth/me answers; "unavailable" when it 404s (not a live-mode server). */
export type SignInStatus = "unknown" | "signed_out" | "signed_in" | "unavailable";

export interface LiveState {
  hasKey: boolean;
  signIn: SignInStatus;
  signedIn: boolean; // signIn === "signed_in" and the sign-in hasn't expired yet
  login: string | null; // the GitHub username while signed in
  refusal: AuthRefusal | null; // the last 401 from the server; cleared by a new key or sign-in
}

interface SignIn {
  status: SignInStatus;
  login: string | null;
  expiresAt: number | null; // ms since epoch
}

// GitHub usernames: letters, digits and single hyphens, at most 39 characters.
const LOGIN_SHAPE = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;

let key: string | null = null;
let signIn: SignIn = { status: "unknown", login: null, expiresAt: null };
let refusal: AuthRefusal | null = null;
const EMPTY: LiveState = { hasKey: false, signIn: "unknown", signedIn: false, login: null, refusal: null };
let snapshot: LiveState = EMPTY;
const listeners = new Set<() => void>();

// An expired sign-in reads as signed out, without waiting for the server's 401.
function currentSignIn(): SignIn {
  if (signIn.status === "signed_in" && signIn.expiresAt !== null && signIn.expiresAt <= Date.now()) {
    signIn = { status: "signed_out", login: null, expiresAt: null };
  }
  return signIn;
}

// A new snapshot object only when something changed, as useSyncExternalStore requires.
function computeSnapshot(): boolean {
  const hasKey = key !== null;
  const current = currentSignIn();
  const signedIn = current.status === "signed_in";
  if (
    hasKey === snapshot.hasKey &&
    current.status === snapshot.signIn &&
    current.login === snapshot.login &&
    refusal === snapshot.refusal
  ) {
    return false;
  }
  snapshot = { hasKey, signIn: current.status, signedIn, login: current.login, refusal };
  return true;
}

function publish(): void {
  if (computeSnapshot()) listeners.forEach((listener) => listener());
}

/** Keep the visitor's key in memory for this tab (after a successful live check). */
export function setKey(value: string): void {
  key = value.trim() || null;
  refusal = null;
  publish();
}

/** Forget the key (for example after Anthropic refused it); the sign-in stays. */
export function clearKey(): void {
  key = null;
  publish();
}

/** Mirror GET /api/auth/me (called by SignInNotice). A malformed login counts as signed out. */
export function setSignIn(signedIn: boolean, login: string | null, expiresAtIso: string | null): void {
  const expiresAt = expiresAtIso ? Date.parse(expiresAtIso) : Number.NaN;
  if (signedIn && typeof login === "string" && LOGIN_SHAPE.test(login)) {
    signIn = { status: "signed_in", login, expiresAt: Number.isNaN(expiresAt) ? null : expiresAt };
    if (refusal?.code === "signin_required") refusal = null;
  } else {
    signIn = { status: "signed_out", login: null, expiresAt: null };
  }
  publish();
}

/** /api/auth/me answered 404: this server has no sign-in (not live mode). */
export function setSignInUnavailable(): void {
  signIn = { status: "unavailable", login: null, expiresAt: null };
  publish();
}

/** Signed out (after "Sign out" or a 401 signin_required); the key stays unless cleared too. */
export function clearSignIn(): void {
  signIn = { status: "signed_out", login: null, expiresAt: null };
  publish();
}

/** "Sign out" in the strip or panel: forget the key and the sign-in state. */
export function clearAll(): void {
  key = null;
  refusal = null;
  clearSignIn();
}

/** Headers for a model route: the key, when held. Empty otherwise (local mode). The sign-in
 * cookie goes with every same-origin request on its own. */
export function authHeaders(): Record<string, string> {
  return key ? { "X-Anthropic-Key": key } : {};
}

/** React to a 401 from any request (called by lib/api.ts): drop whatever the server says is no
 * longer valid and remember why, so the live panel reopens with the right message. */
// An unknown or missing code drops both, so the panel always reopens and no 401 passes silently
// (screens show no error panel for a 401; they rely on the panel).
export function onAuthError(code: string | null, message = ""): void {
  refusal = { code: code ?? "unknown", message };
  if (code === "signin_required") clearSignIn();
  else if (code !== null && code.startsWith("key_")) clearKey();
  else {
    key = null;
    clearSignIn();
  }
}

/** Forget the last refusal once the panel that explained it goes away (LivePanel unmount), so
 * another page doesn't open with a stale error. */
export function clearRefusal(): void {
  refusal = null;
  publish();
}

// The snapshot for a render: recomputed (the sign-in may have expired since the last one) but the
// same object while nothing changed. Never notifies during render.
function currentSnapshot(): LiveState {
  computeSnapshot();
  return snapshot;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const SERVER_STATE: LiveState = EMPTY;

/** The live state right now, outside a render (LivePanel's effects: a render's value can be
 * stale when one page's panel unmounts as the next one mounts). */
export function liveState(): LiveState {
  return currentSnapshot();
}

/** Current live state for a component (never the key itself, only whether it is held). */
export function useLiveSession(): LiveState {
  return useSyncExternalStore(subscribe, currentSnapshot, () => SERVER_STATE);
}

/** Tests only: reset module state. */
export function resetForTests(): void {
  key = null;
  signIn = { status: "unknown", login: null, expiresAt: null };
  refusal = null;
  snapshot = EMPTY;
}
