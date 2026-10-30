import { Bubble } from "../shared/bubble.tsx";
import { Icon } from "../shared/icons.tsx";
import { vector } from "../shared/assets.ts";
import React, { useContext, useEffect, useId, useRef, useState } from "react";
import { Animal, Habitat, Portrait } from "./animal.tsx";
import { animalAt, reactions } from "./animals.ts";
import { Place } from "./place.tsx";
import { watchHabitat, watchIdle, watchScene } from "../shared/motion.ts";
import { useWorld } from "./world.ts";
import { Motion } from "../shared/display.tsx";
import { activity, lives, sleepProfile } from "./life.ts";
import { voices } from "./voices.ts";
import "./animal.css";

import type { Species } from "./animals.ts";

const residents: Record<string, number> = {
  planny: 0,
  scrappy: 1,
  clubby: 2,
  event: 3,
  timey: 4,
  buzzy: 6,
  auth: 5,
  agent: 7,
  hello: 10,
  visitor: 3,
};
const thoughts: Record<string, string> = {
  otter: "I'd love a river with room for my whole family",
  numbat: "Leave me a hollow log. I'll take care of the termites",
  penguin: "I hope there's still a shoal waiting when we reach the sea",
  dodo: "I wish I could waddle through your world again",
  thylacine: "I'd love one more quiet walk beside you",
  auk: "I miss the sea breeze. Could you imagine it with me?",
  pigeon: "I wish we could fill your skies again",
  huia: "I'd like to hear the forest answering me again",
  seacow: "I'd love to drift through the kelp beside you",
  quoll: "A quiet rocky hideaway would be lovely right now",
  pangolin: "Just a safe forest and a trail of ants for me, please",
  kakapo: "The forest gets interesting after everyone else goes to sleep",
  axolotl: "A little patch of clean canal is a whole world to me",
  turtle: "I remember the beach, even after all that ocean",
  bee: "One more wildflower patch? I know just what to do with it",
  saola: "You can keep me company quietly, from over there",
  vaquita: "I'd like to swim without wondering what's caught in the water",
  elephant: "My family remembers the paths. I hope they're still connected",
  frog: "A damp evening, a safe forest floor and somewhere to hop",
  panda: "A branch, some bamboo and a peaceful afternoon",
  horse: "There's nothing quite like being back on the open steppe",
  whale: "I wonder who can hear my song on the other side of the blue",
  rhino: "I'd rather be browsing leaves than making a fuss",
  tiger: "A little shade and a forest big enough to wander",
};

export function Badge({ status }: { status: string }) {
  const kind = status.startsWith("extinct")
    ? "extinct"
    : status.startsWith("critically")
      ? "critical"
      : "endangered";
  return (
    <span
      className={`status-badge status-${kind}`}
      role="img"
      aria-label={status}
      data-tip={status}
    >
      <img className="badge-symbol" src={vector(`icons/status-${kind}`)} alt="" />
    </span>
  );
}

const habitatClocks = new Map<string, Intl.DateTimeFormat>();

function HabitatClock({ animal, active }: { animal: Species; active: boolean }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!active) return;
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  let formatter = habitatClocks.get(animal.zone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-AU", {
      timeZone: animal.zone,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    habitatClocks.set(animal.zone, formatter);
  }
  return <time className="home-clock">{formatter.format(now)}</time>;
}

export function Story({
  animal,
  id,
  open = false,
  wind = 2,
  onToggle,
}: {
  animal: Species;
  id: string;
  open?: boolean;
  wind?: number;
  onToggle?: (open: boolean) => void;
}) {
  const extinct = animal.status.startsWith("extinct");
  return (
    <Bubble
      id={id}
      label={`${animal.name}'s story`}
      className="speech-bubble animal-note"
      region={animal.region}
      onToggle={onToggle}
    >
      <div className="story-top">
        <span className="story-home">
          <Place animal={animal} wind={wind} />
          <span>
            {animal.home}
            <HabitatClock animal={animal} active={open} />
          </span>
        </span>
        <span className="story-actions">
          <button
            type="button"
            className="story-close"
            popoverTarget={id}
            popoverTargetAction="hide"
            aria-label="Close my story"
          >
            <Icon name="close" />
          </button>
          <Badge status={animal.status} />
        </span>
      </div>
      <p className="animal-story">{animal.story}</p>
      <p className="animal-fact">{animal.fact}</p>
      <div className="animal-care">
        <strong>{extinct ? "What happened" : "What I need"}</strong>
        <p>{animal.care}</p>
      </div>
      <a className="protector-link" href={animal.source} target="_blank" rel="noopener noreferrer">
        <span className="protector-mark">
          <Portrait animal={animal} />
        </span>
        <span>{extinct ? "Read my history" : "Meet my protectors"}</span>
        <Icon name="chevron" />
      </a>
    </Bubble>
  );
}

export function nextResident<T extends { index: number; turn: number }>(
  value: T,
  random = Math.random,
) {
  return { ...value, turn: (value.turn + 1 + Math.floor(random() * 31)) % 4096 };
}

