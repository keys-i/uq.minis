import React, { memo, useEffect, useRef } from "react";
import { atlases, artwork, pose, portrait } from "./frames.ts";
import type { Pose } from "./render.ts";
import type { Species } from "./animals.ts";
const landscapes = import.meta.glob<string>("../../assets/habitats/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});
const biomes = [
  "forest",
  "river",
  "reef",
  "prairie",
  "shore",
  "ocean",
  "woodland",
  "kelp",
  "ferns",
  "mountain",
  "steppe",
  "canal",
  "temperate",
  "savanna",
  "scrub",
  "boreal",
  "atlantic",
  "madagascar",
  "island",
  "ghats",
];

type Rect = readonly [number, number, number, number];

/** Crop a shared sheet without copying image bytes into each animal asset */
function sheet(source: string, frame: Rect, width: number, height: number): React.CSSProperties {
  const [x, y, w, h] = frame;
  return {
    backgroundImage: `url("${source}")`,
    backgroundSize: `${(width / w) * 100}% ${(height / h) * 100}%`,
    backgroundPosition: `${(x / Math.max(1, width - w)) * 100}% ${(y / Math.max(1, height - h)) * 100}%`,
  };
}

/** Home daylight and weather tint an individually loaded painted habitat */
export function Habitat({
  animal,
  className = "habitat",
  phase = "day",
  light = 1,
  cloud = 0,
  wind = 0,
}: {
  animal: Species;
  className?: string;
  phase?: string;
  light?: number;
  cloud?: number;
  wind?: number;
}) {
  const scene = animal.scene;
  const plants = atlases.guests;
  const foreground = [0, 3, 6, 8, 9, 10, 11, 12, 13, 14, 15, 17, 19].includes(scene) && plants;
  return (
    <div
      className={className}
      data-light={phase}
      aria-hidden="true"
      style={{
        backgroundImage: `url("${landscapes[`../../assets/habitats/${biomes[scene]}.webp`]}")`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        filter: `brightness(${0.52 + light * 0.48}) saturate(${0.72 + light * 0.28})`,
        "--cloud-cover": String(cloud / 100),
        "--daylight": String(light),
      }}
    >
      <span className="habitat-light" />
      <span className="habitat-clouds" />
      {foreground && (
        <span
          className="habitat-foreground"
          style={{
            ...sheet(
              artwork("guests"),
              plants.frames[[3, 6, 10, 11, 13, 14, 19].includes(scene) ? 7 : 6],
              ...plants.size,
            ),
            "--gust": `${Math.max(3, 12 - wind * 0.4)}s`,
            "--sway": `${Math.min(5, wind * 0.4)}deg`,
          }}
        />
      )}
    </div>
  );
}

export function Portrait({ animal }: { animal: Species }) {
  return (
    <span className="animal-portrait" aria-hidden="true" data-portrait={animal.id}>
      <span
        style={{
          backgroundImage: `url("${portrait(animal.id)}")`,
          backgroundSize: "contain",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
      />
    </span>
  );
}

/** Keep a native still visible until its shared Pixi renderer has painted the whole character */
function Character({
  animal,
  action,
  light,
  wind,
  rain,
  temperature,
  wake,
  animate,
}: {
  animal: Species;
  action: string;
  light: number;
  wind: number;
  rain: number;
  temperature?: number;
  wake: number;
  animate: boolean;
}) {
  const element = useRef<HTMLDivElement>(null),
    snapshot = useRef<Pose>({ animal, action, light, wind, rain, temperature, wake });
  snapshot.current = { animal, action, light, wind, rain, temperature, wake };
  useEffect(() => {
    if (!animate) return;
    let stopped = false,
      release: (() => void) | undefined;
    void import("./render.ts")
      .then((module) => {
        if (!stopped && element.current)
          release = module.register(element.current, () => snapshot.current);
      })
      .catch((error) =>
        console.warn("Character animation is unavailable; the still remains visible", error),
      );
    return () => {
      stopped = true;
      release?.();
    };
  }, [animal.id, animate]);
  const atlas = atlases[animal.id];
  return (
    <div
      ref={element}
      className={`animal animal-${animal.id} animal-cartoon`}
      data-animal={animal.id}
      data-action={action}
      aria-hidden="true"
    >
      <div className="cartoon-still" style={{ filter: `brightness(${0.55 + light * 0.45})` }}>
        <span
          className="cartoon-pose"
          style={sheet(artwork(animal.id), atlas.frames[pose(animal, action)], ...atlas.size)}
        />
      </div>
    </div>
  );
}

export const Animal = memo(function Animal({
  animal,
  backdrop = true,
  action = "listen",
  phase = "day",
  light = 1,
  cloud = 0,
  wind = 0,
  rain = 0,
  temperature,
  wake = 2.2,
  animate = false,
}: {
  animal: Species;
  backdrop?: boolean;
  action?: string;
  phase?: string;
  light?: number;
  cloud?: number;
  wind?: number;
  rain?: number;
  temperature?: number;
  wake?: number;
  animate?: boolean;
}) {
  return (
    <>
      {backdrop && (
        <Habitat animal={animal} phase={phase} light={light} cloud={cloud} wind={wind} />
      )}
      <Character
        animal={animal}
        action={action}
        light={light}
        wind={wind}
        rain={rain}
        temperature={temperature}
        wake={wake}
        animate={animate}
      />
    </>
  );
});
