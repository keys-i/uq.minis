import React, {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from "react";
import type { Tools } from "../study/model.ts";
import { Motion } from "../shared/display.tsx";
import { miniHref } from "../shared/route.ts";

const Resident = lazy(() => import("./mascot.tsx").then((module) => ({ default: module.Pal })));

type Camera = readonly [number, number, number];

export const trailCameras = {
  home: [0, 0, 1],
  planny: [-30, 6, 1.12],
  scrappy: [-18, -4, 1.15],
  buzzy: [-4, 7, 1.12],
  clubby: [10, 0, 1.14],
  event: [24, 5, 1.13],
  timey: [36, -10, 1.16],
} as const satisfies Record<string, Camera>;

export const trailManifest = [
  {
    name: "scrappy",
    place: "Wildflower gate",
    description: "Start with courses that fit where you want to go",
    camera: trailCameras.scrappy,
  },
  {
    name: "planny",
    place: "River bend",
    description: "Turn assessments and marks into a plan you can change",
    camera: trailCameras.planny,
  },
  {
    name: "buzzy",
    place: "Canopy crossing",
    description: "See deadlines and society events across a week or month",
    camera: trailCameras.buzzy,
  },
  {
    name: "clubby",
    place: "Gathering grove",
    description: "Find clubs by interest and keep their events close",
    camera: trailCameras.clubby,
  },
  {
    name: "event",
    place: "Field station",
    description: "Prepare an event and quietly follow its booking",
    camera: trailCameras.event,
  },
  {
    name: "timey",
    place: "Sunset lookout",
    description: "Build a countdown video and preview it before saving",
    camera: trailCameras.timey,
  },
] as const;

const layers = [
  ["sky", 0.08],
  ["clouds", 0.18],
  ["ridge", 0.28],
  ["canopy", 0.42],
  ["water", 0.58],
  ["foreground", 0.76],
] as const;

const TrailAim = createContext<(camera: Camera) => void>(() => {});

function cameraFor(route: string): Camera {
  const name = route === "agent" ? "event" : route;
  return trailCameras[name as keyof typeof trailCameras] ?? trailCameras.home;
}

function layerTransform(camera: Camera, depth: number) {
  return `translate3d(${(camera[0] * depth).toFixed(2)}px, ${(camera[1] * depth).toFixed(2)}px, 0) scale(${camera[2].toFixed(3)})`;
}

function useTrailCamera(root: React.RefObject<HTMLElement | null>, initial: Camera) {
  const { reduced, hidden } = useContext(Motion),
    current = useRef({ x: initial[0], y: initial[1], scale: initial[2] }),
    target = useRef<Camera>(initial),
    requestPaint = useRef<() => void>(() => {});
  useEffect(() => {
    const area = root.current;
    if (!area) return;
    const scenery = [...area.querySelectorAll<HTMLElement>("[data-trail-layer]")],
      still = reduced || hidden || typeof requestAnimationFrame !== "function",
      draw = (camera: Camera) =>
        scenery.forEach((layer, index) => {
          layer.style.transform = layerTransform(camera, layers[index]?.[1] ?? 0);
        }),
      snap = () => {
        current.current = { x: target.current[0], y: target.current[1], scale: target.current[2] };
        draw(target.current);
      };
    if (still) {
      requestPaint.current = snap;
      snap();
      return () => {
        requestPaint.current = () => {};
      };
    }
    const quiet =
      typeof matchMedia === "function"
        ? matchMedia("(prefers-reduced-data: reduce), (forced-colors: active)")
        : null;

    let frame = 0,
      pointerX = 0,
      pointerY = 0,
      scroll = 0;
    const paint = () => {
        const targetX = target.current[0] + pointerX,
          targetY = target.current[1] + pointerY + scroll,
          targetScale = target.current[2],
          point = current.current;
        point.x += (targetX - point.x) * 0.13;
        point.y += (targetY - point.y) * 0.13;
        point.scale += (targetScale - point.scale) * 0.13;
        draw([point.x, point.y, point.scale]);
        if (
          Math.abs(targetX - point.x) > 0.1 ||
          Math.abs(targetY - point.y) > 0.1 ||
          Math.abs(targetScale - point.scale) > 0.001
        )
          frame = requestAnimationFrame(paint);
        else frame = 0;
      },
      settle = () => {
        cancelAnimationFrame(frame);
        frame = 0;
        snap();
      },
      schedule = () => {
        if (quiet?.matches) {
          settle();
          return;
        }
        if (!frame) frame = requestAnimationFrame(paint);
      },
      move = (event: PointerEvent) => {
        if (event.pointerType === "touch") return;
        pointerX = (event.clientX / innerWidth - 0.5) * 18;
        pointerY = (event.clientY / innerHeight - 0.5) * 12;
        schedule();
      },
      leave = () => {
        pointerX = 0;
        pointerY = 0;
        schedule();
      },
      track = () => {
        scroll = Math.max(-14, Math.min(14, -scrollY * 0.02));
        schedule();
      },
      preference = () => {
        if (quiet?.matches) settle();
        else track();
      };
    area.addEventListener("pointermove", move, { passive: true });
    area.addEventListener("pointerleave", leave);
    addEventListener("scroll", track, { passive: true });
    quiet?.addEventListener("change", preference);
    requestPaint.current = schedule;
    track();
    return () => {
      requestPaint.current = () => {};
      cancelAnimationFrame(frame);
      area.removeEventListener("pointermove", move);
      area.removeEventListener("pointerleave", leave);
      removeEventListener("scroll", track);
      quiet?.removeEventListener("change", preference);
    };
  }, [hidden, reduced, root]);
  return useCallback((camera: Camera) => {
    target.current = camera;
    requestPaint.current();
  }, []);
}

export function TrailWorld({ route, children }: { route: string; children: React.ReactNode }) {
  const initial = useRef(cameraFor(route)).current,
    root = useRef<HTMLDivElement>(null),
    aim = useTrailCamera(root, initial);
  useEffect(() => aim(cameraFor(route)), [aim, route]);
  return (
    <TrailAim.Provider value={aim}>
      <div className="expedition-world" data-camera={route} ref={root}>
        <div className="trail-scenery" aria-hidden="true">
          {layers.map(([name, depth]) => (
            <span
              className={`trail-layer trail-layer-${name}`}
              data-trail-layer={name}
              data-depth={depth}
              key={name}
              style={{ transform: layerTransform(initial, depth) }}
            />
          ))}
        </div>
        {children}
      </div>
    </TrailAim.Provider>
  );
}

export function Trail({ tools, open }: { tools: Tools; open: (name: string) => void }) {
  const setCamera = useContext(TrailAim),
    stops = trailManifest.filter((stop) => tools[stop.name]);
  return (
    <section
      className="expedition"
      aria-labelledby="expedition-title"
      onPointerLeave={() => setCamera(trailCameras.home)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setCamera(trailCameras.home);
      }}
    >
      <header className="expedition-head">
        <p className="eyebrow">Your wildlife trail</p>
        <h1 id="expedition-title">Big plans, one connected path</h1>
        <p>Begin anywhere. Each stop keeps the next useful step within sight.</p>
      </header>
      <nav aria-label="Choose a mini along the trail">
        <ol className="trail-route">
          <span className="trail-map" aria-hidden="true" />
          {stops.map((stop, index) => {
            const tool = tools[stop.name];
            return (
              <li
                className="trail-stop"
                data-side={index % 2 ? "right" : "left"}
                data-biome={stop.name}
                data-camera={stop.camera.join(",")}
                key={stop.name}
                onPointerEnter={() => setCamera(stop.camera)}
                onFocusCapture={() => setCamera(stop.camera)}
              >
                <span className="trail-marker" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <article>
                  <div className="trail-habitat">
                    <Suspense fallback={<span className="trail-resident-loading" />}>
                      <Resident name={stop.name} resident={index} />
                    </Suspense>
                  </div>
                  <div className="trail-copy">
                    <span>{stop.place}</span>
                    <h2 style={{ viewTransitionName: `mini-${stop.name}` }}>
                      <a
                        href={miniHref(stop.name)}
                        onClick={(event) => {
                          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
                            return;
                          event.preventDefault();
                          open(stop.name);
                        }}
                      >
                        {tool.title}
                      </a>
                    </h2>
                    <p>{stop.description || tool.about}</p>
                  </div>
                </article>
              </li>
            );
          })}
        </ol>
      </nav>
    </section>
  );
}
