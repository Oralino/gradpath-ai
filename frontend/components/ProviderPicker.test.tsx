import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProviderPicker } from "@/components/ProviderPicker";
import { resetForTests, setSignIn } from "@/lib/liveSession";
import { LocalModelError } from "@/lib/localModels";
import {
  closeDialog,
  openDialog,
  relayModels,
  resetProviderForTests,
  setConnection,
  STORAGE_KEY,
  useProviderSession,
} from "@/lib/providerSession";

const listModels = vi.hoisted(() => vi.fn());
vi.mock("@/lib/localModels", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/localModels")>()),
  listModels,
}));

const LATER = new Date(Date.now() + 3_600_000).toISOString();

function Harness({ mode = "live" }: { mode?: "live" | "local" }) {
  const state = useProviderSession();
  return (
    <>
      <button type="button" onClick={(e) => openDialog(e.currentTarget)}>
        Open setup
      </button>
      <span data-testid="active">{state.active ? state.active.choice : "none"}</span>
      <ProviderPicker mode={mode} />
    </>
  );
}

const open = () => fireEvent.click(screen.getByRole("button", { name: "Open setup" }));
const radio = (name: RegExp) => screen.getByRole("radio", { name }) as HTMLInputElement;
const address = () => screen.getByLabelText("Server address") as HTMLInputElement;
const connectButton = () => screen.getByRole("button", { name: /^Connect/ }) as HTMLButtonElement;
const useModel = () => screen.getByRole("button", { name: "Use this model" }) as HTMLButtonElement;
const dialog = () => screen.queryByRole("dialog");

function openOllama() {
  render(<Harness />);
  open();
  fireEvent.click(radio(/Ollama on this computer/));
}

async function connect(models = ["llama3.1:8b", "qwen2.5:14b"]) {
  listModels.mockResolvedValueOnce(models);
  fireEvent.click(connectButton());
  await waitFor(() => expect(connectButton().disabled).toBe(false));
}

beforeEach(() => {
  resetForTests();
  resetProviderForTests();
  window.localStorage.clear();
  listModels.mockReset();
  setSignIn(true, "octocat", LATER);
});
afterEach(() => {
  cleanup();
  closeDialog();
  resetProviderForTests();
  window.localStorage.clear();
});

