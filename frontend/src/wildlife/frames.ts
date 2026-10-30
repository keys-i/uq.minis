/** Whole painted poses retain the original animals' attached silhouettes */
import data from "../../../out/tools/cartoons.json";
import guests from "../../assets/wildlife/guests.webp";
import type { Species } from "./animals.ts";

interface Atlas {
  size: [number, number];
  frames: [number, number, number, number][];
}
export const atlases = data as unknown as Record<string, Atlas>;
const sources = import.meta.glob<string>("../../assets/wildlife/cartoons/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});
const portraits = import.meta.glob<string>("../../assets/wildlife/cartoons/portraits/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});
export const artwork = (id: string) =>
  id === "guests" ? guests : sources[`../../assets/wildlife/cartoons/${id}.webp`];
export const portrait = (id: string) =>
  portraits[`../../assets/wildlife/cartoons/portraits/${id}.webp`];

/** Select an actual illustrated activity rather than deforming an idle animal */
export function pose(animal: Species, action: string) {
  const resting = ["sleep", "rest", "curl"].includes(action);
  if (atlases[animal.id].frames.length === 2) return resting ? 1 : 0;
  if (resting) {
    if (animal.id === "tiger") return 1;
    if (["elephant", "whale", "pigeon", "huia", "rhino", "vaquita", "seacow"].includes(animal.id))
      return 0;
    return 2;
  }
  if (
    (animal.id === "pigeon" && ["fly", "stretch"].includes(action)) ||
    ["dive", "slide", "dust", "play"].includes(action)
  )
    return 2;
  return ["listen", "wake", "wander", "fly", "soar", "climb", "swim"].includes(action) ? 0 : 1;
}
