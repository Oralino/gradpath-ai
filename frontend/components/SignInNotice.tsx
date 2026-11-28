"use client";

// GitHub sign-in glue for every page (T-026), mounted once in app/layout.tsx. Two jobs:
// 1. In live mode, ask GET /api/auth/me once and mirror the answer into lib/liveSession.ts (the
//    session cookie is HttpOnly, so the page can't read it); a 404 means sign-in isn't available.
// 2. After GitHub sends the visitor back to /?signin=<code>, show that outcome once and remove the
//    parameter from the URL (history.replaceState), so a reload or a shared link doesn't repeat it.
// Only fixed messages are shown: an unknown code is dropped from the URL and ignored. "ok" is
// only a claim in a URL anyone can share, so its text waits for /api/auth/me to confirm the
// sign-in; anything else (signed out, 404, not a live-mode server) shows the "failed" text.

import { useEffect, useState } from "react";
import { OctagonIcon, KeyIcon } from "@/components/icons";
import { textButton } from "@/components/buttonStyles";
import { api, ApiError } from "@/lib/api";
import { setSignIn, setSignInUnavailable, useLiveSession } from "@/lib/liveSession";
import { useServerInfo } from "@/lib/serverInfo";

export const SIGNIN_MESSAGES: Record<string, { tone: "ok" | "stopped"; text: string }> = {
  ok: { tone: "ok", text: "Signed in with GitHub. Add your Anthropic API key to use live mode." },
  too_new: {
    tone: "stopped",
    text: "Your GitHub account is less than 30 days old, so it can't use live mode yet. You can still browse the recorded examples.",
  },
  blocked: { tone: "stopped", text: "This GitHub account can't use live mode on this site." },
  denied: { tone: "stopped", text: "GitHub sign-in was cancelled. Nothing was saved." },
  failed: { tone: "stopped", text: "GitHub sign-in didn't work. Try again in a minute." },
};

// Read and remove ?signin= from the current URL; keeps every other parameter and the hash.
function takeSigninParam(): string | null {
  const url = new URL(window.location.href);
  const code = url.searchParams.get("signin");
  if (code === null) return null;
  url.searchParams.delete("signin");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  return code;
}

export function SignInNotice() {
  const info = useServerInfo();
  const session = useLiveSession();
  const [notice, setNotice] = useState<string | null>(null);
  const [okPending, setOkPending] = useState(false); // ?signin=ok waiting for /api/auth/me

  // Once, after mount (not during render, so server and client HTML match).
  useEffect(() => {
    const code = takeSigninParam();
    if (code === null || !Object.hasOwn(SIGNIN_MESSAGES, code)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (code === "ok") setOkPending(true);
    else setNotice(code);
  }, []);

  const live = info.status === "ready" && info.mode === "live";
  // Settle a pending "ok" once, as soon as the sign-in state is known; a later sign-out doesn't
  // rewrite a message already shown.
  const settled = info.status === "error" || (info.status === "ready" && (!live || session.signIn !== "unknown"));
  useEffect(() => {
    if (!okPending || !settled) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOkPending(false);
    setNotice(session.signedIn ? "ok" : "failed");
  }, [okPending, settled, session.signedIn]);

  useEffect(() => {
    if (!live) return;
    const controller = new AbortController();
    api
      .me(controller.signal)
      .then((me) => setSignIn(me.signed_in === true, me.login, me.expires_at))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) setSignInUnavailable();
        else setSignIn(false, null, null); // can't tell: show the sign-in button
      });
    return () => controller.abort();
  }, [live]);

  const message = notice ? SIGNIN_MESSAGES[notice] : null;
  return (
    <div aria-live="polite">
      {message && (
        <div
          className={`mb-6 flex items-start gap-2 rounded-md border-l-4 p-3 text-small ${
            message.tone === "ok" ? "border-info bg-info-bg" : "border-stopped bg-stopped-bg"
          }`}
        >
          {message.tone === "ok" ? <KeyIcon size={16} /> : <OctagonIcon size={16} />}
          <p className="flex-1">{message.text}</p>
          <button
            type="button"
            className={textButton}
            onClick={() => setNotice(null)}
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
