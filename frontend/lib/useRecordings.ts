"use client";

// Recorded runs for one screen (DESIGN.md "Recorded examples", decision 8). Used by Assistant,
// JobAnalysisView and PlanView through components/RecordedExamples.tsx. One GET /api/demo list
// filtered to the screen's kind, then one GET /api/demo/{id} per pick. `autoShow` (demo mode on
// Job and Plan, which have one recording each) loads the first recording at once, without marking
// it as picked, so the screen does not move focus. The screen holds one result slot: `clear()`
// empties it when a live run starts.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Recording, RecordingKind, RecordingSummary } from "@/lib/types";

type ListState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; items: RecordingSummary[] };

export type OneState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; recording: T };

export interface RecordingSlot<T extends Recording> {
  list: ListState;
  one: OneState<T>;
  selectedId: string | null;
  userPicked: boolean; // true after the visitor chose a row: focus moves to the result h2
  pick: (id: string) => void;
  clear: () => void;
  reloadList: () => void;
  retryOne: () => void;
}

const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";

export function useRecordings<K extends RecordingKind>(
  kind: K,
  { enabled, autoShow }: { enabled: boolean; autoShow: boolean },
): RecordingSlot<Extract<Recording, { kind: K }>> {
  type T = Extract<Recording, { kind: K }>;
  const [list, setList] = useState<ListState>({ status: "loading" });
  const [one, setOne] = useState<OneState<T>>({ status: "idle" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [userPicked, setUserPicked] = useState(false);
  const [listNonce, setListNonce] = useState(0);
  const listCtl = useRef<AbortController | null>(null);
  const oneCtl = useRef<AbortController | null>(null);
  const lastRef = useRef<{ id: string; picked: boolean } | null>(null);

  const load = useCallback(
    (id: string, picked: boolean) => {
      oneCtl.current?.abort();
      const controller = new AbortController();
      oneCtl.current = controller;
      lastRef.current = { id, picked };
      setSelectedId(id);
      setUserPicked(picked);
      setOne({ status: "loading" });
      api
        .recording(id, controller.signal)
        .then((recording) => {
          if (controller.signal.aborted) return;
          setOne(recording.kind === kind ? { status: "ready", recording: recording as T } : { status: "error" });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || isAbort(error)) return;
          setOne({ status: "error" });
        });
    },
    [kind],
  );

  // The list, once the server's mode is known (and again on "Try again").
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    listCtl.current = controller;
    api
      .recordings(controller.signal)
      .then((all) => {
        if (controller.signal.aborted) return;
        const items = all.filter((r) => r.kind === kind);
        setList({ status: "ready", items });
        if (autoShow && items.length > 0) load(items[0].id, false);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return;
        setList({
          status: "error",
          error: error instanceof ApiError ? error : new ApiError("server", null, "Something went wrong."),
        });
      });
    return () => controller.abort();
  }, [enabled, kind, autoShow, load, listNonce]);

  useEffect(() => () => oneCtl.current?.abort(), []);

  const pick = useCallback((id: string) => load(id, true), [load]);
  const clear = useCallback(() => {
    oneCtl.current?.abort();
    lastRef.current = null;
    setSelectedId(null);
    setUserPicked(false);
    setOne({ status: "idle" });
  }, []);
  const reloadList = useCallback(() => {
    setList({ status: "loading" });
    setListNonce((n) => n + 1);
  }, []);
  const retryOne = useCallback(() => {
    if (lastRef.current) load(lastRef.current.id, lastRef.current.picked);
  }, [load]);

  return { list, one, selectedId, userPicked, pick, clear, reloadList, retryOne };
}
