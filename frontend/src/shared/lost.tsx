import { miniHref } from "./route.ts";

export function NotFound({ back }: { back: () => void }) {
  return (
    <section className="not-found" aria-labelledby="not-found-title">
      <h1 id="not-found-title">That habitat isn't on this map</h1>
      <p>The address may have changed, or this mini hasn't opened yet</p>
      <a
        className="button-link"
        href={miniHref("home")}
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          back();
        }}
      >
        Back to the expedition
      </a>
    </section>
  );
}
