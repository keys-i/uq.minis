/** Read weather independently of editor loading and keep each habitat's clock local */
import { useContext, useEffect, useState } from "react";
import * as z from "zod/mini";
import { api } from "../shared/api.ts";
import { queries } from "../shared/query.ts";
import { Motion } from "../shared/display.tsx";
import type { Species } from "./animals.ts";
import { habitatTime } from "./life.ts";

const forecast = z.object({
  habitat: z.string(),
  updated: z.string(),
  expires: z.number(),
  stale: z.boolean(),
  cloud: z.optional(z.number()),
  rain: z.optional(z.number()),
  wind: z.optional(z.number()),
  temperature: z.optional(z.number()),
  symbol: z.optional(z.string()),
  sunrise: z.optional(z.nullable(z.string())),
  sunset: z.optional(z.nullable(z.string())),
  polar_day: z.optional(z.boolean()),
});
export type Weather = z.infer<typeof forecast>;

const smooth = (value: number) => value * value * (3 - 2 * value);

/** Blend real solar events into a continuous light level, retaining an offline home clock */
export function lighting(now: Date, hour: number, weather?: Weather) {
  const rise = Date.parse(weather?.sunrise || ""),
    set = Date.parse(weather?.sunset || "");
  const time = now.getTime(),
    twilight = 45 * 60_000;
  if (
    Number.isFinite(rise) &&
    Number.isFinite(set) &&
    set > rise &&
    Math.abs(time - (rise + set) / 2) < 18 * 3600_000
  ) {
    const edge = Math.min(time - rise, set - time);
    const progress = Math.max(0, Math.min(1, (edge + twilight) / (twilight * 2))),
      amount = smooth(progress);
    const phase =
      edge < -twilight
        ? "night"
        : edge < twilight
          ? time < (rise + set) / 2
            ? "dawn"
            : "dusk"
          : "day";
    return { amount, phase };
  }
  if (weather?.polar_day) return { amount: 1, phase: "day" };
  const daylight = Math.cos(((hour - 12) * Math.PI) / 12);
  const progress = Math.max(0, Math.min(1, daylight * 1.8 + 0.25));
  return {
    amount: smooth(progress),
    phase: hour < 5 || hour >= 20 ? "night" : hour < 8 ? "dawn" : hour < 17 ? "day" : "dusk",
  };
}

export function useWorld(animal: Species, element: React.RefObject<HTMLElement | null>) {
  const { hidden } = useContext(Motion);
  const [now, setNow] = useState(() => new Date()),
    [visible, setVisible] = useState(false);
  useEffect(() => {
    const target = element.current;
    if (!target) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(target);
    return () => observer.disconnect();
  }, [element]);
  useEffect(() => {
    if (hidden || !visible) return;
    setNow(new Date());
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setNow(new Date());
      timer = setTimeout(tick, 60_000);
    };
    timer = setTimeout(tick, 20_000 + animal.id.charCodeAt(0) * 317);
    return () => clearTimeout(timer);
  }, [animal.id, hidden, visible]);
  const [weather, setWeather] = useState<Weather>();
  useEffect(() => {
    if (!visible || hidden) return;
    const key = ["weather", animal.id],
      controller = new AbortController();
    setWeather(queries.getQueryData<Weather>(key));
    const refresh = () => {
      void queries
        .fetchQuery({
          queryKey: key,
          queryFn: ({ signal }) =>
            api(
              `/api/weather/${animal.id}`,
              forecast,
              undefined,
              AbortSignal.any([signal, controller.signal]),
            ),
          staleTime: 5 * 60_000,
        })
        .then(
          (value) => {
            if (!controller.signal.aborted) setWeather(value);
          },
          (error) => {
            // Weather is optional; keep the last forecast and the local habitat clock
            if ((error as Error).name !== "AbortError")
              setWeather(queries.getQueryData<Weather>(key));
          },
        );
    };
    refresh();
    const timer = setInterval(refresh, 10 * 60_000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [animal.id, hidden, visible]);
  const clock = habitatTime(animal, now);
  return { clock: { ...clock, ...lighting(now, clock.hour, weather) }, weather, visible };
}
