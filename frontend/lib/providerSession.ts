"use client";

// The model provider picker's state (T-029 step 3; DESIGN.md "Model provider picker"; always-hard:
// where visitor data goes). One module-level store like lib/liveSession.ts: the radio choice, per
// server the typed address, the Connect result (model names) and the chosen models, and `active`,
// the last CONFIRMED setup ("Use this model" / "Use live mode"), which is what runs use. Cancel
// leaves `active` alone, so typed values survive but never change what is in force. The Claude key
// is NOT here (it stays in liveSession, memory only; decision 18).
//
// Remembered on this device (localStorage "gradpath-provider", decision 19) and nothing else: the
// choice, each server's address, the model names and "one model for both". Never a key, never
// the model list, never a posting. Read defensively: anything odd is ignored.

import { useSyncExternalStore } from "react";
import { checkAddress, DEFAULT_ADDRESS, MAX_NAME, PICKER_SERVERS, type LocalServer } from "@/lib/localModels";
import type { RelayModels } from "@/lib/relayRun";

export type Choice = "claude" | LocalServer;

export const STORAGE_KEY = "gradpath-provider";
const MAX_ADDRESS = 300;
const MAX_STORED = 12_000; // two servers' addresses and up to four names of MAX_NAME

/** One local server's draft in the dialog. `connectedBase` is the checked address the model list
 * came from; editing the address clears the connection. */
export interface ServerDraft {
  address: string;
  connectedBase: string | null;
  models: string[];
  fast: string;
  smart: string;
}

/** What is in force after a confirm. */
export type ActiveSetup =
  | { choice: "claude" }
  | { choice: LocalServer; base: string; fast: string; smart: string };

export interface ProviderState {
  choice: Choice; // the selected radio (a draft until confirmed)
  oneModel: boolean; // "Use one model for both"
  servers: Record<LocalServer, ServerDraft>;
  active: ActiveSetup | null; // the confirmed setup; null until the visitor confirms one
  confirmCount: number; // bumps on every confirm, so the strip can take focus once
  dialogOpen: boolean;
}

function freshServer(server: LocalServer): ServerDraft {
  return { address: DEFAULT_ADDRESS[server], connectedBase: null, models: [], fast: "", smart: "" };
}

function defaults(): ProviderState {
  return {
    choice: "claude",
    oneModel: true,
    servers: { ollama: freshServer("ollama"), llamacpp: freshServer("llamacpp"), lmstudio: freshServer("lmstudio") },
    active: null,
    confirmCount: 0,
    dialogOpen: false,
  };
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown, max: number): string => (typeof v === "string" && v.length <= max ? v : "");

// The remembered choice, read defensively: a stored address is re-checked (this computer only),
// strings are length-capped, anything that is not the expected shape is dropped. Only the servers
// the picker offers are read: a remembered LM Studio choice (now hidden) falls back to the default.
function loadStored(): Partial<ProviderState> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw || raw.length > MAX_STORED) return {};
    const data: unknown = JSON.parse(raw);
    if (!isRecord(data)) return {};
    const out: Partial<ProviderState> = {};
    if (data.choice === "claude") out.choice = "claude";
    const stored = PICKER_SERVERS.find((server) => server === data.choice);
    if (stored) out.choice = stored;
    if (typeof data.oneModel === "boolean") out.oneModel = data.oneModel;
    const servers = defaults().servers;
    for (const server of PICKER_SERVERS) {
      const entry = data[server];
      if (!isRecord(entry)) continue;
      const address = text(entry.address, MAX_ADDRESS);
      const checked = address ? checkAddress(address) : null;
      if (checked?.ok) servers[server].address = checked.base;
      servers[server].fast = text(entry.fast, MAX_NAME);
      servers[server].smart = text(entry.smart, MAX_NAME);
    }
    out.servers = servers;
    return out;
  } catch {
    return {};
  }
}

function persist(): void {
  try {
    const { choice, oneModel, servers } = state;
    const entries = Object.fromEntries(
      PICKER_SERVERS.map((server) => {
        const s = servers[server];
        return [server, { address: s.address, fast: s.fast, smart: s.smart }];
      }),
    );
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice, oneModel, ...entries }));
  } catch {
    // storage blocked: the choice just isn't remembered
  }
}

let state: ProviderState = defaults();
let loaded = false;
let stripFocusPending = false;
let opener: HTMLElement | null = null;
const SERVER_STATE: ProviderState = defaults();
const listeners = new Set<() => void>();

