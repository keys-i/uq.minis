import { acknowledgement } from "../shared/schema.ts";
import {
  courseInfoSchema,
  researchSchema,
  teacherSchema,
  teachersSchema,
  trailSchema,
} from "./model.ts";
import { Motion } from "../shared/display.tsx";
import type {
  Plan,
  Change,
  CourseInfo,
  Metric,
  Readiness,
  ResearchResult,
  Review,
  Selection,
  Subject,
  Trail,
  TrailNode,
} from "./model.ts";
import React, { useContext, useEffect, useId, useRef, useState } from "react";
import { api } from "../shared/api.ts";
import { badges } from "./courses.ts";
import { connected, layout } from "./trail.ts";
import { T } from "../shared/language.tsx";
import { Picker } from "../shared/picker.tsx";
import { Icon } from "../shared/icons.tsx";

const categories = [
  ["overall", "Overall"],
  ["usefulness", "Usefulness"],
  ["fun", "Fun"],
  ["difficulty", "Difficulty"],
  ["secat", "Course feedback"],
];
const statuses: Record<string, string> = {
  ready: "Prerequisites met",
  missing: "A few steps to go",
  review: "Requirements need checking",
  incompatible: "Clashes with a completed course",
};

export function CourseMap({
  info,
  open,
  graph,
}: {
  info: CourseInfo;
  open: (code: string) => void;
  graph?: Trail | null;
}) {
  const title = useId(),
    [hovered, setHovered] = useState("");
  const code = info.details?.["Course Code"] || info.course?.code || "";
  const nodes: TrailNode[] = graph?.nodes || [
    {
      code,
      name: info.course?.name || code,
      required: info.readiness.required,
      wording: info.readiness.wording,
      loaded: true,
      depth: 0,
    },
    ...info.readiness.required.map((code) => ({
      code,
      name: code,
      required: [],
      loaded: false,
      depth: 1,
    })),
  ];
  const { width, height, points } = layout(nodes),
    active = hovered ? connected(nodes, hovered) : null;
  const branches = new Map<string, number>(),
    root = nodes.find((node) => node.code === code);
  function branch(current: string, colour: number, seen = new Set<string>()) {
    if (seen.has(current)) return;
    seen.add(current);
    if (!branches.has(current)) branches.set(current, colour);
    for (const item of nodes.find((node) => node.code === current)?.required || [])
      branch(item, colour, seen);
  }
  root?.required.forEach((item, i) => branch(item, i % 5));
  const edges = useRef<HTMLCanvasElement>(null),
    { scheme } = useContext(Motion);
  useEffect(() => {
    const canvas = edges.current,
      context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    // Match the HTML nodes' resolved border colours, including dark and forced-colour modes
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.scale(ratio, ratio);
    context.lineWidth = 3;
    for (const node of nodes)
      for (const item of node.required) {
        const from = points.get(item),
          to = points.get(node.code);
        if (!from || !to) continue;
        const branch = branches.get(item) || 0;
        const sample = canvas.parentElement?.querySelector<HTMLElement>(
          `.trail-node.branch-${branch}`,
        );
        context.strokeStyle = sample ? getComputedStyle(sample).borderTopColor : "#397b9f";
        context.globalAlpha = !active || (active.has(item) && active.has(node.code)) ? 1 : 0.22;
        context.beginPath();
        context.moveTo(from.x + 98, from.y);
        context.bezierCurveTo(from.x + 150, from.y, to.x - 150, to.y, to.x - 98, to.y);
        context.stroke();
      }
  }, [width, height, nodes, points, active, scheme]);
  const focused = nodes.find((node) => node.code === hovered);
  return (
    <section className="trail" aria-labelledby={title}>
      <h3 id={title}>
        <T>Prerequisite tree</T>
      </h3>
      <p className="muted">
        Follow the coloured branches / hover or focus a course to trace its path
      </p>
      <div
        className="trail-scroll"
        tabIndex={0}
        role="region"
        aria-label="Scrollable prerequisite tree"
      >
        <div className="prerequisite-tree" style={{ width, height }}>
          <canvas ref={edges} className="trail-links" aria-hidden="true" />
          {nodes.map((node) => {
            const point = points.get(node.code)!,
              completed = (info.readiness.known || info.readiness.completed || []).includes(
                node.code,
              );
            return (
              <button
                type="button"
                key={node.code}
                className={`trail-node branch-${branches.get(node.code) || 0}${node.code === code ? " current" : ""}${active && !active.has(node.code) ? " is-muted" : ""}`}
                style={{ left: point.x, top: point.y }}
                onPointerEnter={() => setHovered(node.code)}
                onPointerLeave={() => setHovered("")}
                onFocus={() => setHovered(node.code)}
                onBlur={() => setHovered("")}
                onClick={() => open(node.code)}
                aria-label={`${node.code} / ${node.name}${completed ? " / completed" : ""}`}
              >
                <b dir="ltr">{node.code}</b>
                <span>{node.name}</span>
                <small>
                  {completed
                    ? "Completed"
                    : node.code === code
                      ? statuses[info.readiness.status]
                      : node.loaded
                        ? "View requirements"
                        : "Open to check requirements"}
                </small>
              </button>
            );
          })}
        </div>
      </div>
      <p className="prereq-wording" dir="auto">
        <strong>{focused?.code || code}</strong> ·{" "}
        {focused
          ? focused.wording ||
            (focused.loaded
              ? "No prerequisite wording stated"
              : "Requirements not loaded / open this course to check")
          : info.readiness.wording || "No prerequisite wording available yet"}
      </p>
      {/\bor\b/i.test(info.readiness.wording) && (
        <small>Some branches are alternatives / follow the rule above</small>
      )}
      {graph?.limited && (
        <p className="rule-note">
          Some deeper requirements aren't loaded yet / open a course to continue its tree
        </p>
      )}
    </section>
  );
}

