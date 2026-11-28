import { afterEach, beforeEach, describe, expect, test } from "vitest";
import {
  STORAGE_KEY,
  canConfirm,
  confirmClaude,
  confirmLocal,
  forget,
  openDialog,
  relayModels,
  resetProviderForTests,
  setAddress,
  setChoice,
  setConnection,
  setModel,
  setOneModel,
  takeStripFocus,
  useProviderSession,
} from "@/lib/providerSession";
import { renderHook } from "@testing-library/react";

const state = () => renderHook(() => useProviderSession()).result.current;

beforeEach(() => {
  window.localStorage.clear();
  resetProviderForTests();
});
afterEach(() => {
  window.localStorage.clear();
  resetProviderForTests();
});

describe("remember and forget", () => {
  test("confirming remembers the choice, addresses, model names and oneModel, and nothing else", () => {
    setAddress("ollama", "http://127.0.0.1:11500");
    setConnection("ollama", "http://127.0.0.1:11500", ["a:7b", "b:14b"]);
    setOneModel(false);
    setModel("ollama", "fast", "a:7b");
    setModel("ollama", "smart", "b:14b");
    expect(confirmLocal("ollama")).toBe(true);
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string);
    expect(stored).toEqual({
      choice: "ollama",
      oneModel: false,
      ollama: { address: "http://127.0.0.1:11500", fast: "a:7b", smart: "b:14b" },
      llamacpp: { address: "http://localhost:9931/v1", fast: "", smart: "" },
    });
    expect(window.localStorage.length).toBe(1);
  });

  test("a reload preselects the remembered choice and names; the connection itself is not remembered", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ choice: "llamacpp", oneModel: false, llamacpp: { address: "http://localhost:8080/v1", fast: "f", smart: "s" } }),
    );
    const s = state();
    expect(s.choice).toBe("llamacpp");
    expect(s.oneModel).toBe(false);
    expect(s.servers.llamacpp.address).toBe("http://localhost:8080/v1");
    expect(s.servers.llamacpp.connectedBase).toBeNull();
    expect(s.active).toBeNull();
    // Connect: the remembered name is kept when the list has it, else the first listed.
    setConnection("llamacpp", "http://localhost:8080/v1", ["x", "f", "y"]);
    const after = state().servers.llamacpp;
    expect(after.fast).toBe("f");
    expect(after.smart).toBe("x");
  });

  test("a remembered LM Studio choice (no longer offered) falls back to the default; its entry is dropped", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ choice: "lmstudio", lmstudio: { address: "http://localhost:1235/v1", fast: "f", smart: "f" } }),
    );
    const s = state();
    expect(s.choice).toBe("claude");
    expect(s.servers.lmstudio.address).toBe("http://localhost:1234/v1");
    expect(s.servers.lmstudio.fast).toBe("");
    setConnection("ollama", "http://localhost:11434", ["a"]);
    confirmLocal("ollama");
    expect(Object.keys(JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string)).sort()).toEqual([
      "choice",
      "llamacpp",
      "ollama",
      "oneModel",
    ]);
  });

  test("forget clears storage and resets addresses and connections, leaving the radio and the setup in force", () => {
    setConnection("ollama", "http://localhost:11434", ["m"]);
    confirmLocal("ollama");
    forget();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    const s = state();
    expect(s.choice).toBe("ollama");
    expect(s.servers.ollama.connectedBase).toBeNull();
    expect(s.servers.ollama.address).toBe("http://localhost:11434");
    expect(s.active).not.toBeNull();
  });

  test("a stored address that is not this computer is refused; garbage in storage is ignored", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ choice: "ollama", ollama: { address: "http://evil.example:11434", fast: "m", smart: "m" } }),
    );
    expect(state().servers.ollama.address).toBe("http://localhost:11434");
    resetProviderForTests();
    window.localStorage.setItem(STORAGE_KEY, "{not json");
    expect(state().choice).toBe("claude");
    resetProviderForTests();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: "evil", oneModel: "yes", ollama: 5, llamacpp: { address: 7, fast: {} } }));
    const s = state();
    expect(s.choice).toBe("claude");
    expect(s.oneModel).toBe(true);
    expect(s.servers.llamacpp.address).toBe("http://localhost:9931/v1");
    expect(s.servers.llamacpp.fast).toBe("");
    resetProviderForTests();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: "ollama", ollama: { address: "x".repeat(400), fast: "n".repeat(1_100), smart: "ok" } }));
    const capped = state().servers.ollama;
    expect(capped.address).toBe("http://localhost:11434");
    expect(capped.fast).toBe("");
    expect(capped.smart).toBe("ok");
  });
});

describe("what is in force", () => {
  test("relayModels is null until a local choice is confirmed; Cancel-style edits do not change it", () => {
    expect(relayModels()).toBeNull();
    setConnection("ollama", "http://localhost:11434", ["a", "b"]);
    expect(relayModels()).toBeNull(); // connected, not confirmed
    expect(confirmLocal("ollama")).toBe(true);
    expect(relayModels()).toEqual({ server: "ollama", base: "http://localhost:11434", fast: "a", smart: "a" });
    setModel("ollama", "fast", "b"); // an edit in the dialog, then Cancel
    expect(relayModels()?.fast).toBe("a");
    confirmClaude();
    expect(relayModels()).toBeNull();
  });

  test("two models: smart is kept apart when oneModel is off", () => {
    setConnection("llamacpp", "http://localhost:9931/v1", ["a", "b"]);
    setOneModel(false);
    setModel("llamacpp", "smart", "b");
    confirmLocal("llamacpp");
    expect(relayModels()).toMatchObject({ server: "llamacpp", fast: "a", smart: "b" });
  });

  test("confirming needs a connection and a chosen model; editing the address drops the connection", () => {
    expect(canConfirm(state(), "ollama")).toBe(false);
    expect(confirmLocal("ollama")).toBe(false);
    setConnection("ollama", "http://localhost:11434", ["a"]);
    expect(canConfirm(state(), "ollama")).toBe(true);
    setAddress("ollama", "http://localhost:11435");
    expect(canConfirm(state(), "ollama")).toBe(false);
    expect(state().servers.ollama.models).toEqual([]);
  });

  test("the radio switch keeps what was typed for the other options", () => {
    setAddress("ollama", "http://localhost:9999");
    setChoice("llamacpp");
    setChoice("ollama");
    expect(state().servers.ollama.address).toBe("http://localhost:9999");
  });

  test("opening the dialog preselects the confirmed choice; the strip takes focus once after a confirm", () => {
    setConnection("ollama", "http://localhost:11434", ["a"]);
    confirmLocal("ollama");
    setChoice("claude");
    openDialog();
    expect(state().choice).toBe("ollama");
    expect(state().dialogOpen).toBe(true);
    expect(takeStripFocus()).toBe(true);
    expect(takeStripFocus()).toBe(false);
  });
});
