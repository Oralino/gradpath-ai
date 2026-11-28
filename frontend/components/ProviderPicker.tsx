"use client";

// The model provider picker (T-029 step 3; DESIGN.md "Model provider picker"; always-hard: where
// visitor data goes). A native modal <dialog> opened with showModal(): sign-in row (live mode),
// the radio group, the chosen option's block, footer. Mounted once per model screen (Assistant,
// JobAnalysisView, PlanView) and opened by components/ProviderSetup.tsx. Typed values live in
// lib/providerSession.ts (and the Claude key in useLiveForm), so they survive close and reopen.
// Connect is the only call to the visitor's local server before a run, and only from the click
// (Chrome's local-network prompt); a backdrop click never closes; Escape, x and Cancel all mean
// Cancel and keep the last confirmed setup in force. The dialog's content is rendered only while it
// is open (nothing hidden for assistive tech, no duplicate ids); the state above it persists.

import { useEffect, useRef, useState } from "react";
import { CheckIcon, CloseIcon, TriangleIcon, OctagonIcon } from "@/components/icons";
import { LiveKeyBlock, LiveSignInRow, LiveStoppedLine, useLiveForm } from "@/components/LivePanel";
import { primaryButton, secondaryButton, textButton } from "@/components/buttonStyles";
import {
  checkAddress,
  DEFAULT_ADDRESS,
  listModels,
  LocalModelError,
  modelLabel,
  PICKER_SERVERS,
  SERVER_NAMES,
  shortAddress,
  type LocalServer,
} from "@/lib/localModels";
import {
  canConfirm,
  closeDialog,
  confirmClaude,
  confirmLocal,
  forget,
  setAddress,
  setChoice,
  setConnection,
  setModel,
  setOneModel,
  takeOpener,
  useProviderSession,
  type Choice,
} from "@/lib/providerSession";

export const MSG_NOT_LOCAL = "Only a server on this computer works here: use localhost, 127.0.0.1 or [::1], with any port.";
export const MSG_MALFORMED = "Enter a full address, like http://localhost:11434.";
const INPUT = "h-11 min-w-0 flex-1 basis-56 rounded-md border bg-surface px-3 text-body sm:h-10";
const BUTTON =
  "inline-flex h-11 shrink-0 items-center justify-center rounded-md border border-line bg-surface px-4 text-label text-ink transition-colors duration-150 hover:bg-sunken disabled:opacity-50 sm:h-10";
const SELECT =
  "h-11 w-full rounded-md border border-line bg-surface px-3 text-body sm:h-10 sm:w-auto sm:min-w-64";
const ROW =
  "flex items-start gap-3 rounded-md border border-rule bg-surface p-3 hover:border-line has-checked:border-ink";
const CODE = "break-words rounded-sm bg-sunken px-1 font-mono text-small";
const SIZE_HINT = "A model of 7B or larger is recommended: smaller ones often return replies GradPath can't read.";
const PRIVACY =
  "Your posting and profile go from this page to your own server and to GradPath's server, which runs search and the workflow. Your model's replies go to GradPath's server, which checks them. Search still uses GradPath's source index.";

const HINT: Record<LocalServer, string> = {
  ollama: "Ollama's address on this computer. Default http://localhost:11434.",
  llamacpp: "llama-server's address on this computer, ending in /v1. Default http://localhost:9931/v1.",
  lmstudio:
    "LM Studio's address on this computer, ending in /v1. Use the port LM Studio prints when its server starts (often 1234 or 1235).",
};
const LOCAL_HINT = "Free. Runs on your machine; slower, quality depends on model.";
const OPTION_LABEL: Record<LocalServer, string> = {
  ollama: "Ollama on this computer",
  llamacpp: "llama.cpp on this computer",
  lmstudio: "LM Studio on this computer",
};
// The "connected, no models" line per server.
const NO_MODELS: Record<LocalServer, string> = {
  ollama:
    "Connected, but Ollama has no models installed. Install one (for example `ollama pull llama3.1:8b`), then Connect again.",
  llamacpp: "Connected, but llama-server listed no model. Start it with -m and a model file, then Connect again.",
  lmstudio: "Connected, but LM Studio has no models downloaded. Download one in LM Studio, then Connect again.",
};

type Note = { server: LocalServer; kind: "unreachable" | "not_server" | "cancelled" | "forgotten"; address: string };

/** The picker dialog. `mode` "local" is the server's local mode: no sign-in, and the first option
 * is the server's own model instead of Claude. `firstLine` sits at the top (Plan's note about a
 * run from before a reload). */
