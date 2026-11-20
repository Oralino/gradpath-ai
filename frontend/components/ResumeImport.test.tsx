import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ProfileForm } from "@/components/ProfileForm";
import { PROFILE_STORAGE_KEY, loadProfile, saveProfile } from "@/lib/profileStore";
import { SAMPLE_PROFILE } from "@/lib/sampleProfile";
import type { ResumeImport } from "@/lib/types";

const MARKER = "UNIQUE-RESUME-MARKER";
const RESUME = `${MARKER} ${"r".repeat(150)}`;

const IMPORTED: ResumeImport = {
  profile: {
    education: "BSc from resume",
    skills: ["Go", "Rust"],
    coursework: [],
    projects: [{ name: "Imported app", description: "From the resume", technologies: ["Go"] }],
    experience: [],
    weekly_hours: null,
    timeline_weeks: null,
  },
  notes: ["Kept the first 50 skills of 70."],
};

beforeAll(() => {
  const proto = HTMLDialogElement.prototype;
  proto.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function mockFetch(impl: (init: RequestInit) => Promise<Response>) {
  const fn = vi.fn((_url: string, init: RequestInit) => impl(init));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));

async function renderForm() {
  render(<ProfileForm />);
  await screen.findByText(/Stored only in this browser/);
  document.querySelector("details")!.open = true;
}

function paste(text: string) {
  fireEvent.change(screen.getByLabelText("Resume text"), { target: { value: text } });
}

describe("fill from a resume", () => {
  test("a valid paste sends the body, fills the form, shows badge and notes, clears the box", async () => {
    const fn = mockFetch(async () => jsonResponse(200, IMPORTED));
    await renderForm();
    expect(screen.getByText(/Contact details are dropped/)).toBeTruthy();
    paste(RESUME);
    click("Extract profile");
    await screen.findByText("From your resume: review before saving");
    expect(fn.mock.calls[0][0]).toBe("/api/profile/from-resume");
    expect(JSON.parse(fn.mock.calls[0][1].body as string)).toEqual({ resume_text: RESUME });
    expect((screen.getByLabelText("Education") as HTMLInputElement).value).toBe("BSc from resume");
    expect((screen.getByLabelText("Skills") as HTMLTextAreaElement).value).toBe("Go\nRust");
    expect(screen.getByText("Some details were left out:")).toBeTruthy();
    expect(screen.getByText("Kept the first 50 skills of 70.")).toBeTruthy();
    expect((screen.getByLabelText("Resume text") as HTMLTextAreaElement).value).toBe("");
    expect(document.activeElement?.id).toBe("education");
    expect(screen.getByRole("status").textContent).toMatch(/Profile filled from your resume/);
    expect(window.localStorage.getItem(PROFILE_STORAGE_KEY)).toBeNull();
  });

  test("the live region and panel are the same elements across the first import", async () => {
    mockFetch(async () => jsonResponse(200, IMPORTED));
    await renderForm();
    const live = screen.getByRole("status");
    const details = document.querySelector("details");
    paste(RESUME);
    click("Extract profile");
    await screen.findByText("From your resume: review before saving");
    expect(screen.getByRole("status")).toBe(live);
    expect(document.querySelector("details")).toBe(details);
    expect(live.textContent).toBe("Profile filled from your resume. Review it, then save.");
  });

  test("the current hours and weeks are kept", async () => {
    saveProfile(SAMPLE_PROFILE);
    mockFetch(async () => jsonResponse(200, IMPORTED));
    await renderForm();
    paste(RESUME);
    click("Extract profile");
    await screen.findByText("From your resume: review before saving");
    expect((screen.getByLabelText("Weekly study hours") as HTMLInputElement).value).toBe("8");
    expect((screen.getByLabelText("Timeline in weeks") as HTMLInputElement).value).toBe("6");
  });

  test("the resume text never reaches localStorage, even after Save", async () => {
    mockFetch(async () => jsonResponse(200, IMPORTED));
    await renderForm();
    paste(RESUME);
    click("Extract profile");
    await screen.findByText("From your resume: review before saving");
    click("Save profile");
    expect(loadProfile()?.profile.education).toBe("BSc from resume");
    expect(window.localStorage.getItem(PROFILE_STORAGE_KEY)).not.toContain(MARKER);
    expect(screen.queryByText("From your resume: review before saving")).toBeNull();
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(MARKER);
  });

  test("too short or too long sends nothing", async () => {
    const fn = mockFetch(async () => jsonResponse(200, IMPORTED));
    await renderForm();
    paste("short");
    click("Extract profile");
    expect(screen.getByText(/at least 100 characters/)).toBeTruthy();
    paste("x".repeat(15001));
    click("Extract profile");
    expect(screen.getByText(/over the 15,000 character limit/)).toBeTruthy();
    expect(fn).not.toHaveBeenCalled();
  });

  test("unsaved edits ask first: keep current, then replace", async () => {
    mockFetch(async () => jsonResponse(200, IMPORTED));
    await renderForm();
    click("Start from blank");
    fireEvent.change(screen.getByLabelText("Education"), { target: { value: "Mine" } });
    paste(RESUME);
    click("Extract profile");
    const dialog = await waitFor(() => {
      const d = document.querySelector("dialog[aria-labelledby=replace-title]") as HTMLDialogElement;
      expect(d.hasAttribute("open")).toBe(true);
      return d;
    });
    expect(within(dialog).getByText("Replace your current profile with the one from your resume?")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep current" }));
    expect((screen.getByLabelText("Education") as HTMLInputElement).value).toBe("Mine");

    paste(RESUME);
    click("Extract profile");
    await waitFor(() => expect(dialog.hasAttribute("open")).toBe(true));
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Replace" }));
    });
    expect((screen.getByLabelText("Education") as HTMLInputElement).value).toBe("BSc from resume");
  });

  test("a busy server shows the info panel with Try again", async () => {
    mockFetch(async () => jsonResponse(503, { detail: "A request is already in progress. Try again soon." }));
    await renderForm();
    paste(RESUME);
    click("Extract profile");
    await screen.findByText("The server is busy.");
    expect(screen.getByText("A request is already in progress. Try again soon.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  test("Stop waiting aborts quietly", async () => {
    mockFetch(
      (init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    await renderForm();
    paste(RESUME);
    click("Extract profile");
    expect(screen.getByText(/Reading your resume/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Extract profile" }) as HTMLButtonElement).disabled).toBe(true);
    click("Stop waiting");
    await waitFor(() => expect(screen.queryByText(/Reading your resume/)).toBeNull());
    expect(screen.queryByText("The request failed")).toBeNull();
    expect(screen.queryByText("The server is busy.")).toBeNull();
  });
});
