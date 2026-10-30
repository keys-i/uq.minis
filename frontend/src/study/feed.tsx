import { feedSchema } from "./model.ts";
import type {
  Announcement as Post,
  Change,
  Modal,
  Plan,
  Source,
  PlanProps,
  SheetProps,
  Feed,
} from "./model.ts";
import React, { useEffect, useState } from "react";
import { api } from "../shared/api.ts";
import { format, included, timestamp, upcoming } from "./dates.ts";
import { EventCard } from "../shared/cards.tsx";
import { useNotice } from "../shared/notice.ts";
import { terms, matches } from "../shared/search.ts";
import { Button, Link, Field, Empty } from "../shared/controls.tsx";

export function useAnnouncements(plan: Plan) {
  const [feed, setFeed] = useState<{ rows: Post[]; warning: string }>({ rows: [], warning: "" }),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api("/api/clubs/feed", feedSchema, undefined, controller.signal)
      .then((data) => {
        setFeed(data);
        setError("");
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError((error as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [version]);
  const saved = new Map(plan.announcements.map((item) => [item.id, item]));
  const rows = [
    ...feed.rows.map((item) => {
      const prior = saved.get(item.id);
      saved.delete(item.id);
      return { ...item, saved: prior?.saved || false };
    }),
    ...saved.values(),
  ];
  return {
    rows,
    loading,
    error: error || feed.warning,
    retry: () => setVersion((value) => value + 1),
  };
}

export function saveAnnouncement(change: Change, item: Post) {
  return change((next) => {
    const existing = next.announcements.find((row) => row.id === item.id);
    if (existing) existing.saved = !existing.saved;
    else next.announcements.push({ ...item, saved: true });
  });
}

export function Announcement({ item }: { item: Post }) {
  return (
    <>
      <span className="pill mint">{item.source}</span>
      <p>{item.club}</p>
      <p>
        {item.start
          ? format(item.start, {
              weekday: "long",
              year: "numeric",
              hour: "numeric",
              minute: "2-digit",
            })
          : "Announcement / no event date"}
      </p>
      <pre>{item.notes}</pre>
      <Link href={item.url}>Open original source</Link>
    </>
  );
}

export function Buzz({
  feed,
  plan,
  source,
  change,
  modal,
  close,
  discover,
}: PlanProps & SheetProps & { feed: Feed; source: Source; modal: Modal; discover: () => void }) {
  const [query, setQuery] = useState(""),
    [past, setPast] = useState(false),
    [offset, setOffset] = useState(0),
    [scope, setScope] = useState("all"),
    report = useNotice((state) => state.report),
    following = plan.settings.following || [];
  useEffect(() => setOffset(0), [query, past, scope]);
  const pool = feed.rows.filter((item) => past || upcoming(item));
  const picks = pool.filter((item) => included(item, following));
  const words = terms(query, "announcements");
  const rows = (scope === "all" ? pool : picks)
    .filter((item) => matches(`${item.title} ${item.club} ${item.notes}`, words))
    .sort((a, b) => (a.start || "z").localeCompare(b.start || "z"));
  const page = Math.min(offset, Math.max(0, Math.floor((rows.length - 1) / 40)) * 40);
  return (
    <>
      <div className="discovery-intro">
        <h2>Find your next good thing</h2>
        <p>Club plans, useful announcements and a bit of life between deadlines</p>
      </div>
      <div className="feed-header">
        <div className="search">
          <input
            type="search"
            aria-label="Search announcements"
            placeholder="A club, a plan, something you're into…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="feed-tabs" aria-label="Announcement selection">
          <Button
            className={scope === "all" ? "selected" : ""}
            aria-pressed={scope === "all"}
            onClick={() => setScope("all")}
          >
            Explore <span>{pool.length}</span>
          </Button>
          <Button
            className={scope === "mine" ? "selected" : ""}
            aria-pressed={scope === "mine"}
            onClick={() => setScope("mine")}
          >
            Your picks <span>{picks.length}</span>
          </Button>
        </div>
      </div>
      {feed.loading && <p role="status">Checking what's coming up…</p>}
      {feed.error && (
        <p className="rule-note">
          Some announcements couldn't update
          <Button className="quiet" onClick={feed.retry}>
            Try again
          </Button>
        </p>
      )}
      <div className="feed-meta">
        <p className="muted">{rows.length} matches</p>
        <label className="check-field">
          <input
            type="checkbox"
            checked={past}
            onChange={(event) => setPast(event.target.checked)}
          />
          Include past and cancelled events
        </label>
      </div>
      <div className="feed-grid">
        {rows.slice(page, page + 40).map((item) => (
          <EventCard key={item.id} item={item}>
            <Button
              className={`save-button ${included(item, following) ? "is-saved" : ""}`}
              disabled={following.includes(item.club_url || "")}
              aria-pressed={included(item, following)}
              aria-label={`${following.includes(item.club_url || "") ? "Following club for" : item.saved && item.start ? "Remove from your calendar:" : item.start ? "Save to your calendar:" : "Read details for"} ${item.title}`}
              onClick={() =>
                item.start
                  ? change((next) => {
                      const row = next.announcements.find((row) => row.id === item.id);
                      if (row) row.saved = !row.saved;
                      else next.announcements.push({ ...item, saved: true });
                    })
                  : modal({ title: item.title, body: <Announcement item={item} /> })
              }
            >
              {following.includes(item.club_url || "")
                ? "✓ Following"
                : item.saved && item.start
                  ? "✓ Saved"
                  : item.start
                    ? "+ Save"
                    : "Read details"}
            </Button>
          </EventCard>
        ))}
      </div>
      <details className="directory-tools">
        <summary>Announcement tools</summary>
        <div className="row">
          <Button
            className="quiet"
            onClick={() =>
              modal({
                title: "Save an announcement",
                body: <PostEditor change={change} close={close} />,
              })
            }
          >
            Add a plan
          </Button>
          <Button
            className="quiet"
            onClick={() =>
              modal({
                title: "Bring announcements together",
                body: <PostImport source={source} close={close} />,
              })
            }
          >
            Import announcements
          </Button>
        </div>
        <>
          <div className="row">
            <Button
              className="secondary"
              onClick={() =>
                modal({
                  title: "Connect club accounts",
                  body: <Connections source={source} close={close} />,
                })
              }
            >
              Connect club accounts
            </Button>
            <Button
              className="secondary"
              onClick={async () => {
                await source("/api/sync");
                report("Club announcements updated");
              }}
            >
              Update announcements
            </Button>
          </div>
        </>
      </details>
      {!rows.length && (
        <Empty
          title={scope === "mine" ? "Make a little room for your people" : "Your buzz starts here"}
          action={<Button onClick={discover}>Discover clubs</Button>}
        >
          {scope === "mine"
            ? "Follow a club or save a plan. The good stuff will gather here"
            : "Try another search or check back for the next club plans"}
        </Empty>
      )}
      {rows.length > 40 && (
        <div className="toolbar">
          <Button
            className="secondary"
            disabled={page === 0}
            onClick={() => setOffset(Math.max(0, page - 40))}
          >
            Previous 40
          </Button>
          <span className="muted">
            {page + 1}–{Math.min(page + 40, rows.length)} of {rows.length}
          </span>
          <Button
            className="secondary"
            disabled={page + 40 >= rows.length}
            onClick={() => setOffset(page + 40)}
          >
            Next 40
          </Button>
        </div>
      )}
    </>
  );
}

function Connections({ source, close }: SheetProps & { source: Source }) {
  const report = useNotice((state) => state.report),
    [busy, setBusy] = useState(false),
    [problem, setProblem] = useState("");
  return (
    <>
      <h3>Discord scheduled events</h3>
      <p>
        Create a Discord bot and invite it to servers where an administrator authorises access. Keep
        its token in <code>backend/.config/clubby/.env</code> as <code>DISCORD_BOT_TOKEN</code>, or
        in the backend process environment
      </p>
      <Link href="https://discord.com/developers/applications">Discord developer portal</Link>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const guilds = new FormData(event.currentTarget).get("guilds");
          try {
            await source("/api/discord", { guilds });
            report("Discord scheduled events refreshed");
            close();
          } catch (error) {
            report((error as Error).message, true);
          }
        }}
      >
        <Field label="Authorised server IDs / separate with commas" name="guilds" required />
        <div className="form-actions">
          <button>Refresh Discord events</button>
        </div>
      </form>
      <h3>Instagram & Facebook</h3>
      <p>
        Create a Meta developer app for a Page or supported professional account you manage. Choose
        the necessary read permissions and complete Meta's access review where required. A normal
        social login doesn't grant access to every club's feed
      </p>
      <Link href="https://developers.facebook.com/docs/">Meta developer documentation</Link>
      <h3>LinkedIn</h3>
      <p>
        Organisation feeds use LinkedIn's approved APIs and organisation roles. Confirm Community
        Management access for your organisation before connecting
      </p>
      <Link href="https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview">
        LinkedIn Community Management access
      </Link>
      <h3 id="social-heading">Read your club's announcements</h3>
      <p id="social-access">
        Configure the approved account's token and supported API version in private backend settings
        first. Each refresh reads one recent page of up to 100 posts. A post's publication date is
        never used as an event date
      </p>
      <form
        aria-labelledby="social-heading"
        aria-describedby="social-access"
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          const data = Object.fromEntries(new FormData(event.currentTarget));
          setBusy(true);
          setProblem("");
          try {
            await source("/api/social", data);
            report("Authorised social announcements refreshed");
            close();
          } catch (error) {
            setProblem((error as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-grid">
          <Field label="Social source">
            <select name="provider">
              <option value="facebook">Facebook Page</option>
              <option value="instagram">Professional Instagram / Facebook Login</option>
              <option value="linkedin">LinkedIn organisation</option>
            </select>
          </Field>
          <Field
            label="Authorised Page, Instagram or organisation ID"
            name="account"
            inputMode="numeric"
            pattern="[1-9][0-9]{0,31}"
            maxLength={32}
            required
          />
          <Field label="Club name" name="club" maxLength={300} />
          <Field
            label="Union directory link / optional, to match followed clubs"
            name="club_url"
            type="url"
          />
        </div>
        {problem && (
          <p className="rule-note" role="alert">
            {problem}
          </p>
        )}
        <div className="form-actions">
          <button disabled={busy} aria-busy={busy}>
            {busy ? "Reading announcements…" : "Refresh social announcements"}
          </button>
        </div>
      </form>
      <p className="rule-note">
        Union listings don't grant social API access. Account owners must authorise it; exports and
        saved source links remain available. The old Discord prototype's embedded token must be
        revoked by its owner
      </p>
    </>
  );
}

function PostEditor({ change, close }: SheetProps & { change: Change }) {
  const report = useNotice((state) => state.report);
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        try {
          await change((next) =>
            next.announcements.push({
              ...values,
              title: String(values.title || ""),
              notes: String(values.notes || ""),
              id: crypto.randomUUID(),
              start: timestamp(values.start),
              end: timestamp(values.end),
              saved: true,
            }),
          );
          close();
        } catch (error) {
          report((error as Error).message, true);
        }
      }}
    >
      <div className="form-grid">
        <Field name="title" label="Announcement or event" required />
        <Field name="club" label="Club or organiser" />
        <Field name="source" label="Source / Instagram, Facebook, LinkedIn…" value="Instagram" />
        <Field name="url" label="Original source link" type="url" required />
        <Field name="start" label="Event starts / blank for a post" type="datetime-local" />
        <Field name="end" label="Event ends / if supplied" type="datetime-local" />
        <Field name="notes" label="Useful details & what you need to do" type="textarea" />
      </div>
      <div className="form-actions">
        <button>Save announcement</button>
      </div>
    </form>
  );
}

function PostImport({ source, close }: SheetProps & { source: Source }) {
  const [text, setText] = useState(""),
    report = useNotice((state) => state.report);
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        try {
          await source("/api/import", {
            text,
            kind: new FormData(event.currentTarget).get("kind"),
          });
          close();
        } catch (error) {
          report((error as Error).message, true);
        }
      }}
    >
      <Field label="Import type">
        <select name="kind">
          <option value="social">Social announcements</option>
          <option value="discord">Discord scheduled-event JSON</option>
        </select>
      </Field>
      <Field label="JSON export">
        <textarea value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      <Field label="Or choose a JSON file">
        <input
          type="file"
          accept=".json,application/json"
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (file) {
              if (file.size > 8 * 1024 * 1024) {
                report("Choose a file smaller than 8 MiB", true);
                return;
              }
              setText(await file.text());
            }
          }}
        />
      </Field>
      <details>
        <summary>Social announcement format</summary>
        <pre>
          {JSON.stringify(
            [
              {
                title: "Your event",
                source: "Instagram",
                club: "Your club",
                url: "https://www.instagram.com/p/POST_ID/",
                start: "2026-10-25T18:00:00+10:00",
                notes: "Location, cost and how to join",
              },
            ],
            null,
            2,
          )}
        </pre>
      </details>
      <div className="form-actions">
        <button>Import announcements</button>
      </div>
    </form>
  );
}