function Score({ name, value }: { name: string; value?: Metric }) {
  if (value?.mean == null) return null;
  return (
    <span className="review-score">
      <small>
        <T>{name}</T>
      </small>
      <strong>
        {value.mean}
        <small> / 5</small>
      </strong>
      <meter min="0" max="5" value={value.mean} aria-label={name} />
      <small>
        {value.count} {value.count === 1 ? "rating" : "ratings"}
      </small>
    </span>
  );
}

function Rating({ value }: { value?: Metric }) {
  return (
    <div
      className={`minis-rating${value?.mean == null ? " is-unrated" : ""}`}
      aria-label={
        value?.mean == null
          ? "No rating yet"
          : `${value.mean} out of 5, ${value.confidence} evidence`
      }
    >
      <Icon name="star" />
      <div>
        <strong>
          {value?.mean ?? "-"}
          <small>{value?.mean != null && "/ 5"}</small>
        </strong>
        {value?.mean == null && <span>Not rated yet</span>}
      </div>
      {value?.mean != null && (
        <small>
          {
            (
              { strong: "More evidence", building: "Taking shape", early: "Early days" } as Record<
                string,
                string
              >
            )[value.confidence || ""]
          }
        </small>
      )}
    </div>
  );
}

export function Requirements({
  value,
  detailed = false,
}: {
  value: Readiness;
  detailed?: boolean;
}) {
  return (
    <div className="requirements" data-status={value.status}>
      <p className="requirement-status">
        <Icon
          name={
            value.status === "ready"
              ? "check"
              : value.status === "incompatible"
                ? "warning"
                : "courses"
          }
        />
        <strong>
          <T>{statuses[value.status]}</T>
        </strong>
      </p>
      {value.missing.length > 0 && (
        <div className="requirement-codes">
          {value.missing.map((code) => (
            <span key={code} dir="ltr">
              {code}
            </span>
          ))}
        </div>
      )}
      {value.incompatible.length > 0 && (
        <p className="requirement-alert">
          <Icon name="warning" />
          {value.incompatible.join(", ")}
        </p>
      )}
      {value.restrictions && (
        <div className="requirement-alert">
          <Icon name="lock" />
          <div>
            <strong>Restricted entry</strong>
            <p>
              <T original>{value.restrictions}</T>
            </p>
          </div>
        </div>
      )}
      {detailed && (
        <div className="knowledge-meaning">
          <h3>Required before enrolment</h3>
          <p>
            <T original>{value.wording || "Not confirmed yet / check the course profile"}</T>
          </p>
          <h3>Assumed knowledge</h3>
          <p>
            <T original>{value.assumed || "Not stated in the saved course details"}</T>
          </p>
          <small>Background you're expected to know / separate from formal prerequisites</small>
        </div>
      )}
      {detailed && !!value.topics?.length && (
        <div className="course-skills">
          <h3>Skills & topics to brush up on</h3>
          <p className="muted">Mentioned in the course text / a starting point for preparation</p>
          <div className="course-badges">
            {value.topics?.map((topic) => (
              <span className="pill mint" key={topic}>
                {topic}
              </span>
            ))}
          </div>
        </div>
      )}
      {detailed && value.skills.length > 0 && <p>Familiar topics: {value.skills.join(", ")}</p>}
    </div>
  );
}

