import { useEffect, useState } from "react";
import type { Values } from "./model.ts";

type HSV = [number, number, number];
const swatches = [
  ["Cream", "#fff2ce"],
  ["Honey", "#ffd45a"],
  ["Peach", "#ed865f"],
  ["Rose", "#ef9cba"],
  ["Iris", "#ab95ed"],
  ["Sky", "#72c8ed"],
  ["Leaf", "#8fda53"],
  ["Pearl", "#e9edea"],
  ["Ink", "#292532"],
];

export function hex([hue, saturation, value]: HSV): string {
  const channel = (offset: number) => {
    const part = (offset + hue / 60) % 6;
    return Math.round(255 * value * (1 - saturation * Math.max(0, Math.min(part, 4 - part, 1))))
      .toString(16)
      .padStart(2, "0");
  };
  return `#${channel(5)}${channel(3)}${channel(1)}`;
}

export function hsv(colour: string): HSV {
  const rgb = [1, 3, 5].map((offset) => parseInt(colour.slice(offset, offset + 2), 16) / 255);
  const [r, g, b] = rgb,
    high = Math.max(...rgb),
    low = Math.min(...rgb),
    delta = high - low;
  const hue = !delta
    ? 0
    : high === r
      ? (g - b) / delta
      : high === g
        ? (b - r) / delta + 2
        : (r - g) / delta + 4;
  return [(hue * 60 + 360) % 360, high ? delta / high : 0, high];
}

export function wheel(x: number, y: number, radius: number): [number, number] {
  return [((Math.atan2(y, x) * 180) / Math.PI + 450) % 360, Math.min(1, Math.hypot(x, y) / radius)];
}

export function Colour({
  value,
  custom,
  change,
}: {
  value: string;
  custom: boolean;
  change: (patch: Values) => void;
}) {
  const [colour, setColour] = useState<HSV>(() => hsv(value)),
    [text, setText] = useState(value);
  useEffect(() => {
    setColour((current) => (hex(current) === value.toLowerCase() ? current : hsv(value)));
    setText(value);
  }, [value]);
  function choose(next: HSV) {
    setColour(next);
    const accent = hex(next);
    setText(accent);
    change({ accent, use_accent: "on" });
  }
  function point(event: React.PointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    choose([
      ...wheel(
        event.clientX - bounds.left - bounds.width / 2,
        event.clientY - bounds.top - bounds.height / 2,
        bounds.width / 2,
      ),
      colour[2],
    ]);
  }
  const angle = (colour[0] * Math.PI) / 180,
    saturation = colour[1] * 48;
  return (
    <div className="timer-colours">
      <div
        className="colour-wheel"
        role="slider"
        tabIndex={0}
        aria-label="Hue"
        aria-valuemin={0}
        aria-valuemax={360}
        aria-valuenow={Math.round(colour[0])}
        aria-valuetext={`${Math.round(colour[0])} degrees`}
        style={{ "--brightness": colour[2] }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          point(event);
        }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) point(event);
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onKeyDown={(event) => {
          const step = event.shiftKey ? 10 : 1;
          if (
            ["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowUp", "Home", "End"].includes(event.key)
          ) {
            event.preventDefault();
            choose([
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? 359
                  : (colour[0] +
                      (["ArrowLeft", "ArrowDown"].includes(event.key) ? -step : step) +
                      360) %
                    360,
              colour[1],
              colour[2],
            ]);
          }
        }}
      >
        <i
          style={{
            left: `${50 + Math.sin(angle) * saturation}%`,
            top: `${50 - Math.cos(angle) * saturation}%`,
            background: hex(colour),
          }}
        />
      </div>
      <div className="colour-swatches" aria-label="Colour swatches">
        {swatches.map(([name, swatch]) => (
          <button
            key={swatch}
            type="button"
            aria-label={name}
            data-tip={name}
            aria-pressed={custom && value.toLowerCase() === swatch}
            style={{ "--swatch": swatch }}
            onClick={() => choose(hsv(swatch))}
          />
        ))}
      </div>
      <label>
        Saturation
        <input
          type="range"
          min="0"
          max="100"
          value={Math.round(colour[1] * 100)}
          onChange={(event) => choose([colour[0], Number(event.target.value) / 100, colour[2]])}
        />
      </label>
      <label>
        Brightness
        <input
          type="range"
          min="0"
          max="100"
          value={Math.round(colour[2] * 100)}
          onChange={(event) => choose([colour[0], colour[1], Number(event.target.value) / 100])}
        />
      </label>
      <div className="colour-value">
        <input
          aria-label="Hex colour"
          value={text}
          maxLength={7}
          spellCheck={false}
          onChange={(event) => {
            const next = event.target.value;
            setText(next);
            if (/^#[\da-f]{6}$/i.test(next)) choose(hsv(next));
          }}
          onBlur={() => setText(value)}
        />
        <button
          type="button"
          className="quiet"
          aria-pressed={!custom}
          onClick={() => change({ use_accent: "" })}
        >
          Theme colour
        </button>
      </div>
    </div>
  );
}
