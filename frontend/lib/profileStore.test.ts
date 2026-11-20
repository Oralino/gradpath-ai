import { afterEach, describe, expect, test, vi } from "vitest";
import {
  PROFILE_STORAGE_KEY,
  clearProfile,
  loadProfile,
  profileSize,
  saveProfile,
  validateProfile,
} from "@/lib/profileStore";
import { SAMPLE_PROFILE } from "@/lib/sampleProfile";
import type { UserProfile } from "@/lib/types";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const base = (over: Partial<UserProfile> = {}): UserProfile => ({
  skills: ["Python"],
  coursework: [],
  projects: [],
  experience: [],
  ...over,
});

describe("storage", () => {
  test("save then load round-trips, clear removes", () => {
    expect(loadProfile()).toBeNull();
    saveProfile(SAMPLE_PROFILE);
    const loaded = loadProfile();
    expect(loaded?.profile).toEqual(SAMPLE_PROFILE);
    expect(Number.isNaN(Date.parse(loaded!.savedAt))).toBe(false);
    clearProfile();
    expect(loadProfile()).toBeNull();
  });

  test("junk or a wrong shape is no profile", () => {
    for (const raw of [
      "not json",
      "null",
      "[]",
      JSON.stringify({ savedAt: "x" }),
      JSON.stringify({ savedAt: "x", profile: { skills: "Python" } }),
      JSON.stringify({ savedAt: "x", profile: { ...base(), projects: [{ name: 1 }] } }),
      JSON.stringify({ profile: base() }),
    ]) {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, raw);
      expect(loadProfile()).toBeNull();
    }
  });

  test("blocked storage never throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadProfile()).toBeNull();
    expect(saveProfile(base())).toBeNull();
    expect(() => clearProfile()).not.toThrow();
  });
});

describe("validateProfile", () => {
  test("the sample is valid", () => {
    expect(validateProfile(SAMPLE_PROFILE).errors).toEqual({});
  });

  test("empty optional fields are fine", () => {
    const { errors } = validateProfile(
      base({
        education: null,
        weekly_hours: null,
        timeline_weeks: null,
        experience: [{ role: "TA", organisation: null, description: "d" }],
      }),
    );
    expect(errors).toEqual({});
  });

  test("skill and list limits", () => {
    expect(validateProfile(base({ skills: ["a".repeat(201)] })).errors.skills).toBeTruthy();
    expect(validateProfile(base({ skills: ["a".repeat(200)] })).errors.skills).toBeUndefined();
    const many = Array.from({ length: 51 }, () => "x");
    expect(validateProfile(base({ skills: many })).errors.skills).toBeTruthy();
    const course = Array.from({ length: 31 }, () => "x");
    expect(validateProfile(base({ coursework: course })).errors.coursework).toBeTruthy();
  });

  test("hours and weeks", () => {
    expect(validateProfile(base({ weekly_hours: 0 })).errors.weekly_hours).toBeTruthy();
    expect(validateProfile(base({ weekly_hours: 81 })).errors.weekly_hours).toBeTruthy();
    expect(validateProfile(base({ weekly_hours: 2.5 })).errors.weekly_hours).toBeTruthy();
    expect(validateProfile(base({ weekly_hours: 80 })).errors.weekly_hours).toBeUndefined();
    expect(validateProfile(base({ timeline_weeks: 53 })).errors.timeline_weeks).toBeTruthy();
    expect(validateProfile(base({ timeline_weeks: Number.NaN })).errors.timeline_weeks).toBeTruthy();
  });

  test("project description, blank row, counts and technologies", () => {
    const project = (description: string) => ({ name: "n", description, technologies: [] });
    const long = validateProfile(base({ projects: [project("ok"), project("d".repeat(1201))] }));
    expect(long.errors["projects.1.description"]).toBeTruthy();
    expect(long.errors["projects.0.description"]).toBeUndefined();
    const blank = validateProfile(base({ projects: [{ name: " ", description: "", technologies: [] }] }));
    expect(blank.errors["projects.0"]).toMatch(/remove it/);
    const seven = Array.from({ length: 7 }, () => project("d"));
    expect(validateProfile(base({ projects: seven })).errors.projects).toBeTruthy();
    const techs = Array.from({ length: 16 }, () => "t");
    const tooMany = validateProfile(base({ projects: [{ name: "n", description: "d", technologies: techs }] }));
    expect(tooMany.errors["projects.0.technologies"]).toBeTruthy();
  });

  test("experience: blank row, missing role, count", () => {
    const e = validateProfile(
      base({
        experience: [
          { role: "", organisation: "", description: "" },
          { role: "", description: "d" },
        ],
      }),
    );
    expect(e.errors["experience.0"]).toBeTruthy();
    expect(e.errors["experience.1.role"]).toBeTruthy();
    const many = Array.from({ length: 7 }, () => ({ role: "r", description: "d" }));
    expect(validateProfile(base({ experience: many })).errors.experience).toBeTruthy();
  });

  test("size counts the omitted fields as null, like model_dump_json", () => {
    const empty: UserProfile = { skills: [], coursework: [], projects: [], experience: [] };
    const expected =
      '{"profile_id":null,"name":null,"education":null,"skills":[],"coursework":[],"projects":[],' +
      '"experience":[],"weekly_hours":null,"timeline_weeks":null,"note":null}';
    expect(profileSize(empty)).toBe(expected.length);
    expect(validateProfile(empty).size).toBe(expected.length);
  });

  test("a profile over 12,000 characters is an error", () => {
    const big = base({
      skills: Array.from({ length: 50 }, () => "s".repeat(200)),
      coursework: Array.from({ length: 30 }, () => "c".repeat(200)),
    });
    const { errors, size } = validateProfile(big);
    expect(size).toBeGreaterThan(12000);
    expect(errors.size).toBeTruthy();
  });
});

