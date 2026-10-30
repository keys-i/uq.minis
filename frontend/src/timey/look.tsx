import { useRef, useState, useEffect, useEffectEvent } from "react";
import { importMedia, mediaLink } from "./media.ts";
import { api, type Failure } from "../shared/api.ts";
import { Icon } from "../shared/icons.tsx";
import { Issue, Status, message as explain } from "./feedback.tsx";
import { clamp, fonts, transferred, fontsSchema, type Values, type Font } from "./model.ts";

export function fontInput(value: string): string {
  const text = value.trim();
  if (
    /^(\/|\.\.?\/|~\/)/.test(text) ||
    (/\.(ttf|otf|ttc|woff2?)$/i.test(text) && !text.includes(":"))
  )
    return text;
  if (!/^https?:/i.test(text)) return "";
  const url = new URL(text);
  if (
    url.protocol !== "https:" ||
    !["fonts.google.com", "fonts.googleapis.com", "fonts.gstatic.com"].includes(url.hostname) ||
    url.username ||
    url.password ||
    url.port
  )
    throw new Error("Use an HTTPS Google Fonts link");
  return url.href;
}

export function fontName(value: string): string {
  if (!value) return "Theme font";
  try {
    const url = new URL(value);
    const family =
      url.searchParams.get("family") ||
      (url.hostname === "fonts.google.com" && url.pathname.startsWith("/specimen/")
        ? decodeURIComponent(url.pathname.slice(10).replaceAll("+", " "))
        : "");
    return family.split(":")[0] || "Custom font";
  } catch {
    return value.split("/").pop() || "Custom font";
  }
}