describe("opening and closing", () => {
  test("opens as a named dialog with the radio group; Claude is checked and holds focus", () => {
    render(<Harness />);
    expect(dialog()).toBeNull();
    open();
    expect(screen.getByRole("dialog", { name: "Use live mode" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "How answers are generated" })).toBeTruthy();
    expect(radio(/Claude \(your API key\)/).checked).toBe(true);
    expect(document.activeElement).toBe(radio(/Claude/));
    const browser = radio(/Model in your browser/);
    expect(browser.disabled).toBe(true);
    expect(screen.getByText("Coming soon")).toBeTruthy();
    expect(screen.getByText("Signed in as @octocat")).toBeTruthy();
  });

  test("Escape, the x and Cancel close it and give focus back to the opener; a backdrop click does not", () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open setup" });
    open();
    fireEvent.click(screen.getByRole("dialog")); // a click on the backdrop lands on the dialog itself
    expect(dialog()).toBeTruthy();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(opener);
    open();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(dialog()).toBeNull();
    open();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(dialog()).toBeNull();
    expect(screen.getByTestId("active").textContent).toBe("none");
  });

  test("local mode: the first option is the server's model and there is no sign-in row", () => {
    render(<Harness mode="local" />);
    open();
    expect(radio(/This server's model \(local mode\)/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Sign in with GitHub" })).toBeNull();
    expect(screen.queryByText("Signed in as @octocat")).toBeNull();
    expect(screen.queryByLabelText("Anthropic API key")).toBeNull();
  });
});

describe("the options", () => {
  test("switching radios keeps what was typed for each option, and the Claude key", () => {
    render(<Harness />);
    open();
    fireEvent.change(screen.getByLabelText("Anthropic API key"), { target: { value: "sk-ant-typed" } });
    fireEvent.click(radio(/Ollama on this computer/));
    fireEvent.change(address(), { target: { value: "http://localhost:9999" } });
    fireEvent.click(radio(/llama\.cpp on this computer/));
    expect(address().value).toBe("http://localhost:9931/v1");
    fireEvent.click(radio(/Ollama on this computer/));
    expect(address().value).toBe("http://localhost:9999");
    fireEvent.click(radio(/Claude \(your API key\)/));
    expect((screen.getByLabelText("Anthropic API key") as HTMLInputElement).value).toBe("sk-ant-typed");
  });

  test("typed values survive a close and reopen in the same tab", () => {
    openOllama();
    fireEvent.change(address(), { target: { value: "http://localhost:9999" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    open();
    expect(radio(/Ollama on this computer/).checked).toBe(true); // the draft choice comes back too
    expect(address().value).toBe("http://localhost:9999");
  });

  test("the address help differs per server and 'Use the default' appears only for a changed value", () => {
    openOllama();
    expect(screen.getByText(/Ollama's address on this computer\. Default http:\/\/localhost:11434\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Use the default" })).toBeNull();
    fireEvent.change(address(), { target: { value: "http://localhost:1" } });
    fireEvent.click(screen.getByRole("button", { name: "Use the default" }));
    expect(address().value).toBe("http://localhost:11434");
    fireEvent.click(radio(/llama\.cpp on this computer/));
    expect(screen.getByText(/llama-server's address on this computer, ending in \/v1\. Default http:\/\/localhost:9931\/v1\./)).toBeTruthy();
  });

  test("LM Studio is not offered (its client is kept for later)", () => {
    render(<Harness />);
    open();
    expect(screen.queryByRole("radio", { name: /LM Studio/ })).toBeNull();
    expect(screen.getAllByRole("radio").map((r) => (r as HTMLInputElement).value)).toEqual([
      "claude",
      "ollama",
      "llamacpp",
      "browser",
    ]);
  });
});

describe("Connect", () => {
  test.each([
    ["http://example.com:11434", "Only a server on this computer works here: use localhost, 127.0.0.1 or [::1], with any port."],
    ["not an address", "Enter a full address, like http://localhost:11434."],
  ])("the address %s is refused before any request, and the field takes focus", (value, text) => {
    openOllama();
    fireEvent.change(address(), { target: { value } });
    fireEvent.click(connectButton());
    expect(screen.getByText(text)).toBeTruthy();
    expect(address().getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(address());
    expect(listModels).not.toHaveBeenCalled();
  });

  test("lists the models: the status line, the model menu and the size hint", async () => {
    openOllama();
    await connect();
    expect(listModels).toHaveBeenCalledWith("ollama", "http://localhost:11434", expect.any(AbortSignal));
    expect(screen.getByText("Connected to Ollama: 2 models.")).toBeTruthy();
    const select = screen.getByLabelText("Model") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["llama3.1:8b", "qwen2.5:14b"]);
    expect(select.value).toBe("llama3.1:8b");
    expect(screen.getByText(/A model of 7B or larger is recommended/)).toBeTruthy();
    expect(document.activeElement).toBe(connectButton());
  });

  test("while it waits: Connecting..., the Chrome hint and a Cancel that stops only the connect", async () => {
    openOllama();
    let signal: AbortSignal | undefined;
    listModels.mockImplementationOnce((_s: string, _b: string, s: AbortSignal) => {
      signal = s;
      return new Promise(() => {});
    });
    fireEvent.click(connectButton());
    expect(screen.getByRole("button", { name: "Connecting..." }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Waiting for Ollama at localhost:11434\. If Chrome asks/)).toBeTruthy();
    const [connectCancel] = screen.getAllByRole("button", { name: "Cancel" });
    fireEvent.click(connectCancel);
    expect(signal?.aborted).toBe(true);
    expect(screen.getByText("Connection cancelled.")).toBeTruthy();
    expect(dialog()).toBeTruthy(); // the dialog stays open
  });

  test("no models: the caution line for each server", async () => {
    openOllama();
    await connect([]);
    expect(screen.getByText(/Connected, but Ollama has no models installed\./)).toBeTruthy();
    expect(useModel().disabled).toBe(true);
    fireEvent.click(radio(/llama\.cpp on this computer/));
    await connect([]);
    expect(screen.getByText(/Connected, but llama-server listed no model\./)).toBeTruthy();
  });

  test("can't reach: an alert with the checklist, setup help opens, focus stays on Connect", async () => {
    openOllama();
    listModels.mockRejectedValueOnce(new LocalModelError("unreachable"));
    fireEvent.click(connectButton());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Can't reach Ollama at localhost:11434. The browser can't tell why, so check:");
    expect(alert.textContent).toContain("You chose Allow when Chrome asked about apps on this device.");
    expect(screen.getByText("Setup help for Ollama").closest("details")?.open).toBe(true);
    expect(screen.queryByText(/Connected to Ollama/)).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(connectButton()));
  });

  test("something answered that is not the server: its own line, with the /v1 hint for llama.cpp", async () => {
    openOllama();
    fireEvent.click(radio(/llama\.cpp on this computer/));
    listModels.mockRejectedValueOnce(new LocalModelError("not_server"));
    fireEvent.click(connectButton());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Something answered at localhost:9931/v1, but not like llama.cpp. Check the address; llama.cpp's ends in /v1.");
  });

  test("llama.cpp: the menu shows a model file's name, not its folders, but keeps the full name as the value", async () => {
    openOllama();
    fireEvent.click(radio(/llama\.cpp on this computer/));
    const path = "H:/Models/Some Folder/Qwen2.5-7B-Instruct-Q4_K_M.gguf";
    await connect([path]);
    expect(listModels).toHaveBeenCalledWith("llamacpp", "http://localhost:9931/v1", expect.any(AbortSignal));
    const select = screen.getByLabelText("Model") as HTMLSelectElement;
    expect(select.options[0].value).toBe(path);
    expect(select.options[0].textContent).toBe("Qwen2.5-7B-Instruct-Q4_K_M.gguf");
    expect(dialog()?.textContent).not.toContain("Some Folder");
  });

  test("llama.cpp setup help: the start command with this site, and the warning to always set --cors-origins", () => {
    openOllama();
    fireEvent.click(radio(/llama\.cpp on this computer/));
    const origin = window.location.origin;
    expect(screen.getByText(`llama-server -m <model.gguf> -c 32768 --reasoning off --cors-origins ${origin}`)).toBeTruthy();
    expect(screen.getByText(/without it llama-server lets any website you visit use your model and read its replies/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
  });

  test("the setup help names this site's address for OLLAMA_ORIGINS", () => {
    openOllama();
    expect(screen.getAllByText(window.location.origin).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(screen.getByText(/Chrome asks once whether this site may access apps and services/)).toBeTruthy();
  });
});

describe("choosing models and confirming", () => {
  test("'Use one model for both' is on by default; off shows a fast and a smart menu", async () => {
    openOllama();
    await connect();
    const box = screen.getByRole("checkbox", { name: "Use one model for both" }) as HTMLInputElement;
    expect(box.checked).toBe(true);
    box.focus();
    fireEvent.click(box);
    expect(screen.queryByLabelText("Model")).toBeNull();
    expect(screen.getByLabelText("Fast model")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Smart model"), { target: { value: "qwen2.5:14b" } });
    expect(document.activeElement).toBe(box);
  });

  test("'Use this model' waits for a connection, then closes the dialog and puts the setup in force", async () => {
    openOllama();
    expect(useModel().disabled).toBe(true);
    await connect();
    expect(useModel().disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "qwen2.5:14b" } });
    fireEvent.click(useModel());
    expect(dialog()).toBeNull();
    expect(screen.getByTestId("active").textContent).toBe("ollama");
    expect(relayModels()).toEqual({ server: "ollama", base: "http://localhost:11434", fast: "qwen2.5:14b", smart: "qwen2.5:14b" });
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string);
    expect(stored.choice).toBe("ollama");
    expect(stored.ollama.fast).toBe("qwen2.5:14b");
  });

  test("editing the address after Connect returns to not connected", async () => {
    openOllama();
    await connect();
    fireEvent.change(address(), { target: { value: "http://localhost:11435" } });
    expect(screen.queryByText(/Connected to Ollama/)).toBeNull();
    expect(useModel().disabled).toBe(true);
  });

  test("Cancel after changes keeps the last confirmed setup in force", async () => {
    setConnection("ollama", "http://localhost:11434", ["a", "b"]);
    openOllama();
    fireEvent.click(useModel());
    open();
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(relayModels()?.fast).toBe("a");
  });

  test("Forget clears the remembered choice and says so", async () => {
    openOllama();
    await connect();
    fireEvent.click(useModel());
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull();
    open();
    fireEvent.click(radio(/Ollama on this computer/));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Forget" }));
    });
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(screen.getByText("Forgotten on this device")).toBeTruthy();
    expect(screen.queryByText(/Connected to Ollama/)).toBeNull();
  });

  test("the privacy line says where the posting goes", () => {
    openOllama();
    expect(screen.getByText(/Your posting and profile go from this page to your own server and to GradPath's server/)).toBeTruthy();
  });
});