describe("code points", () => {
  test("150 emoji in a skill is accepted (300 UTF-16 units, 150 characters)", () => {
    expect(validateProfile(base({ skills: ["😀".repeat(150)] })).errors).toEqual({});
    expect(validateProfile(base({ skills: ["😀".repeat(201)] })).errors.skills).toBeTruthy();
  });

  test("the size limit is exactly 12,000 code points", () => {
    const coursework = Array.from({ length: 30 }, () => "c".repeat(100));
    const skills = Array.from({ length: 50 }, () => "s".repeat(200));
    const withFill = (len: number) => base({ skills, coursework: coursework.slice(0, 15).concat(["😀".repeat(len)]) });
    // find the filler length that lands on exactly 12,000
    const room = 12000 - profileSize(withFill(0));
    expect(room).toBeGreaterThan(0);
    expect(room).toBeLessThanOrEqual(200);
    expect(profileSize(withFill(room))).toBe(12000);
    expect(validateProfile(withFill(room)).errors.size).toBeUndefined();
    expect(validateProfile(withFill(room + 1)).errors.size).toBeTruthy();
  });
});

describe("loadProfile re-validates what it reads", () => {
  const store = (profile: unknown) =>
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify({ savedAt: "2026-01-01T00:00:00Z", profile }));

  test("extra keys are dropped, top level and per row", () => {
    store({
      ...base(),
      name: "Someone",
      projects: [{ name: "n", description: "d", technologies: ["t"], secret: 1 }],
      experience: [{ role: "r", description: "d", organisation: "o", email: "x" }],
    });
    const loaded = loadProfile();
    expect(loaded).not.toBeNull();
    expect(JSON.stringify(loaded!.profile)).not.toMatch(/Someone|secret|email/);
    expect(loaded!.profile.projects[0]).toEqual({ name: "n", description: "d", technologies: ["t"] });
  });

  test("a profile the backend would reject is no profile", () => {
    for (const bad of [
      base({ weekly_hours: 2.5 }),
      base({ weekly_hours: 81 }),
      base({ skills: ["a".repeat(201)] }),
      base({ skills: Array.from({ length: 51 }, () => "x") }),
      base({ projects: [{ name: "n", description: "d".repeat(1201), technologies: [] }] }),
      base({ projects: Array.from({ length: 7 }, () => ({ name: "n", description: "d", technologies: [] })) }),
    ]) {
      store(bad);
      expect(loadProfile()).toBeNull();
    }
  });
});
