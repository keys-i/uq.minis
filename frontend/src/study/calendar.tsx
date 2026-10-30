import { api } from "../shared/api.ts";
import { useSession } from "../shared/session.ts";
import * as z from "zod/mini";
import React, { useEffect, useState } from "react";
import { subscription } from "./calendar.ts";

export function CalendarSettings({ base }: { base: string }) {
  const [provider, setProvider] = useState("device"),
    [copied, setCopied] = useState("");
  const hosted = useSession((state) => state.hosted);
  const [address, setAddress] = useState(base),
    [error, setError] = useState("");
  useEffect(() => {
    if (!hosted) return;
    const controller = new AbortController();
    api("/api/calendar", z.object({ url: z.string() }), undefined, controller.signal)
      .then(({ url }) => setAddress(new URL(url, location.origin).href))
      .catch((error: Error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [hosted]);
  const { feed, href } = subscription(provider, address);
  if (hosted && address === base)
    return (
      <p role={error ? "alert" : "status"}>{error || "Preparing your private calendar link…"}</p>
    );
  return (
    <>
      <p>Keep official deadlines, personal targets and saved club events in your own calendar</p>
      <label className="field">
        <span>Your calendar app</span>
        <select
          value={provider}
          onChange={(event) => {
            setProvider(event.target.value);
            setCopied("");
          }}
        >
          <option value="device">Apple Calendar / app on this device</option>
          <option value="google">Google Calendar</option>
          <option value="outlook">Outlook on the web</option>
          <option value="other">Another calendar app</option>
        </select>
      </label>
      {href && provider !== "other" && (
        <p className="calendar-subscribe">
          <a
            className="subscribe-link"
            href={href}
            target={provider === "device" ? undefined : "_blank"}
            rel="noopener noreferrer"
          >
            {provider === "google"
              ? "Subscribe in Google Calendar"
              : provider === "outlook"
                ? "Subscribe in Outlook"
                : "Open calendar app to subscribe"}
          </a>
        </p>
      )}
      {!href ? (
        <p className="notice">
          {provider === "google" ? "Google Calendar" : "Outlook on the web"} can't reach this Mac's
          local calendar - a hosted, protected feed is needed first
        </p>
      ) : (
        <p className="rule-note">
          Your calendar app controls refresh timing - keep minis running for updates
        </p>
      )}
      <details className="calendar-address">
        <summary>{provider === "other" ? "Subscription link" : "Copy subscription link"}</summary>
        <label className="field">
          <span>Live calendar address</span>
          <input readOnly value={feed} onFocus={(event) => event.target.select()} />
        </label>
        <button
          type="button"
          className="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(feed);
              setCopied("Link copied");
            } catch {
              setCopied("Select the address above and copy it");
            }
          }}
        >
          Copy link
        </button>
        <span className="copy-state" role="status">
          {copied}
        </span>
      </details>
      <h3>Keep a private copy</h3>
      <a href="/api/backup" download="planny-backup.json">
        Download enrolments, assessments and marks
      </a>
    </>
  );
}
