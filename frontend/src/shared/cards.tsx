import type { Announcement, Club, Mini, Tools } from "../study/model.ts";
import React, { useContext, useEffect, useState } from "react";
import { T } from "./language.tsx";
import { format } from "../study/dates.ts";
import { Icon } from "./icons.tsx";
import { Pal } from "../wildlife/mascot.tsx";
import { Motion } from "./display.tsx";
import { typeText } from "./motion.ts";
import { miniHref } from "./route.ts";

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

const descriptions: Record<string, string> = {
  planny: "Turn assessments into an earlier, manageable plan",
  scrappy: "Choose courses and compare their requirements",
  buzzy: "See deadlines and club events in one calendar",
  clubby: "Find clubs by interest and follow their events",
  event: "Prepare the forms and risk plan for a club activity",
  timey: "Make and preview a countdown video for your event",
};
const miniOrder = ["planny", "scrappy", "buzzy", "clubby", "event", "timey"];

function TypedCopy({ text, active }: { text: string; active: boolean }) {
  const [typed, setTyped] = useState(active ? "" : text);
  const { reduced, hidden } = useContext(Motion);
  useEffect(
    () => typeText(text, setTyped, active && !reduced && !hidden),
    [active, hidden, reduced, text],
  );
  return (
    <>
      <span className="typed-copy" data-typing={active && typed !== text} aria-hidden="true">
        <span className="typed-measure">{text}</span>
        <span>{typed}</span>
      </span>
      <span className="sr-only">{text}</span>
    </>
  );
}

export function MiniTitle({
  name,
  title,
  open,
}: {
  name: string;
  title: string;
  open: (name: string) => void;
}) {
  return (
    <a
      className="card-title"
      href={miniHref(name)}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        open(name);
      }}
    >
      {title}
    </a>
  );
}

/** Keep the habitat and its controls separate from the mini navigation link */
export function MiniCard({
  name,
  mini,
  open,
  featured = false,
  feature = () => {},
  resident,
}: {
  name: string;
  mini: Mini;
  open: (name: string) => void;
  featured?: boolean;
  feature?: (name: string) => void;
  resident?: number;
}) {
  return (
    <article
      className={`mini-card${featured ? " is-featured" : ""}`}
      data-mini={name}
      onPointerEnter={(event) => {
        if (!featured && event.pointerType !== "touch") feature(name);
      }}
      onFocusCapture={() => feature(name)}
    >
      <div className="mini-art">
        <Pal name={name} resident={resident} />
        <span className="mini-mark">
          <Icon name={name} />
        </span>
      </div>
      <div className="card-body">
        <h2>
          <MiniTitle name={name} title={mini.title} open={open} />
        </h2>
        <div className="preview-copy">
          <div>
            <p>
              <TypedCopy text={descriptions[name] || mini.about} active={featured} />
            </p>
          </div>
        </div>
      </div>
    </article>
  );
}

/** Group cards by visual row without changing their keyboard reading order */
export function MiniShelf({ tools, open }: { tools: Tools; open: (name: string) => void }) {
  const entries = Object.entries(tools).sort(
    ([left], [right]) => miniOrder.indexOf(left) - miniOrder.indexOf(right),
  );
  const initial = tools.planny ? "planny" : (entries[0]?.[0] ?? "");
  const [featured, setFeatured] = useState(initial);
  const active = tools[featured] ? featured : initial;
  return (
    <section
      className="expedition-board"
      aria-label="Choose a mini"
      onPointerLeave={(event) => {
        if (event.pointerType !== "touch" && !event.currentTarget.contains(document.activeElement))
          setFeatured(initial);
      }}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFeatured(initial);
      }}
    >
      <div className="mini-grid">
        {Array.from({ length: Math.ceil(entries.length / 3) }, (_, row) => (
          <div
            className="mini-row"
            style={{
              gridTemplateColumns: Array.from({ length: 3 }, (_, column) =>
                entries[row * 3 + column]?.[0] === active ? "1.42fr" : "1fr",
              ).join(" "),
            }}
            key={row}
          >
            {entries.slice(row * 3, row * 3 + 3).map(([name, mini], column) => (
              <MiniCard
                key={name}
                name={name}
                mini={mini}
                open={open}
                feature={setFeatured}
                featured={name === active}
                resident={row * 3 + column}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
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
