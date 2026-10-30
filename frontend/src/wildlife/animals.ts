/** Source-backed wildlife metadata shared with the habitat weather service */
import catalogue from "../../../out/tools/wildlife.json";

export interface Species {
  id: string;
  name: string;
  status: string;
  place: string;
  source: string;
  family: string;
  movement: string;
  scene: number;
  region: string;
  home: string;
  story: string;
  care: string;
  places: string[];
  zone: string;
  latitude: number;
  longitude: number;
  nocturnal: boolean;
  reaction: string;
  fact: string;
}

export const animals: Species[] = Object.entries(catalogue.species).map(([id, entry]) => ({
  id,
  ...entry,
}));

/** Preserve stable residents when a mini or saved choice is unfamiliar */
export function animalAt(index: number): Species {
  return animals[((index % animals.length) + animals.length) % animals.length];
}

export const reactions: Record<string, string> = Object.fromEntries(
  animals.map((animal) => [animal.id, animal.reaction]),
);
