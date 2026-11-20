// The saved profile: stored only in this browser (localStorage), plus the limits that mirror the
// backend's UserProfile (backend/src/gradpath/workflows/schemas.py). Used by ProfileForm and the
// Ask tray. Every storage access is guarded because storage can be blocked (private mode).

import { charCount } from "@/lib/charCount";
import type { UserProfile } from "@/lib/types";

export const PROFILE_STORAGE_KEY = "gradpath-profile";

export const SHORT_MAX = 200;
export const LONG_MAX = 1200;
export const MAX_SKILLS = 50;
export const MAX_COURSEWORK = 30;
export const MAX_PROJECTS = 6;
export const MAX_TECHNOLOGIES = 15;
export const MAX_EXPERIENCE = 6;
export const MAX_PROFILE_CHARS = 12_000;

export interface SavedProfile {
  profile: UserProfile;
  savedAt: string; // ISO time
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isStringArray = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");
const isOptString = (v: unknown) => v === undefined || v === null || typeof v === "string";
const isOptNumber = (v: unknown) => v === undefined || v === null || typeof v === "number";

// Shape check for parsed storage content; called by loadProfile. A wrong shape counts as no profile.
function isUserProfile(v: unknown): v is UserProfile {
  if (!isObject(v)) return false;
  if (!isOptString(v.education) || !isStringArray(v.skills) || !isStringArray(v.coursework)) return false;
  if (!isOptNumber(v.weekly_hours) || !isOptNumber(v.timeline_weeks)) return false;
  if (!Array.isArray(v.projects) || !Array.isArray(v.experience)) return false;
  const projectsOk = v.projects.every(
    (p) =>
      isObject(p) &&
      typeof p.name === "string" &&
      typeof p.description === "string" &&
      isStringArray(p.technologies),
  );
  const experienceOk = v.experience.every(
    (e) =>
      isObject(e) &&
      typeof e.role === "string" &&
      typeof e.description === "string" &&
      isOptString(e.organisation),
  );
  return projectsOk && experienceOk;
}

// Copy only the known fields (top level and per row) into a fresh object, so extra stored keys are
// never sent to the server. Called by loadProfile after the shape check.
function pickKnownFields(p: UserProfile): UserProfile {
  return {
    education: p.education,
    skills: [...p.skills],
    coursework: [...p.coursework],
    projects: p.projects.map((x) => ({
      name: x.name,
      description: x.description,
      technologies: [...x.technologies],
    })),
    experience: p.experience.map((x) => ({
      role: x.role,
      organisation: x.organisation,
      description: x.description,
    })),
    weekly_hours: p.weekly_hours,
    timeline_weeks: p.timeline_weeks,
  };
}

/** The saved profile, or null when none is saved, storage is blocked or the content is junk. */
export function loadProfile(): SavedProfile | null {
  try {
    const raw = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    if (!raw) return null;
    const data: unknown = JSON.parse(raw);
    if (!isObject(data) || typeof data.savedAt !== "string" || !isUserProfile(data.profile)) return null;
    const profile = pickKnownFields(data.profile);
    // A stored profile the backend would reject is treated as no profile.
    if (Object.keys(validateProfile(profile).errors).length > 0) return null;
    return { profile, savedAt: data.savedAt };
  } catch {
    return null;
  }
}

/** Save the profile with the current time. Returns the saved record, or null if storage failed. */
export function saveProfile(profile: UserProfile): SavedProfile | null {
  const saved: SavedProfile = { profile, savedAt: new Date().toISOString() };
  try {
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(saved));
    return saved;
  } catch {
    return null;
  }
}

export function clearProfile(): void {
  try {
    window.localStorage.removeItem(PROFILE_STORAGE_KEY);
  } catch {
    // Storage blocked: nothing was saved, so nothing to clear.
  }
}

/**
 * Length of the profile as the backend measures it: len(model_dump_json()), which is compact JSON
 * with the fields the form omits (profile_id, name, note) and unset optionals as null. Called by
 * the form's counter and validateProfile. JSON.stringify gives the same character count.
 */
export function profileSize(profile: UserProfile): number {
  return charCount(
    JSON.stringify({
    profile_id: null,
    name: null,
    education: profile.education ?? null,
    skills: profile.skills,
    coursework: profile.coursework,
    projects: profile.projects.map((p) => ({
      name: p.name,
      description: p.description,
      technologies: p.technologies,
    })),
    experience: profile.experience.map((e) => ({
      role: e.role,
      organisation: e.organisation ?? null,
      description: e.description,
    })),
    weekly_hours: profile.weekly_hours ?? null,
    timeline_weeks: profile.timeline_weeks ?? null,
    note: null,
  }),
  );
}

