import { courseInfoSchema } from "./model.ts";
/** Select courses and keep their published assessments synchronised with the private plan */
import type { Course, CourseInfo, Modal, Selection, PlanProps } from "./model.ts";
import React, { lazy, Suspense, useState } from "react";
import { api } from "../shared/api.ts";
import { enrol, years } from "./courses.ts";
const Research = lazy(() =>
  import("./research.tsx").then((module) => ({ default: module.Research })),
);
import { useNotice } from "../shared/notice.ts";
import { Button, Link } from "../shared/controls.tsx";
import { Icon } from "../shared/icons.tsx";

export function Courses({
  plan,
  change,
  modal,
  continuePlan,
}: PlanProps & { modal: Modal; continuePlan: () => void }) {
  const [compared, setCompared] = useState(new Set<string>()),
    report = useNotice((state) => state.report);
  const choose = async (row: Selection, known?: CourseInfo) => {
    const code = row.course_code || row.code || "";
    let info = known,
      lookupError = "";
    if (!info)
      try {
        info = await api(`/api/research/course?code=${encodeURIComponent(code)}`, courseInfoSchema);
      } catch (error) {
        lookupError = (error as Error).message;
      }
    await change((next) => {
      const selected = enrol(next, row);
      if (!info) return;
      const current = years(info.offerings).latest.find((item) => item.profile);
      Object.assign(selected, {
        profile: current?.profile || "",
        prerequisites: info.details["Pre-Requisites"] || row.readiness?.wording || "",
        notes: current ? `${current.period} / ${current.campus}` : "",
      });
    });
    if (!info)
      report(
        `${code} is saved, but Scrappy couldn't get its profile yet${lookupError ? ` / ${lookupError}` : ""}`,
        true,
      );
  };
  const remove = async (course: Course) => {
    if (!confirm(`Remove ${course.code} and all its assessments and marks?`)) return;
    await change((next) => {
      next.courses = next.courses.filter((row) => row.id !== course.id);
      next.assessments = next.assessments.filter((row) => row.course !== course.id);
    });
  };
  const compare = async () => {
    if (compared.size < 2) throw new Error("Select two or three courses to compare");
    const rows = [];
    for (const code of compared)
      rows.push(await api(`/api/research/course?code=${code}`, courseInfoSchema));
    modal({
      title: "Compare course requirements",
      body: (
        <div className="comparison">
          {rows.map(({ course, details, url, official_error }) => (
            <section className="course-sheet" key={url}>
              <span className="pill">{course?.code || details["Course Code"]}</span>
              <h3>{course?.name || details["Course Name"]}</h3>
              {official_error && <p className="rule-note">Live requirements couldn't refresh</p>}
              {[
                ["Units", "Units"],
                ["Pre-Requisites", "Required before enrolment"],
                ["Assumed Background", "Assumed knowledge"],
                ["Incompatibles", "Can't count together"],
              ].map(([key, label]) => (
                <p key={key}>
                  <strong>{label}</strong>
                  <br />
                  {details[key] || "Check the course profile"}
                </p>
              ))}
              <Link href={url}>Official requirements</Link>
            </section>
          ))}
        </div>
      ),
    });
  };
  return (
    <>
      <section className="selected-courses" aria-label="Your selected courses">
        <div className="section-head">
          <h2>
            {plan.courses.length
              ? `Your courses / ${plan.courses.length}`
              : "Choose your courses first"}
          </h2>
          {plan.courses.length > 0 && <Button onClick={continuePlan}>Plan my assessments</Button>}
        </div>
        {!plan.courses.length && (
          <p>
            Search by course code or describe what you need. Scrappy gets the latest published
            assessments ready for you
          </p>
        )}
        {plan.courses.map((course) => (
          <article key={course.id} className="selected-course">
            <div>
              <span className="pill">{course.code}</span>
              <h3>{course.name}</h3>
              {course.notes && <p className="muted">{course.notes.split("\n")[0]}</p>}
            </div>
            <div className="row course-actions">
              <Link href={course.profile}>
                <img src="/api/brand/uq.png" alt="" loading="lazy" decoding="async" />
                <span className="sr-only">View {course.code} on UQ</span>
              </Link>
              <Button
                className="danger"
                aria-label={`Remove ${course.code}`}
                onClick={() => remove(course)}
              >
                <Icon name="close-small" />
              </Button>
            </div>
          </article>
        ))}
      </section>
      <div className="section-head">
        <h2>Find a course</h2>
        {compared.size > 0 && (
          <Button className="secondary" disabled={compared.size < 2} onClick={compare}>
            Compare courses ({compared.size})
          </Button>
        )}
      </div>
      <Suspense fallback={<p role="status">Opening course research…</p>}>
        <Research
          plan={plan}
          change={change}
          choose={choose}
          compared={compared}
          toggle={(code, checked) => {
            const next = new Set(compared);
            if (checked) {
              if (next.size === 3) {
                report("Compare up to three courses at a time");
                return;
              }
              next.add(code);
            } else next.delete(code);
            setCompared(next);
          }}
        />
      </Suspense>
    </>
  );
}
