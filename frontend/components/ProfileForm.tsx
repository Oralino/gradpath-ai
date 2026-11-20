"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { CharCount } from "@/components/CharCount";
import { DashIcon, InfoIcon, OctagonIcon } from "@/components/icons";
import { ResumeImport } from "@/components/ResumeImport";
import { StatusBadge } from "@/components/StatusBadge";
import { primaryButton, secondaryButton, textButton } from "@/components/buttonStyles";
import {
  LONG_MAX,
  MAX_COURSEWORK,
  MAX_EXPERIENCE,
  MAX_PROFILE_CHARS,
  MAX_PROJECTS,
  MAX_SKILLS,
  SHORT_MAX,
  clearProfile,
  loadProfile,
  profileSize,
  saveProfile,
  validateProfile,
} from "@/lib/profileStore";
import { charCount } from "@/lib/charCount";
import { SAMPLE_PROFILE } from "@/lib/sampleProfile";
import type { ResumeImport as ResumeImportResult, UserProfile } from "@/lib/types";

// The form edits text. Lists are kept as text (one per line, comma-separated) and converted on
// save, so typing a comma or a new line never fights the user. Rows carry a local id for React keys.
interface ProjectDraft {
  key: number;
  name: string;
  description: string;
  technologies: string;
}
interface ExperienceDraft {
  key: number;
  role: string;
  organisation: string;
  description: string;
}
interface Draft {
  education: string;
  skills: string;
  coursework: string;
  projects: ProjectDraft[];
  experience: ExperienceDraft[];
  weeklyHours: string;
  timelineWeeks: string;
}

const BLANK: Draft = {
  education: "",
  skills: "",
  coursework: "",
  projects: [],
  experience: [],
  weeklyHours: "",
  timelineWeeks: "",
};

const inputClass = (error: boolean) =>
  `w-full rounded-md border bg-surface px-3 py-2 text-body ${error ? "border-stopped" : "border-line"}`;

const lines = (text: string) =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
const commas = (text: string) =>
  text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
const optional = (text: string) => (text.trim() === "" ? null : text.trim());
const optionalNumber = (text: string) => (text.trim() === "" ? null : Number(text));

// Draft text to the UserProfile that is validated, counted and saved. Trims values and drops empty
// lines and technologies. Blank rows are kept so validateProfile can ask to fill or remove them.
function toProfile(d: Draft): UserProfile {
  return {
    education: optional(d.education),
    skills: lines(d.skills),
    coursework: lines(d.coursework),
    projects: d.projects.map((p) => ({
      name: p.name.trim(),
      description: p.description.trim(),
      technologies: commas(p.technologies),
    })),
    experience: d.experience.map((e) => ({
      role: e.role.trim(),
      organisation: optional(e.organisation),
      description: e.description.trim(),
    })),
    weekly_hours: optionalNumber(d.weeklyHours),
    timeline_weeks: optionalNumber(d.timelineWeeks),
  };
}

let nextKey = 1;

// A UserProfile back into editable text (loading the saved or sample profile).
function toDraft(p: UserProfile): Draft {
  return {
    education: p.education ?? "",
    skills: p.skills.join("\n"),
    coursework: p.coursework.join("\n"),
    projects: p.projects.map((x) => ({
      key: nextKey++,
      name: x.name,
      description: x.description,
      technologies: x.technologies.join(", "),
    })),
    experience: p.experience.map((x) => ({
      key: nextKey++,
      role: x.role,
      organisation: x.organisation ?? "",
      description: x.description,
    })),
    weeklyHours: p.weekly_hours == null ? "" : String(p.weekly_hours),
    timelineWeeks: p.timeline_weeks == null ? "" : String(p.timeline_weeks),
  };
}

