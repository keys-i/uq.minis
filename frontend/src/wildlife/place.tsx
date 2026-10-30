import type { Species } from "./animals.ts";
import { type CSSProperties, useContext } from "react";
import { Motion } from "../shared/display.tsx";
import { vector } from "../shared/assets.ts";

/** Use a static variant whenever the person's motion preferences require it */
function PlaceImage({ name, className }: { name: string; className: string }) {
  const { paused, reduced } = useContext(Motion);
  return (
    <img
      className={className}
      src={vector(`places/${name}${paused || reduced ? "" : "-live"}`)}
      alt=""
      aria-hidden="true"
      data-live={(!paused && !reduced) || undefined}
    />
  );
}
export function Flag({ code, wind = 2 }: { code: string; wind?: number }) {
  const speed = Math.max(1.8, 4.2 - Math.min(12, Math.max(0, wind)) * 0.18);
  return (
    <span className="place-flag" style={{ "--flag-speed": `${speed}s` } as CSSProperties}>
      <PlaceImage className="flag-cloth" name={code} />
    </span>
  );
}
export function Globe({ region }: { region: string }) {
  return <PlaceImage className="place-globe" name={region} />;
}
export function Place({ animal, wind = 2 }: { animal: Species; wind?: number }) {
  return (
    <span className="place-mark" aria-hidden="true">
      {animal.places.map((code) =>
        ["americas", "africa", "asia", "europe", "world"].includes(code) ? (
          <Globe key={code} region={code} />
        ) : (
          <Flag key={code} code={code} wind={wind} />
        ),
      )}
    </span>
  );
}
