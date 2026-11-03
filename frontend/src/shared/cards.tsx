import type { Announcement, Club } from "../study/model.ts";
import React, { useState } from "react";
import { T } from "./language.tsx";
import { format } from "../study/dates.ts";
import { Icon } from "./icons.tsx";

function Picture({
  src,
  alt = "",
  className = "",
}: {
  src?: string;
  alt?: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  return src && !failed ? (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  ) : null;
}

function Artwork({
  banner,
  logo,
  name,
  children,
}: {
  banner?: string;
  logo?: string;
  name: string;
  children?: React.ReactNode;
}) {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("");
  return (
    <div className={`card-art ${!banner && logo ? "card-art--brand" : ""}`}>
      <span className="card-monogram" aria-hidden="true">
        {letters}
      </span>
      <Picture
        key={banner || logo || "banner"}
        src={banner || logo}
        alt={banner ? `Artwork for ${name}` : ""}
        className="card-banner"
      />
      <div className="card-logo" aria-hidden="true">
        <span>{letters}</span>
        <Picture key={logo || "logo"} src={logo} />
      </div>
      {children}
    </div>
  );
}

export function EventCard({ item, children }: { item: Announcement; children?: React.ReactNode }) {
  return (
    <article className="discovery-card event-card">
      <Artwork banner={item.banner} logo={item.logo} name={item.club || item.title}>
        {item.start && (
          <time className="date-stamp" dateTime={item.start}>
            <strong>{format(item.start, { month: undefined })}</strong>
            <span>{format(item.start, { day: undefined })}</span>
          </time>
        )}
      </Artwork>
      <div className="card-body">
        {item.club && <p className="card-club">{item.club}</p>}
        <h3>
          {item.url ? (
            <a className="card-title" href={item.url} target="_blank" rel="noopener noreferrer">
              {item.title}
            </a>
          ) : (
            item.title
          )}
        </h3>
        <p className="card-copy">{item.notes.slice(0, 200)}</p>
        <div className="card-actions">
          <span className="card-time">
            {item.start
              ? format(item.start, { weekday: "short", hour: "numeric", minute: "2-digit" })
              : "Announcement"}
          </span>
          {children}
        </div>
      </div>
    </article>
  );
}

export function SocialLinks({ club, membership = false }: { club: Club; membership?: boolean }) {
  return (
    <div className="club-links">
      {[
        ["website", "Website"],
        ["instagram", "Instagram"],
        ["facebook", "Facebook"],
        ["discord", "Discord"],
        ["linkedin", "LinkedIn"],
        ...(membership ? [["membership", "Membership"]] : []),
      ]
        .filter(([key]) => club[key as keyof Club])
        .map(([key, label]) => (
          <a
            key={key}
            href={club[key as keyof Club]}
            aria-label={`${club.name} / ${label}`}
            data-tip={label}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Icon name={key === "membership" ? "event" : key} />
          </a>
        ))}
    </div>
  );
}

export function ClubCard({
  club,
  nextEvent,
  open,
  children,
}: {
  club: Club;
  nextEvent?: Announcement;
  open?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <article className="discovery-card club-card">
      <Artwork banner={nextEvent?.banner || club.banner} logo={club.logo} name={club.name} />
      <div className="card-body">
        {club.interests && (
          <p className="club-category">
            <T>{club.interests}</T>
          </p>
        )}
        <h3>
          {open ? (
            <button type="button" className="card-open" onClick={open}>
              {club.name}
            </button>
          ) : (
            <a
              className="card-title"
              href={club.directory_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {club.name}
            </a>
          )}
        </h3>
        {club.description && (
          <p className="card-copy">
            <T original>
              {club.description.length > 230
                ? `${club.description.slice(0, 227).trimEnd()}…`
                : club.description}
            </T>
          </p>
        )}
        {nextEvent && (
          <p className="club-next">
            <span>Next up / {format(nextEvent.start)}</span>
            {nextEvent.title}
          </p>
        )}
        <div className="card-actions">
          <SocialLinks club={club} />
          {children}
        </div>
      </div>
    </article>
  );
}

export function CourseCard({
  course,
  action,
  children,
}: {
  course: { course_code: string };
  action?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <article className="discovery-card course-card">
      <div className="course-art">
        <span>University of Queensland</span>
        <strong aria-hidden="true">
          {course.course_code.slice(0, 4)}
          <b>{course.course_code.slice(4)}</b>
        </strong>
        <img
          className="course-logo"
          src="/api/brand/uq.png"
          alt=""
          loading="lazy"
          decoding="async"
        />
      </div>
      <div className="card-body">
        <h3>{children}</h3>
        <div className="card-actions">{action}</div>
      </div>
    </article>
  );
}
