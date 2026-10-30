import { test } from "vitest";
import assert from "node:assert/strict";
import { subscription } from "../src/study/calendar.ts";

test("device calendars receive a live webcal subscription, including the server port", () => {
  assert.deepEqual(subscription("device", "http://127.0.0.1:8765"), {
    feed: "http://127.0.0.1:8765/calendar.ics",
    href: "webcal://127.0.0.1:8765/calendar.ics",
  });
});

test("cloud calendars never receive an unreachable local or insecure feed", () => {
  for (const host of [
    "127.0.0.1",
    "localhost",
    "minis.local",
    "[::1]",
    "10.0.0.2",
    "192.168.1.5",
    "172.16.0.4",
  ]) {
    for (const provider of ["google", "outlook"])
      assert.equal(subscription(provider, `https://${host}`).href, null);
  }
  assert.equal(subscription("google", "http://example.org").href, null);
});

test("hosted provider links encode the feed as a subscription rather than a single event", () => {
  for (const provider of ["google", "outlook"]) {
    const { href, feed } = subscription(provider, "https://uni.keysi.dev/minis/?mini=planny#week");
    assert.ok(href);
    assert.equal(feed, "https://uni.keysi.dev/minis/calendar.ics");
    const link = new URL(href);
    assert.equal(link.protocol, "https:");
    assert.equal(link.searchParams.get(provider === "google" ? "cid" : "url"), feed);
    assert.doesNotMatch(href, /action=TEMPLATE|eventedit/);
  }
  assert.equal(
    subscription("other", "https://uni.keysi.dev/minis").feed,
    "https://uni.keysi.dev/minis/calendar.ics",
  );
});
