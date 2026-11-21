import { inLocal } from "@/components/serverFixtures";
import { afterEach, beforeAll, describe, expect, test } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ProfileForm } from "@/components/ProfileForm";
import { PROFILE_STORAGE_KEY, loadProfile, saveProfile } from "@/lib/profileStore";
import { SAMPLE_PROFILE } from "@/lib/sampleProfile";

// jsdom may lack the dialog methods: minimal stand-ins that toggle the open attribute.
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
  window.localStorage.clear();
});

const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const type = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function renderForm() {
  render(inLocal(<ProfileForm />));
  await screen.findByText(/Stored only in this browser/);
}

describe("empty state", () => {
  test("the sample fills the fields with a badge that goes away on edit", async () => {
    await renderForm();
    expect(screen.getByText("No profile saved in this browser.")).toBeTruthy();
    click("Load sample profile");
    expect((screen.getByLabelText("Education") as HTMLInputElement).value).toBe(SAMPLE_PROFILE.education);
    expect(screen.getByText("Sample (fictional)")).toBeTruthy();
    expect(screen.getByText("Projects (2 of 6)")).toBeTruthy();
    expect(screen.getByText("Experience (1 of 6)")).toBeTruthy();
    type("Education", "Changed");
    expect(screen.queryByText("Sample (fictional)")).toBeNull();
  });

  test("start from blank shows an empty form", async () => {
    await renderForm();
    click("Start from blank");
    expect(screen.getByText("Projects (0 of 6)")).toBeTruthy();
    expect(screen.getByText(/\/ 12,000/)).toBeTruthy();
  });
});

describe("saving", () => {
  test("edit then save writes localStorage and shows the saved line", async () => {
    await renderForm();
    click("Start from blank");
    type("Education", "  BSc  ");
    type("Skills", "Python\n\n  SQL  \n");
    click("+ Add project");
    type("Name", "App");
    type("Description", "Does things");
    type("Technologies", "Flask, , SQLite ");
    type("Weekly study hours", "5");
    click("Save profile");
    expect(screen.getByText(/Saved in this browser,/)).toBeTruthy();
    expect(loadProfile()?.profile).toEqual({
      education: "BSc",
      skills: ["Python", "SQL"],
      coursework: [],
      projects: [{ name: "App", description: "Does things", technologies: ["Flask", "SQLite"] }],
      experience: [],
      weekly_hours: 5,
      timeline_weeks: null,
    });
  });

  test("invalid input shows the summary and saves nothing", async () => {
    await renderForm();
    click("Start from blank");
    click("+ Add project");
    type("Weekly study hours", "81");
    click("Save profile");
    const alert = screen.getByRole("alert");
    expect(within(alert).getAllByRole("listitem").length).toBe(2);
    expect(window.localStorage.getItem(PROFILE_STORAGE_KEY)).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(alert));
    expect(screen.getByLabelText("Weekly study hours").getAttribute("aria-invalid")).toBe("true");
  });

  test("a saved profile is shown on load with its saved line", async () => {
    saveProfile(SAMPLE_PROFILE);
    await renderForm();
    expect((screen.getByLabelText("Education") as HTMLInputElement).value).toBe(SAMPLE_PROFILE.education);
    expect(screen.getByText(/Saved in this browser,/)).toBeTruthy();
    expect(screen.queryByText("Sample (fictional)")).toBeNull();
  });
});

describe("repeated groups", () => {
  test("add and remove projects with the count; Add is hidden at 6", async () => {
    await renderForm();
    click("Start from blank");
    for (let i = 0; i < 6; i++) click("+ Add project");
    expect(screen.getByText("Projects (6 of 6)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "+ Add project" })).toBeNull();
    click("Remove Project 6");
    expect(screen.getByText("Projects (5 of 6)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "+ Add project" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Project 2" })).toBeTruthy();
  });

  test("experience rows add and remove", async () => {
    await renderForm();
    click("Start from blank");
    click("+ Add experience");
    expect(screen.getByText("Experience (1 of 6)")).toBeTruthy();
    click("Remove Experience 1");
    expect(screen.getByText("Experience (0 of 6)")).toBeTruthy();
  });
});

describe("clear", () => {
  test("cancel keeps the profile, confirm removes it", async () => {
    saveProfile(SAMPLE_PROFILE);
    await renderForm();
    click("Clear profile");
    const dialog = document.querySelector("dialog[aria-labelledby=clear-title]") as HTMLDialogElement;
    expect(dialog.hasAttribute("open")).toBe(true);
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep profile" }));
    expect(dialog.hasAttribute("open")).toBe(false);
    expect(loadProfile()).not.toBeNull();

    click("Clear profile");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Yes, clear profile" }));
    });
    expect(loadProfile()).toBeNull();
    expect(screen.getByText("No profile saved in this browser.")).toBeTruthy();
  });
});

describe("errors follow edits", () => {
  test("no errors before the first save; removing a row drops its error, the other keeps its own", async () => {
    await renderForm();
    click("Start from blank");
    click("+ Add project");
    click("+ Add project");
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.change(screen.getAllByLabelText("Name")[1], { target: { value: "Second" } });
    click("Save profile");
    let items = within(screen.getByRole("alert")).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "Project 1 is empty. Fill it in or remove it.",
      "Project 2: description is required.",
    ]);
    expect(within(items[1]).getByRole("link").getAttribute("href")).toMatch(/^#project-\d+-description$/);
    click("Remove Project 1");
    items = within(screen.getByRole("alert")).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["Project 1: description is required."]);
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Fixed" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("a number that is not a whole number in range is an error, not dropped", async () => {
    await renderForm();
    click("Start from blank");
    type("Timeline in weeks", "2.5");
    click("Save profile");
    expect(screen.getByRole("alert").textContent).toMatch(/Timeline in weeks/);
    expect(screen.getByLabelText("Timeline in weeks").getAttribute("max")).toBe("52");
  });
});

describe("focus", () => {
  test("a new row takes focus on its first input; Clear moves focus to the empty state", async () => {
    saveProfile(SAMPLE_PROFILE);
    await renderForm();
    click("+ Add project");
    await waitFor(() => expect(document.activeElement?.id).toMatch(/^project-\d+-name$/));
    click("Clear profile");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Yes, clear profile" }));
    });
    await waitFor(() => expect(document.activeElement?.id).toBe("profile-empty"));
  });
});
