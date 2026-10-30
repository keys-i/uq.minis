// Each pair of new poses depicts an activity, not a translated copy of the resting artwork
import { animals, type Species } from "./animals.ts";

interface Life {
  call: string;
  acts: string[];
}

export interface SleepProfile {
  delay: number;
  wake: number;
  line: string;
}

const sleepProfiles = {
    heavy: { delay: 60_000, wake: 3200, line: "Mmm… five more minutes" },
    ordinary: { delay: 90_000, wake: 2200, line: "Oh! You're back" },
    light: { delay: 120_000, wake: 1800, line: "Ughhh… you woke me up" },
  } satisfies Record<string, SleepProfile>,
  heavySleepers = new Set(["panda", "kakapo", "turtle", "whale", "seacow", "elephant", "rhino"]),
  lightSleepers = new Set(["quoll", "numbat", "bee", "huia", "pigeon", "frog", "otter"]);

/** Give each species a stable sleep temperament */
export function sleepProfile(animal: Species): SleepProfile {
  return heavySleepers.has(animal.id)
    ? sleepProfiles.heavy
    : lightSleepers.has(animal.id)
      ? sleepProfiles.light
      : sleepProfiles.ordinary;
}

export const lives: Record<string, Life> = {
  otter: {
    call: "Chrrr! Squeak!",
    acts: ["groom", "play", "swim", "listen"],
  },
  numbat: {
    call: "Chrr-chrr",
    acts: ["forage", "wander", "rest", "listen"],
  },
  penguin: {
    call: "Haaaw!",
    acts: ["preen", "slide", "wander", "call"],
  },
  dodo: {
    call: "Hrrroo?",
    acts: ["forage", "wander", "rest", "listen"],
  },
  quoll: {
    call: "Chik-chik!",
    acts: ["groom", "wander", "rest", "listen"],
  },
  pangolin: {
    call: "Snff…",
    acts: ["forage", "wander", "curl", "listen"],
  },
  kakapo: {
    call: "Booom… ching!",
    acts: ["stretch", "wander", "rest", "call"],
  },
  axolotl: {
    call: "blub… blub",
    acts: ["forage", "swim", "rest", "listen"],
  },
  thylacine: {
    call: "Yap-yap",
    acts: ["yawn", "wander", "listen", "rest"],
  },
  turtle: {
    call: "swish…",
    acts: ["swim", "dive", "rest", "swim"],
  },
  bee: {
    call: "Bzzzz!",
    acts: ["feed", "fly", "groom", "listen"],
  },
  saola: {
    call: "Snff?",
    acts: ["browse", "listen", "rest", "wander"],
  },
  auk: {
    call: "Krrr…",
    acts: ["preen", "wander", "rest", "call"],
  },
  vaquita: {
    call: "click click",
    acts: ["surface", "swim", "dive", "swim"],
  },
  elephant: {
    call: "PrrrOOO!",
    acts: ["drink", "dust", "wander", "listen"],
  },
  pigeon: {
    call: "Coo-coo",
    acts: ["forage", "stretch", "wander", "call"],
  },
  frog: {
    call: "Whoop!",
    acts: ["call", "hop", "rest", "listen"],
  },
  panda: {
    call: "Twee-twee!",
    acts: ["feed", "wander", "rest", "listen"],
  },
  horse: {
    call: "Hrrr-heee!",
    acts: ["graze", "roll", "wander", "listen"],
  },
  whale: {
    call: "Ooooo…",
    acts: ["surface", "dive", "swim", "call"],
  },
  huia: {
    call: "Hui-aa!",
    acts: ["probe", "preen", "listen", "call"],
  },
  rhino: {
    call: "Huff!",
    acts: ["wallow", "browse", "wander", "listen"],
  },
  seacow: {
    call: "Hrrr…",
    acts: ["feed", "swim", "rest", "dive"],
  },
  tiger: {
    call: "Prrff!",
    acts: ["groom", "stretch", "wander", "listen"],
  },
};

// Each species keeps its own capability list; flightless birds never inherit flying
export const flighted = new Set([
  "bee",
  "huia",
  "pigeon",
  "parakeet",
  "eagle",
  "vulture",
  "bustard",
  "florican",
]);
export const diggers = new Set(["pangolin", "indipangolin", "crayfish", "solenodon", "potoroo"]);
for (const animal of animals) {
  if (lives[animal.id]) {
    if (flighted.has(animal.id) && !lives[animal.id].acts.includes("fly"))
      lives[animal.id].acts.push("fly");
    if (diggers.has(animal.id)) lives[animal.id].acts.push("dig");
    continue;
  }
  const acts = flighted.has(animal.id)
    ? ["fly", "preen", "forage", "listen", "rest"]
    : diggers.has(animal.id)
      ? ["dig", "forage", "groom", "listen", "rest"]
      : ["cetacean", "fish", "axolotl", "turtle"].includes(animal.family)
        ? ["swim", "surface", "dive", "listen", "rest"]
        : animal.family === "primate"
          ? ["climb", "forage", "groom", "listen", "rest"]
          : animal.id === "gharial"
            ? ["swim", "bask", "dive", "listen", "rest"]
            : ["wander", "forage", "groom", "listen", "rest"];
  lives[animal.id] = { call: "", acts };
}
const clocks = new Map<string, Intl.DateTimeFormat>();

/** Format a resident's own clock without a shared page-wide ticking context */
export function habitatTime(animal: Species, now = new Date()) {
  const zone = animal.zone;
  let formatter = clocks.get(zone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-AU", {
      timeZone: zone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    clocks.set(zone, formatter);
  }
  const time = formatter.format(now),
    [hours, minutes] = time.split(":").map(Number);
  const hour = hours + minutes / 60;
  return {
    time,
    zone,
    hour,
    phase: hour < 5 || hour >= 20 ? "night" : hour < 8 ? "dawn" : hour < 17 ? "day" : "dusk",
  };
}

/** Choose varied species behaviour, avoiding an immediate repeated action */
export function activity(animal: Species, turn: number, hour: number, previous = ""): string {
  const life = lives[animal.id],
    night = hour < 6 || hour >= 19;
  let hash = Math.imul(turn + 17, 0x45d9f3b);
  for (const code of animal.id) hash = Math.imul(hash ^ code.charCodeAt(0), 0x45d9f3b);
  hash = (hash ^ (hash >>> 16)) >>> 0;
  if (previous !== "rest" && night !== animal.nocturnal && hash % 5 < 3) return "rest";
  const options = life.acts.filter((action) => action !== previous);
  return options[hash % options.length] || "listen";
}