function current(): ProviderState {
  if (!loaded && typeof window !== "undefined") {
    loaded = true;
    state = { ...state, ...loadStored() };
  }
  return state;
}

function set(patch: Partial<ProviderState>): void {
  state = { ...current(), ...patch };
  listeners.forEach((listener) => listener());
}

function setServer(server: LocalServer, patch: Partial<ServerDraft>): void {
  const s = current();
  set({ servers: { ...s.servers, [server]: { ...s.servers[server], ...patch } } });
}

/** Pick a radio. Typed values of the other options are kept. */
export function setChoice(choice: Choice): void {
  set({ choice });
}

/** The visitor typed in the address field: the old connection no longer applies. */
export function setAddress(server: LocalServer, address: string): void {
  setServer(server, { address, connectedBase: null, models: [] });
}

/** A successful Connect: keep the names and preselect the remembered ones when the list has them,
 * else the first listed (DESIGN.md, "After connect"). */
export function setConnection(server: LocalServer, base: string, models: string[]): void {
  const draft = current().servers[server];
  const pick = (name: string) => (models.includes(name) ? name : (models[0] ?? ""));
  setServer(server, { connectedBase: base, models, fast: pick(draft.fast), smart: pick(draft.smart) });
}

export function setModel(server: LocalServer, tier: "fast" | "smart", name: string): void {
  setServer(server, { [tier]: name });
}

export function setOneModel(oneModel: boolean): void {
  set({ oneModel });
}

/** True when the draft for `server` has a connection and a chosen model (two if not "one model"). */
export function canConfirm(s: ProviderState, server: LocalServer): boolean {
  const d = s.servers[server];
  if (d.connectedBase === null || d.models.length === 0 || !d.models.includes(d.fast)) return false;
  return s.oneModel || d.models.includes(d.smart);
}

/** "Use this model": the draft becomes the setup in force, and is remembered on this device. */
export function confirmLocal(server: LocalServer): boolean {
  const s = current();
  if (!canConfirm(s, server)) return false;
  const d = s.servers[server];
  const smart = s.oneModel ? d.fast : d.smart;
  stripFocusPending = true;
  set({
    choice: server,
    active: { choice: server, base: d.connectedBase as string, fast: d.fast, smart },
    confirmCount: s.confirmCount + 1,
  });
  persist();
  return true;
}

/** "Use live mode" (Claude): Claude becomes the setup in force; the key itself is in liveSession. */
export function confirmClaude(): void {
  set({ choice: "claude", active: { choice: "claude" }, confirmCount: current().confirmCount + 1 });
  persist();
}

/** "Forget": clear what is remembered and reset the addresses, connections, names and "one model"
 * to defaults. The radio on screen and the setup in force stay. */
export function forget(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // nothing to clear
  }
  const fresh = defaults();
  set({ oneModel: fresh.oneModel, servers: fresh.servers });
}

/** The models a relay run answers on: null unless a local choice is confirmed with models. The
 * address was checked before it got here. Called by lib/useRelayRun.ts at the start of a run. */
export function relayModels(): RelayModels | null {
  const a = current().active;
  if (!a || a.choice === "claude" || !a.fast || !a.smart) return null;
  return { server: a.choice, base: a.base, fast: a.fast, smart: a.smart };
}

/** Open the dialog. The visitor's last confirmed choice is preselected (decision 19). */
export function openDialog(from?: HTMLElement | null): void {
  opener = from ?? (typeof document !== "undefined" ? (document.activeElement as HTMLElement | null) : null);
  const a = current().active;
  set({ dialogOpen: true, ...(a ? { choice: a.choice } : {}) });
}

export function closeDialog(): void {
  set({ dialogOpen: false });
}

/** The element that opened the dialog, to give focus back to (once). */
export function takeOpener(): HTMLElement | null {
  const el = opener;
  opener = null;
  return el;
}

/** True once after a confirm: the strip that appears takes focus and announces itself. */
export function takeStripFocus(): boolean {
  const pending = stripFocusPending;
  stripFocusPending = false;
  return pending;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The picker's state for a component (defaults on the server, the remembered values after mount). */
export function useProviderSession(): ProviderState {
  return useSyncExternalStore(subscribe, current, () => SERVER_STATE);
}

/** Tests only: back to defaults, nothing loaded from storage until the next read. */
export function resetProviderForTests(): void {
  state = defaults();
  loaded = false;
  stripFocusPending = false;
  opener = null;
}