const isBlank = (s: string | null | undefined) => !s || s.trim() === "";
const n = (value: number) => value.toLocaleString("en-US");

// One message when text is empty-but-required or too long; used by validateProfile.
function textError(label: string, value: string | null | undefined, max: number, required: boolean): string | null {
  const len = charCount((value ?? "").trim());
  if (len === 0) return required ? `${label} is required.` : null;
  return len > max ? `${label} is over the ${n(max)} character limit.` : null;
}

// Limits for a one-per-line list (skills, coursework): count first, then each line's length.
function listError(label: string, items: string[], maxCount: number): string | null {
  if (items.length > maxCount) return `Add at most ${maxCount} ${label}s, one per line.`;
  if (items.some((item) => charCount(item.trim()) > SHORT_MAX)) {
    return `Each ${label} must be ${SHORT_MAX} characters or fewer.`;
  }
  return null;
}

/**
 * Apply the backend's limits to a profile and report one message per field, keyed by path
 * ("projects.1.description"). Optional fields may be empty. A fully blank project or experience
 * row is one error on the row ("projects.0"). Called by ProfileForm before saving.
 */
export function validateProfile(profile: UserProfile): { errors: Record<string, string>; size: number } {
  const errors: Record<string, string> = {};
  const put = (key: string, message: string | null) => {
    if (message) errors[key] = message;
  };

  put("education", textError("Education", profile.education, SHORT_MAX, false));
  put("skills", listError("skill", profile.skills, MAX_SKILLS));
  put("coursework", listError("coursework item", profile.coursework, MAX_COURSEWORK));

  if (profile.projects.length > MAX_PROJECTS) errors.projects = `Add at most ${MAX_PROJECTS} projects.`;
  profile.projects.forEach((p, i) => {
    const row = `projects.${i}`;
    if (isBlank(p.name) && isBlank(p.description) && p.technologies.every(isBlank)) {
      errors[row] = `Project ${i + 1} is empty. Fill it in or remove it.`;
      return;
    }
    put(`${row}.name`, textError(`Project ${i + 1}: name`, p.name, SHORT_MAX, true));
    put(`${row}.description`, textError(`Project ${i + 1}: description`, p.description, LONG_MAX, true));
    if (p.technologies.length > MAX_TECHNOLOGIES) {
      errors[`${row}.technologies`] = `Project ${i + 1}: add at most ${MAX_TECHNOLOGIES} technologies.`;
    } else if (p.technologies.some((t) => charCount(t.trim()) > SHORT_MAX)) {
      errors[`${row}.technologies`] = `Project ${i + 1}: each technology must be ${SHORT_MAX} characters or fewer.`;
    }
  });

  if (profile.experience.length > MAX_EXPERIENCE) {
    errors.experience = `Add at most ${MAX_EXPERIENCE} experience entries.`;
  }
  profile.experience.forEach((e, i) => {
    const row = `experience.${i}`;
    if (isBlank(e.role) && isBlank(e.organisation) && isBlank(e.description)) {
      errors[row] = `Experience ${i + 1} is empty. Fill it in or remove it.`;
      return;
    }
    put(`${row}.role`, textError(`Experience ${i + 1}: role`, e.role, SHORT_MAX, true));
    put(`${row}.organisation`, textError(`Experience ${i + 1}: organisation`, e.organisation, SHORT_MAX, false));
    put(`${row}.description`, textError(`Experience ${i + 1}: description`, e.description, LONG_MAX, true));
  });

  for (const [key, label, max] of [
    ["weekly_hours", "Weekly study hours", 80],
    ["timeline_weeks", "Timeline in weeks", 52],
  ] as const) {
    const value = profile[key];
    if (value !== null && value !== undefined && (!Number.isInteger(value) || value < 1 || value > max)) {
      errors[key] = `${label} must be a whole number from 1 to ${max}.`;
    }
  }

  const size = profileSize(profile);
  if (size > MAX_PROFILE_CHARS) {
    errors.size = `The whole profile is over the ${n(MAX_PROFILE_CHARS)} character limit. Shorten some fields.`;
  }
  return { errors, size };
}
