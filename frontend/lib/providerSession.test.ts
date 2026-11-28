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
      lmstudio: { address: "http://localhost:1234/v1", fast: "", smart: "" },
    });
    expect(window.localStorage.length).toBe(1);
  });

  test("a reload preselects the remembered choice and names; the connection itself is not remembered", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ choice: "lmstudio", oneModel: false, lmstudio: { address: "http://localhost:1235/v1", fast: "f", smart: "s" } }),
    );
    const s = state();
    expect(s.choice).toBe("lmstudio");
    expect(s.oneModel).toBe(false);
    expect(s.servers.lmstudio.address).toBe("http://localhost:1235/v1");
    expect(s.servers.lmstudio.connectedBase).toBeNull();
    expect(s.active).toBeNull();
    // Connect: the remembered name is kept when the list has it, else the first listed.
    setConnection("lmstudio", "http://localhost:1235/v1", ["x", "f", "y"]);
    const after = state().servers.lmstudio;
    expect(after.fast).toBe("f");
    expect(after.smart).toBe("x");
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
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: "evil", oneModel: "yes", ollama: 5, lmstudio: { address: 7, fast: {} } }));
    const s = state();
    expect(s.choice).toBe("claude");
    expect(s.oneModel).toBe(true);
    expect(s.servers.lmstudio.address).toBe("http://localhost:1234/v1");
    expect(s.servers.lmstudio.fast).toBe("");
    resetProviderForTests();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: "ollama", ollama: { address: "x".repeat(400), fast: "n".repeat(300), smart: "ok" } }));
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
    setConnection("lmstudio", "http://localhost:1234/v1", ["a", "b"]);
    setOneModel(false);
    setModel("lmstudio", "smart", "b");
    confirmLocal("lmstudio");
    expect(relayModels()).toMatchObject({ server: "lmstudio", fast: "a", smart: "b" });
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
    setChoice("lmstudio");
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
