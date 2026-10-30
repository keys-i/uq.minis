import { marksSchema, profileSchema } from "./model.ts";
/** Turn accepted course assessments into personal targets without changing official deadlines */
import type {
  Assessment,
  Change,
  Course,
  Modal,
  Plan,
  PlanProps,
  SheetProps,
  Mark,
} from "./model.ts";
import React, { useEffect, useRef, useState } from "react";
import { api } from "../shared/api.ts";
import { DAY, deadline, format, localInput, personal, timestamp, weekStart } from "./dates.ts";
import { Icon } from "../shared/icons.tsx";
import { useNotice } from "../shared/notice.ts";
import { Button, Field, Empty, Link } from "../shared/controls.tsx";
import { syncProfile } from "./courses.ts";

const plannerViews = [
  ["tasks", "Assessments"],
  ["gantt", "Timeline"],
  ["marks", "Marks"],
];

const assessmentKinds = [
  ["exam", "Exam", "marks", /\b(exam|final)\b/i],
  ["quiz", "Quiz or test", "check", /\b(quiz|test|midsemester|mid-semester)\b/i],
  ["presentation", "Presentation", "volume", /\b(presentation|oral|pitch|demonstration)\b/i],
  ["project", "Project", "courses", /\b(project|capstone)\b/i],
  ["practical", "Practical", "look", /\b(practical|laboratory|lab)\b/i],
] as const;

function assessmentKind(title: string) {
  const match = assessmentKinds.find(([, , , pattern]) => pattern.test(title));
  return match || (["assignment", "Assignment", "planny"] as const);
}

export function Planner({
  plan,
  change,
  modal,
  courses,
}: PlanProps & { modal: Modal; courses: () => void }) {
  const [view, setView] = useState("tasks"),
    [offset, setOffset] = useState(0),
    [courseId, setCourseId] = useState(plan.courses[0]?.id || "");
  const report = useNotice((state) => state.report),
    coursesRef = useRef(plan.courses),
    profiles = plan.courses.map((course) => `${course.id}:${course.profile}`).join("|");
  coursesRef.current = plan.courses;
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const failed: string[] = [];
      await Promise.all(
        coursesRef.current
          .filter((course) => course.profile)
          .map(async (course) => {
            try {
              const draft = await api(
                "/api/profile",
                profileSchema,
                { url: course.profile },
                controller.signal,
              );
              if (controller.signal.aborted) return;
              await change((next) => {
                const current = next.courses.find((item) => item.id === course.id);
                if (current) syncProfile(next, current, draft);
              });
            } catch (error) {
              if ((error as Error).name !== "AbortError") failed.push(course.code);
            }
          }),
      );
      if (failed.length && !controller.signal.aborted)
        report(`${failed.join(", ")} assessments couldn't sync just now`, true);
    })();
    return () => controller.abort();
  }, [change, profiles, report]);
  const close = () => modal(null);
  const editTask = (item: Assessment) =>
    modal({
      title: item.title,
      body: <TaskEditor item={item} plan={plan} change={change} close={close} />,
    });
  if (!plan.courses.length)
    return (
      <Empty
        title="First, choose your courses"
        action={<Button onClick={courses}>Select courses in Scrappy</Button>}
      >
        Your selected courses bring their assessments, marks and deadlines together here
      </Empty>
    );
  const first = weekStart(offset),
    end = new Date(first.getTime() + 27 * DAY),
    selectedCourse = plan.courses.some((course) => course.id === courseId)
      ? courseId
      : plan.courses[0].id,
    visible = [...plan.assessments]
      .sort((a, b) => (a.due || "z").localeCompare(b.due || "z"))
      .slice(0, 100),
    openMarks = (id: string) => {
      setCourseId(id);
      setView("marks");
    };
  return (
    <>
      <div className="planner-nav">
        <div className="planner-tabs" aria-label="Planny views">
          {plannerViews.map(([id, label]) => (
            <button
              key={id}
              className={view === id ? "selected" : ""}
              onClick={() => setView(id)}
              aria-pressed={view === id}
            >
              <Icon name={id === "tasks" ? "planny" : id} />
              {label}
            </button>
          ))}
        </div>
        <Button className="quiet" onClick={courses}>
          Manage courses in Scrappy
        </Button>
      </div>
      {view !== "marks" && (
        <>
          <Nudgy buffer={plan.settings.buffer} assessments={plan.assessments} change={change} />
          <div className="toolbar">
            {view === "gantt" ? (
              <div className="row calendar-controls">
                <Button
                  className="secondary"
                  aria-label="Previous week"
                  onClick={() => setOffset(offset - 1)}
                >
                  ‹
                </Button>
                <strong>
                  {format(first)} – {format(end)}
                </strong>
                <Button
                  className="secondary"
                  aria-label="Next week"
                  onClick={() => setOffset(offset + 1)}
                >
                  ›
                </Button>
                <Button className="quiet" onClick={() => setOffset(0)}>
                  Today
                </Button>
              </div>
            ) : (
              <h2>Your assessments</h2>
            )}
          </div>
          {view === "gantt" ? (
            <Gantt plan={plan} first={first} edit={editTask} />
          ) : (
            <>
              {plan.assessments.length ? (
                <div className="course-tasks">
                  {plan.courses.map((course) => (
                    <CourseTasks
                      key={course.id}
                      course={course}
                      items={visible.filter((item) => item.course === course.id)}
                      buffer={plan.settings.buffer}
                      change={change}
                      edit={editTask}
                      marks={() => openMarks(course.id)}
                    />
                  ))}
                </div>
              ) : (
                <Empty title="Waiting for published assessments">
                  Planny will add them when UQ publishes the selected course profiles
                </Empty>
              )}
            </>
          )}
        </>
      )}
      {view === "marks" && (
        <Marks plan={plan} change={change} courseId={selectedCourse} select={setCourseId} />
      )}
    </>
  );
}

