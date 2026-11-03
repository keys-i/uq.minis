import { clubProfileSchema, clubResultSchema } from "./model.ts";
/** Browse the club directory and save following choices to the shared student plan */
import type { Announcement as Post, Club, Modal, PlanProps, ClubResult } from "./model.ts";
import React, { useEffect, useState } from "react";
import { api } from "../shared/api.ts";
import { format, included, upcoming } from "./dates.ts";
import { ClubCard, SocialLinks } from "../shared/cards.tsx";
import { Icon } from "../shared/icons.tsx";
import { T } from "../shared/language.tsx";
import { Picker } from "../shared/picker.tsx";
import { Button, Link, Empty } from "../shared/controls.tsx";
import { Mini } from "../shared/mini.tsx";
import { useAnnouncements, saveAnnouncement, Announcement } from "./feed.tsx";

export function Clubs({ plan, change, modal }: PlanProps & { modal: Modal }) {
  const following = plan.settings.following || [],
    next = new Map<string, Post>(),
    feed = useAnnouncements(plan),
    [scope, setScope] = useState("all"),
    [limit, setLimit] = useState(8);
  const coming = feed.rows
    .filter((item) => upcoming(item))
    .sort((a, b) => (a.start || "z").localeCompare(b.start || "z"));
  for (const item of coming)
    if (item.club_url && item.start && !next.has(item.club_url)) next.set(item.club_url, item);
  const announcements = coming.filter(
    (item) => scope === "all" || following.includes(item.club_url || ""),
  );
  return (
    <>
      <div className="discovery-intro">
        <h2>
          <T>There's a club for that</T>
        </h2>
        <p>
          <T>A familiar interest, a new obsession, or just somewhere to show up</T>
        </p>
      </div>
      <a className="mobile-noticeboard" href="#club-noticeboard">
        <Icon name="buzz" />
        What's coming up?
      </a>
      <div className="club-discovery">
        <section aria-label="Discover clubs">
          <Search
            render={(row) => (
              <ClubCard
                key={row.directory_url}
                club={row}
                nextEvent={next.get(row.directory_url)}
                open={() => modal({ title: row.name, body: <ClubProfile club={row} /> })}
              >
                <Button
                  className={`follow-button ${following.includes(row.directory_url) ? "is-saved" : ""}`}
                  aria-pressed={following.includes(row.directory_url)}
                  aria-label={`${following.includes(row.directory_url) ? "Unfollow" : "Follow"} ${row.name}`}
                  onClick={() =>
                    change((next) => {
                      const selected = new Set(next.settings.following || []);
                      if (selected.has(row.directory_url)) selected.delete(row.directory_url);
                      else selected.add(row.directory_url);
                      next.settings.following = [...selected];
                    })
                  }
                >
                  <Icon name={following.includes(row.directory_url) ? "check" : "heart"} />
                  <span>{following.includes(row.directory_url) ? "Following" : "Follow"}</span>
                </Button>
              </ClubCard>
            )}
          />
        </section>
        <aside
          className="club-feed"
          id="club-noticeboard"
          tabIndex={-1}
          aria-label="Club announcements"
        >
          <div className="club-feed-heading">
            <Icon name="buzz" />
            <h2>
              <T>The noticeboard</T>
            </h2>
          </div>
          <div className="feed-tabs">
            <Button
              className={scope === "all" ? "selected" : ""}
              aria-pressed={scope === "all"}
              onClick={() => {
                setScope("all");
                setLimit(8);
              }}
            >
              Everyone
            </Button>
            <Button
              className={scope === "mine" ? "selected" : ""}
              aria-pressed={scope === "mine"}
              onClick={() => {
                setScope("mine");
                setLimit(8);
              }}
            >
              Following
            </Button>
          </div>
          {feed.loading && <p role="status">Checking what's coming up…</p>}
          {feed.error && (
            <p className="rule-note" role="status">
              Some announcements couldn't update
              <Button className="quiet" onClick={feed.retry}>
                Try again
              </Button>
            </p>
          )}
          <div className="noticeboard-posts">
            {announcements.slice(0, limit).map((item) => (
              <article key={item.id} className="noticeboard-post">
                <div className="noticeboard-date">
                  {item.start ? (
                    <time dateTime={item.start}>
                      <strong>{format(item.start, { month: undefined })}</strong>
                      <span>{format(item.start, { day: undefined })}</span>
                    </time>
                  ) : (
                    <Icon name="buzz" />
                  )}
                </div>
                <div>
                  <p>
                    {item.logo && <img src={item.logo} alt="" loading="lazy" decoding="async" />}
                    {item.club}
                  </p>
                  <h3>
                    <a href={item.url} target="_blank" rel="noopener noreferrer">
                      {item.title}
                    </a>
                  </h3>
                  {item.start && (
                    <small>
                      {format(item.start, { weekday: "short", hour: "numeric", minute: "2-digit" })}
                    </small>
                  )}
                  {item.notes && <p className="noticeboard-notes">{item.notes.slice(0, 160)}</p>}
                  <Button
                    className="quiet"
                    disabled={following.includes(item.club_url || "")}
                    aria-pressed={included(item, following)}
                    onClick={() =>
                      item.start
                        ? saveAnnouncement(change, item)
                        : modal({ title: item.title, body: <Announcement item={item} /> })
                    }
                  >
                    {following.includes(item.club_url || "")
                      ? "In your calendar"
                      : item.saved && item.start
                        ? "Saved / remove"
                        : item.start
                          ? "Save to calendar"
                          : "Read announcement"}
                  </Button>
                </div>
              </article>
            ))}
          </div>
          {!feed.loading && !announcements.length && (
            <p>
              {scope === "mine"
                ? "Follow a club and its next plans will gather here"
                : "No upcoming plans just yet"}
            </p>
          )}
          {announcements.length > limit && (
            <Button className="secondary" onClick={() => setLimit((value) => value + 8)}>
              More announcements
            </Button>
          )}
        </aside>
      </div>
      <details className="directory-tools">
        <summary>Club directory tools</summary>
        <Mini name="clubby" />
      </details>
    </>
  );
}

function ClubProfile({ club }: { club: Club }) {
  const [result, setResult] = useState<{
      club: Club;
      events: { url: string; title: string; when: string }[];
    } | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api(
      `/api/club?url=${encodeURIComponent(club.directory_url)}`,
      clubProfileSchema,
      undefined,
      controller.signal,
    )
      .then(setResult)
      .catch((error) => {
        if (error.name !== "AbortError") setError((error as Error).message);
      });
    return () => controller.abort();
  }, [club.directory_url]);
  const detail = result?.club || club;
  return (
    <div className="club-profile">
      {detail.banner && <img className="club-profile-banner" src={detail.banner} alt="" />}
      <div className="club-profile-heading">
        {detail.logo && <img src={detail.logo} alt="" />}
        <span className="pill mint">{detail.interests || "UQ club"}</span>
      </div>
      {!result && !error && <p role="status">Bringing in the club's public profile…</p>}
      {error && (
        <p className="rule-note" role="status">
          {error}
        </p>
      )}
      {detail.description && (
        <p>
          <T original>{detail.description}</T>
        </p>
      )}
      <div className="club-profile-links">
        <SocialLinks club={detail} membership />
      </div>
      {detail.contact && (
        <p>
          Club contact: <span dir="auto">{detail.contact}</span>
        </p>
      )}
      {!!result?.events.length && (
        <section>
          <h3>Coming up</h3>
          {result?.events.map((event) => (
            <p key={event.url}>
              <Link href={event.url}>{event.title}</Link>
              <small className="club-when">{event.when}</small>
            </p>
          ))}
        </section>
      )}
      <Link href={club.directory_url}>Official club page & membership</Link>
    </div>
  );
}

