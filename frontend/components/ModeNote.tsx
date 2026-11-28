"use client";

// The one-paragraph mode note under each model screen's intro (DESIGN.md, "Mode note"): a fact
// about the site, not a result status. Used by Assistant, JobAnalysisView and PlanView. Nothing in
// local mode or while health loads.

import Link from "next/link";
import { textButton } from "@/components/buttonStyles";
import { useServerInfo } from "@/lib/serverInfo";

export function ModeNote({ screen }: { screen: "ask" | "job" | "plan" }) {
  const info = useServerInfo();
  if (info.status !== "ready" || info.mode === "local") return null;
  const search = (
    <Link href="/search" className={textButton}>
      search the sources
    </Link>
  );
  let body;
  if (info.mode === "live") {
    body = (
      <>
        Live mode: sign in with GitHub, then use your own Anthropic API key or a model on your computer. Without
        them you can still browse the recorded examples and {search}.
      </>
    );
  } else if (screen === "ask") {
    body = (
      <>
        This site runs in demo mode: no model runs here, so it can&apos;t answer a new question. Below are recorded
        runs of the real app on a sample posting and a fictional profile. To try your own question, {search}: you get
        the matching passages, not a written answer.
      </>
    );
  } else {
    body = (
      <>
        This site runs in demo mode, so it can&apos;t analyse a new posting. Below is a recorded run on the sample
        posting{screen === "plan" ? ", with the fictional sample profile" : ""}.
      </>
    );
  }
  return <p className="max-w-3xl text-small text-ink-muted">{body}</p>;
}
