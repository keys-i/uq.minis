/** Combine personal deadlines and followed club events into the same calendar */
import type { Modal, PlanProps } from "./model.ts";
import type { CalendarEvent } from "./dates.ts";
import React, { useState } from "react";
import { DAY, calendarEvents, format, onDay, weekStart } from "./dates.ts";
import { Icon } from "../shared/icons.tsx";
import { Button } from "../shared/controls.tsx";
import { TaskEditor } from "./planner.tsx";
import { useAnnouncements, Announcement } from "./feed.tsx";

type View = "week" | "month";

export function Buzzy({
  plan,
  change,
  modal,
  calendar,
  choose,
}: PlanProps & {
  modal: Modal;
  calendar: () => void;
  choose: (name: string) => void;
}) {
  const [offset, setOffset] = useState(0),
    [view, setView] = useState<View>("week"),
    feed = useAnnouncements(plan);
  const now = new Date(),
    month = new Date(now.getFullYear(), now.getMonth() + offset, 1),
    first = view === "week" ? weekStart(offset, now) : weekStart(0, month),
    days = view === "week" ? 7 : 42,
    end = new Date(first.getTime() + (days - 1) * DAY),
    events = calendarEvents(plan, feed.rows);
  const edit = (item: CalendarEvent) =>
    modal({
      title: item.title,
      body:
        item.kind === "club" ? (
          <Announcement item={item} />
        ) : (
          <TaskEditor item={item} plan={plan} change={change} close={() => modal(null)} />
        ),
    });
  return (
    <>
      <div className="toolbar">
        <div className="calendar-views" role="group" aria-label="Calendar view">
          {(["week", "month"] as const).map((name) => (
            <Button
              key={name}
              className={view === name ? "selected" : "secondary"}
              aria-pressed={view === name}
              onClick={() => {
                setView(name);
                setOffset(0);
              }}
            >
              {name === "week" ? "Week" : "Month"}
            </Button>
          ))}
        </div>
        <Button onClick={calendar}>
          <Icon name="buzzy" /> Subscribe to your calendar
        </Button>
      </div>
      {!plan.courses.length && (
        <div className="course-start">
          <Icon name="courses" />
          <p>Select your courses to bring their assessment deadlines into this calendar</p>
          <Button onClick={() => choose("scrappy")}>Select courses</Button>
        </div>
      )}
      <div className="toolbar">
        <div className="row calendar-controls">
          <Button
            className="secondary"
            aria-label={`Previous ${view}`}
            onClick={() => setOffset(offset - 1)}
          >
            ‹
          </Button>
          <strong>
            {view === "week"
              ? `${format(first)} – ${format(end)}`
              : format(month, { day: undefined, month: "long", year: "numeric" })}
          </strong>
          <Button
            className="secondary"
            aria-label={`Next ${view}`}
            onClick={() => setOffset(offset + 1)}
          >
            ›
          </Button>
          <Button className="quiet" onClick={() => setOffset(0)}>
            Today
          </Button>
        </div>
        <Button className="secondary" onClick={() => choose("clubby")}>
          Find society events
        </Button>
      </div>
      {feed.error && (
        <p className="rule-note">
          Society events couldn't refresh / saved events are still here{" "}
          <Button className="quiet" onClick={feed.retry}>
            Try again
          </Button>
        </p>
      )}
      <div
        className={`week ${view}`}
        role="grid"
        aria-label={`Buzzy ${view === "week" ? "weekly" : "monthly"} calendar`}
      >
        {Array.from({ length: days }, (_, i) => {
          const day = new Date(first.getTime() + i * DAY),
            rows = events.filter((item) => onDay(item, day)),
            outside = view === "month" && day.getMonth() !== month.getMonth();
          return (
            <section
              className={`day ${day.toDateString() === now.toDateString() ? "today" : ""} ${outside ? "outside" : ""}`}
              key={i}
              role="gridcell"
              aria-label={format(day, { weekday: "long" })}
            >
              <div className="day-header">
                {(view === "week" || i < 7) &&
                  format(day, { weekday: "short", day: undefined, month: undefined })}
                <span className="day-number">{day.getDate()}</span>
              </div>
              {rows.length ? (
                rows.map((item) => (
                  <Button
                    key={`${item.id}-${item.kind}`}
                    className={`event ${item.kind}`}
                    onClick={() => edit(item)}
                  >
                    <small>
                      {item.kind === "club"
                        ? item.club
                        : plan.courses.find((course) => course.id === item.course)?.code}
                    </small>
                    <strong>{item.title}</strong>
                    <span>{item.label}</span>
                    <time dateTime={item.when}>
                      {format(item.when, {
                        hour: "numeric",
                        minute: "2-digit",
                        day: undefined,
                        month: undefined,
                      })}
                    </time>
                  </Button>
                ))
              ) : view === "week" ? (
                <p className="day-empty">Room to breathe</p>
              ) : null}
            </section>
          );
        })}
      </div>
      <div className="legend">
        <span>Official deadline</span>
        <span>Your target</span>
        <span>Society event</span>
      </div>
    </>
  );
}
import "./buzzy.css";
