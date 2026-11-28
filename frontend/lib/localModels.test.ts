import { afterEach, describe, expect, test, vi } from "vitest";
import {
  chat,
  checkAddress,
  listModels,
  LocalModelError,
  MAX_MODELS,
  OLLAMA_NUM_CTX,
  shortAddress,
} from "@/lib/localModels";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function stubFetch(impl: (url: string, init: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function failure(promise: Promise<unknown>): Promise<LocalModelError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof LocalModelError) return error;
    throw error;
  }
  throw new Error("expected a LocalModelError");
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("checkAddress", () => {
  test.each([
    ["http://localhost:11434", "http://localhost:11434"],
    ["http://localhost:11434/", "http://localhost:11434"],
    ["  http://127.0.0.1:1235/v1/ ", "http://127.0.0.1:1235/v1"],
    ["http://[::1]:8080", "http://[::1]:8080"],
    ["https://localhost", "https://localhost"],
    ["http://LOCALHOST:11434", "http://localhost:11434"],
  ])("accepts %s", (raw, base) => {
    expect(checkAddress(raw)).toEqual({ ok: true, base });
  });

  test.each([
    "http://192.168.1.20:11434",
    "http://10.0.0.5:1234/v1",
    "https://example.com",
    "http://localhost.example.com:11434",
    "http://127.0.0.2:11434",
    "http://0.0.0.0:11434",
  ])("refuses %s as not this computer", (raw) => {
    expect(checkAddress(raw)).toEqual({ ok: false, error: "not_local" });
  });

  test.each([
    "",
    "localhost:11434",
    "ftp://localhost",
    "javascript:alert(1)",
    "http://user:pass@localhost:11434",
    "http://localhost:11434/?x=1",
    "http://localhost:11434/#a",
  ])("refuses %s as malformed", (raw) => {
    expect(checkAddress(raw)).toEqual({ ok: false, error: "malformed" });
  });

  test("shortAddress drops the scheme", () => {
    expect(shortAddress("http://localhost:11434")).toBe("localhost:11434");
    expect(shortAddress("http://localhost:1235/v1")).toBe("localhost:1235/v1");
  });
});

describe("listModels", () => {
  test("Ollama reads /api/tags names, without cookies or referrer", async () => {
    const fetchMock = stubFetch(async () =>
      jsonResponse(200, { models: [{ name: "llama3.1:8b", model: "llama3.1:8b" }, { name: "qwen38-27b" }] }),
    );
    expect(await listModels("ollama", "http://localhost:11434")).toEqual(["llama3.1:8b", "qwen38-27b"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:11434/api/tags");
    expect(init.credentials).toBe("omit");
    expect(init.referrerPolicy).toBe("no-referrer");
  });

  test("LM Studio reads /v1/models ids", async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { data: [{ id: "qwen2.5-7b-instruct" }], object: "list" }));
    expect(await listModels("lmstudio", "http://localhost:1235/v1")).toEqual(["qwen2.5-7b-instruct"]);
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:1235/v1/models");
  });

  test("an empty list means connected with no models", async () => {
    stubFetch(async () => jsonResponse(200, { models: [] }));
    expect(await listModels("ollama", "http://localhost:11434")).toEqual([]);
  });

  test("skips bad entries, de-duplicates and caps the list", async () => {
    const models = [{ name: 5 }, { name: "" }, { name: "a" }, { name: "a" }, { name: "x".repeat(201) }, "b", null];
    for (let i = 0; i < MAX_MODELS + 10; i += 1) models.push({ name: `m${i}` });
    stubFetch(async () => jsonResponse(200, { models }));
    const listed = await listModels("ollama", "http://localhost:11434");
    expect(listed[0]).toBe("a");
    expect(listed).toHaveLength(MAX_MODELS);
  });

  test("a network failure is unreachable", async () => {
    stubFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect((await failure(listModels("ollama", "http://localhost:11434"))).kind).toBe("unreachable");
  });

  test("something that isn't the server is not_server", async () => {
    stubFetch(async () => new Response("<html>hello</html>", { status: 200 }));
    expect((await failure(listModels("ollama", "http://localhost:11434"))).kind).toBe("not_server");
    stubFetch(async () => jsonResponse(200, { hello: "world" }));
    expect((await failure(listModels("lmstudio", "http://localhost:1234/v1"))).kind).toBe("not_server");
  });

  test("an error status is model_error with the status", async () => {
    stubFetch(async () => jsonResponse(404, { error: "secret details" }));
    const error = await failure(listModels("lmstudio", "http://localhost:1234/v1"));
    expect(error.kind).toBe("model_error");
    expect(error.status).toBe(404);
    expect(error.message).not.toContain("secret");
  });

  test("the caller's abort is aborted", async () => {
    stubFetch(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const controller = new AbortController();
    const pending = listModels("ollama", "http://localhost:11434", controller.signal);
    controller.abort();
    expect((await failure(pending)).kind).toBe("aborted");
  });
});

describe("chat", () => {
  const messages = [
    { role: "system" as const, content: "sys" },
    { role: "user" as const, content: "hi" },
  ];
  const schema = { type: "object", properties: { a: { type: "string" } } };

  test("Ollama sends format = schema, no streaming and a large context", async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { message: { role: "assistant", content: '{"a":"x"}' } }));
    const text = await chat("ollama", "http://localhost:11434", "llama3.1:8b", messages, schema);
    expect(text).toBe('{"a":"x"}');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:11434/api/chat");
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      model: "llama3.1:8b",
      messages,
      stream: false,
      options: { num_ctx: OLLAMA_NUM_CTX },
      format: schema,
    });
  });

  test("Ollama plain prompts send no format", async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { message: { content: "hello" } }));
    await chat("ollama", "http://localhost:11434", "m", messages, null);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).not.toHaveProperty("format");
  });

  test("LM Studio sends response_format json_schema and reads choices[0]", async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { choices: [{ message: { content: '{"a":"y"}' } }] }));
    const text = await chat("lmstudio", "http://localhost:1235/v1", "qwen2.5-7b-instruct", messages, schema);
    expect(text).toBe('{"a":"y"}');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:1235/v1/chat/completions");
    const body = JSON.parse(String(init.body));
    expect(body.response_format).toEqual({ type: "json_schema", json_schema: { name: "reply", strict: true, schema } });
    expect(body.stream).toBe(false);
  });

  test("only role and content are sent", async () => {
    const fetchMock = stubFetch(async () => jsonResponse(200, { message: { content: "ok" } }));
    const extra = [{ role: "user" as const, content: "hi", name: "x" } as never];
    await chat("ollama", "http://localhost:11434", "m", extra, null);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body)).messages).toEqual([{ role: "user", content: "hi" }]);
  });

  test("a reply without text is not_server", async () => {
    stubFetch(async () => jsonResponse(200, { choices: [] }));
    expect((await failure(chat("lmstudio", "http://localhost:1234/v1", "m", messages, null))).kind).toBe("not_server");
  });

  test("a model that never answers times out", async () => {
    vi.useFakeTimers();
    stubFetch(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const pending = failure(chat("ollama", "http://localhost:11434", "m", messages, null, undefined, 1_000));
    await vi.advanceTimersByTimeAsync(1_001);
    expect((await pending).kind).toBe("timeout");
  });
});
