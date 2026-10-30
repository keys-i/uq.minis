import { Suggestions } from "./suggest.tsx";
import { useEffect, useRef, useState } from "react";
import { api, type Failure } from "../shared/api.ts";
import { Icon } from "../shared/icons.tsx";
import { Issue, Status, message } from "./feedback.tsx";
import { importMedia, mediaLink, prepare } from "./media.ts";
import {
  clamp,
  transferred,
  music,
  video,
  videosSchema,
  type Clip,
  type Values,
  type Video,
} from "./model.ts";

export function videoSound(values: Values): boolean {
  return values.mute !== "on" && (!values.music || values.mix_audio === "on");
}

export function Sound({
  values,
  change,
  background,
  onListen,
}: {
  values: Values;
  change: (patch: Values) => void;
  background: React.RefObject<HTMLVideoElement | null>;
  onListen: () => void;
}) {
  const [query, setQuery] = useState(""),
    [rows, setRows] = useState<Video[]>([]),
    [track, setTrack] = useState<Clip | null>(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [playing, setPlaying] = useState(false),
    [dropping, setDropping] = useState(false);
  const audio = useRef<HTMLAudioElement>(null),
    request = useRef<AbortController>(null),
    preparing = useRef<AbortController>(null),
    depth = useRef(0),
    armed = useRef(false);
  const graph = useRef<{ context: AudioContext; gain: GainNode } | null>(null);
  const volume = clamp(Number(values.music_volume ?? 1), 0, 2);
  useEffect(() => {
    if (graph.current) graph.current.gain.gain.value = volume;
  }, [volume]);
  useEffect(() => {
    audio.current?.pause();
    armed.current = false;
    setError("");
    if (!values.music) {
      setTrack(null);
      setBusy("");
      return;
    }
    if (track?.source === values.music) {
      setBusy("");
      return;
    }
    const controller = new AbortController();
    preparing.current = controller;
    const timer = setTimeout(async () => {
      setBusy("Opening music…");
      const body = new FormData();
      body.set("source", values.music);
      body.set("audio", "on");
      body.set("complete", "on");
      try {
        const ready = await prepare(body, controller.signal);
        if (!controller.signal.aborted) setTrack({ ...ready, source: values.music, start: 0 });
      } catch (caught) {
        const failure = caught as Failure;
        if (!controller.signal.aborted) setError(message(failure, "opening music"));
      } finally {
        if (!controller.signal.aborted) setBusy("");
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [values.music]);
  useEffect(() => {
    const player = audio.current!,
      backdrop = background.current;
    const pause = () => player.pause();
    const play = () => {
      if (armed.current)
        player.play().catch((failure) => setError(message(failure, "opening music")));
    };
    const seek = () => {
      if (armed.current) player.currentTime = 0;
    };
    backdrop?.addEventListener("pause", pause);
    backdrop?.addEventListener("play", play);
    backdrop?.addEventListener("seeked", seek);
    return () => {
      backdrop?.removeEventListener("pause", pause);
      backdrop?.removeEventListener("play", play);
      backdrop?.removeEventListener("seeked", seek);
    };
  }, [background, track?.url]);
  useEffect(() => {
    const player = audio.current;
    return () => {
      request.current?.abort();
      player?.pause();
      player?.removeAttribute("src");
      player?.load();
      if (graph.current && graph.current.context.state !== "closed")
        void graph.current.context.close();
    };
  }, []);
  function choose(source: string) {
    request.current?.abort();
    setBusy("");
    change({ music: source });
    setRows([]);
    setQuery("");
    setError("");
  }
  async function find(term = query) {
    request.current?.abort();
    const selected = video(term);
    if (selected) {
      choose(selected.url);
      return;
    }
    if (mediaLink(term)) {
      await upload(term.trim());
      return;
    }
    if (!term.trim()) {
      setBusy("");
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setBusy("Finding music…");
    setError("");
    try {
      const data = await api(
        `/api/timey/search?${new URLSearchParams({ query: term })}`,
        videosSchema,
        undefined,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setRows(data.rows);
        if (!data.rows.length) setError("No music found / try another search");
      }
    } catch (caught) {
      const failure = caught as Failure;
      if (!controller.signal.aborted) setError(message(failure, "searching YouTube"));
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  async function upload(file?: File | string) {
    if (!file) return;
    if (typeof file === "string") setQuery(file);
    if (typeof file !== "string" && file.size > 512 * 1024 ** 2) {
      setError("Choose a file under 512 MiB");
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy("Opening music…");
    setError("");
    try {
      const result = await importMedia(file, "music", controller.signal);
      if (!controller.signal.aborted) choose(result.source);
    } catch (caught) {
      const failure = caught as Failure;
      if (!controller.signal.aborted) setError(message(failure, "opening music"));
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  function take(data: DataTransfer) {
    try {
      const item = transferred(data);
      if (item instanceof File) void upload(item);
      else {
        const selected = video(item);
        if (selected) choose(selected.url);
        else if (mediaLink(item)) void upload(item);
        else setError("Add an audio file, a video with sound or a music link");
      }
    } catch (error) {
      setError(message(error, "adding music"));
    }
  }
  function listen() {
    const player = audio.current!;
    if (!player.paused) {
      armed.current = false;
      player.pause();
      return;
    }
    if (!graph.current) {
      const context = new AudioContext(),
        gain = context.createGain();
      context.createMediaElementSource(player).connect(gain);
      gain.connect(context.destination);
      graph.current = { context, gain };
    }
    armed.current = true;
    graph.current.gain.gain.value = volume;
    onListen();
    graph.current.context.resume().catch((failure) => setError(message(failure, "opening music")));
    player.play().catch((failure) => setError(message(failure, "opening music")));
    background.current?.play().catch((failure) => setError(message(failure, "opening music")));
  }
  return (
    <div
      className="timer-sound"
      onPaste={(event) => {
        if (event.clipboardData.files.length || mediaLink(event.clipboardData.getData("text"))) {
          event.preventDefault();
          event.stopPropagation();
          take(event.clipboardData);
        }
      }}
      data-dropping={dropping || undefined}
      onDragEnter={(event) => {
        event.stopPropagation();
        event.preventDefault();
        depth.current++;
        setDropping(true);
      }}
      onDragOver={(event) => {
        event.stopPropagation();
        event.preventDefault();
      }}
      onDragLeave={(event) => {
        event.stopPropagation();
        depth.current = Math.max(0, depth.current - 1);
        if (!depth.current) setDropping(false);
      }}
      onDrop={(event) => {
        event.stopPropagation();
        event.preventDefault();
        depth.current = 0;
        setDropping(false);
        take(event.dataTransfer);
      }}
    >
      <div className="timer-source-search">
        <input
          type="search"
          role="combobox"
          aria-label="Search music or paste a link"
          placeholder="Search anything here…"
          value={query}
          maxLength={200}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.nativeEvent.isComposing) {
              event.preventDefault();
              find();
            }
          }}
        />
        <Suggestions
          query={query}
          choose={(term) => {
            setQuery(term);
            void find(term);
          }}
        />
        <label className="timer-upload" data-tip="Add music">
          <Icon name="upload" />
          <input
            type="file"
            accept={music}
            aria-label="Upload music"
            onChange={(event) => {
              upload(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </label>
      </div>
      {!!rows.length && (
        <div className="sound-results">
          {rows.map((row) => {
            const selected = video(row.url);
            return (
              <button type="button" className="quiet" key={row.url} onClick={() => choose(row.url)}>
                {selected && (
                  <img
                    src={`https://i.ytimg.com/vi/${selected.id}/mqdefault.jpg`}
                    alt=""
                    width="80"
                    height="45"
                    loading="lazy"
                    referrerPolicy="no-referrer"
                  />
                )}
                <span>
                  {row.title}
                  <small>{row.length}</small>
                </span>
              </button>
            );
          })}
        </div>
      )}
      <audio
        ref={audio}
        src={track?.url}
        preload="metadata"
        loop
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onError={() => {
          if (track) setError("This music couldn't play / choose it again");
        }}
      />
      {!!(values.music || busy) && (
        <div className="sound-track">
          <button
            type="button"
            className="quiet"
            aria-label={playing ? "Pause music preview" : "Play music preview"}
            data-tip={playing ? "Pause music" : "Listen"}
            disabled={!track || !!busy}
            onClick={listen}
          >
            <Icon name={playing ? "pause" : "play"} />
          </button>
          <span>{busy || track?.title}</span>
          {values.music && (
            <button
              type="button"
              className="quiet"
              aria-label="Remove music"
              data-tip="Remove music"
              onClick={() => choose("")}
            >
              <Icon name="close" />
            </button>
          )}
        </div>
      )}
      <div className="sound-controls">
        <Icon name="music" />
        <input
          type="range"
          aria-label="Music volume"
          aria-valuetext={`${Math.round(volume * 100)}%`}
          min="0"
          max="2"
          step=".05"
          value={volume}
          onChange={(event) => change({ music_volume: event.target.value })}
        />
        <button
          type="button"
          className="quiet"
          aria-label="Mix video audio with music"
          data-tip="Mix video audio"
          aria-pressed={values.mix_audio === "on"}
          disabled={values.mute === "on"}
          onClick={() => change({ mix_audio: values.mix_audio === "on" ? "" : "on" })}
        >
          <Icon name="mix" />
        </button>
        <button
          type="button"
          className="quiet"
          aria-label="Video sound"
          data-tip={values.mute === "on" ? "Unmute video" : "Mute video"}
          aria-pressed={values.mute !== "on"}
          onClick={() => change({ mute: values.mute === "on" ? "" : "on" })}
        >
          <Icon name={values.mute === "on" ? "video-muted" : "video-sound"} />
        </button>
      </div>
      {busy && (
        <Status
          text={busy}
          cancel={() => {
            request.current?.abort();
            preparing.current?.abort();
            setBusy("");
            if (track?.source !== values.music) change({ music: track?.source || "" });
          }}
        />
      )}
      {error && (
        <Issue title="Let's find your sound" message={error}>
          <button
            type="button"
            className="quiet"
            onClick={() =>
              document.querySelector<HTMLInputElement>('[aria-label="Upload music"]')?.click()
            }
          >
            Choose a file
          </button>
        </Issue>
      )}

      {dropping && (
        <div className="sound-drop" aria-hidden="true">
          <Icon name="music" />
        </div>
      )}
    </div>
  );
}