function Knowledge({
  plan,
  change,
  run,
}: {
  plan: Plan;
  change: Change;
  run: (action: () => Promise<unknown>) => void;
}) {
  return (
    <details className="knowledge">
      <summary>
        <T>What you already know</T>
        <span>{plan.settings.completed?.length || 0} completed courses</span>
      </summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          run(() =>
            change((next) => {
              next.settings.completed = String(values.get("completed"))
                .toUpperCase()
                .split(/[\s,;]+/)
                .filter(Boolean);
              next.settings.skills = String(values.get("skills"));
            }),
          );
        }}
      >
        <div className="form-grid">
          <label className="field">
            <span>
              <T>Completed courses</T>
            </span>
            <textarea
              name="completed"
              defaultValue={(plan.settings.completed || []).join(", ")}
              placeholder="CSSE1001, MATH1051"
              maxLength={6000}
            />
          </label>
          <label className="field">
            <span>
              <T>Skills and topics you know</T>
            </span>
            <textarea
              name="skills"
              defaultValue={plan.settings.skills || ""}
              placeholder="Python, calculus, academic writing…"
              maxLength={6000}
            />
          </label>
        </div>
        <p className="muted">
          Skills highlight relevant topics; they don't replace formal prerequisites
        </p>
        <button>Save my starting point</button>
      </form>
    </details>
  );
}

