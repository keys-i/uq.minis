import { Connection } from "./connect.tsx";
import { Suggestions } from "./suggest.tsx";
import { formSchema } from "../shared/schema.ts";
import React, { useContext, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import {
  configuration,
  pictures,
  transferred,
  seconds,
  video,
  videosSchema,
  type Clip,
  type Values,
  type Video,
} from "./model.ts";
import type { Schema } from "../shared/forms.tsx";
import type { Failure } from "../shared/api.ts";
import { api } from "../shared/api.ts";
import { initial, Input } from "../shared/forms.tsx";
import { Canvas } from "./canvas.tsx";
import { Dial } from "./dial.tsx";
import { Look } from "./look.tsx";
import { Icon } from "../shared/icons.tsx";
import { Motion } from "../shared/display.tsx";
import { Picker } from "../shared/picker.tsx";
import "./style.css";

import { backdrop, prepare, preview, importMedia, mediaLink } from "./media.ts";
import { Issue, message } from "./feedback.tsx";
import { Themes } from "./looks.tsx";
import { useDraft, setValues, timerResultSchema } from "./draft.ts";
import { Share } from "./share.tsx";
import { Save } from "./save.tsx";
const qualities: [string, string][] = [
  ["0", "Original"],
  ["240", "Tiny file (240p)"],
  ["360", "Data saver (360p)"],
  ["480", "Small file (480p)"],
  ["720", "HD (720p)"],
  ["1080", "Full HD (1080p)"],
  ["1440", "Quad HD (1440p)"],
  ["2160", "4K (2160p)"],
];

export function Quality({
  values,
  change,
}: {
  values: Values;
  change: (name: string, value: string) => void;
}) {
  const height = String(values.height ?? 0);
  return (
    <div className="timer-quality">
      <Picker
        compact
        label="Quality"
        value={height}
        options={qualities}
        onChange={(value) => change("height", value)}
      />
      <Picker
        compact
        label="Motion"
        value={values.fps || 30}
        options={[
          [24, "Cinematic (24 fps)"],
          [30, "Standard (30 fps)"],
          [60, "Smooth (60 fps)"],
        ]}
        onChange={(value) => change("fps", value)}
      />
      <label className="timer-refresh">
        <span>Refresh footage</span>
        <input
          type="checkbox"
          checked={values.no_cache === "on"}
          onChange={(event) => change("no_cache", event.target.checked ? "on" : "")}
        />
      </label>
    </div>
  );
}

export function Publication({
  schema,
  values,
  change,
}: {
  schema: Schema;
  values: Values;
  change: (name: string, value: string) => void;
}) {
  return (
    <section className="timer-publication" aria-label="Publication settings">
      <button
        type="button"
        className="secondary timer-draft"
        aria-pressed={values.metadata === "on"}
        onClick={() => change("metadata", values.metadata === "on" ? "" : "on")}
      >
        <Icon name="marks" />
        Video details
      </button>
      {values.metadata === "on" &&
        schema.fields
          .filter((field) => field.name === "metadata_instructions")
          .map((field) => <Input key={field.name} field={field} values={values} change={change} />)}
    </section>
  );
}

export function VideoResults({
  rows,
  choose,
}: {
  rows: Video[];
  choose: (source: string) => void;
}) {
  const { reduced, hidden } = useContext(Motion),
    [active, setActive] = useState(""),
    [sample, setSample] = useState<
      (Partial<Clip> & { source: string; loading?: boolean; error?: string }) | null
    >(null),
    player = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (
      !active ||
      reduced ||
      hidden ||
      navigator.connection?.saveData ||
      (sample?.source === active && sample.url)
    )
      return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSample({ source: active, loading: true });
      const data = new FormData();
      data.set("source", active);
      data.set("start", "0");
      try {
        const next = await prepare(data, controller.signal);
        if (!controller.signal.aborted) setSample({ ...next, source: active });
      } catch (caught) {
        const error = caught as Failure;
        if (!controller.signal.aborted && error.name !== "AbortError")
          setSample({ source: active, error: error.message || "This video couldn’t be previewed" });
      }
    }, 400);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [active, reduced, hidden]);
  const playing = !reduced && !hidden && sample?.source === active && sample.url;
  useEffect(() => {
    const element = player.current;
    return () => {
      if (element) {
        element.pause();
        element.removeAttribute("src");
        element.load();
      }
    };
  }, [playing]);
  return (
    <div
      className="video-results"
      role="group"
      aria-label="Background videos"
      onPointerLeave={() => setActive("")}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setActive("");
      }}
    >
      {rows.map((row) => {
        const chosen = video(row.url),
          selected = active === row.url;
        return (
          <button
            type="button"
            key={row.url}
            className="video-choice"
            onPointerEnter={(event) => {
              if (event.pointerType === "mouse") setActive(row.url);
            }}
            onFocus={() => setActive(row.url)}
            onClick={() => choose(row.url)}
          >
            <span className="video-thumbnail" aria-hidden="true">
              {chosen && (
                <img
                  src={`https://i.ytimg.com/vi/${chosen.id}/mqdefault.jpg`}
                  alt=""
                  width="320"
                  height="180"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              )}
              {selected && playing && (
                <video
                  ref={player}
                  src={sample.url}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="auto"
                  onError={() =>
                    setSample({
                      source: row.url,
                      error: "This preview couldn’t play / choose the video to retry",
                    })
                  }
                />
              )}
              <small>{row.length}</small>
              {selected && sample?.source === row.url && sample.loading && (
                <i className="video-loading" />
              )}
            </span>
            <span className="video-description">
              <strong>{row.title}</strong>
              {selected && sample?.source === row.url && sample.error && (
                <small>{sample.error}</small>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function Timey() {
  const { reduced, hidden } = useContext(Motion);
  const [schema, setSchema] = useState<Schema>({ fields: [] });
  const { values: saved, phase: mode, movie, questions } = useDraft();
  const values = useMemo<Values>(
    () => ({
      length: "10m",
      start_gap: "5s",
      end_gap: "5s",
      ...initial(schema),
      style: "minimal",
      accent: "#e9edea",
      action: "render",
      ...saved,
    }),
    [schema, saved],
  );
  const result = movie?.data;
  const [query, setQuery] = useState(""),
    [rows, setRows] = useState<Video[]>([]),
    [searching, setSearching] = useState(false),
    [searchError, setSearchError] = useState("");
  const [clip, setClip] = useState<Clip | null>(null),
    [loading, setLoading] = useState(false),
    [clipError, setClipError] = useState(""),
    [clipVersion, setClipVersion] = useState(0);
  const [image, setImage] = useState(""),
    [updating, setUpdating] = useState(false),
    [previewError, setPreviewError] = useState(""),
    [previewVersion, setPreviewVersion] = useState(0);
  const [animation, setAnimation] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [sharing, setSharing] = useState(() =>
      new URLSearchParams(typeof location === "undefined" ? "" : location.search).has("join"),
    );
  const setQuestions = (questions: string[]) => useDraft.setState({ questions });
  const requested = useRef<"sample" | "render">("sample");
  const acceptedQuality = useRef("");
  const quality = `${values.height || "0"}:${values.fps || "30"}`;
  const [uploading, setUploading] = useState(false),
    [sources, setSources] = useState(false),
    [poster, setPoster] = useState("");
  const search = useRef<AbortController>(null),
    transfer = useRef<AbortController>(null),
    preparing = useRef<AbortController>(null),
    mounted = useRef(true),
    picture = useRef(""),
    localPoster = useRef(""),
    stage = useRef<HTMLElement>(null),
    file = useRef<HTMLInputElement>(null),
    finder = useRef<HTMLInputElement>(null);
  const change = (patch: Values) => setValues((old) => ({ ...old, ...patch }));
  const update = (name: string, value: string) =>
    change({ [name]: value, ...(name === "accent" ? { use_accent: "on" } : {}) });
  const body = (action?: string) => {
    const data = new FormData();
    for (const [key, value] of Object.entries(configuration(values, action))) data.set(key, value);
    if (action) data.set("action", action);
    else {
      const scale = Math.min(1, 960 / width, 540 / height);
      data.set("width", String(Math.max(2, Math.round(width * scale))));
      data.set("height", String(Math.max(2, Math.round(height * scale))));
      data.set("panel", "on");
      data.set("size", "3");
    }
    return data;
  };
  const stamp = seconds(values.start ?? "0"),
    width = clip?.width || 960,
    height = clip?.height || 540;

  useEffect(() => {
    const controller = new AbortController();
    api("/api/minis/timey", formSchema, undefined, controller.signal)
      .then((data) => {
        setSchema(data);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, []);
  useEffect(
    () => () => {
      mounted.current = false;
      search.current?.abort();
      transfer.current?.abort();
      URL.revokeObjectURL(picture.current);
      URL.revokeObjectURL(localPoster.current);
    },
    [],
  );
  useEffect(() => {
    if (
      sources &&
      document.activeElement === stage.current?.querySelector<HTMLElement>(".timer-canvas")
    )
      finder.current?.focus();
  }, [sources]);
  useEffect(() => {
    setClipError("");
    if (mode !== "edit") {
      setLoading(false);
      return;
    }
    if (!values.source) {
      setClip(null);
      setLoading(false);
      return;
    }
    if (
      clip?.complete &&
      clip.source === values.source &&
      acceptedQuality.current === quality &&
      !clipError
    ) {
      setLoading(false);
      return;
    }
    setLoading(!clip || clip.source !== values.source);
    const controller = new AbortController();
    preparing.current = controller;
    const timer = setTimeout(
      async () => {
        if (controller.signal.aborted) return;
        if (stamp == null || stamp > 2147483647) {
          setClipError("Use a start time like 1:20, 2m or 80 seconds");
          setLoading(false);
          return;
        }
        try {
          await backdrop(
            values.source,
            stamp,
            controller.signal,
            (next) => {
              // Publish a replacement only when playable; cancellation keeps the accepted backdrop
              setClip(next);
              acceptedQuality.current = quality;
              setClipError("");
              setLoading(false);
            },
            { height: values.height || "0", fps: values.fps || "30" },
          );
        } catch (caught) {
          const error = caught as Failure;
          if (controller.signal.aborted || error.name === "AbortError") return;
          setClipError(message(error, "preparing your background"));
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      },
      clip?.source === values.source ? 180 : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [values.source, stamp, clipVersion, quality, mode]);
  useEffect(() => {
    if (mode !== "edit") {
      setUpdating(false);
      return;
    }
    if (!clip || seconds(values.length) == null) {
      URL.revokeObjectURL(picture.current);
      picture.current = "";
      setImage("");
      setPreviewError("");
      setUpdating(false);
      return;
    }
    setUpdating(true);
    const controller = new AbortController(),
      timer = setTimeout(async () => {
        try {
          const data = body();
          const blob = await preview(data, controller.signal);
          if (!controller.signal.aborted) {
            URL.revokeObjectURL(picture.current);
            picture.current = URL.createObjectURL(blob);
            setImage(picture.current);
            setPreviewError("");
          }
        } catch (caught) {
          const error = caught as Failure;
          if (error.name !== "AbortError") setPreviewError(message(error, "drawing the timer"));
        } finally {
          if (!controller.signal.aborted) setUpdating(false);
        }
      }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    schema,
    !!clip,
    values.length,
    values.style,
    values.label,
    values.accent,
    values.use_accent,
    values.font,
    values.custom_style,
    values.fps,
    width,
    height,
    previewVersion,
    mode,
  ]);
  useEffect(() => {
    setAnimation("");
    if (
      mode !== "edit" ||
      !image ||
      reduced ||
      hidden ||
      values.motion !== "on" ||
      navigator.connection?.saveData
    )
      return;
    const controller = new AbortController();
    let url = "";
    const timer = setTimeout(async () => {
      try {
        const data = body();
        data.set("animated", "on");
        const blob = await preview(data, controller.signal);
        if (!controller.signal.aborted) {
          url = URL.createObjectURL(blob);
          setAnimation(url);
        }
      } catch (caught) {
        const error = caught as Failure;
        if (!controller.signal.aborted) setPreviewError(message(error, "drawing the timer"));
      }
    }, 700);
    return () => {
      clearTimeout(timer);
      controller.abort();
      URL.revokeObjectURL(url);
    };
  }, [image, reduced, hidden, values.motion, values.fps, mode]);

  function choose(source: string, start = 0) {
    transfer.current?.abort();
    search.current?.abort();
    setUploading(false);
    setSearching(false);
    const chosen = video(source);
    if (chosen) {
      URL.revokeObjectURL(localPoster.current);
      localPoster.current = "";
      setPoster(`https://i.ytimg.com/vi/${chosen.id}/default.jpg`);
    }
    setValues((old) => ({ ...old, source, start: String(start) }));
    setRows([]);
    setSources(false);
    setSearchError("");
  }
  function cancel() {
    search.current?.abort();
    transfer.current?.abort();
    preparing.current?.abort();
    setSearching(false);
    setUploading(false);
    setLoading(false);
    setSources(true);
    URL.revokeObjectURL(localPoster.current);
    localPoster.current = "";
    setPoster("");
    setValues((old) => ({ ...old, source: clip?.source || "" }));
  }
  async function upload(file?: File | string) {
    if (!file) return;
    if (typeof file === "string") setQuery(file);
    if (typeof file !== "string" && file.size > 512 * 1024 ** 2) {
      setSources(true);
      setSearchError("Choose a file under 512 MiB");
      return;
    }
    transfer.current?.abort();
    search.current?.abort();
    const controller = new AbortController();
    transfer.current = controller;
    setUploading(true);
    setSearching(false);
    setRows([]);
    setSearchError("");
    setSources(false);
    URL.revokeObjectURL(localPoster.current);
    localPoster.current =
      typeof file !== "string" && file.type.startsWith("image/") ? URL.createObjectURL(file) : "";
    setPoster(
      typeof file !== "string" && file.type.startsWith("image/") ? localPoster.current : "",
    );
    try {
      const data = await importMedia(file, "background", controller.signal);
      if (!controller.signal.aborted) choose(data.source);
    } catch (caught) {
      const error = caught as Failure;
      if (error.name !== "AbortError") {
        setSources(true);
        setSearchError(message(error, "opening the background"));
      }
    } finally {
      if (!controller.signal.aborted) setUploading(false);
    }
  }

  function drop(data: DataTransfer) {
    try {
      const item = transferred(data),
        chosen = typeof item === "string" ? video(item) : null;
      if (chosen) choose(chosen.url, chosen.start);
      else if (item instanceof File || mediaLink(item)) void upload(item);
      else throw new Error("Drop a picture, video or file link here, or search for a video");
    } catch (caught) {
      const error = caught as Failure;
      setSources(true);
      setSearchError(message(error, "opening the background"));
    }
  }

  async function find(term = query) {
    search.current?.abort();
    const chosen = video(term);
    if (chosen) {
      choose(chosen.url, chosen.start);
      setSearching(false);
      return;
    }
    if (mediaLink(term)) {
      await upload(term.trim());
      return;
    }
    if (!term.trim()) {
      setSearching(false);
      setSources(true);
      setSearchError("Enter a video name or YouTube link");
      return;
    }
    const controller = new AbortController();
    search.current = controller;
    setSearching(true);
    setSources(false);
    setRows([]);
    setSearchError("");
    stage.current?.querySelector<HTMLElement>(".timer-canvas")?.focus();
    try {
      const data = await api(
        `/api/timey/search?${new URLSearchParams({ query: term })}`,
        videosSchema,
        undefined,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setRows(data.rows);
        if (!data.rows.length) setSearchError("No videos found / try another search");
      }
    } catch (caught) {
      const error = caught as Failure;
      if (!controller.signal.aborted && error.name !== "AbortError")
        setSearchError(message(error, "searching YouTube"));
    } finally {
      if (!controller.signal.aborted) {
        setSearching(false);
        setSources(true);
      }
    }
  }
  const paste = useEffectEvent((event: ClipboardEvent) => {
    if (event.defaultPrevented || !event.clipboardData) return;
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest(".timer-sound,.timer-look-settings")) return;
    const editing = target?.closest("input,textarea,[contenteditable=true]");
    if (
      event.clipboardData.files.length ||
      (!editing && mediaLink(event.clipboardData.getData("text")))
    ) {
      event.preventDefault();
      if (event.clipboardData.files.length || video(event.clipboardData.getData("text")))
        drop(event.clipboardData);
      else void upload(event.clipboardData.getData("text"));
    }
  });
  useEffect(() => {
    const handle = (event: ClipboardEvent) => paste(event);
    document.addEventListener("paste", handle);
    return () => document.removeEventListener("paste", handle);
  }, []);

  async function render(action: "sample" | "render") {
    if (busy) return;
    requested.current = action;
    const data = body(action);
    if (values.style === "custom" && !values.custom_style && !values.instructions?.trim()) {
      setError("Describe your custom look before making the video");
      return;
    }
    if (values.style === "custom" && questions.length) {
      if (questions.some((_, index) => !values[`answer_${index}`]?.trim())) {
        setError("Answer the design questions before continuing");
        return;
      }
      data.set(
        "instructions",
        `${values.design_context || values.draft_prompt || values.instructions || ""}\n${questions.map((question, index) => `${question} ${values[`answer_${index}`]}`).join("\n")}`,
      );
    }
    if (String(data.get("instructions") || "").length > 4000) {
      setError(
        "Keep the brief and follow-up answers within 4,000 characters; your text is still here",
      );
      return;
    }
    setBusy(true);
    setError("");
    const phase = action === "sample" ? "preview" : "video";
    useDraft.setState({ phase });
    try {
      const result = await api("/api/minis/timey", timerResultSchema, data);
      if (!mounted.current) return;
      if (result.questions?.length) {
        setQuestions(result.questions);
        setValues((draft) => ({
          ...draft,
          design_context: String(data.get("instructions") || ""),
          answer_0: "",
          answer_1: "",
          answer_2: "",
          answer_3: "",
        }));
        useDraft.setState({ phase: "edit" });
        return;
      }
      if (!result.downloads?.some((file) => file.name.endsWith(".mp4")))
        throw new Error("The video wasn't returned. Your edits are still here; try again");
      if (result.design) {
        setValues((draft) => ({
          ...draft,
          custom_style: result.design!.id,
          design_name: result.design!.name,
          instructions: "",
        }));
        setQuestions([]);
      }
      useDraft.setState({ movie: { phase, quality, data: result } });
    } catch (caught) {
      if (mounted.current) {
        setError(message(caught, "making the video"));
        useDraft.setState({ phase: "edit" });
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  const rebuild = useEffectEvent(() => {
    void render(mode === "preview" ? "sample" : "render");
  });
  useEffect(() => {
    if (mode === "edit" || busy || !movie || movie.phase !== mode || movie.quality === quality)
      return;
    const timer = setTimeout(() => rebuild(), 250);
    return () => clearTimeout(timer);
  }, [mode, busy, movie, quality]);
  const length = seconds(values.length),
    valid =
      clip &&
      clip.source === values.source &&
      (clip.complete || clip.start === stamp) &&
      !loading &&
      !uploading &&
      length != null &&
      length >= 1 &&
      length <= 86400;
  const output = result?.downloads?.find((file) => file.name.endsWith(".mp4"));
  const playback: Clip | null =
    mode !== "edit" && output
      ? {
          url: output.url,
          source: output.url,
          title: values.label || "Your timer",
          kind: "video",
          width,
          height,
          complete: true,
          start: 0,
          duration:
            movie?.phase === "preview"
              ? Math.min(
                  10,
                  (length || 0) + (seconds(values.start_gap) || 0) + (seconds(values.end_gap) || 0),
                )
              : (length || 0) + (seconds(values.start_gap) || 0) + (seconds(values.end_gap) || 0),
        }
      : null;
  const status = busy
    ? "Making your video…"
    : uploading
      ? "Opening your background…"
      : searching
        ? "Finding videos…"
        : loading
          ? "Caching your backdrop…"
          : updating
            ? "Updating timer…"
            : "";
  return (
    <>
      <form
        className="timer-studio"
        data-stage={mode}
        aria-label="Timer studio"
        onSubmit={(event) => {
          event.preventDefault();
          render("render");
        }}
      >
        <aside className="timer-controls timer-left" aria-label="Timing and video quality">
          {mode === "edit" && (
            <section className="timer-section">
              <h2 className="sr-only">Timing</h2>
              <div className="timer-clock" role="group" aria-label="Countdown and gaps">
                <Dial value={length} change={(value) => update("length", `${value}s`)} />
                <div className="timer-gap-rings">
                  <div>
                    <span>Get ready</span>
                    <Dial
                      gap
                      reverse
                      label="Get-ready time"
                      value={seconds(values.start_gap)}
                      change={(value) => update("start_gap", `${value}s`)}
                    />
                  </div>
                  <div>
                    <span>Finish</span>
                    <Dial
                      gap
                      label="Finishing hold"
                      value={seconds(values.end_gap)}
                      change={(value) => update("end_gap", `${value}s`)}
                    />
                  </div>
                </div>
              </div>
              <div className="timer-presets" role="group" aria-label="Quick durations">
                {[5, 10, 25, 45, 60].map((value) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={length === value * 60}
                    className="secondary"
                    onClick={() => update("length", `${value}m`)}
                  >
                    {value}m
                  </button>
                ))}
              </div>
            </section>
          )}
          <div className="timer-output">
            <Quality values={values} change={update} />
            {mode === "edit" && <Publication schema={schema} values={values} change={update} />}
          </div>
        </aside>
        <section ref={stage} className="timer-stage" aria-label="Your timer preview">
          <Connection
            ready={() => {
              setClipVersion((value) => value + 1);
              if (query.trim()) void find(query);
            }}
          >
            <h2 className="sr-only">Timer preview</h2>
            <input
              ref={file}
              hidden
              type="file"
              accept={pictures}
              aria-label="Upload video or image"
              disabled={uploading}
              onChange={(event) => {
                upload(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
            <Canvas
              clip={playback || clip}
              poster={poster}
              onReady={(source) => {
                if (source !== values.source) return;
                setClipError("");
                URL.revokeObjectURL(localPoster.current);
                localPoster.current = "";
                setPoster("");
              }}
              image={
                mode === "edit"
                  ? (!reduced && !hidden && values.motion === "on" && animation) || image
                  : ""
              }
              values={mode === "edit" ? values : { ...values, start: "0", mute: "", music: "" }}
              change={mode === "edit" ? change : () => {}}
              editing={mode === "edit"}
              look={<Look values={values} change={change} />}
              onDropMedia={mode === "edit" ? drop : undefined}
              status={status}
              onCancel={loading || uploading || searching ? cancel : undefined}
              loading={loading || uploading || searching || busy}
              updating={updating}
              onError={() =>
                setClipError("This file couldn't play. Try preparing it again, or add a local copy")
              }
            >
              {mode === "edit" &&
                !searching &&
                !uploading &&
                !loading &&
                (clip && !sources ? (
                  <button
                    type="button"
                    className="timer-change"
                    aria-label="Change background"
                    data-tip="Change background"
                    onClick={() => setSources(true)}
                  >
                    <Icon name="media" />
                    <span>Change background</span>
                  </button>
                ) : (
                  <div className="timer-sources">
                    <div className="timer-source-search">
                      <input
                        ref={finder}
                        type="search"
                        role="combobox"
                        aria-label="Search YouTube or paste a link"
                        enterKeyHint="search"
                        maxLength={200}
                        value={query}
                        onChange={(event) => {
                          setQuery(event.target.value);
                          setSearchError("");
                          setRows([]);
                        }}
                        onPaste={(event) => {
                          const chosen = video(event.clipboardData.getData("text"));
                          if (!chosen && mediaLink(event.clipboardData.getData("text"))) {
                            event.preventDefault();
                            void upload(event.clipboardData.getData("text"));
                            return;
                          }
                          if (chosen) {
                            event.preventDefault();
                            setQuery(chosen.url);
                            choose(chosen.url, chosen.start);
                          }
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                            event.preventDefault();
                            find();
                          }
                        }}
                        placeholder="Search anything here…"
                      />
                      {!searchError && !rows.length && (
                        <Suggestions
                          query={query}
                          choose={(term) => {
                            setQuery(term);
                            void find(term);
                          }}
                        />
                      )}
                      <button
                        type="button"
                        className="timer-upload"
                        aria-label="Add a video or image"
                        data-tip={uploading ? "Opening background…" : "Add a video or image"}
                        disabled={uploading}
                        onClick={() => file.current?.click()}
                      >
                        <Icon name="media" />
                      </button>
                      {clip && (
                        <button
                          type="button"
                          className="quiet"
                          aria-label="Close background search"
                          data-tip="Close background search"
                          onClick={() => setSources(false)}
                        >
                          <Icon name="close" />
                        </button>
                      )}
                    </div>
                    {!rows.length && !searchError && (
                      <p className="timer-source-hint">Drop a video or image</p>
                    )}
                    {searchError && (
                      <Issue title="Let's try another way" message={searchError}>
                        <button
                          type="button"
                          className="quiet"
                          onClick={() => finder.current?.focus()}
                        >
                          Edit search
                        </button>
                      </Issue>
                    )}
                    {!!rows.length && <VideoResults rows={rows} choose={choose} />}
                  </div>
                ))}
            </Canvas>
            {clipError && (
              <Issue title="That background needs another try" message={clipError}>
                <button
                  type="button"
                  className="quiet"
                  disabled={uploading}
                  onClick={() => file.current?.click()}
                >
                  Add a file
                </button>
                <button
                  type="button"
                  className="quiet"
                  onClick={() => setClipVersion((value) => value + 1)}
                >
                  Try backdrop again
                </button>
              </Issue>
            )}
            {previewError && (
              <Issue title="Your timer is still here" message={previewError}>
                <button
                  type="button"
                  className="quiet"
                  onClick={() => setPreviewVersion((value) => value + 1)}
                >
                  Retry timer preview
                </button>
              </Issue>
            )}
            {error && <Issue title="Your edits are still here" message={error} />}
            <div className="timer-actions">
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  mode === "edit" ? void render("sample") : useDraft.setState({ phase: "edit" })
                }
                disabled={mode === "edit" && (busy || !valid)}
              >
                {mode === "edit" ? "Watch preview" : "Edit video"}
              </button>
              <button
                type="button"
                disabled={
                  busy ||
                  (mode === "edit" && !valid) ||
                  (mode === "video" &&
                    (!output || movie?.phase !== "video" || movie.quality !== quality))
                }
                onClick={() => (mode === "video" ? setSaving(true) : void render("render"))}
              >
                {mode === "video" ? "Save video" : "Make video"}
              </button>
            </div>
            <button type="button" className="quiet timer-share" onClick={() => setSharing(true)}>
              Make it together
            </button>
          </Connection>
        </section>
        {clip && mode === "edit" && (
          <aside className="timer-controls timer-right" aria-label="Timer appearance">
            <section className="timer-section">
              <h2 className="sr-only">Timer look</h2>
              <Themes
                values={values}
                change={change}
                questions={questions}
                onDesign={() => void render(requested.current)}
                busy={busy}
              />
            </section>
          </aside>
        )}
      </form>
      {sharing && <Share close={() => setSharing(false)} />}
      {saving && output && (
        <Save
          source={output.url}
          title={values.label || values.design_name || "My countdown"}
          close={() => setSaving(false)}
        />
      )}
    </>
  );
}
