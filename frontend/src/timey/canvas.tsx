import React, { useContext, useEffect, useId, useRef, useState } from "react";
import { Motion } from "../shared/display.tsx";
import { Icon } from "../shared/icons.tsx";
import { Colour } from "./colour.tsx";
import { Sound, videoSound } from "./sound.tsx";
import { Status } from "./feedback.tsx";
import { Mist } from "./mist.tsx";
import { Bubble } from "../shared/bubble.tsx";
import type { Clip, Values } from "./model.ts";
import { clamp, clock, dock, move, placement, resize, resume, scale, seconds } from "./model.ts";

const places: [string, [string, number, number][]][] = [
  [
    "Edges",
    [
      ["Left", 0, 0.5],
      ["Right", 1, 0.5],
      ["Top", 0.5, 0],
      ["Bottom", 0.5, 1],
    ],
  ],
  [
    "Corners",
    [
      ["Top left", 0, 0],
      ["Top right", 1, 0],
      ["Bottom left", 0, 1],
      ["Bottom right", 1, 1],
    ],
  ],
  ["", [["Centre", 0.5, 0.5]]],
];

interface Props {
  clip: Clip | null;
  image: string;
  poster?: string;
  onReady?: (source: string) => void;
  values: Values;
  change: (patch: Values) => void;
  look?: React.ReactNode;
  status?: string;
  loading?: boolean;
  updating?: boolean;
  onError: (error?: unknown) => void;
  onDropMedia?: (data: DataTransfer) => void;
  onCancel?: () => void;
  children?: React.ReactNode;
  editing?: boolean;
}
interface Gesture {
  x: number;
  y: number;
  values: Values;
  edge: string;
  scale: number;
  element: HTMLButtonElement;
  pointer: number;
  moved?: boolean;
  patch?: Values;
}
type PointEvent = React.PointerEvent<HTMLElement>;