export function Research({
  plan,
  change,
  choose,
  compared,
  toggle,
}: {
  plan: Plan;
  change: Change;
  choose: (row: Selection, info?: CourseInfo) => Promise<void>;
  compared: Set<string>;
  toggle: (code: string, checked: boolean) => void;
}) {
  const [query, setQuery] = useState(""),
    [faculty, setFaculty] = useState(""),
    [metric, setMetric] = useState(""),
    [order, setOrder] = useState(""),
    [minimum, setMinimum] = useState(1),
    [target, setTarget] = useState("course"),
    [offset, setOffset] = useState(0),
    [version, setVersion] = useState(0),
    [evidence, setEvidence] = useState(false);
  const [result, setResult] = useState<ResearchResult>({
      rows: [],
      total: 0,
      faculties: [],
      study_year: new Date().getFullYear(),
    }),
    [selected, setSelected] = useState(""),
    [detail, setDetail] = useState<CourseInfo | null>(null),
    [teacher, setTeacher] = useState<{
      name: string;
      faculty: string;
      metrics: Subject["metrics"];
      reviews: Review[];
    } | null>(null),
    [graph, setGraph] = useState<Trail | null>(null),
    [graphError, setGraphError] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [preparing, setPreparing] = useState(false),
    [loading, setLoading] = useState(true);
  const origin = useRef<HTMLButtonElement>(null),
    prepared = useRef(false);
  function openCourse(code: string, event?: React.MouseEvent<HTMLButtonElement>) {
    if (event) origin.current = event.currentTarget;
    setEvidence(false);
    setSelected(code);
    setTeacher(null);
  }
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    setOffset(0);
  }, [query, faculty, metric, order, minimum, target]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(
      () => {
        setLoading(true);
        api(
          `/api/research?${new URLSearchParams({ q: query, faculty, metric, order, minimum: String(minimum), offset: String(offset), target })}`,
          target === "course" ? researchSchema : teachersSchema,
          undefined,
          controller.signal,
        )
          .then((data) => {
            setResult(data);
            setError("");
          })
          .catch((error) => {
            if (error.name !== "AbortError") setError(error.message);
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });
      },
      query ? 100 : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    query,
    faculty,
    metric,
    order,
    minimum,
    offset,
    target,
    version,
    plan.settings.completed,
    plan.settings.skills,
  ]);
  useEffect(() => {
    if (loading || result.updated || result.rows.length || error || prepared.current) return;
    const controller = new AbortController();
    prepared.current = true;
    setPreparing(true);
    api("/api/research/refresh", acknowledgement, {}, controller.signal)
      .then(() => setVersion((value) => value + 1))
      .catch((error) => {
        if (error.name !== "AbortError") {
          prepared.current = false;
          setError((error as Error).message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setPreparing(false);
      });
    return () => controller.abort();
  }, [error, loading, result.rows.length, result.updated]);
  useEffect(() => {
    if (!selected) {
      setDetail(null);
      origin.current?.focus();
      return;
    }
    const controller = new AbortController();
    setDetail(null);
    api(
      `/api/research/course?code=${encodeURIComponent(selected)}`,
      courseInfoSchema,
      undefined,
      controller.signal,
    )
      .then((data) => {
        setDetail(data);
        setVersion((value) => value + 1);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, [selected, plan.settings.completed, plan.settings.skills]);
  useEffect(() => {
    setGraph(null);
    setGraphError("");
    if (
      !evidence ||
      !detail ||
      (detail.course?.code || detail.details?.["Course Code"]) !== selected
    )
      return;
    const controller = new AbortController();
    api(
      `/api/research/trail?code=${encodeURIComponent(selected)}`,
      trailSchema,
      undefined,
      controller.signal,
    )
      .then(setGraph)
      .catch((error) => {
        if (error.name !== "AbortError") setGraphError(error.message);
      });
    return () => controller.abort();
  }, [selected, detail, evidence]);
  useEffect(() => {
    if (detail) document.getElementById("course-detail")?.focus({ preventScroll: false });
  }, [detail]);
  async function showTeacher(id: string) {
    setSelected("");
    setTeacher(await api(`/api/research/professor?id=${encodeURIComponent(id)}`, teacherSchema));
  }
  return (
    <section className="research">
      <div className="research-search">
        <label className="field">
          <span>
            <T>What would you like to study?</T>
          </span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find fun first year coding courses…"
            maxLength={500}
          />
        </label>
        <div className="query-picks">
          {["fun first year coding", "easiest statistics", "highest rated"].map((text) => (
            <button type="button" className="quiet" key={text} onClick={() => setQuery(text)}>
              <T>{text}</T>
            </button>
          ))}
        </div>
      </div>
      <details className="research-options">
        <summary>Refine results</summary>
        <div className="research-filters">
          <Picker
            label="Look for"
            value={target}
            onChange={(value) => {
              setTarget(value);
              setMetric("");
              setFaculty("");
              setSelected("");
              setTeacher(null);
            }}
            options={[
              ["course", "Courses"],
              ["professor", "Professors"],
            ]}
          />
          <Picker
            label="Faculty"
            value={faculty}
            onChange={setFaculty}
            options={[
              ["", "All faculties"],
              ...result.faculties.map((item) => [item, item] as const),
            ]}
          />
          <Picker
            label="Rank by"
            value={metric}
            onChange={setMetric}
            options={[
              ["", "Understand my search"],
              ...categories
                .filter(([key]) => target === "course" || !["secat", "overall"].includes(key))
                .map(
                  ([key, label]) =>
                    [
                      key,
                      target === "professor" && key === "usefulness"
                        ? "Teaching quality"
                        : target === "professor" && key === "fun"
                          ? "Rapport"
                          : label,
                    ] as [string, string],
                ),
            ]}
          />
          <Picker
            label="Order"
            value={order}
            onChange={setOrder}
            options={[
              ["", "From my search"],
              ["desc", "Highest first"],
              ["asc", "Lowest first"],
            ]}
          />
          <label className="evidence-range">
            <span>
              At least <output>{minimum}</output> {minimum === 1 ? "rating" : "ratings"}
            </span>
            <input
              type="range"
              min="1"
              max="50"
              value={minimum}
              aria-label="Minimum ratings for ranking"
              onChange={(event) => setMinimum(Number(event.target.value))}
            />
          </label>
        </div>
        <Knowledge plan={plan} change={change} run={run} />
      </details>
      <div className="research-meta">
        <p role="status">
          {preparing
            ? "Getting the course catalogue…"
            : loading
              ? "Finding your next subject…"
              : `${result.total} matches`}
          {target === "course" &&
            result.semester &&
            ` · ${result.semester === "summer" ? "Summer" : `Sem ${result.semester}`}, ${result.study_year}`}
        </p>
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error}
          <button
            type="button"
            className="quiet"
            onClick={() => {
              setVersion((value) => value + 1);
              setSelected("");
            }}
          >
            Try again
          </button>
        </p>
      )}
      {selected && !detail && !error && <p role="status">Opening {selected}'s requirements…</p>}
      {detail && (
        <article className="research-detail" id="course-detail" tabIndex={-1}>
          <div className="section-head">
            <div>
              <span className="pill" dir="ltr">
                {selected}
              </span>
              <h2>{detail.course?.name || detail.details?.["Course Name"]}</h2>
            </div>
            <button type="button" className="secondary" onClick={() => setSelected("")}>
              Close course
            </button>
          </div>
          {detail.official_error && <p className="rule-note">{detail.official_error}</p>}
          <p>
            <T original>{detail.course?.description || detail.details?.Description || ""}</T>
          </p>
          <Requirements value={detail.readiness} />
          <div className="row">
            <button
              type="button"
              disabled={busy || plan.courses.some((course) => course.code === selected)}
              onClick={() =>
                run(() =>
                  choose(
                    {
                      course_code: selected,
                      course_name: detail.course?.name || detail.details?.["Course Name"],
                    },
                    detail,
                  ),
                )
              }
            >
              {plan.courses.some((course) => course.code === selected) ? "Selected" : "Add course"}
            </button>
            <a href={detail.url} target="_blank" rel="noopener noreferrer">
              Official course page
            </a>
          </div>
          <p className="muted">
            Prerequisites are a guide / availability, permission and assumed knowledge still need
            checking
          </p>
          <details
            className="course-evidence"
            onToggle={(event) => setEvidence(event.currentTarget.open)}
          >
            <summary>Requirements and student feedback</summary>
            <Requirements value={detail.readiness} detailed />
            <CourseMap info={detail} open={setSelected} graph={graph} />
            {!graph && !graphError && <p role="status">Following the earlier branches…</p>}
            {graphError && (
              <p className="rule-note">
                The deeper tree couldn’t load / open a prerequisite to inspect it
              </p>
            )}
            {detail.secat.length > 0 && (
              <section>
                <h3>Course feedback</h3>
                <div className="secat-results">
                  {detail.secat.map((item) => (
                    <div key={`${item.period}:${item.question}`}>
                      <strong>{item.mean}/5</strong>
                      <span>
                        {item.question}
                        <small>
                          {item.period} / {item.count} responses
                        </small>
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}
            {!!detail.feedback?.count && (
              <p className="feedback-summary">
                <Icon name="star" />
                {detail.feedback?.mean?.toFixed(1)} / 5 from {detail.feedback?.count} additional
                student {detail.feedback?.count === 1 ? "rating" : "ratings"}
              </p>
            )}
            <ReviewList reviews={detail.reviews} />
          </details>
        </article>
      )}
      {teacher && (
        <article className="research-detail">
          <div className="section-head">
            <h2>{teacher.name}</h2>
            <button type="button" className="secondary" onClick={() => setTeacher(null)}>
              Close professor
            </button>
          </div>
          <p>{teacher.faculty}</p>
          <div className="review-dimensions">
            <Score name="Teaching quality" value={teacher.metrics.usefulness} />
            <Score name="Difficulty" value={teacher.metrics.difficulty} />
            <Score name="Rapport" value={teacher.metrics.fun} />
          </div>
          <ReviewList reviews={teacher.reviews} />
        </article>
      )}
      <div className="research-results" aria-busy={loading}>
        {result.rows.map((row) => (
          <article className="research-course" key={row.code}>
            <div className="course-heading">
              <div className="course-identity">
                <img src="/api/brand/uq.png" alt="UQ" loading="lazy" decoding="async" />
                <span dir="ltr">{target === "course" ? row.code : "Professor"}</span>
              </div>
              {target === "course" && <Rating value={row.metrics.overall} />}
            </div>
            <h3>
              <button
                type="button"
                className="card-open"
                onClick={(event) =>
                  target === "course"
                    ? openCourse(row.code, event)
                    : run(() => showTeacher(row.code))
                }
              >
                <T>{row.name}</T>
              </button>
            </h3>
            <p className="course-faculty">
              <T>{row.faculty}</T>
            </p>
            {row.description && (
              <p className="course-description">
                <T>{row.description}</T>
              </p>
            )}
            {row.offered && (
              <div className="course-badges" aria-label="When and where">
                {badges(row.offered).map((label) => (
                  <span className="pill" key={label}>
                    {label}
                  </span>
                ))}
                {row.year && row.year < result.study_year && <small>Last offered {row.year}</small>}
              </div>
            )}
            <div className="review-dimensions">
              {(target === "course"
                ? categories.filter(([key]) => ["usefulness", "fun", "difficulty"].includes(key))
                : [
                    ["usefulness", "Teaching quality"],
                    ["difficulty", "Difficulty"],
                    ["fun", "Rapport"],
                  ]
              ).map(([key, name]) => (
                <Score key={key} name={name} value={row.metrics[key]} />
              ))}
            </div>
            {target === "course" && (
              <>
                {row.readiness && <Requirements value={row.readiness} />}
                <div className="research-rank">
                  <button
                    type="button"
                    disabled={busy || plan.courses.some((course) => course.code === row.code)}
                    onClick={() => run(() => choose(row))}
                  >
                    {plan.courses.some((course) => course.code === row.code)
                      ? "Selected"
                      : "Add course"}
                  </button>
                  <button
                    type="button"
                    className="quiet"
                    onClick={(event) => openCourse(row.code, event)}
                  >
                    Course details
                  </button>
                  <button
                    type="button"
                    className="quiet"
                    aria-pressed={compared.has(row.code)}
                    onClick={() => toggle(row.code, !compared.has(row.code))}
                  >
                    {compared.has(row.code) ? "Comparing" : "Compare"}
                  </button>
                </div>
              </>
            )}
          </article>
        ))}
      </div>
      {!loading && !preparing && !result.rows.length && (
        <p className="empty">
          {result.updated
            ? "Try a course code, a broader topic or a different rating category"
            : "The course catalogue hasn't arrived yet"}
        </p>
      )}
      {result.total > 30 && (
        <div className="toolbar">
          <button
            type="button"
            className="secondary"
            disabled={offset === 0 || loading}
            onClick={() => setOffset((value) => Math.max(0, value - 30))}
          >
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + 30, result.total)}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={offset + 30 >= result.total || loading}
            onClick={() => setOffset((value) => value + 30)}
          >
            Next 30
          </button>
        </div>
      )}
    </section>
  );
}

function ReviewList({ reviews }: { reviews: Review[] }) {
  const [limit, setLimit] = useState(10);
  return (
    <section className="review-list">
      <h3>Student experiences</h3>
      {!reviews.length && <p>No written experiences yet</p>}
      {reviews.slice(0, limit).map((item) => (
        <article key={item.id}>
          <div className="row">
            <small>{item.date && new Date(item.date).toLocaleDateString()}</small>
            {item.professor && <strong>{item.professor}</strong>}
          </div>
          <p>
            <T source={item.text ? "auto" : "en"} original>
              {item.text || "Rating only"}
            </T>
          </p>
          <div className="review-dimensions">
            <Score
              name={item.target === "professor" ? "Teaching quality" : "Usefulness"}
              value={{ mean: item.usefulness, count: 1 }}
            />
            <Score name="Fun" value={{ mean: item.fun, count: 1 }} />
            <Score name="Difficulty" value={{ mean: item.difficulty, count: 1 }} />
          </div>
          <a href={item.url} target="_blank" rel="noopener noreferrer">
            Read full review
          </a>
        </article>
      ))}
      {limit < reviews.length && (
        <button type="button" className="secondary" onClick={() => setLimit((value) => value + 10)}>
          Read 10 more
        </button>
      )}
    </section>
  );
}
