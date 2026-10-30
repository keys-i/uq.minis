export function subscription(provider: string, base: string) {
  const feed = new URL(base);
  if (!feed.pathname.endsWith("/calendar.ics")) {
    feed.pathname = `${feed.pathname.replace(/\/$/, "")}/calendar.ics`;
    feed.search = "";
  }
  feed.hash = "";
  const host = feed.hostname.toLowerCase();
  const local =
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host === "[::1]" ||
    /^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host);
  if (provider === "google" || provider === "outlook") {
    if (local || feed.protocol !== "https:") return { feed: feed.href, href: null };
    const link = new URL(
      provider === "google"
        ? "https://calendar.google.com/calendar/r"
        : "https://outlook.office.com/calendar/0/addfromweb",
    );
    link.searchParams.set(provider === "google" ? "cid" : "url", feed.href);
    if (provider === "outlook") link.searchParams.set("name", "Planny");
    return { feed: feed.href, href: link.href };
  }
  return { feed: feed.href, href: feed.href.replace(/^https?:/, "webcal:") };
}