// One labelled input or textarea with help, an error linked by aria-describedby and an optional
// counter (DESIGN.md, Field). Used by every field in ProfileForm.
function Field({
  id,
  label,
  value,
  onChange,
  error,
  help,
  max,
  rows,
  type = "text",
  range,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  help?: string;
  max?: number;
  rows?: number;
  type?: "text" | "number";
  range?: [number, number];
}) {
  const describedBy = [help ? `${id}-help` : "", max ? `${id}-count` : "", error ? `${id}-error` : ""]
    .filter(Boolean)
    .join(" ");
  const common = {
    id,
    value,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy || undefined,
    className: inputClass(Boolean(error)),
  };
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-label">
        {label}
      </label>
      {rows ? (
        <textarea {...common} rows={rows} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input
          {...common}
          type={type}
          inputMode={type === "number" ? "numeric" : undefined}
          step={type === "number" ? 1 : undefined}
          min={range?.[0]}
          max={range?.[1]}
          // A number input reports "" for text it cannot parse: pass a marker so validation
          // shows an error instead of silently treating the field as empty.
          onChange={(e) => onChange(e.target.validity.badInput ? "?" : e.target.value)}
        />
      )}
      {help && (
        <p id={`${id}-help`} className="text-meta text-ink-muted">
          {help}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="flex items-center gap-1 text-meta text-stopped">
          <OctagonIcon size={14} />
          {error}
        </p>
      )}
      {max ? <CharCount id={`${id}-count`} value={charCount(value)} max={max} /> : null}
    </div>
  );
}

// A repeated group (projects, experience): legend with the count, rows, then the Add button, which
// is hidden at the limit. Used twice by ProfileForm.
function Group({
  id,
  title,
  count,
  max,
  error,
  addLabel,
  onAdd,
  children,
}: {
  id: string;
  title: string;
  count: number;
  max: number;
  error?: string;
  addLabel: string;
  onAdd: () => void;
  children: ReactNode;
}) {
  return (
    <fieldset id={id} tabIndex={-1} className="space-y-3">
      <legend className="text-label">
        {title} ({count} of {max})
      </legend>
      {error && (
        <p className="flex items-center gap-1 text-meta text-stopped">
          <OctagonIcon size={14} />
          {error}
        </p>
      )}
      {children}
      {count < max && (
        <p>
          <button type="button" className={textButton} onClick={onAdd}>
            {addLabel}
          </button>
        </p>
      )}
    </fieldset>
  );
}

// A single row's fieldset with its accessible name ("Project 2") and Remove button.
function Row({
  id,
  name,
  error,
  onRemove,
  children,
}: {
  id: string;
  name: string;
  error?: string;
  onRemove: () => void;
  children: ReactNode;
}) {
  return (
    <fieldset
      id={id}
      tabIndex={-1}
      aria-describedby={error ? `${id}-error` : undefined}
      className="space-y-3 rounded-md border border-rule bg-sunken p-3"
    >
      <legend className="px-1 text-label">{name}</legend>
      {error && (
        <p id={`${id}-error`} className="flex items-center gap-1 text-meta text-stopped">
          <OctagonIcon size={14} />
          {error}
        </p>
      )}
      {children}
      <button type="button" className={textButton} onClick={onRemove} aria-label={`Remove ${name}`}>
        Remove
      </button>
    </fieldset>
  );
}

// The element id a validation path points to ("projects.1.name" is the second project name
// input), used for the error summary links.
function fieldId(path: string, d: Draft): string {
  const [group, index, field] = path.split(".");
  if (group === "weekly_hours") return "weekly-hours";
  if (group === "timeline_weeks") return "timeline-weeks";
  if (group === "size") return "profile-size";
  if (group === "projects" || group === "experience") {
    const row = (group === "projects" ? d.projects : d.experience)[Number(index)];
    if (index === undefined || !row) return `${group}-group`;
    const prefix = `${group === "projects" ? "project" : "experience"}-${row.key}`;
    return field ? `${prefix}-${field}` : prefix;
  }
  return group;
}

