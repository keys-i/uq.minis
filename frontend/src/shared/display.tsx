import { Icon } from "./icons.tsx";
import { vector } from "./assets.ts";
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { watchMotion } from "./motion.ts";

import { preferencesSchema, type Preferences } from "./schema.ts";

interface Environment {
  reduced: boolean;
  hidden: boolean;
}
interface Display extends Environment {
  paused: boolean;
  now: Date;
  preferences: Preferences;
  scheme?: string;
  soundError?: string;
  change: (next: Partial<Preferences>) => void;
  speak: (voice?: { src: string }) => void;
}

export const Motion = createContext<Display>({
  paused: false,
  reduced: true,
  hidden: false,
  now: new Date(),
  preferences: { still: false, contrast: false, size: 1, sound: false, theme: "system" },
  change: () => {},
  speak: () => {},
});

export function preferences(raw: string | null): Preferences {
  let saved;
  try {
    saved = JSON.parse(raw || "null");
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
  }
  const checked = preferencesSchema.safeParse(saved);
  return checked.success ? checked.data : preferencesSchema.parse({});
}

export function Wildlife({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState(() => {
    try {
      return preferences(
        typeof localStorage === "undefined" ? null : localStorage.getItem("minis.display"),
      );
    } catch (error) {
      if ((error instanceof Error ? error.name : "") !== "SecurityError") throw error;
      return preferences(null);
    }
  });
  const [environment, setEnvironment] = useState({ reduced: true, hidden: false }),
    [now] = useState(() => new Date()),
    [soundError, setSoundError] = useState(""),
    [scheme, setScheme] = useState("light");
  const audio = useRef<HTMLAudioElement>(null),
    lastCall = useRef(0);
  useEffect(() => watchMotion(setEnvironment), []);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const next =
        settings.theme === "system" ? (media.matches ? "dark" : "light") : settings.theme;
      document.documentElement.dataset.theme = next;
      setScheme(next);
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [settings.theme]);
  useEffect(() => {
    document.documentElement.dataset.contrast = settings.contrast ? "high" : "normal";
    document.documentElement.dataset.still = String(settings.still || environment.reduced);
    document.documentElement.style.setProperty("--reading-size", String(settings.size));
    try {
      localStorage.setItem("minis.display", JSON.stringify(settings));
    } catch (error) {
      if (
        !["SecurityError", "QuotaExceededError"].includes(error instanceof Error ? error.name : "")
      )
        throw error;
    }
  }, [settings, environment.reduced]);
  useEffect(
    () => () => {
      if (audio.current) {
        audio.current.pause();
        audio.current.removeAttribute("src");
        audio.current.load();
      }
    },
    [],
  );
  useEffect(() => {
    if (!settings.sound || environment.hidden) audio.current?.pause();
  }, [settings.sound, environment.hidden]);
  function speak(voice?: { src: string }) {
    if (!settings.sound || !voice || Date.now() - lastCall.current < 2500) return;
    audio.current ??= new Audio();
    const player = audio.current;
    player.pause();
    player.volume = 0.25;
    player.src = voice.src;
    lastCall.current = Date.now();
    player.play().catch((error) => {
      if ((error instanceof Error ? error.name : "") !== "AbortError")
        setSoundError("Your browser couldn't play this animal recording");
    });
  }
  return (
    <Motion.Provider
      value={{
        ...environment,
        now,
        soundError,
        scheme,
        paused: settings.still,
        preferences: settings,
        change: (next) => {
          setSoundError("");
          setSettings((value) => ({ ...value, ...next }));
        },
        speak,
      }}
    >
      {children}
    </Motion.Provider>
  );
}

/** Match compact editor controls while keeping every preference labelled */
export function MotionSettings() {
  const { preferences: value, reduced, change, soundError } = useContext(Motion);
  return (
    <div className="access-controls">
      <div className="access-switches">
        <button
          type="button"
          aria-pressed={!value.still && !reduced}
          disabled={reduced}
          data-tip={reduced ? "Following your device" : "Animal movement"}
          onClick={() => change({ still: !value.still })}
        >
          <Icon name={value.still || reduced ? "still" : "motion"} />
          <span>Motion</span>
        </button>
        <button
          type="button"
          aria-pressed={value.contrast}
          onClick={() => change({ contrast: !value.contrast })}
        >
          <Icon name="look" />
          <span>Contrast</span>
        </button>
        <button
          type="button"
          aria-pressed={value.sound}
          onClick={() => change({ sound: !value.sound })}
        >
          <Icon name={value.sound ? "volume" : "muted"} />
          <span>Voices</span>
        </button>
      </div>
      <label className="access-range">
        <Icon name="font" />
        <span>Text</span>
        <input
          type="range"
          aria-label="Reading size"
          min="1"
          max="1.3"
          step="0.1"
          value={value.size}
          onChange={(event) =>
            change({ size: preferencesSchema.shape.size.parse(Number(event.target.value)) })
          }
        />
        <output>{Math.round(value.size * 100)}%</output>
      </label>
      {reduced && <small>Motion follows your device</small>}
      {soundError && <p role="status">{soundError}</p>}
    </div>
  );
}

export function ThemePicker() {
  const { scheme = "light", change } = useContext(Motion),
    dark = scheme === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      data-dark={dark}
      aria-pressed={dark}
      aria-label={`App theme / switch to ${dark ? "light" : "dark"} mode`}
      data-tip={`Switch to ${dark ? "light" : "dark"} mode`}
      onClick={() => change({ theme: dark ? "light" : "dark" })}
    >
      <span className="theme-window">
        <img className="theme-sun" src={vector("icons/sun")} alt="" />
        <img className="theme-moon" src={vector("icons/moon")} alt="" />
      </span>
      <span>{dark ? "Dark" : "Light"}</span>
    </button>
  );
}