export function Look({ values, change }: { values: Values; change: (patch: Values) => void }) {
  const [query, setQuery] = useState(""),
    [selectedName, setSelectedName] = useState(() => fontName(values.font || "")),
    [rows, setRows] = useState<Font[]>([]),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  const request = useRef<AbortController>(null),
    prediction = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    results = useRef<HTMLDivElement>(null);
  const blend = clamp(Number(values.loop_blend ?? 0.6), 0, 2),
    motion = values.motion === "on";
  useEffect(() => () => request.current?.abort(), []);
  const predict = useEffectEvent(() => {
    void find();
    return request.current;
  });
  useEffect(() => {
    if (query.trim().length < 2 || /[:/\\]/.test(query) || /\.(ttf|otf|ttc|woff2?)$/i.test(query))
      return;
    let active: AbortController | null = null;
    prediction.current = setTimeout(() => {
      active = predict();
    }, 180);
    return () => {
      clearTimeout(prediction.current);
      active?.abort();
      if (active && request.current === active) setBusy(false);
    };
  }, [query]);
  function choose(source: string, name = "") {
    clearTimeout(prediction.current);
    request.current?.abort();
    setBusy(false);
    setSelectedName(name || fontName(source));
    change({ font: source });
    setRows([]);
    setQuery("");
    setMessage("");
    setError("");
  }
  async function find() {
    clearTimeout(prediction.current);
    request.current?.abort();
    setRows([]);
    setMessage("");
    setError("");
    if (
      mediaLink(query) &&
      !["fonts.google.com", "fonts.googleapis.com", "fonts.gstatic.com"].includes(
        new URL(query).hostname,
      )
    ) {
      await upload(query.trim());
      return;
    }
    try {
      const source = fontInput(query);
      if (source) {
        choose(source);
        return;
      }
    } catch (caught) {
      setBusy(false);
      setError((caught as Error).message);
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      const data = await api(
        `/api/timey/fonts?${new URLSearchParams({ query: query.trim() })}`,
        fontsSchema,
        undefined,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setRows(data.rows);
        setMessage(
          !data.total
            ? "No fonts found / try a name or style"
            : data.notice ||
                (data.total > data.rows.length ? "Keep searching to narrow it down" : ""),
        );
      }
    } catch (caught) {
      const failure = caught as Failure;
      if (!controller.signal.aborted) setError(explain(failure, "finding your font"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function upload(file?: File | string) {
    if (!file) return;
    clearTimeout(prediction.current);
    if (typeof file === "string") setQuery(file);
    if (typeof file !== "string" && file.size > 8 * 1024 ** 2) {
      setError("Choose a font under 8 MiB");
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    setRows([]);
    try {
      const result = await importMedia(file, "font", controller.signal);
      if (!controller.signal.aborted) choose(result.source, result.title);
    } catch (error) {
      if (!controller.signal.aborted) setError(explain(error, "opening your font"));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  function take(data: DataTransfer) {
    try {
      const item = transferred(data);
      if (item instanceof File) void upload(item);
      else {
        if (
          mediaLink(item) &&
          !["fonts.google.com", "fonts.googleapis.com", "fonts.gstatic.com"].includes(
            new URL(item).hostname,
          )
        ) {
          void upload(item);
          return;
        }
        const source = fontInput(item);
        if (source) choose(source);
        else {
          setQuery(item);
          setMessage("Press Enter to search this font name");
        }
      }
    } catch (error) {
      setError(explain(error, "opening your font"));
    }
  }
  return (
    <div
      className="timer-look-settings"
      onPaste={(event) => {
        const text = event.clipboardData.getData("text");
        if (event.clipboardData.files.length || /^https?:|^(\/|\.\.?\/|~\/)/i.test(text)) {
          event.preventDefault();
          event.stopPropagation();
          take(event.clipboardData);
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        take(event.dataTransfer);
      }}
    >
      <div className="timer-source-search">
        <input
          type="search"
          aria-label="Search any font"
          placeholder="Search any font…"
          enterKeyHint="search"
          maxLength={200}
          value={query}
          onChange={(event) => {
            request.current?.abort();
            setBusy(false);
            setRows([]);
            setMessage("");
            setError("");
            setQuery(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return;
            if (event.key === "Enter") {
              event.preventDefault();
              find();
            }
            if (event.key === "ArrowDown" && rows.length) {
              event.preventDefault();
              results.current?.querySelector<HTMLButtonElement>("button")?.focus();
            }
          }}
        />
        <label className="timer-upload" data-tip="Add font">
          <Icon name="upload" />
          <input
            type="file"
            accept={fonts}
            aria-label="Upload font"
            onChange={(event) => {
              void upload(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      </div>
      {!!rows.length && (
        <div ref={results} className="font-results" role="group" aria-label="Matching fonts">
          {rows.map((row) => (
            <button
              type="button"
              key={row.source}
              className="quiet"
              aria-pressed={values.font === row.source}
              onClick={() => choose(row.source)}
            >
              <Icon name="font" />
              <span>
                <strong>{row.name}</strong>
                <small>{row.description}</small>
              </span>
              {values.font === row.source && <Icon name="check" />}
            </button>
          ))}
        </div>
      )}
      {values.font && (
        <div className="font-current">
          <Icon name="font" />
          <span>{selectedName}</span>
          <button
            type="button"
            className="quiet"
            data-tip="Use theme font"
            aria-label="Use theme font"
            onClick={() => choose("")}
          >
            <Icon name="close" />
          </button>
        </div>
      )}
      <p className="look-status" role="status">
        {message}
      </p>
      {busy && (
        <Status
          text="Finding your font…"
          cancel={() => {
            request.current?.abort();
            setBusy(false);
          }}
        />
      )}
      {error && <Issue title="A different font, perhaps?" message={error} />}
      <fieldset className="digit-choices">
        <legend>
          <Icon name="motion" />
          Digit changes
        </legend>
        <div>
          {[
            ["on", "Rolling digits", "motion"],
            ["off", "Simple countdown", "still"],
          ].map(([value, label, icon]) => (
            <button
              type="button"
              key={value}
              className="quiet"
              aria-pressed={motion === (value === "on")}
              onClick={() => change({ motion: value })}
            >
              <span className="digit-demo" data-motion={value} aria-hidden="true">
                <span>09</span>
                <span>08</span>
              </span>
              <span>
                <Icon name={icon} />
                {label}
              </span>
            </button>
          ))}
        </div>
      </fieldset>
      <label className="loop-control">
        <span>
          <Icon name="repeat" />
          Video loop<output>{blend ? `${blend.toFixed(1)}s fade` : "Cut"}</output>
        </span>
        <input
          type="range"
          aria-label="Loop fade"
          aria-valuetext={blend ? `${blend.toFixed(1)} second crossfade` : "Cut without fading"}
          min="0"
          max="2"
          step=".1"
          value={blend}
          style={{ "--played": `${(blend / 2) * 100}%` }}
          onChange={(event) => change({ loop_blend: event.target.value })}
        />
        <span className="loop-scale">
          <span>Cut</span>
          <span>Soft fade</span>
        </span>
      </label>
    </div>
  );
}