export function ProviderPicker({ mode, firstLine }: { mode: "live" | "local"; firstLine?: string | null }) {
  const provider = useProviderSession();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const addressRef = useRef<HTMLInputElement>(null);
  const connectButtonRef = useRef<HTMLButtonElement>(null);
  const connectRef = useRef<AbortController | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const [addressError, setAddressError] = useState<{ server: LocalServer; text: string } | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [origin, setOrigin] = useState("");
  const liveMode = mode === "live";

  // Closing for a confirm: close the dialog first, so the strip that appears can take focus.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const signInRef = useRef<HTMLAnchorElement>(null);
  const keyRef = useRef<HTMLInputElement>(null);
  const form = useLiveForm({
    headingRef,
    signInRef,
    keyRef,
    consumeCleared: false,
    onSuccess: () => {
      closeNow();
      confirmClaude();
    },
  });

  function closeNow() {
    dialogRef.current?.close();
    closeDialog();
  }

  // Cancel, x and Escape: abort a pending Connect or key check, keep the setup in force.
  function cancel() {
    connectRef.current?.abort();
    connectRef.current = null;
    setConnecting(false);
    form.abortCheck();
    closeNow();
    const opener = takeOpener();
    if (opener?.isConnected) opener.focus();
  }

  // The store says open or closed; the element follows. On open the checked radio takes focus
  // (never the close button), as DESIGN.md "Focus on open" says.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (provider.dialogOpen && !dialog.open) {
      dialog.showModal();
      dialog.querySelector<HTMLInputElement>('input[name="provider"]:checked')?.focus();
    } else if (!provider.dialogOpen && dialog.open) {
      dialog.close();
    }
  }, [provider.dialogOpen]);

  // When a Connect ends the disabled button is enabled again: put focus back on it ("focus stays on
  // Connect"). Done here, after the render, because a disabled button can't take focus.
  const wasConnecting = useRef(false);
  useEffect(() => {
    if (wasConnecting.current && !connecting) connectButtonRef.current?.focus();
    wasConnecting.current = connecting;
  }, [connecting]);

  // This site's address for the setup help; read after mount so server and client HTML match.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOrigin(window.location.origin);
  }, []);

  // A Connect still waiting when the screen goes away is dropped, and the next screen starts closed.
  useEffect(
    () => () => {
      connectRef.current?.abort();
      closeDialog();
    },
    [],
  );

  const choice = provider.choice;
  const server: LocalServer | null = choice === "claude" ? null : choice;
  const draft = server ? provider.servers[server] : null;
  const name = server ? SERVER_NAMES[server] : "";
  const connected = draft !== null && draft.connectedBase !== null;
  const shownNote = note && note.server === server ? note : null;
  const shownAddressError = addressError && addressError.server === server ? addressError.text : null;

  function pick(next: Choice) {
    setChoice(next);
  }

  // Connect: check the address, then the one call to the local server (this click is what Chrome's
  // local-network prompt attaches to). Cancel (the text button) stops only this.
  async function connect() {
    if (connecting || !server || !draft) return;
    setNote(null);
    const checked = checkAddress(draft.address);
    if (!checked.ok) {
      setAddressError({ server, text: checked.error === "not_local" ? MSG_NOT_LOCAL : MSG_MALFORMED });
      addressRef.current?.focus();
      return;
    }
    setAddressError(null);
    const controller = new AbortController();
    connectRef.current = controller;
    setConnecting(true);
    try {
      const models = await listModels(server, checked.base, controller.signal);
      if (controller.signal.aborted) return;
      setConnection(server, checked.base, models);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const kind = caught instanceof LocalModelError ? caught.kind : "unreachable";
      const address = shortAddress(checked.base);
      if (kind === "not_server" || kind === "model_error") {
        setNote({ server, kind: "not_server", address });
      } else {
        setNote({ server, kind: "unreachable", address });
        setHelpOpen(true);
      }
    } finally {
      if (connectRef.current === controller) {
        connectRef.current = null;
        setConnecting(false);
      }
    }
  }

  function cancelConnect() {
    connectRef.current?.abort();
    connectRef.current = null;
    setConnecting(false);
    if (server) setNote({ server, kind: "cancelled", address: "" });
  }

  function onAddress(value: string) {
    if (!server) return;
    setAddress(server, value);
    setNote(null);
    setAddressError(null);
  }

  function confirmModel() {
    if (!server) return;
    if (!canConfirm(provider, server)) return;
    closeNow();
    confirmLocal(server);
  }

  // Claude: a key typed here is checked first; with a key already held and the field empty, the
  // click just makes Claude the setup in force again (decision 18: switching back is one click).
  function confirmClaudeChoice() {
    if (!liveMode) {
      closeNow();
      confirmClaude();
    } else if (form.key.trim() === "" && form.live.hasKey && form.signedIn) {
      closeNow();
      confirmClaude();
    } else {
      void form.submitLive();
    }
  }

  async function copyOrigin() {
    try {
      await navigator.clipboard.writeText(origin);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard blocked: the address is on screen to copy by hand
    }
  }

  function doForget() {
    forget();
    setNote(null);
    setAddressError(null);
    if (server) setNote({ server, kind: "forgotten", address: "" });
  }

  const claudeLabel = liveMode ? "Claude (your API key)" : "This server's model (local mode)";
  const claudeHint = liveMode
    ? "Fastest and most reliable. Uses your Anthropic credit."
    : "Uses the model this server is set up with. Nothing leaves this server's own setup.";
  const primaryLabel = choice === "claude" && liveMode ? (form.checking ? "Checking..." : "Use live mode") : "Use this model";
  const primaryDisabled =
    choice === "claude"
      ? liveMode && (!form.signedIn || form.checking || form.waiting)
      : server === null || !canConfirm(provider, server);

  const radios: { value: Choice; label: string; hint: string }[] = [
    { value: "claude", label: claudeLabel, hint: claudeHint },
    ...PICKER_SERVERS.map((s) => ({ value: s, label: OPTION_LABEL[s], hint: LOCAL_HINT })),
  ];

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="live-title"
      className="m-auto max-h-[90vh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto rounded-md border border-rule bg-surface p-4 text-ink backdrop:bg-black/60 sm:p-6"
      onCancel={(e) => {
        e.preventDefault();
        cancel();
      }}
      onClose={() => closeDialog()}
    >
      {provider.dialogOpen && (
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <h2 id="live-title" ref={headingRef} tabIndex={-1} className="text-heading">
            Use live mode
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={cancel}
            className="inline-flex size-11 items-center justify-center rounded-md text-ink-muted hover:bg-sunken sm:size-9"
          >
            <CloseIcon />
          </button>
        </div>
        <p className="text-small text-ink-muted">
          {liveMode
            ? "Runs the real app after you sign in with GitHub. Answers come from Claude with your own API key, or from a model running on this computer."
            : "Answers come from this server's own model, or from a model running on this computer."}
        </p>
        {firstLine && <p className="text-small">{firstLine}</p>}

        {liveMode && <LiveSignInRow form={form} signInRef={signInRef} />}

        <fieldset className="space-y-2">
          <legend className="mb-2 text-label">How answers are generated</legend>
          {radios.map((r) => (
            <label key={r.value} className={ROW}>
              <input
                type="radio"
                name="provider"
                value={r.value}
                checked={choice === r.value}
                onChange={() => pick(r.value)}
                className="mt-0.5 size-5 shrink-0 accent-ink"
              />
              <span className="min-w-0">
                <span className="block text-label">{r.label}</span>
                <span className="block text-small text-ink-muted">{r.hint}</span>
              </span>
            </label>
          ))}
          <label className={`${ROW} text-ink-muted`}>
            <input type="radio" name="provider" value="browser" disabled className="mt-0.5 size-5 shrink-0" />
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2 text-label">
                Model in your browser
                <span className="inline-flex items-center rounded-sm border border-neutral bg-neutral-bg px-2 py-0.5 text-label text-neutral">
                  Coming soon
                </span>
              </span>
              <span className="block text-small">No install needed. Not available yet.</span>
            </span>
          </label>
        </fieldset>

        {choice === "claude" && liveMode && (
          <div className="space-y-3">
            {form.live.hasKey && (
              <p className="text-meta text-ink-muted">
                A key is already held in this tab. Leave the field empty to keep it.
              </p>
            )}
            <LiveKeyBlock form={form} keyRef={keyRef} />
          </div>
        )}

        {server && draft && (
          <div className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="provider-address" className="text-label">
                Server address
              </label>
              <div className="flex flex-wrap gap-2">
                <input
                  id="provider-address"
                  ref={addressRef}
                  type="text"
                  inputMode="url"
                  autoComplete="off"
                  spellCheck={false}
                  autoCapitalize="none"
                  autoCorrect="off"
                  value={draft.address}
                  onChange={(e) => onAddress(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    e.preventDefault();
                    void connect();
                  }}
                  aria-invalid={shownAddressError ? true : undefined}
                  aria-describedby={`provider-address-help${shownAddressError ? " provider-address-error" : ""}`}
                  className={`${INPUT} ${shownAddressError ? "border-stopped" : "border-line"}`}
                />
                <button ref={connectButtonRef} type="button" className={BUTTON} disabled={connecting} onClick={() => void connect()}>
                  {connecting ? "Connecting..." : "Connect"}
                </button>
                {connecting && (
                  <button type="button" className={`${textButton} text-small`} onClick={cancelConnect}>
                    Cancel
                  </button>
                )}
              </div>
              <p id="provider-address-help" className="text-meta text-ink-muted">
                {HINT[server]}
                {draft.address !== DEFAULT_ADDRESS[server] && (
                  <>
                    {" "}
                    <button type="button" className={textButton} onClick={() => onAddress(DEFAULT_ADDRESS[server])}>
                      Use the default
                    </button>
                  </>
                )}
              </p>
              {shownAddressError && (
                <p id="provider-address-error" className="flex items-center gap-1 text-meta text-stopped">
                  <OctagonIcon size={14} />
                  {shownAddressError}
                </p>
              )}
              {connecting && (
                <p className="text-meta text-ink-muted">
                  Waiting for {name} at {shortAddress(checkedBase(draft.address))}. If Chrome asks to let this site
                  access apps and services on this device, choose Allow.
                </p>
              )}
            </div>

            <div role="status">
              {!connecting && connected && draft.models.length > 0 && (
                <p className="flex items-center gap-1 text-small text-positive">
                  <CheckIcon size={14} />
                  Connected to {name}: {draft.models.length} {draft.models.length === 1 ? "model" : "models"}.
                </p>
              )}
              {!connecting && connected && draft.models.length === 0 && (
                <p className="flex items-start gap-1 text-small text-caution">
                  <TriangleIcon size={14} />
                  <span>
                    {NO_MODELS[server]}
                  </span>
                </p>
              )}
              {shownNote?.kind === "cancelled" && <p className="text-meta text-ink-muted">Connection cancelled.</p>}
              {shownNote?.kind === "forgotten" && <p className="text-meta text-ink-muted">Forgotten on this device</p>}
              {copied && <span className="sr-only">Address copied</span>}
            </div>

            {shownNote?.kind === "unreachable" && (
              <div role="alert" className="flex items-start gap-2 rounded-md border-l-4 border-stopped bg-stopped-bg p-3 text-small">
                <OctagonIcon size={16} />
                <div className="space-y-1">
                  <p>
                    Can&apos;t reach {name} at {shownNote.address}. The browser can&apos;t tell why, so check:
                  </p>
                  <ul className="list-disc pl-5">
                    <li>It is running.</li>
                    <li>The address and port are right.</li>
                    <li>It allows this site (see Setup help).</li>
                    <li>You chose Allow when Chrome asked about apps on this device.</li>
                  </ul>
                </div>
              </div>
            )}
            {shownNote?.kind === "not_server" && (
              <div role="alert" className="flex items-start gap-2 rounded-md border-l-4 border-stopped bg-stopped-bg p-3 text-small">
                <OctagonIcon size={16} />
                <p>
                  Something answered at {shownNote.address}, but not like {name}. Check the address
                  {server === "ollama" ? "" : `; ${name}'s ends in /v1`}.
                </p>
              </div>
            )}

            {connected && draft.models.length > 0 && (
              <div className="space-y-3">
                <label className="flex items-center gap-2 text-label">
                  <input
                    type="checkbox"
                    checked={provider.oneModel}
                    onChange={(e) => setOneModel(e.target.checked)}
                    className="size-5 accent-ink"
                  />
                  Use one model for both
                </label>
                {provider.oneModel ? (
                  <ModelSelect
                    id="provider-model"
                    label="Model"
                    value={draft.fast}
                    models={draft.models}
                    help={SIZE_HINT}
                    onChange={(v) => {
                      setModel(server, "fast", v);
                      setModel(server, "smart", v);
                    }}
                  />
                ) : (
                  <>
                    <ModelSelect
                      id="provider-model-fast"
                      label="Fast model"
                      value={draft.fast}
                      models={draft.models}
                      help="Reads the request and the posting."
                      onChange={(v) => setModel(server, "fast", v)}
                    />
                    <ModelSelect
                      id="provider-model-smart"
                      label="Smart model"
                      value={draft.smart}
                      models={draft.models}
                      help="Writes and checks the plan."
                      onChange={(v) => setModel(server, "smart", v)}
                    />
                    <p className="text-meta text-ink-muted">{SIZE_HINT}</p>
                  </>
                )}
              </div>
            )}

            <p className="text-meta text-ink-muted">
              Address and model names are remembered on this device (they aren&apos;t secret; a llama.cpp name is
              the model file&apos;s path).{" "}
              <button type="button" className={textButton} onClick={doForget}>
                Forget
              </button>
            </p>

            <details open={helpOpen} onToggle={(e) => setHelpOpen(e.currentTarget.open)}>
              <summary className="cursor-pointer text-label text-link">Setup help for {name}</summary>
              <div className="mt-2 space-y-2 text-small">
                {server === "ollama" ? (
                  <ol className="list-decimal space-y-2 pl-5">
                    <li>Quit Ollama (its tray or menu-bar icon, then Quit).</li>
                    <li className="space-y-1">
                      <span className="block">
                        Set the user environment variable <code className={CODE}>OLLAMA_ORIGINS</code> to this
                        site&apos;s address, exactly:
                      </span>
                      <span className="flex flex-wrap items-center gap-2">
                        <code className="min-w-0 break-all rounded-md bg-sunken px-3 py-2 text-small">{origin}</code>
                        <button type="button" className={BUTTON} onClick={() => void copyOrigin()}>
                          {copied ? "Copied" : "Copy"}
                        </button>
                      </span>
                      <span className="block">
                        Windows: Settings, search &ldquo;environment variables&rdquo;, &ldquo;Edit environment
                        variables for your account&rdquo;, New. macOS:{" "}
                        <code className={CODE}>{`launchctl setenv OLLAMA_ORIGINS "${origin}"`}</code>
                      </span>
                    </li>
                    <li>Start Ollama again, then Connect.</li>
                  </ol>
                ) : server === "llamacpp" ? (
                  <ol className="list-decimal space-y-2 pl-5">
                    <li className="space-y-1">
                      <span className="block">
                        Start llama-server with your model, a long enough context, thinking off and this site
                        allowed:
                      </span>
                      <code className={`block ${CODE}`}>
                        {`llama-server -m <model.gguf> -c 32768 --reasoning off --cors-origins ${origin}`}
                      </code>
                      <span className="flex flex-wrap items-center gap-2">
                        <span>This site&apos;s address:</span>
                        <code className="min-w-0 break-all rounded-md bg-sunken px-3 py-2 text-small">{origin}</code>
                        <button type="button" className={BUTTON} onClick={() => void copyOrigin()}>
                          {copied ? "Copied" : "Copy"}
                        </button>
                      </span>
                    </li>
                    <li>
                      Always set <code className={CODE}>--cors-origins</code>: without it llama-server lets any website
                      you visit use your model and read its replies.
                    </li>
                    <li>Then Connect, using the port llama-server prints when it starts.</li>
                  </ol>
                ) : (
                  <p>
                    Start the server with CORS on: <code className={CODE}>lms server start --cors</code>, or turn on
                    &ldquo;Enable CORS&rdquo; in the server settings. Then Connect with the port it prints.
                  </p>
                )}
                <p>
                  Chrome asks once whether this site may access apps and services on your device: choose Allow. If you
                  chose Block, use the site settings icon left of the address bar to allow it.
                </p>
              </div>
            </details>

            <p className="text-meta text-ink-muted">{PRIVACY}</p>
          </div>
        )}

        {choice === "claude" && liveMode && <LiveStoppedLine form={form} />}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-rule pt-4">
          <button
            type="button"
            className={`${primaryButton} w-full sm:w-auto`}
            disabled={primaryDisabled}
            onClick={() => (choice === "claude" ? confirmClaudeChoice() : confirmModel())}
          >
            {primaryLabel}
          </button>
          <button type="button" className={`${secondaryButton} w-full sm:w-auto`} onClick={cancel}>
            Cancel
          </button>
        </div>
        <span role="status" className="sr-only">
          {form.announce}
        </span>
      </div>
      )}
    </dialog>
  );
}

// The address as the Connect hint shows it ("localhost:11434"); the typed text when it isn't valid yet.
function checkedBase(address: string): string {
  const checked = checkAddress(address);
  return checked.ok ? checked.base : address;
}

// One model menu with its help text, linked by aria-describedby (DESIGN.md, "After connect").
function ModelSelect({
  id,
  label,
  value,
  models,
  help,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  models: string[];
  help: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-label">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={`${id}-help`}
        className={SELECT}
      >
        {models.map((m) => (
          <option key={m} value={m}>
            {modelLabel(m)}
          </option>
        ))}
      </select>
      <p id={`${id}-help`} className="text-meta text-ink-muted">
        {help}
      </p>
    </div>
  );
}
