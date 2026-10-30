/** Lightweight predictions arrive while typing and never block a full search */
import { useEffect, useEffectEvent, useId, useRef, useState } from "react";
import * as z from "zod/mini";
import { api } from "../shared/api.ts";

const schema = z.object({
    suggestions: z.array(z.string().check(z.maxLength(200))).check(z.maxLength(10)),
  }),
  cache = new Map<string, { time: number; rows: string[] }>();
export function Suggestions({ query, choose }: { query: string; choose: (query: string) => void }) {
  const [rows, setRows] = useState<string[]>([]),
    [active, setActive] = useState(-1),
    panel = useRef<HTMLDivElement>(null),
    id = useId();
  const pick = useEffectEvent((text: string) => {
    setRows([]);
    choose(text);
  });
  useEffect(() => {
    const text = query.trim();
    setActive(-1);
    if (text.length < 2 || /[:/\\]/.test(text)) {
      setRows([]);
      return;
    }
    const stored = cache.get(text);
    if (stored && Date.now() - stored.time < 300_000) {
      setRows(stored.rows);
      return;
    }
    setRows(
      [...cache.values()]
        .filter((entry) => Date.now() - entry.time < 300_000)
        .flatMap((entry) => entry.rows)
        .filter(
          (row, index, all) =>
            row.toLowerCase().startsWith(text.toLowerCase()) && all.indexOf(row) === index,
        )
        .slice(0, 6),
    );
    const controller = new AbortController(),
      timer = setTimeout(async () => {
        try {
          const data = await api(
            `/api/timey/suggest?${new URLSearchParams({ query: text })}`,
            schema,
            undefined,
            controller.signal,
          );
          if (!controller.signal.aborted) {
            cache.set(text, { time: Date.now(), rows: data.suggestions });
            while (cache.size > 60) cache.delete(cache.keys().next().value!);
            setRows(data.suggestions);
          }
        } catch {
          // A missing prediction service leaves Enter and the person's text usable
        }
      }, 100);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);
  useEffect(() => {
    const input =
      panel.current?.parentElement?.querySelector<HTMLInputElement>('input[type="search"]');
    if (!input) return;
    input.setAttribute("aria-controls", id);
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", String(!!rows.length));
    if (active >= 0) input.setAttribute("aria-activedescendant", `${id}-${active}`);
    const key = (event: KeyboardEvent) => {
      if (!rows.length || event.isComposing) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        event.stopPropagation();
        setActive(
          (current) =>
            (current + (event.key === "ArrowDown" ? 1 : rows.length - 1) + rows.length) %
            rows.length,
        );
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        event.stopPropagation();
        pick(rows[active]);
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setRows([]);
      }
    };
    const blur = (event: FocusEvent) => {
      if (
        !(
          event.relatedTarget instanceof Node &&
          panel.current?.parentElement?.contains(event.relatedTarget)
        )
      )
        setRows([]);
    };
    input.addEventListener("keydown", key);
    input.addEventListener("blur", blur);
    return () => {
      input.removeEventListener("keydown", key);
      input.removeEventListener("blur", blur);
      for (const attribute of [
        "aria-autocomplete",
        "aria-controls",
        "aria-expanded",
        "aria-activedescendant",
      ])
        input.removeAttribute(attribute);
    };
  }, [rows, active, id]);
  return (
    <div
      ref={panel}
      id={id}
      className="search-suggestions"
      role="listbox"
      aria-label="Search suggestions"
      hidden={!rows.length}
    >
      {rows.map((text, index) => (
        <button
          type="button"
          role="option"
          tabIndex={-1}
          id={`${id}-${index}`}
          key={text}
          aria-selected={index === active}
          onPointerDown={(event) => event.preventDefault()}
          onClick={() => {
            setRows([]);
            choose(text);
          }}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