export function Pal({
  name = "planny",
  controls = true,
  thoughts: thinking = false,
  page = false,
  resident,
  children,
}: {
  name?: string;
  controls?: boolean;
  thoughts?: boolean;
  page?: boolean;
  resident?: number;
  children?: React.ReactNode;
}) {
  const seed = resident ?? residents[name] ?? 0;
  const [life, setLife] = useState(() => ({ index: seed, turn: 0, previous: "" })),
    [details, setDetails] = useState(false),
    [focused, setFocused] = useState(false);
  const [pats, setPats] = useState(0);
  const [petting, setPetting] = useState(false),
    [touch, setTouch] = useState(0),
    [thought, setThought] = useState(false),
    [editing, setEditing] = useState(false);
  const [sleeping, setSleeping] = useState(false),
    [waking, setWaking] = useState(false);
  const ref = useRef<HTMLDivElement>(null),
    holding = useRef(false),
    storyId = useId(),
    { paused, reduced, hidden, speak } = useContext(Motion);
  const animal = animalAt(life.index),
    profile = lives[animal.id],
    sleeper = sleepProfile(animal);
  const { clock, weather, visible } = useWorld(animal, ref);
  const action = activity(animal, life.turn, clock.hour, life.previous);
  const currentAction = useRef(action);
  currentAction.current = action;
  holding.current = !!(focused || petting || touch || thought);
  useEffect(
    () =>
      page
        ? watchIdle(sleeper.delay, (asleep) => {
            setSleeping(asleep);
            if (!asleep) setWaking(true);
          })
        : undefined,
    [page, sleeper.delay],
  );
  useEffect(() => {
    if (!waking) return;
    const timer = setTimeout(() => setWaking(false), sleeper.wake);
    return () => clearTimeout(timer);
  }, [sleeper.wake, waking]);
  useEffect(() => {
    if (page) return watchHabitat(ref.current!);
  }, [page]);
  useEffect(
    () =>
      watchScene(
        ref.current!,
        !paused && !reduced && !hidden && !details && !editing,
        () => 12_000 + Math.random() * 26_000 + seed * 173,
        () => {
          if (holding.current) return false;
          setLife((value) => ({ ...nextResident(value), previous: currentAction.current }));
          return true;
        },
      ),
    [paused, reduced, hidden, details, editing, seed],
  );
  useEffect(() => {
    if (!touch) return;
    const timer = setTimeout(() => setTouch(0), 1700);
    return () => clearTimeout(timer);
  }, [touch]);
  const stage = (
    <div className="animal-stage">
      <div className="animal-presence">
        <Animal
          key={animal.id}
          animal={animal}
          backdrop={!thinking && !page}
          action={
            sleeping
              ? "sleep"
              : waking
                ? "wake"
                : touch
                  ? profile.acts[2]
                  : petting || (page && action === "rest")
                    ? "listen"
                    : action
          }
          phase={clock.phase}
          light={clock.amount}
          cloud={weather?.cloud || 0}
          wind={weather?.wind || 0}
          rain={weather?.rain || 0}
          temperature={weather?.temperature}
          wake={sleeper.wake / 1000}
          animate={!paused && !reduced && !hidden && visible && !details && (!editing || waking)}
        />
        <button
          type="button"
          className="animal-touch"
          aria-label={
            thinking ? `Hear ${animal.name}` : `Gently pat the illustrated ${animal.name}`
          }
          aria-expanded={thinking ? thought : undefined}
          onPointerEnter={() => setPetting(true)}
          onPointerLeave={() => setPetting(false)}
          onClick={() => {
            setTouch((value) => value + 1);
            setPats((value) => value + 1);
            speak(voices[animal.id]);
            if (thinking) setThought(!thought);
          }}
        >
          <span className="pat-spark" aria-hidden="true">
            ♡
          </span>
        </button>
        {waking ? (
          <span className="animal-call" role="status">
            {sleeper.line}
          </span>
        ) : !thinking && !!profile.call && (touch || action === "call") ? (
          <span className="animal-call" aria-hidden="true">
            {profile.call}
          </span>
        ) : null}
        {!thinking && (
          <span className="sr-only" role="status">
            {touch ? reactions[animal.id] : ""}
          </span>
        )}
        {page && pats >= 3 && touch > 0 && (
          <div className="animal-discovery" role="status">
            <p>{[animal.fact, animal.care, animal.story][Math.floor((pats - 3) / 3) % 3]}</p>
            <button type="button" popoverTarget={storyId}>
              Let me tell you more
            </button>
          </div>
        )}
        {thought && (
          <div className="animal-thought" role="status">
            <b>{profile.call}</b>
            <p>{thoughts[animal.id] || animal.fact}</p>
          </div>
        )}
      </div>
      {controls && (
        <div className="animal-tools">
          <button
            type="button"
            className="animal-details"
            popoverTarget={storyId}
            aria-label={`My story: ${animal.name}`}
          >
            <Portrait animal={animal} />
            <span>
              <strong>{animal.name}</strong>
              <small>My story</small>
            </span>
          </button>
          <Story
            animal={animal}
            id={storyId}
            open={details}
            wind={weather?.wind ?? 2}
            onToggle={setDetails}
          />
        </div>
      )}
    </div>
  );
  return (
    <div
      className={`pal${page ? " habitat-page" : ""}${petting || touch ? " is-petted" : ""}${thought ? " is-thinking" : ""}`}
      ref={ref}
      data-running="false"
      data-resident={animal.id}
      data-kind={
        ["bee", "pigeon", "huia"].includes(animal.id)
          ? "air"
          : animal.movement === "swim"
            ? "water"
            : "land"
      }
      onFocusCapture={(event) => {
        setFocused((event.target as Element).matches(":focus-visible"));
        setEditing(
          page && (event.target as Element).matches("input,textarea,select,[contenteditable=true]"),
        );
      }}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setFocused(false);
          setEditing(false);
        }
      }}
    >
      {page ? (
        <>
          <Habitat
            animal={animal}
            className="page-habitat"
            phase={clock.phase}
            light={clock.amount}
            cloud={weather?.cloud || 0}
            wind={weather?.wind || 0}
          />
          <div className="habitat-content">{children}</div>
          <div className="habitat-clearing">{stage}</div>
        </>
      ) : (
        stage
      )}
    </div>
  );
}