function CourseTasks({
  course,
  items,
  buffer,
  change,
  edit,
  marks,
}: {
  course: Course;
  items: Assessment[];
  buffer: number;
  change: Change;
  edit: (item: Assessment) => void;
  marks: () => void;
}) {
  const done = items.filter((item) => item.done).length;
  return (
    <section className="course-task-group" aria-labelledby={`course-${course.id}`}>
      <div className="course-task-head">
        <Button
          className="course-jump"
          aria-label={`View ${course.code} ${course.name} marks`}
          onClick={marks}
        >
          <span>
            <strong id={`course-${course.id}`}>{course.code}</strong>
            <span>{course.name}</span>
            <small>
              {done} of {items.length} complete
            </small>
          </span>
          <Icon name="marks" />
        </Button>
        {course.profile && (
          <span className="course-profile-link">
            <Link href={course.profile}>
              <img src="/api/brand/uq.png" alt="" loading="lazy" decoding="async" />
              <span className="sr-only">View {course.code} on UQ</span>
            </Link>
          </span>
        )}
      </div>
      {items.length ? (
        <div className="task-list">
          {items.map((item) => {
            const [kind, label, icon] = assessmentKind(item.title);
            return (
              <div
                className={`task-row ${item.done ? "task-done" : ""}`}
                data-kind={kind}
                key={item.id}
              >
                <span className="task-kind" role="img" aria-label={`${label} assessment`}>
                  <Icon name={icon} />
                </span>
                <div className="task-title">
                  <Button className={item.done ? "done-text" : ""} onClick={() => edit(item)}>
                    {item.title}
                  </Button>
                  <small>
                    {label} · Due {deadline(item, { hour: "numeric", minute: "2-digit" })}
                  </small>
                </div>
                {item.due && (
                  <span className="pill pink task-target">
                    Target {format(personal(item, buffer))}
                  </span>
                )}
                <span className="pill task-weight">{item.weight}%</span>
                <Button
                  className={`task-check ${item.done ? "is-done" : ""}`}
                  aria-label={`${item.done ? "Reopen" : "Complete"} ${item.title}`}
                  aria-pressed={item.done}
                  onClick={() =>
                    change((next) => {
                      next.assessments.find((row) => row.id === item.id)!.done = !item.done;
                    })
                  }
                >
                  {item.done ? "✓" : ""}
                </Button>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="course-task-empty">No published assessments yet</p>
      )}
    </section>
  );
}

function Nudgy({
  buffer,
  assessments,
  change,
}: {
  buffer: number;
  assessments: Assessment[];
  change: Change;
}) {
  const [value, setValue] = useState(buffer);
  useEffect(() => setValue(buffer), [buffer]);
  const sample = assessments.find(
    (item) => item.due && !item.done && item.buffer == null && Date.parse(item.due) >= Date.now(),
  );
  return (
    <section className="nudgy">
      <div>
        <span className="eyebrow">Personal target</span>
        <h2>{value ? `Finish ${value} days early` : "Use the official due date"}</h2>
        <p>Applies to every assessment unless you change it there</p>
      </div>
      <div className="nudgy-control">
        <input
          aria-label="Personal deadline head start in days"
          aria-valuetext={`${value} days${sample ? `, target ${format(personal(sample, value))}` : ""}`}
          type="range"
          min="0"
          max="14"
          value={value}
          onChange={(event) => setValue(Number(event.target.value))}
        />
        <output>
          {value}
          <small>days early</small>
        </output>
        <Button
          className="secondary"
          disabled={value === buffer}
          onClick={() =>
            change((plan) => {
              plan.settings.buffer = value;
            })
          }
        >
          {value === buffer ? "Saved" : "Use this"}
        </Button>
      </div>
      {sample && (
        <div className="nudge-preview">
          <small>Try it with {sample.title}</small>
          <strong>Target {format(personal(sample, value))}</strong>
          <span>Official due {format(sample.due)}</span>
        </div>
      )}
    </section>
  );
}

function Gantt({
  plan,
  first,
  edit,
}: {
  plan: Plan;
  first: Date;
  edit: (item: Assessment) => void;
}) {
  const position = (value?: string) =>
    Math.max(
      0,
      Math.min(1000, ((new Date(value || "").getTime() - first.getTime()) / (28 * DAY)) * 1000),
    );
  const rows = plan.assessments.filter(
    (item) =>
      item.due &&
      new Date(item.due) >= first &&
      new Date(item.start || personal(item, plan.settings.buffer)) <=
        new Date(first.getTime() + 28 * DAY),
  );
  return (
    <>
      <p className="muted">
        The runway is your head start; the pin marks the official deadline. Unless you set a start
        date, planning starts today
      </p>
      {rows.length ? (
        <div className="gantt">
          <div className="gantt-axis">
            <span>Assessment</span>
            <div className="gantt-days">
              {[0, 7, 14, 21, 27].map((day) => (
                <span key={day}>{format(new Date(first.getTime() + day * DAY))}</span>
              ))}
            </div>
          </div>
          {rows.map((item) => {
            const start = position(item.start || new Date().toISOString()),
              target = position(personal(item, plan.settings.buffer)),
              due = position(item.due);
            return (
              <div className="gantt-row" key={item.id}>
                <Button className="gantt-name" onClick={() => edit(item)}>
                  {plan.courses.find((course) => course.id === item.course)!.code}
                  <br />
                  {item.title}
                </Button>
                <div
                  className="gantt-track"
                  role="img"
                  aria-label={`${item.title}; target ${format(personal(item, plan.settings.buffer))}; official deadline ${format(item.due)}`}
                >
                  <span
                    className="runway"
                    style={{
                      left: `${Math.min(start, due) / 10}%`,
                      width: `${Math.max(2, due - start) / 10}%`,
                    }}
                  />
                  <span
                    className="headstart"
                    style={{ left: `${target / 10}%`, width: `${Math.max(0, due - target) / 10}%` }}
                  />
                  <span className="pin" style={{ left: `${Math.min(996, due) / 10}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty title="Nothing on this stretch yet">
          Move to another week to see the published assessment dates
        </Empty>
      )}
    </>
  );
}

export function TaskEditor({
  item,
  plan,
  change,
  close,
}: PlanProps & SheetProps & { item: Assessment }) {
  const report = useNotice((state) => state.report),
    [busy, setBusy] = useState(false),
    [team, setTeam] = useState(item.team ?? (item.factor ?? 1) !== 1);
  const course = plan.courses.find((row) => row.id === item.course)!;
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        const form = Object.fromEntries(new FormData(event.currentTarget));
        const result = {
          ...item,
          ...form,
          start: timestamp(form.start),
          team,
          factor: team ? Number(form.factor) : 1,
        };
        for (const key of ["score", "maximum", "penalty", "hurdle", "buffer"] as const) {
          if ((key === "score" || key === "hurdle" || key === "buffer") && form[key] === "")
            result[key] = null;
          else result[key] = Number(form[key]);
        }
        setBusy(true);
        try {
          await change((next) => {
            const index = next.assessments.findIndex((row) => row.id === item.id);
            if (index >= 0) next.assessments[index] = result;
          });
          close();
        } catch (error) {
          report((error as Error).message, true);
        } finally {
          setBusy(false);
        }
      }}
    >
      <section className="course-sheet">
        <div className="row">
          <span className="pill">{course.code}</span>
          <span className="pill">{item.weight}%</span>
        </div>
        <strong>{deadline(item, { hour: "numeric", minute: "2-digit" })}</strong>
        {item.notes && (
          <details>
            <summary>Published task details</summary>
            <p>{item.notes}</p>
          </details>
        )}
      </section>
      <div className="task-sections">
        <fieldset className="task-fields">
          <legend>Plan</legend>
          <div className="form-grid">
            <Field
              label="When you'd like to start"
              name="start"
              type="datetime-local"
              value={localInput(item.start)}
            />
            <Field
              label="Personal head start / blank uses Nudgy"
              name="buffer"
              type="number"
              min="0"
              step="any"
              value={item.buffer}
            />
          </div>
        </fieldset>
        <fieldset className="task-fields">
          <legend>Result</legend>
          <div className="form-grid">
            {[
              ["score", "Your mark / blank if unmarked"],
              ["maximum", "Marks available"],
              ["penalty", "Penalty / percentage points"],
            ].map(([key, label]) => (
              <Field
                key={key}
                label={label}
                name={key}
                type="number"
                min="0"
                step="any"
                value={item[key as "score" | "maximum" | "penalty"]}
              />
            ))}
          </div>
        </fieldset>
        <fieldset className="task-fields">
          <legend>Group project</legend>
          <label className="check-field">
            <input
              type="checkbox"
              name="team"
              checked={team}
              onChange={(event) => setTeam(event.target.checked)}
            />
            This is a group project
          </label>
          {team && (
            <Field
              label="Peer assessment factor (PAF)"
              name="factor"
              type="number"
              min="0"
              step="any"
              required
              value={item.factor ?? 1}
            />
          )}
        </fieldset>
        <fieldset className="task-fields">
          <legend>Course rules</legend>
          <div className="form-grid">
            <Field
              label="Hurdle minimum (%) / blank for none"
              name="hurdle"
              type="number"
              min="0"
              step="any"
              value={item.hurdle}
            />
            <Field label="Drop-lowest set / e.g. quizzes" name="group" value={item.group} />
          </div>
        </fieldset>
      </div>
      <div className="form-actions">
        <button disabled={busy}>{busy ? "Saving…" : "Save result and plan"}</button>
      </div>
    </form>
  );
}

function Marks({
  plan,
  change,
  courseId,
  select,
}: PlanProps & { courseId: string; select: (id: string) => void }) {
  const [estimate, setEstimate] = useState(75),
    [target, setTarget] = useState(plan.settings.target),
    [results, setResults] = useState<Record<string, Mark>>({}),
    report = useNotice((state) => state.report);
  const course = plan.courses.find((item) => item.id === courseId)!,
    result = results[course.id];
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(
      () =>
        api("/api/marks", marksSchema, { plan, estimate }, controller.signal)
          .then(setResults)
          .catch((error) => {
            if (error.name !== "AbortError") report((error as Error).message, true);
          }),
      80,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [plan, estimate]);
  return (
    <>
      <section className="marks-calculator">
        <h2>Marks calculator</h2>
        <div className="form-grid">
          <Field label="Course">
            <select value={course.id} onChange={(event) => select(event.target.value)}>
              {plan.courses.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.code} · {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Target course mark (%)">
            <input
              type="number"
              min="0"
              max="100"
              value={target}
              onChange={(event) => setTarget(Number(event.target.value))}
            />
          </Field>
          <Field label="Estimated mark on unmarked work (%)">
            <input
              type="number"
              min="0"
              max="100"
              value={estimate}
              onChange={(event) => setEstimate(Number(event.target.value))}
            />
          </Field>
        </div>
        <div className="form-actions">
          <Button
            className="secondary"
            onClick={() =>
              change((next) => {
                next.settings.target = target;
              })
            }
          >
            Save target
          </Button>
        </div>
      </section>
      {!result ? (
        <p>Calculating {course.code}…</p>
      ) : (
        <section className="marks-card">
          <div className="marks-head">
            <div>
              <span className="pill">{course.code}</span>
              <h2>{course.name}</h2>
              <small>
                {result.completed} of {result.count} results entered
              </small>
            </div>
            <div className="mark-number">
              {result.projection ?? "-"}
              {result.projection != null && "%"}
              <small> projected</small>
            </div>
          </div>
          <meter
            min="0"
            max="100"
            value={result.projection || 0}
            aria-label={`${course.code} projected percentage`}
          />
          {result.high != null && (
            <p>
              Possible range: {result.low}–{result.high}%.{" "}
              {result.required == null
                ? `Your ${plan.settings.target}% target isn't reachable under these inputs and rules`
                : `To reach ${plan.settings.target}%, you'd need about ${result.required}% raw marks across the remaining work`}
            </p>
          )}
          {result.warnings.map((warning) => (
            <p className="rule-note" key={warning}>
              {warning}
            </p>
          ))}
        </section>
      )}
    </>
  );
}
