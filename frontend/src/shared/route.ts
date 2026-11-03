const publicBase = () => (import.meta.env.BASE_URL === "/" ? "/mini/" : import.meta.env.BASE_URL);

export const miniName = (name: string) =>
  name === "agent" ? "event" : name === "auth" ? "home" : name;

export function miniHref(name: string) {
  const route = name === "auth" ? "home" : name;
  return route === "home"
    ? import.meta.env.BASE_URL
    : `${publicBase()}${encodeURIComponent(route)}`;
}

function pathMini() {
  const path = location.pathname.startsWith(publicBase())
    ? location.pathname.slice(publicBase().length).replace(/\/$/, "")
    : "";
  if (path && !path.includes("/")) {
    try {
      const name = decodeURIComponent(path);
      if (/^[a-z0-9-]+$/.test(name)) return name;
    } catch {
      // Legacy query routes remain available when the path is malformed
    }
  }
}

export function requestedMini() {
  const path = pathMini();
  const query = new URLSearchParams(location.search);
  const name = path || query.get("m") || query.get("mini") || "home";
  canonicaliseMiniRoute(name);
  return name;
}

function canonicaliseMiniRoute(name: string) {
  const query = new URLSearchParams(location.search);
  if (!query.has("m") && !query.has("mini")) return;
  query.delete("m");
  query.delete("mini");
  const path = miniHref(pathMini() || name);
  const search = query.size ? `?${query}` : "";
  history.replaceState(history.state, "", `${path}${search}${location.hash}`);
}