function Search({ render }: { render: (row: Club) => React.ReactNode }) {
  const [query, setQuery] = useState(""),
    [offset, setOffset] = useState(0),
    [result, setResult] = useState<ClubResult>({ rows: [], total: 0, categories: [] }),
    [version, setVersion] = useState(0),
    [category, setCategory] = useState(""),
    [channel, setChannel] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(
      () => {
        setLoading(true);
        api(
          `/api/search?kind=clubs&q=${encodeURIComponent(query)}&offset=${offset}&category=${encodeURIComponent(category)}&channel=${channel}`,
          clubResultSchema,
          undefined,
          controller.signal,
        )
          .then((data) => {
            setResult(data);
            setError("");
          })
          .catch((error) => {
            if (error.name !== "AbortError") setError((error as Error).message);
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
  }, [query, offset, version, category, channel]);
  return (
    <>
      <div className="club-search">
        <label className="field">
          <span>
            <T>Find your people</T>
          </span>
          <input
            type="search"
            placeholder="A club, an interest, something you've always wanted to try…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>
      <div className="research-filters">
        <Picker
          label="Interest & faculty"
          value={category}
          onChange={(value) => {
            setCategory(value);
            setOffset(0);
          }}
          options={[
            ["", "All interests"],
            ...result.categories.map((value) => [value, value] as const),
          ]}
        />
        <Picker
          label="Where they connect"
          value={channel}
          onChange={(value) => {
            setChannel(value);
            setOffset(0);
          }}
          options={[
            ["", "Any channel"],
            ["instagram", "Instagram"],
            ["facebook", "Facebook"],
            ["discord", "Discord"],
            ["website", "Website"],
          ]}
        />
      </div>
      <p className="muted" role="status">
        {loading
          ? "Finding your people…"
          : `${result.total} clubs${result.total ? ` / ${offset + 1}–${offset + result.rows.length}` : ""}`}
      </p>
      {error && (
        <div role="alert" className="notice error">
          {error}
          <Button className="secondary" onClick={() => setVersion((value) => value + 1)}>
            Try again
          </Button>
        </div>
      )}
      {result.warning && (
        <p className="rule-note">Showing the saved directory / try again a little later</p>
      )}
      <div className="club-grid" aria-busy={loading}>
        {result.rows.map(render)}
      </div>
      {!loading && !result.rows.length && !error && (
        <Empty title="A different trail, perhaps?">
          Try another interest or broaden the filters
        </Empty>
      )}
      <div className="toolbar">
        {offset > 0 && (
          <Button className="secondary" onClick={() => setOffset(Math.max(0, offset - 40))}>
            Previous
          </Button>
        )}
        {offset + 40 < result.total && (
          <Button className="secondary" onClick={() => setOffset(offset + 40)}>
            Next 40
          </Button>
        )}
      </div>
    </>
  );
}
import "./clubs.css";
