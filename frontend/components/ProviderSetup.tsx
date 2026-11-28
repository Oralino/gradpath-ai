"use client";

// The pieces of the picker that sit in the form (T-029 step 3; DESIGN.md "Model provider picker"):
// the "Set up live mode" row that replaces the submit row until live mode is ready, the strip at
// the top of the form once it is (the Claude LiveStrip or the local-model strip), and the local
// mode's "Use a model on this computer" button. They open the dialog in components/ProviderPicker.tsx
// through lib/providerSession.ts. Used by Assistant, JobAnalysisView and PlanView.

import { useEffect, useRef, useState } from "react";
import { LiveStrip, stripSignOut, takePanelCleared } from "@/components/LivePanel";
import { MonitorIcon } from "@/components/icons";
import { primaryButton, textButton } from "@/components/buttonStyles";
import { SERVER_NAMES } from "@/lib/localModels";
import { openDialog, takeStripFocus, useProviderSession } from "@/lib/providerSession";
import { useLiveSession } from "@/lib/liveSession";
import { useProviderRoute } from "@/lib/useProviderRoute";

/** The row that replaces the submit row while live mode is not ready: what to do, the examples
 * link, and "Set up live mode" (opens the dialog). After a strip's "Clear key" / "Sign out" it
 * takes focus and says so. */
export function SetupRow({ examplesHref = "#recorded-examples" }: { examplesHref?: string }) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    const said = takePanelCleared();
    if (said === null) return;
    buttonRef.current?.focus();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnnounce(said);
  }, []);
  return (
    <div className="flex flex-wrap items-center justify-end gap-3">
      <p className="w-full text-meta text-ink-muted sm:mr-auto sm:w-auto">
        Live mode: sign in with GitHub, then choose Claude or a model on your computer.
      </p>
      <a href={examplesHref} className={`${textButton} text-small`}>
        Browse the examples instead
      </a>
      <button
        ref={buttonRef}
        type="button"
        className={`${primaryButton} w-full sm:w-auto`}
        onClick={(e) => openDialog(e.currentTarget)}
      >
        Set up live mode
      </button>
      <span role="status" className="sr-only">
        {announce}
      </span>
    </div>
  );
}

/** Local mode's way in: a text button near the submit button that opens the dialog. */
export function LocalModelButton() {
  return (
    <button type="button" className={`${textButton} text-small`} onClick={(e) => openDialog(e.currentTarget)}>
      Use a model on this computer
    </button>
  );
}

// The strip for a confirmed local model: "Using Ollama · llama3.1:8b on this computer, signed in as
// @login." with Change and Sign out. Takes focus once when it appears after "Use this model".
function LocalStrip() {
  const provider = useProviderSession();
  const live = useLiveSession();
  const ref = useRef<HTMLDivElement>(null);
  const [announce, setAnnounce] = useState("");
  const active = provider.active;
  const count = provider.confirmCount;
  useEffect(() => {
    if (!takeStripFocus() || !active || active.choice === "claude") return;
    ref.current?.focus();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnnounce(`Using ${SERVER_NAMES[active.choice]}`);
  }, [count, active]);
  if (!active || active.choice === "claude") return null;
  const name = SERVER_NAMES[active.choice];
  const models =
    active.fast === active.smart ? active.fast : `fast ${active.fast}, smart ${active.smart}`;
  const signedAs = live.login ? `, signed in as @${live.login}` : "";
  return (
    <div
      ref={ref}
      tabIndex={-1}
      className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-md border-l-4 border-info bg-info-bg p-3 text-small"
    >
      <p className="flex min-w-0 flex-1 items-start gap-2">
        <MonitorIcon size={16} />
        <span>
          {active.fast === active.smart
            ? `Using ${name} · ${models} on this computer${signedAs}.`
            : `Using ${name} on this computer · ${models}${signedAs}.`}
        </span>
      </p>
      <button type="button" className={textButton} onClick={(e) => openDialog(e.currentTarget)}>
        Change
      </button>
      {live.login && (
        <button type="button" className={textButton} onClick={() => stripSignOut()}>
          Sign out
        </button>
      )}
      <span role="status" className="sr-only">
        {announce}
      </span>
    </div>
  );
}

/** The strip at the top of a form once a route is ready: Claude's LiveStrip, or the local-model
 * strip. Nothing while setup is incomplete (the row shows instead) or in local mode's own model. */
export function ProviderStrip() {
  const { route } = useProviderRoute();
  if (route === "claude") return <LiveStrip />;
  if (route === "relay") return <LocalStrip />;
  return null;
}
