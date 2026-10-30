import React, { useContext, useEffect, useRef, useState } from "react";
import { clamp, clock, dial, phase, recoil, wind } from "./model.ts";
import { Motion } from "../shared/display.tsx";

export function Dial({
  value,
  change,
  gap = false,
  reverse = false,
  label = "Countdown length",
}: {
  value: number | null;
  change: (value: number) => void;
  gap?: boolean;
  reverse?: boolean;
  label?: string;
}) {
  const minimum = 0,
    limit = gap ? 3600 : 86400,
    base = gap ? 60 : 7200;
  const [pull, setPull] = useState(0),
    { reduced } = useContext(Motion),
    drag = useRef<{
      turn: number;
      maximum: number;
      initial: number;
      pointer: number;
      pull: number;
    } | null>(null),
    animation = useRef<Animation>(null);
  const amount = clamp(value ?? (gap ? 5 : 600), minimum, limit),
    maximum = Math.max(base, Math.ceil(amount / base) * base),
    angle = (amount / maximum + pull) * Math.PI * 2 * (reverse ? -1 : 1);
  useEffect(() => () => animation.current?.cancel(), []);
  function point(event: React.PointerEvent<HTMLDivElement>, first = false) {
    const action = drag.current;
    if (!action) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left - bounds.width / 2) * (reverse ? -1 : 1),
      y = event.clientY - bounds.top - bounds.height / 2;
    if (Math.hypot(x, y) < bounds.width * 0.25) return;
    action.turn = first ? phase(x, y) : wind(action.turn, phase(x, y));
    action.pull =
      clamp(action.turn < 0 ? action.turn : action.turn > 1 ? action.turn - 1 : 0, -0.4, 0.4) *
      0.25;
    setPull(action.pull);
    change(
      action.turn <= 0 ? 0 : action.turn >= 1 ? action.maximum : dial(x, y, action.maximum, gap),
    );
  }
  function finish(
    event: React.PointerEvent<HTMLDivElement> | React.KeyboardEvent<HTMLDivElement>,
    cancel = false,
  ) {
    const action = drag.current;
    if (!action) return;
    drag.current = null;
    if (cancel || event.type === "pointercancel") change(action.initial);
    else if (action.turn > 1 || action.turn < 0) {
      change(0);
      if (!reduced)
        animation.current =
          event.currentTarget
            .querySelector(".dial-ring")
            ?.animate(recoil(action.pull), { duration: 650, easing: "linear" }) ?? null;
    }
    setPull(0);
    if (event.currentTarget.hasPointerCapture(action.pointer))
      event.currentTarget.releasePointerCapture(action.pointer);
  }
  return (
    <div
      className="timer-dial"
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={minimum}
      aria-valuemax={maximum}
      aria-valuenow={amount}
      aria-valuetext={clock(amount)}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        animation.current?.cancel();
        drag.current = {
          turn: amount / maximum,
          maximum,
          initial: amount,
          pointer: event.pointerId,
          pull: 0,
        };
        event.currentTarget.focus();
        event.currentTarget.setPointerCapture(event.pointerId);
        point(event, true);
      }}
      onPointerMove={point}
      onPointerUp={finish}
      onPointerCancel={finish}
      onLostPointerCapture={(event) => finish(event, true)}
      onKeyDown={(event) => {
        if (event.key === "Escape" && drag.current) {
          event.preventDefault();
          finish(event, true);
          return;
        }
        const step = gap ? (event.shiftKey ? 5 : 1) : event.shiftKey ? 300 : event.altKey ? 15 : 60;
        const next = {
          ArrowUp: amount + step,
          ArrowRight: amount + step,
          ArrowDown: amount - step,
          ArrowLeft: amount - step,
          Home: minimum,
          End: maximum,
        }[event.key as "ArrowUp" | "ArrowRight" | "ArrowDown" | "ArrowLeft" | "Home" | "End"];
        if (next != null) {
          event.preventDefault();
          change(clamp(next, minimum, limit));
        }
      }}
    >
      <span
        className="dial-ring"
        aria-hidden="true"
        style={{
          transform: pull ? `scale(${1 + Math.abs(pull)},${1 - Math.abs(pull) * 0.65})` : undefined,
        }}
      >
        <span className="dial-track" />
        <span
          className="dial-progress"
          style={{
            "--sweep": `${(amount / maximum) * 360}deg`,
            transform: reverse ? "scaleX(-1)" : undefined,
          }}
        />
        <span
          className="dial-thumb"
          style={{
            left: `${50 + 42 * Math.sin(angle)}%`,
            top: `${50 - 42 * Math.cos(angle)}%`,
            width: gap ? "8%" : "7%",
            height: gap ? "8%" : "7%",
          }}
        />
      </span>
      <span className="dial-time">{clock(amount).padStart(5, "0")}</span>
    </div>
  );
}
