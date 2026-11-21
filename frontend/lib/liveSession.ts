"use client";

// The visitor's live-mode credentials (T-018 step 9; DESIGN.md "Live mode panel", decisions 10-12;
// always-hard area). The Anthropic key lives ONLY in this module's memory: never in
// localStorage, sessionStorage, the URL or a log, so a reload or a closed tab drops it. The
// passcode is never stored at all: POST /api/live/check exchanges it for a signed session token,
// and only that token is kept, in sessionStorage (plus module memory, so live mode still works
// when storage is blocked), until it expires (12 h) or is cleared.
// lib/api.ts reads `authHeaders()` for the model routes only; screens subscribe with
// `useLiveSession()`.

import { useSyncExternalStore } from "react";

export const TOKEN_STORAGE_KEY = "gradpath-live-token";
const TOKEN_SHAPE = /^\d{1,12}\.[0-9a-f]{64}$/;

/** Why the server last refused live credentials (fixed server text), so the panel can say so. */
export interface AuthRefusal {
  code: string;
  message: string;
}

export interface LiveState {
  hasKey: boolean;
  hasToken: boolean; // a token that hasn't expired yet
  refusal: AuthRefusal | null; // the last 401 from the server; cleared by a new key or token
}

interface StoredToken {
  token: string;
  expiresAt: number; // ms since epoch
}

let key: string | null = null;
let memoryToken: StoredToken | null = null; // same value as storage; survives blocked storage
let refusal: AuthRefusal | null = null;
const EMPTY: LiveState = { hasKey: false, hasToken: false, refusal: null };
let snapshot: LiveState = EMPTY;
const listeners = new Set<() => void>();

function readToken(): StoredToken | null {
  if (memoryToken && memoryToken.expiresAt > Date.now()) return memoryToken;
  memoryToken = null;
  try {
    const raw = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredToken>;
    const valid =
      typeof parsed.token === "string" &&
      TOKEN_SHAPE.test(parsed.token) &&
      typeof parsed.expiresAt === "number" &&
      parsed.expiresAt > Date.now();
    if (!valid) {
      window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
      return null;
    }
    memoryToken = { token: parsed.token as string, expiresAt: parsed.expiresAt as number };
    return memoryToken;
  } catch {
    return null; // storage blocked or tampered: behave as if there is no token
  }
}

// A new snapshot object only when something changed, as useSyncExternalStore requires.
function computeSnapshot(): boolean {
  const hasKey = key !== null;
  const hasToken = readToken() !== null;
  if (hasKey === snapshot.hasKey && hasToken === snapshot.hasToken && refusal === snapshot.refusal) {
    return false;
  }
  snapshot = { hasKey, hasToken, refusal };
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

/** Keep the session token from POST /api/live/check (never the passcode itself). */
export function setToken(token: string, expiresAtIso: string): void {
  const expiresAt = Date.parse(expiresAtIso);
  if (!TOKEN_SHAPE.test(token) || Number.isNaN(expiresAt)) return;
  memoryToken = { token, expiresAt };
  refusal = null;
  try {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify({ token, expiresAt }));
  } catch {
    // Storage blocked: the token can't survive a reload, which only means re-entering the passcode.
  }
  publish();
}

/** Forget the key (for example after Anthropic refused it); the token stays. */
export function clearKey(): void {
  key = null;
  publish();
}

/** Forget the token (expired or refused); the key stays. */
export function clearToken(): void {
  memoryToken = null;
  try {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // nothing stored
  }
  publish();
}

/** "Clear key and passcode": forget everything. */
export function clearAll(): void {
  key = null;
  refusal = null;
  clearToken();
  publish();
}

/** Headers for a model route: the token and the key, when held. Empty otherwise (local mode). */
export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const stored = readToken();
  if (stored) headers["X-GradPath-Token"] = stored.token;
  if (key) headers["X-Anthropic-Key"] = key;
  return headers;
}

/** React to a 401 from any request (called by lib/api.ts): drop whatever the server says is no
 * longer valid and remember why, so the live panel reopens with the right field error. */
// An unknown or missing code drops both values, so the panel always reopens and no 401 passes
// silently (screens show no error panel for a 401; they rely on the panel).
export function onAuthError(code: string | null, message = ""): void {
  refusal = { code: code ?? "unknown", message };
  if (code === "passcode_required") clearToken();
  else if (code === "key_refused" || code === "key_required") clearKey();
  else {
    key = null;
    clearToken();
  }
}

/** Forget the last refusal once the panel that explained it goes away (LivePanel unmount), so
 * another page doesn't open with a stale error. */
export function clearRefusal(): void {
  refusal = null;
  publish();
}

// The snapshot for a render: recomputed (a token may have expired since the last one) but the same
// object while nothing changed. Never notifies during render.
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

/** Current live state for a component (no values, only whether each is held). */
export function useLiveSession(): LiveState {
  return useSyncExternalStore(subscribe, currentSnapshot, () => SERVER_STATE);
}

/** Tests only: reset module state, including the stored token. */
export function resetForTests(): void {
  key = null;
  memoryToken = null;
  refusal = null;
  snapshot = EMPTY;
  try {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // nothing stored
  }
}