export function Canvas({
  clip,
  image,
  poster,
  onReady,
  values,
  change,
  look,
  status,
  loading,
  updating,
  onError,
  onDropMedia,
  onCancel,
  children,
  editing = true,
}: Props) {
  const { reduced, hidden } = useContext(Motion),
    player = useRef<HTMLVideoElement>(null),
    backdrop = useRef<HTMLImageElement>(null),
    canvas = useRef<HTMLDivElement>(null),
    drag = useRef<Gesture | null>(null),
    label = useRef<HTMLInputElement>(null),
    expiry = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    focusLabel = useRef(false);
  const menu = useRef<HTMLElement>(null),
    arrange = useRef<HTMLButtonElement>(null),
    closing = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    hovering = useRef(false),
    menuId = useId();
  const [draft, setDraft] = useState<Values | null>(null),
    [decoded, setDecoded] = useState(""),
    [failed, setFailed] = useState(""),
    [tools, setTools] = useState(false),
    [playing, setPlaying] = useState(false),
    [muted, setMuted] = useState(true);
  const [current, setCurrent] = useState(0),
    [duration, setDuration] = useState(10),
    [buffer, setBuffer] = useState(0),
    [seeking, setSeeking] = useState<number | null>(null);
  const [volume, setVolume] = useState(0.65);
  const [dropping, setDropping] = useState(false),
    depth = useRef(0);
  const [gesture, setGesture] = useState(""),
    [snap, setSnap] = useState<Values | null>(null);
  const head = useRef({ source: "", time: 0, paused: false });
  const accepts = (event: React.DragEvent) =>
    onDropMedia &&
    Array.from(event.dataTransfer.types).some(
      (type) => type === "Files" || type === "text/uri-list" || type === "text/plain",
    );
  const width = clip?.width || 960,
    height = clip?.height || 540,
    settings = { ...values, ...draft },
    box = placement(settings, width, height);
  const anchor = draft ? placement(values, width, height) : box;
  const destination = snap ? placement({ ...values, ...snap }, width, height) : null;
  const start = clip?.start || 0,
    total = clip?.duration || start + duration,
    position = seeking ?? start + current;
  const misty = !!loading || (!!clip && decoded !== clip.url && failed !== clip.url);
  const gentle = !!(reduced || hidden || navigator.connection?.saveData);
  const origin = seconds(values.start || "0") || 0;
  const panels: [string, string, React.ReactNode][] = [
    ["look", "Fine-tune the look", look],
    [
      "music",
      "Music & sound",
      <Sound
        key={clip?.source}
        values={values}
        change={change}
        background={player}
        onListen={() => setMuted(false)}
      />,
    ],
    [
      "colour",
      "Timer colour",
      <Colour
        value={values.accent || "#e9edea"}
        custom={values.use_accent === "on"}
        change={change}
      />,
    ],
  ];
  useEffect(() => {
    const action = drag.current;
    drag.current = null;
    if (action?.element.hasPointerCapture(action.pointer))
      action.element.releasePointerCapture(action.pointer);
    setCurrent(clip?.complete ? seconds(values.start || "0") || 0 : 0);
    setBuffer(0);
    setDuration(10);
    setSeeking(null);
    setTools(false);
    setDraft(null);
    setGesture("");
    setSnap(null);
    const element = player.current;
    return () => {
      if (element) {
        element.pause();
        element.removeAttribute("src");
        element.load();
      }
    };
  }, [clip?.source]);
  useEffect(() => {
    if (hidden || reduced) player.current?.pause();
  }, [hidden, reduced, clip?.url]);
  useEffect(() => {
    if (player.current) player.current.volume = volume;
  }, [volume, clip?.url]);
  useEffect(
    () => () => {
      clearTimeout(expiry.current);
      clearTimeout(closing.current);
    },
    [],
  );
  useEffect(() => {
    if (tools && focusLabel.current) {
      label.current?.focus();
      focusLabel.current = false;
    }
  }, [tools]);
  useEffect(() => {
    if (!tools)
      canvas.current
        ?.querySelectorAll<HTMLElement>("[popover]")
        .forEach((panel) => panel.hidePopover());
  }, [tools]);
  function idle() {
    clearTimeout(expiry.current);
    expiry.current = setTimeout(() => {
      if (
        !drag.current &&
        !canvas.current?.querySelector(".timer-tools:focus-within,.timer-tools:hover,:popover-open")
      )
        setTools(false);
    }, 3200);
  }
  function select() {
    setTools(true);
    idle();
  }
  function configure(event: React.MouseEvent<HTMLButtonElement>, name: string) {
    event.preventDefault();
    const panel = document.getElementById(`${menuId}-${name}`)!;
    if (panel.matches(":popover-open")) {
      panel.hidePopover();
      return;
    }
    panel.showPopover();
    idle();
  }
  function layouts(event: React.MouseEvent | React.KeyboardEvent) {
    event.preventDefault();
    clearTimeout(closing.current);
    const expanded = menu.current!.matches(":popover-open");
    if (event.type === "click" && expanded && !hovering.current) {
      menu.current!.hidePopover();
      return;
    }
    hovering.current = false;
    menu.current!.showPopover();
    (
      menu.current!.querySelector<HTMLElement>("[aria-pressed=true]") ||
      menu.current!.querySelector<HTMLElement>("button")
    )?.focus();
  }
  function leave() {
    clearTimeout(closing.current);
    closing.current = setTimeout(() => {
      if (
        hovering.current &&
        !drag.current &&
        !menu.current?.matches(":hover") &&
        !arrange.current?.matches(":hover") &&
        !menu.current?.contains(document.activeElement)
      )
        menu.current?.hidePopover();
    }, 180);
  }
  function target(event: PointEvent) {
    if (event.altKey) return null;
    const hit = document.elementFromPoint(event.clientX, event.clientY);
    if (drag.current && hit?.closest(".timer-arrange") === arrange.current) {
      clearTimeout(closing.current);
      hovering.current = true;
      if (!menu.current!.matches(":popover-open")) menu.current!.showPopover();
    }
    const option = hit?.closest<HTMLElement>("[data-x][data-y]");
    if (option && menu.current?.contains(option))
      return { x: option.dataset.x!, y: option.dataset.y! };
    const bounds = canvas.current!.getBoundingClientRect();
    return dock(
      event.clientX - bounds.left,
      event.clientY - bounds.top,
      bounds.width,
      bounds.height,
    );
  }
  function seek(value: string | number) {
    const next = clamp(Number(value), 0, Math.max(0, total - 0.1));
    if (clip?.complete || (next >= start && next < start + duration)) {
      if (player.current) player.current.currentTime = next - start;
      setCurrent(next - start);
      setSeeking(null);
      if (clip?.complete) change({ start: String(Math.floor(next)) });
    } else {
      setSeeking(next);
      change({ start: String(Math.floor(next)) });
    }
  }
  function loaded(event: React.SyntheticEvent<HTMLVideoElement>) {
    const element = event.currentTarget;
    setDuration(element.duration || 10);
    element.currentTime = resume(head.current, clip!, element.duration, origin);
    setCurrent(element.currentTime);
    setSeeking(null);
  }
  function tick(event: React.SyntheticEvent<HTMLVideoElement>) {
    const element = event.currentTarget;
    if (editing && clip?.complete && element.currentTime >= origin + 10) {
      if (reduced) element.pause();
      else element.currentTime = origin;
    }
    setCurrent(element.currentTime);
    head.current = {
      source: clip!.source,
      time: start + element.currentTime,
      paused: element.paused,
    };
  }
  function ended(event: React.SyntheticEvent<HTMLVideoElement>) {
    if (editing && clip?.complete && !reduced) {
      event.currentTarget.currentTime = origin;
      startPlayback(event.currentTarget);
    }
  }
  function startPlayback(element: HTMLVideoElement) {
    element.play().catch((error: Error) => {
      // A cache swap or pause can cancel play without making the media unusable
      if (error.name !== "AbortError") onError(error);
    });
  }
  function play() {
    const element = player.current;
    if (!element || !element.paused) {
      element?.pause();
      return;
    }
    if (element.ended || (editing && clip?.complete && element.currentTime >= origin + 10))
      element.currentTime = origin;
    startPlayback(element);
  }
  function begin(event: React.PointerEvent<HTMLButtonElement>, edge = "") {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      values,
      edge,
      scale: width / canvas.current!.getBoundingClientRect().width,
      element: event.currentTarget,
      pointer: event.pointerId,
    };
    select();
  }
  function moving(event: React.PointerEvent<HTMLButtonElement>) {
    const action = drag.current;
    if (!action) return;
    if (!action.moved && Math.hypot(event.clientX - action.x, event.clientY - action.y) < 3) return;
    action.moved = true;
    setGesture(action.edge ? "resize" : "move");
    const dx = (event.clientX - action.x) * action.scale,
      dy = (event.clientY - action.y) * action.scale;
    const next = action.edge
      ? resize(action.values, width, height, dx, dy, action.edge)
      : move(action.values, width, height, dx, dy);
    action.patch = next;
    setDraft(next);
    setSnap(action.edge ? null : target(event));
  }
  function finish(event: React.PointerEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>) {
    const action = drag.current;
    if (!action) return;
    drag.current = null;
    if (event.type === "pointerup" && action.patch) {
      const preset = action.edge || !("clientX" in event) ? null : target(event);
      change(preset || action.patch);
    }
    if (action.element.hasPointerCapture(action.pointer))
      action.element.releasePointerCapture(action.pointer);
    menu.current?.hidePopover();
    setDraft(null);
    setGesture("");
    setSnap(null);
    idle();
  }
  function keyboard(event: React.KeyboardEvent<HTMLButtonElement>, sizing = "") {
    const step = event.shiftKey ? 20 : 4,
      delta = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, -step],
        ArrowDown: [0, step],
      }[event.key as "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown"];
    if (delta) {
      event.preventDefault();
      change(
        sizing
          ? resize(values, width, height, delta[0], delta[1], sizing)
          : move(values, width, height, delta[0], delta[1]),
      );
    } else if (event.key === "Home" && !sizing) {
      event.preventDefault();
      change({ x: ".5", y: ".5" });
    } else if (["+", "=", "-"].includes(event.key)) {
      event.preventDefault();
      change(
        scale(
          values,
          width,
          height,
          clamp(Number(values.size) + (event.key === "-" ? -0.1 : 0.1), 0.5, 3),
        ),
      );
    } else if (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey)) open(event);
  }
  const open = (event: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>) => {
    event.preventDefault();
    event.currentTarget.focus();
    if (tools) label.current?.focus();
    else focusLabel.current = true;
    select();
  };
  return (
    <div
      className="timer-editor"
      data-tools={tools ? "timer" : undefined}
      data-gesture={gesture || undefined}
      data-empty={!clip || undefined}
      onKeyDown={(event) => {
        if (
          event.key === "Escape" &&
          (drag.current || !canvas.current!.querySelector<HTMLElement>(":popover-open"))
        ) {
          event.preventDefault();
          finish(event);
          setTools(false);
          canvas.current!.querySelector<HTMLElement>(".timer-object")?.focus();
        }
      }}
    >
      <div
        ref={canvas}
        className="timer-canvas"
        data-dropping={dropping || undefined}
        data-loading={loading || undefined}
        data-misty={misty || undefined}
        data-gentle={gentle || undefined}
        data-ready={(!!clip && decoded === clip.url) || undefined}
        tabIndex={0}
        role="group"
        aria-label="Background preview"
        style={{ aspectRatio: `${width}/${height}`, "--ratio": width / height }}
        aria-busy={!!(status || loading || updating || misty)}
        onPointerMove={(event) => {
          if (gentle || (!misty && !event.currentTarget.querySelector("[data-refining]"))) return;
          const bounds = event.currentTarget.getBoundingClientRect();
          event.currentTarget.style.setProperty("--mist-x", `${event.clientX - bounds.left}px`);
          event.currentTarget.style.setProperty("--mist-y", `${event.clientY - bounds.top}px`);
        }}
        onDragEnter={(event) => {
          if (accepts(event)) {
            event.preventDefault();
            depth.current++;
            setDropping(true);
          }
        }}
        onDragOver={(event) => {
          if (accepts(event)) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }
        }}
        onDragLeave={() => {
          depth.current = Math.max(0, depth.current - 1);
          if (!depth.current) setDropping(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          depth.current = 0;
          setDropping(false);
          onDropMedia?.(event.dataTransfer);
        }}
        onPointerLeave={idle}
        onPointerDown={(event) => {
          if (
            !(event.target as Element).closest(
              ".timer-object-box,.timer-tools,.timer-player,.timer-settings",
            )
          )
            setTools(false);
        }}
        onContextMenu={(event) => {
          if (!clip || !image || (event.target as Element).closest(".timer-tools")) return;
          const bounds = canvas.current!.getBoundingClientRect(),
            x = ((event.clientX - bounds.left) / bounds.width) * width,
            y = ((event.clientY - bounds.top) / bounds.height) * height;
          if (x >= box.left && x <= box.left + box.w && y >= box.top && y <= box.top + box.h)
            open(event);
        }}
      >
        {clip?.kind === "image" ? (
          <img
            key={clip.url}
            ref={backdrop}
            className="timer-picture"
            src={clip.url}
            alt={clip.title || "Your background"}
            draggable="false"
            onLoad={() => {
              setDecoded(clip.url);
              onReady?.(clip.source);
            }}
            onError={(event) => {
              setFailed(clip.url);
              onError(event);
            }}
          />
        ) : clip ? (
          <video
            key={clip.source}
            ref={player}
            src={clip.url}
            aria-label="Cached backdrop preview"
            autoPlay={!reduced && (head.current.source !== clip.source || !head.current.paused)}
            muted={muted || !videoSound(values)}
            loop={!reduced && !clip.complete}
            playsInline
            preload="auto"
            onError={(event) => {
              if (event.currentTarget.error?.code === 1) return;
              setFailed(clip.url);
              onError(event);
            }}
            onLoadedData={() => {
              setDecoded(clip.url);
              onReady?.(clip.source);
            }}
            onLoadedMetadata={loaded}
            onTimeUpdate={tick}
            onEnded={ended}
            onPlay={(event) => {
              head.current = {
                source: clip.source,
                time: start + event.currentTarget.currentTime,
                paused: false,
              };
              setPlaying(true);
            }}
            onPause={(event) => {
              if (event.currentTarget.readyState >= 2)
                head.current = {
                  source: clip.source,
                  time: start + event.currentTarget.currentTime,
                  paused: true,
                };
              setPlaying(false);
            }}
            onProgress={(event) => {
              const ranges = event.currentTarget.buffered;
              setBuffer(ranges.length ? ranges.end(ranges.length - 1) : 0);
            }}
          />
        ) : (
          <div className="timer-backdrop" />
        )}
        {children}
        <Mist
          waiting={misty}
          poster={poster}
          media={clip?.kind === "image" ? backdrop : player}
          source={decoded === clip?.url ? clip.source : undefined}
          gentle={gentle}
          timer={clock(seconds(values.length))}
        />
        <div className="timer-progress">
          {(status || misty) && (
            <Status text={status || "Bringing the picture into focus…"} cancel={onCancel} />
          )}
        </div>
        {clip && image && destination && (
          <div
            className="timer-snap"
            aria-hidden="true"
            style={{
              left: `${(destination.left / width) * 100}%`,
              top: `${(destination.top / height) * 100}%`,
              width: `${(destination.w / width) * 100}%`,
              height: `${(destination.h / height) * 100}%`,
            }}
          />
        )}
        {clip && image && (
          <div
            className="timer-object-box"
            data-dragging={!!gesture || undefined}
            style={{
              left: `${(box.left / width) * 100}%`,
              top: `${(box.top / height) * 100}%`,
              width: `${(box.w / width) * 100}%`,
              height: `${(box.h / height) * 100}%`,
            }}
          >
            <button
              type="button"
              className="timer-object"
              aria-label="Move timer"
              aria-expanded={tools}
              aria-controls="timer-tools"
              data-tip="Move timer"
              onClick={select}
              onPointerDown={begin}
              onPointerMove={moving}
              onPointerUp={finish}
              onPointerCancel={finish}
              onLostPointerCapture={finish}
              onKeyDown={keyboard}
            >
              <img
                src={image}
                alt={`${values.style} timer / ${values.length}${values.label ? ` / ${values.label}` : ""}`}
                draggable="false"
              />
            </button>
            {[
              ["nw", "top left"],
              ["ne", "top right"],
              ["sw", "bottom left"],
              ["se", "bottom right"],
            ].map(([edge, name]) => (
              <button
                key={edge}
                type="button"
                className="timer-handle"
                data-corner={edge}
                aria-label={`Resize ${name}`}
                data-tip="Resize timer"
                onPointerDown={(event) => begin(event, edge)}
                onPointerMove={moving}
                onPointerUp={finish}
                onPointerCancel={finish}
                onLostPointerCapture={finish}
                onKeyDown={(event) => keyboard(event, edge)}
              >
                <span />
              </button>
            ))}
          </div>
        )}
        {clip && image && (
          <div
            id="timer-tools"
            className="timer-tools timer-object-tools"
            role="toolbar"
            aria-label="Timer tools"
            data-side={anchor.top > height * 0.2 ? "above" : "below"}
            style={{
              top:
                anchor.top > height * 0.2
                  ? `max(10px, calc(${(anchor.top / height) * 100}% - 80px))`
                  : `min(calc(100% - 130px), calc(${((anchor.top + anchor.h) / height) * 100}% + 12px))`,
            }}
            onPointerMove={idle}
            onPointerLeave={idle}
            onFocusCapture={idle}
            onBlurCapture={idle}
          >
            <label data-tip="Timer label">
              <input
                ref={label}
                aria-label="Timer label"
                placeholder="Add a label"
                maxLength={32}
                value={values.label || ""}
                onChange={(event) => change({ label: event.target.value })}
              />
            </label>
            <button
              type="button"
              className="quiet"
              aria-label="Fine-tune the look"
              data-tip="Look"
              aria-haspopup="dialog"
              aria-controls={`${menuId}-look`}
              popoverTarget={`${menuId}-look`}
              onClick={(event) => configure(event, "look")}
            >
              <Icon name="look" />
            </button>
            <button
              type="button"
              className="quiet timer-swatch"
              aria-label="Timer colour"
              data-tip="Colour"
              aria-haspopup="dialog"
              aria-controls={`${menuId}-colour`}
              popoverTarget={`${menuId}-colour`}
              onClick={(event) => configure(event, "colour")}
            >
              <span style={{ background: values.accent || "#e9edea" }} />
            </button>
            <button
              ref={arrange}
              type="button"
              className="quiet timer-arrange"
              aria-label="Align timer"
              data-tip="Align timer"
              aria-haspopup="dialog"
              popoverTarget={menuId}
              onClick={layouts}
              onContextMenu={layouts}
              onPointerEnter={(event) => {
                if (event.pointerType !== "mouse") return;
                clearTimeout(closing.current);
                hovering.current = true;
                if (!menu.current!.matches(":popover-open")) menu.current!.showPopover();
              }}
              onPointerLeave={leave}
              onKeyDown={(event) => {
                if (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey))
                  layouts(event);
              }}
            >
              <Icon name="position" />
            </button>
            <button
              type="button"
              className="quiet"
              aria-label="Music & sound"
              data-tip="Music"
              aria-haspopup="dialog"
              aria-controls={`${menuId}-music`}
              popoverTarget={`${menuId}-music`}
              onClick={(event) => configure(event, "music")}
            >
              <Icon name="music" />
            </button>
            <button
              type="button"
              className="quiet"
              aria-label="Close timer tools"
              data-tip="Close"
              onClick={() => {
                setTools(false);
                canvas.current!.querySelector<HTMLElement>(".timer-object")?.focus();
              }}
            >
              <Icon name="close" />
            </button>
            <Bubble
              ref={menu}
              id={menuId}
              label="Timer placement"
              className="timer-layout"
              focus={false}
              onToggle={(open) => {
                if (!open) {
                  clearTimeout(closing.current);
                  hovering.current = false;
                  setSnap(null);
                }
                idle();
              }}
              onPointerEnter={() => clearTimeout(closing.current)}
              onPointerLeave={() => {
                if (!drag.current) setSnap(null);
                leave();
              }}
              onFocusCapture={() => {
                hovering.current = false;
              }}
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null))
                  setSnap(null);
              }}
            >
              {places.map(([group, options]) => (
                <fieldset key={group} className={group ? "" : "timer-layout-centre"}>
                  <legend className={group ? "" : "sr-only"}>{group || "Centre"}</legend>
                  {options.map(([name, x, y]) => (
                    <button
                      key={name}
                      type="button"
                      aria-label={name}
                      data-tip={name}
                      data-x={x}
                      data-y={y}
                      aria-pressed={box.x === x && box.y === y}
                      onPointerEnter={() => setSnap({ x: String(x), y: String(y) })}
                      onFocus={() => setSnap({ x: String(x), y: String(y) })}
                      onClick={() => {
                        change({ x: String(x), y: String(y) });
                        menu.current!.hidePopover();
                        arrange.current?.focus();
                      }}
                    >
                      <Icon name={`align-${x}-${y}`} />
                      {!group && <span>Centre</span>}
                    </button>
                  ))}
                </fieldset>
              ))}
            </Bubble>
          </div>
        )}
        {clip &&
          editing &&
          panels.map(([name, title, content]) => (
            <Bubble key={name} id={`${menuId}-${name}`} label={title} onToggle={idle}>
              {content}
            </Bubble>
          ))}
        {clip && clip.kind !== "image" && (
          <div className="timer-player" role="group" aria-label="Video playback">
            <div className="timer-volume">
              <input
                type="range"
                aria-label="Preview volume"
                min="0"
                max="1"
                step=".05"
                value={muted ? 0 : volume}
                onChange={(event) => {
                  setVolume(Number(event.target.value));
                  setMuted(false);
                }}
              />
              <button
                type="button"
                className="quiet"
                aria-label={muted ? "Unmute preview" : "Mute preview"}
                data-tip={muted ? "Unmute" : "Mute"}
                onClick={() => setMuted((value) => !value)}
              >
                <Icon name={muted ? "muted" : "volume"} />
              </button>
            </div>
            <div className="timer-transport">
              <button
                type="button"
                className="quiet"
                aria-label="Back 10 seconds"
                data-tip="Back 10 seconds"
                disabled={!clip || loading || position <= 0}
                onClick={() => seek(Math.max(0, position - 10))}
              >
                <Icon name="back10" />
              </button>
              <button
                type="button"
                className="quiet timer-play"
                aria-label={playing ? "Pause preview" : "Play preview"}
                data-tip={playing ? "Pause" : "Play"}
                disabled={!clip || loading}
                onClick={play}
              >
                <Icon name={playing ? "pause" : "play"} />
              </button>
              <button
                type="button"
                className="quiet"
                aria-label="Forward 10 seconds"
                data-tip="Forward 10 seconds"
                disabled={
                  !clip || loading || ((clip?.duration || 0) > 0 && position >= total - 0.1)
                }
                onClick={() =>
                  clip?.duration
                    ? seek(position + 10)
                    : change({ start: String(Math.floor(position + 10)) })
                }
              >
                <Icon name="forward10" />
              </button>
            </div>
            <div className="timer-timeline">
              <div className="timer-film-title">
                <strong>{clip.title}</strong>
              </div>
              <div className="timer-scrubber">
                <div
                  className="timer-buffer"
                  aria-hidden="true"
                  style={{
                    left: `${(start / total) * 100}%`,
                    width: clip.complete
                      ? "100%"
                      : `${(Math.min(buffer, duration) / total) * 100}%`,
                  }}
                />
                <input
                  type="range"
                  aria-label="Video position"
                  aria-valuetext={`${clock(position)} of ${clock(total)}`}
                  min="0"
                  max={Math.max(1, total)}
                  step=".1"
                  value={position}
                  disabled={loading}
                  style={{ "--played": `${(position / total) * 100}%` }}
                  onChange={(event) => {
                    if (clip?.complete) seek(event.target.value);
                    else setSeeking(Number(event.target.value));
                  }}
                  onPointerUp={(event) => {
                    if (!clip.complete) seek(event.currentTarget.value);
                  }}
                  onKeyUp={(event) => {
                    if (
                      !clip.complete &&
                      ["ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"].includes(
                        event.key,
                      )
                    )
                      seek(event.currentTarget.value);
                  }}
                  onBlur={(event) => {
                    if (seeking != null) seek(event.currentTarget.value);
                  }}
                />
              </div>
              <div className="timer-time">
                <output aria-label="Playback time">{clock(position)}</output>
                <span>−{clock(Math.max(0, total - position))}</span>
              </div>
            </div>
          </div>
        )}
        {dropping && (
          <div className="timer-drop" role="status">
            <Icon name="upload" />
            <span>Drop to set background</span>
          </div>
        )}
      </div>
    </div>
  );
}