// The Profile screen's form (DESIGN.md, Screens 4). Reads and writes only localStorage through
// lib/profileStore and makes no API calls. User text renders as input values or React text only.
export function ProfileForm() {
  const [ready, setReady] = useState(false);
  const [started, setStarted] = useState(false);
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [isSample, setIsSample] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  // Errors show only after the first save attempt, then follow every edit.
  const [attempted, setAttempted] = useState(false);
  const [summaryNonce, setSummaryNonce] = useState(0);
  const [saveFailed, setSaveFailed] = useState(false);
  // Set by a resume import: drives the review badge, the left-out notes and the live message.
  const [fromResume, setFromResume] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const [live, setLive] = useState("");

  const summaryRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  // Element id to focus after the next render (a new row, or the empty state after Clear).
  const pendingFocus = useRef<string | null>(null);

  // Read the saved profile after mount, not during render, so the server and client HTML match.
  useEffect(() => {
    const saved = loadProfile();
    if (saved) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setDraft(toDraft(saved.profile));
      setSavedAt(saved.savedAt);
      setStarted(true);
    }
    setReady(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  // Focus the error summary after a failed save (DESIGN.md, States).
  useEffect(() => {
    if (summaryNonce > 0) summaryRef.current?.focus();
  }, [summaryNonce]);

  // Move focus queued by an add or a clear once the new element exists.
  useEffect(() => {
    if (!pendingFocus.current) return;
    document.getElementById(pendingFocus.current)?.focus();
    pendingFocus.current = null;
  });

  // Every field change goes through here, as an updater on the latest draft: the sample badge goes
  // away and the saved line is stale.
  function edit(change: (d: Draft) => Draft) {
    setDraft(change);
    setIsSample(false);
    setDirty(true);
    setSaveFailed(false);
  }

  function loadSample() {
    setDraft(toDraft(SAMPLE_PROFILE));
    setIsSample(true);
    setFromResume(false);
    setNotes([]);
    setDirty(true);
    setAttempted(false);
    setSaveFailed(false);
    setStarted(true);
  }

  // Replace the draft with a resume import, keeping the hours and weeks (a resume has neither).
  // Called by ResumeImport. Nothing is saved until "Save profile".
  function applyImport(result: ResumeImportResult) {
    setDraft((prev) => ({
      ...toDraft(result.profile),
      weeklyHours: prev.weeklyHours,
      timelineWeeks: prev.timelineWeeks,
    }));
    setIsSample(false);
    setFromResume(true);
    setNotes(result.notes);
    setDirty(true);
    setAttempted(false);
    setSaveFailed(false);
    setStarted(true);
    setLive("Profile filled from your resume. Review it, then save.");
    pendingFocus.current = "education";
  }

  function startBlank() {
    setDraft(BLANK);
    setAttempted(false);
    setStarted(true);
  }

  function setField(change: Partial<Draft>) {
    edit((d) => ({ ...d, ...change }));
  }

  function updateProject(key: number, change: Partial<ProjectDraft>) {
    edit((d) => ({ ...d, projects: d.projects.map((p) => (p.key === key ? { ...p, ...change } : p)) }));
  }

  function updateExperience(key: number, change: Partial<ExperienceDraft>) {
    edit((d) => ({
      ...d,
      experience: d.experience.map((e) => (e.key === key ? { ...e, ...change } : e)),
    }));
  }

  // Validate, then save; on errors nothing is saved and the summary takes focus.
  function save() {
    setAttempted(true);
    if (Object.keys(validateProfile(toProfile(draft)).errors).length > 0) {
      setSummaryNonce((c) => c + 1);
      return;
    }
    const saved = saveProfile(toProfile(draft));
    if (!saved) {
      setSaveFailed(true);
      setSummaryNonce((c) => c + 1);
      return;
    }
    setSaveFailed(false);
    setSavedAt(saved.savedAt);
    setDirty(false);
    setFromResume(false);
    setNotes([]);
  }

  function confirmClear() {
    clearProfile();
    dialogRef.current?.close();
    setDraft(BLANK);
    setStarted(false);
    setIsSample(false);
    setSavedAt(null);
    setDirty(false);
    setAttempted(false);
    setSaveFailed(false);
    setFromResume(false);
    setNotes([]);
    pendingFocus.current = "profile-empty";
  }

  const profile = toProfile(draft);
  const size = profileSize(profile);
  const errors = attempted ? validateProfile(profile).errors : {};
  // One summary line per error entry, each linking to its field.
  const summary = Object.entries(errors).map(([path, message]) => ({
    path,
    message,
    href: `#${fieldId(path, draft)}`,
  }));

  const infoPanel = (
    <div className="rounded-md border-l-4 border-info bg-info-bg p-4 text-small">
      Stored only in this browser. It is sent to the GradPath server only when you build a plan. Leave out
      contact details.
    </div>
  );

  const importPanel = <ResumeImport hasUnsavedEdits={started && dirty} onImported={applyImport} />;
  const liveRegion = (
    <div role="status" className="sr-only">
      {live}
    </div>
  );

  // One return for every state, so the resume panel and the live region mount once and are not
  // remounted when the first import leaves the empty state (the live region must exist before its
  // text changes to be announced).
  return (
    <div className="space-y-6">
      {infoPanel}
      {ready && importPanel}
      {liveRegion}
      {ready && !started && (
        <div className="space-y-3 rounded-md border border-rule bg-surface p-4 sm:p-6">
    <p id="profile-empty" tabIndex={-1}>
      No profile saved in this browser.
    </p>
    <p className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <button type="button" className={secondaryButton} onClick={loadSample}>
        Load sample profile
      </button>
      <button type="button" className={textButton} onClick={startBlank}>
        Start from blank
      </button>
    </p>
  </div>
      )}
      {ready && started && (
        <>
      <form
        className="space-y-6 rounded-md border border-rule bg-surface p-4 sm:p-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        {(summary.length > 0 || saveFailed) && (
          <div ref={summaryRef} tabIndex={-1} role="alert" className="rounded-md border-l-4 border-stopped bg-stopped-bg p-4">
            <p className="flex items-center gap-2 text-label text-stopped">
              <OctagonIcon size={16} />
              Fix these before saving
            </p>
            <ul className="mt-2 list-disc pl-5 text-small">
              {summary.map((item) => (
                <li key={item.path}>
                  <a href={item.href} className="underline underline-offset-4">
                    {item.message}
                  </a>
                </li>
              ))}
              {saveFailed && <li>This browser would not save the profile (storage may be blocked).</li>}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={secondaryButton} onClick={loadSample}>
            Load sample profile
          </button>
          <button
            type="button"
            className={`${secondaryButton} border-stopped text-stopped`}
            onClick={() => dialogRef.current?.showModal()}
          >
            Clear profile
          </button>
          {isSample && (
            <StatusBadge tone="neutral" icon={<DashIcon />}>
              Sample (fictional)
            </StatusBadge>
          )}
          {fromResume && (
            <StatusBadge tone="info" icon={<InfoIcon />}>
              From your resume: review before saving
            </StatusBadge>
          )}
          <span className="ml-auto">
            <CharCount id="profile-size" value={size} max={MAX_PROFILE_CHARS} />
          </span>
        </div>

        {fromResume && notes.length > 0 && (
          <div className="space-y-1 rounded-md border-l-4 border-caution bg-caution-bg p-3 text-small">
            <p className="text-label">Some details were left out:</p>
            <ul className="list-disc pl-5">
              {notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          </div>
        )}

        <Field
          id="education"
          label="Education"
          value={draft.education}
          onChange={(v) => setField({ education: v })}
          error={errors.education}
          help={`Optional, up to ${SHORT_MAX} characters.`}
        />
        <Field
          id="skills"
          label="Skills"
          rows={5}
          value={draft.skills}
          onChange={(v) => setField({ skills: v })}
          error={errors.skills}
          help={`One per line (up to ${MAX_SKILLS}).`}
        />
        <Field
          id="coursework"
          label="Coursework"
          rows={4}
          value={draft.coursework}
          onChange={(v) => setField({ coursework: v })}
          error={errors.coursework}
          help={`One per line (up to ${MAX_COURSEWORK}).`}
        />

        <Group
          id="projects-group"
          title="Projects"
          count={draft.projects.length}
          max={MAX_PROJECTS}
          error={errors.projects}
          addLabel="+ Add project"
          onAdd={() => {
            const key = nextKey++;
            pendingFocus.current = `project-${key}-name`;
            edit((d) => ({
              ...d,
              projects: [...d.projects, { key, name: "", description: "", technologies: "" }],
            }));
          }}
        >
          {draft.projects.map((p, i) => {
            const path = `projects.${i}`;
            const id = `project-${p.key}`;
            return (
              <Row
                key={p.key}
                id={id}
                name={`Project ${i + 1}`}
                error={errors[path]}
                onRemove={() => {
                  edit((d) => ({ ...d, projects: d.projects.filter((x) => x.key !== p.key) }));
                  document.getElementById("projects-group")?.focus();
                }}
              >
                <Field
                  id={`${id}-name`}
                  label="Name"
                  value={p.name}
                  onChange={(v) => updateProject(p.key, { name: v })}
                  error={errors[`${path}.name`]}
                />
                <Field
                  id={`${id}-description`}
                  label="Description"
                  rows={4}
                  max={LONG_MAX}
                  value={p.description}
                  onChange={(v) => updateProject(p.key, { description: v })}
                  error={errors[`${path}.description`]}
                />
                <Field
                  id={`${id}-technologies`}
                  label="Technologies"
                  value={p.technologies}
                  onChange={(v) => updateProject(p.key, { technologies: v })}
                  error={errors[`${path}.technologies`]}
                  help="Comma-separated, up to 15."
                />
              </Row>
            );
          })}
        </Group>

        <Group
          id="experience-group"
          title="Experience"
          count={draft.experience.length}
          max={MAX_EXPERIENCE}
          error={errors.experience}
          addLabel="+ Add experience"
          onAdd={() => {
            const key = nextKey++;
            pendingFocus.current = `experience-${key}-role`;
            edit((d) => ({
              ...d,
              experience: [...d.experience, { key, role: "", organisation: "", description: "" }],
            }));
          }}
        >
          {draft.experience.map((e, i) => {
            const path = `experience.${i}`;
            const id = `experience-${e.key}`;
            return (
              <Row
                key={e.key}
                id={id}
                name={`Experience ${i + 1}`}
                error={errors[path]}
                onRemove={() => {
                  edit((d) => ({ ...d, experience: d.experience.filter((x) => x.key !== e.key) }));
                  document.getElementById("experience-group")?.focus();
                }}
              >
                <Field
                  id={`${id}-role`}
                  label="Role"
                  value={e.role}
                  onChange={(v) => updateExperience(e.key, { role: v })}
                  error={errors[`${path}.role`]}
                />
                <Field
                  id={`${id}-organisation`}
                  label="Organisation (optional)"
                  value={e.organisation}
                  onChange={(v) => updateExperience(e.key, { organisation: v })}
                  error={errors[`${path}.organisation`]}
                />
                <Field
                  id={`${id}-description`}
                  label="Description"
                  rows={4}
                  max={LONG_MAX}
                  value={e.description}
                  onChange={(v) => updateExperience(e.key, { description: v })}
                  error={errors[`${path}.description`]}
                />
              </Row>
            );
          })}
        </Group>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="weekly-hours"
            label="Weekly study hours"
            type="number"
            value={draft.weeklyHours}
            onChange={(v) => setField({ weeklyHours: v })}
            range={[1, 80]}
            error={errors.weekly_hours}
            help="Optional, 1 to 80."
          />
          <Field
            id="timeline-weeks"
            label="Timeline in weeks"
            type="number"
            value={draft.timelineWeeks}
            onChange={(v) => setField({ timelineWeeks: v })}
            range={[1, 52]}
            error={errors.timeline_weeks}
            help="Optional, 1 to 52."
          />
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          {savedAt && !dirty && (
            <p className="mr-auto text-meta text-ink-muted">
              Saved in this browser, {new Date(savedAt).toLocaleTimeString()}
            </p>
          )}
          {dirty && <p className="mr-auto text-meta text-ink-muted">Not saved yet.</p>}
          <button type="submit" className={primaryButton}>
            Save profile
          </button>
        </div>
      </form>

      <dialog ref={dialogRef} aria-labelledby="clear-title" className="rounded-md border border-line bg-surface p-6 text-ink backdrop:bg-black/50">
        <div className="space-y-4">
          <h2 id="clear-title" className="text-heading">
            Clear your profile?
          </h2>
          <p className="text-small">This removes the saved profile from this browser. It cannot be undone.</p>
          <div className="flex flex-wrap justify-end gap-3">
            <button type="button" className={secondaryButton} onClick={() => dialogRef.current?.close()}>
              Keep profile
            </button>
            <button type="button" className={`${secondaryButton} border-stopped text-stopped`} onClick={confirmClear}>
              Yes, clear profile
            </button>
          </div>
        </div>
      </dialog>
        </>
      )}
    </div>
  );
}
