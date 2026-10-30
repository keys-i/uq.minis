/** Render visible whole-character residents in one viewport-sized Pixi application

React owns controls and infrequent behaviour changes; the ticker owns scenery and character
movement and never publishes animation frames through component state
*/
import { Application, Container, Graphics, Rectangle, Sprite, Texture } from "pixi.js";
// Pixi's compatibility module replaces generated functions under the site's strict CSP
import "pixi.js/unsafe-eval";
import { artwork, atlases, pose } from "./frames.ts";
import { diggers } from "./life.ts";
import type { Species } from "./animals.ts";

export interface Pose {
  animal: Species;
  action: string;
  light: number;
  wind: number;
  rain: number;
  wake: number;
  temperature?: number;
}
interface Resident {
  element: HTMLElement;
  read: () => Pose;
  group: Container;
  mask: Graphics;
  sprite?: Sprite;
  previousSprite?: Sprite;
  box: DOMRect;
  seed: number;
  resource: string;
  released: boolean;
  entered: number;
  previous: string;
  frame: number;
  changed: number;
  images: Texture[];
  offset: number;
  lift: number;
  scene: Container;
  ground: Graphics;
  effects: Graphics;
  burrow: number;
  guest?: Sprite;
  guests?: Texture[];
  facing: number;
}
interface Resource {
  promise: Promise<Texture[]>;
  users: number;
  used: number;
  source?: Texture;
}
const residents = new Map<HTMLElement, Resident>(),
  resources = new Map<string, Resource>();
let application: Application | undefined, starting: Promise<Application> | undefined;
let layout: PerformanceObserver | undefined;
let observer: ResizeObserver | undefined,
  dirty = true,
  contextLost = false;

function unload(id: string, resource: Resource) {
  resources.delete(id);
  void resource.promise
    .then((textures) => {
      for (const texture of textures) texture.destroy(false);
      resource.source?.destroy(true);
    })
    .catch((error) => console.warn("Character texture cleanup failed", error));
}
function release(id: string, promise: Promise<Texture[]>) {
  const resource = resources.get(id);
  if (resource?.promise === promise) {
    resource.users--;
    resource.used = performance.now();
  }
  const idle = [...resources]
    .filter(([, item]) => item.users === 0)
    .sort((a, b) => a[1].used - b[1].used);
  while (resources.size > 8 && idle.length) {
    const [key, item] = idle.shift()!;
    unload(key, item);
  }
}
function acquire(id: string) {
  let resource = resources.get(id);
  if (!resource) {
    const image = new Image();
    image.src = artwork(id);
    const created: Resource = {
      users: 0,
      used: performance.now(),
      promise: image
        .decode()
        .then(() => {
          const texture = Texture.from(image);
          created.source = texture;
          return atlases[id].frames.map(
            ([x, y, width, height]) =>
              new Texture({ source: texture.source, frame: new Rectangle(x, y, width, height) }),
          );
        })
        .catch((error) => {
          if (resources.get(id) === created) resources.delete(id);
          throw error;
        }),
    };
    resource = created;
    resources.set(id, resource);
  }
  resource.users++;
  return resource.promise;
}
const invalidate = () => {
  dirty = true;
};
const resolution = () =>
  Math.min(devicePixelRatio || 1, 2, Math.sqrt(4_000_000 / Math.max(1, innerWidth * innerHeight)));
const lost = () => {
  contextLost = true;
  for (const resident of residents.values()) delete resident.element.dataset.rendered;
};
const restored = () => {
  contextLost = false;
  dirty = true;
};

async function start() {
  if (application) return application;
  if (starting) return starting;
  starting = (async () => {
    const app = new Application();
    try {
      await app.init({
        width: innerWidth,
        height: innerHeight,
        resolution: resolution(),
        autoDensity: true,
        backgroundAlpha: 0,
        antialias: true,
        autoStart: false,
      });
    } catch (error) {
      if (app.renderer) app.destroy(true, { children: true });
      throw error;
    }
    if (!residents.size) {
      app.destroy(true, { children: true });
      for (const [key, value] of resources) if (value.users === 0) unload(key, value);
      return app;
    }
    app.canvas.className = "wildlife-canvas";
    app.canvas.setAttribute("aria-hidden", "true");
    app.canvas.addEventListener("webglcontextlost", lost);
    app.canvas.addEventListener("webglcontextrestored", restored);
    document.body.append(app.canvas);
    application = app;
    contextLost = false;
    observer = new ResizeObserver(invalidate);
    observer.observe(document.body);
    if (
      typeof PerformanceObserver !== "undefined" &&
      PerformanceObserver.supportedEntryTypes.includes("layout-shift")
    ) {
      layout = new PerformanceObserver(invalidate);
      layout.observe({ type: "layout-shift" });
    }
    window.addEventListener("scroll", invalidate, { capture: true, passive: true });
    window.addEventListener("resize", invalidate, { passive: true });
    app.ticker.maxFPS = navigator.hardwareConcurrency <= 4 ? 30 : 60;
    app.ticker.add(tick);
    app.start();
    return app;
  })();
  try {
    return await starting;
  } finally {
    starting = undefined;
  }
}

function tick() {
  const app = application;
  if (!app) return;
  const now = performance.now() / 1000;
  if (dirty) {
    if (
      app.screen.width !== innerWidth ||
      app.screen.height !== innerHeight ||
      app.renderer.resolution !== resolution()
    ) {
      app.renderer.resolution = resolution();
      app.renderer.resize(innerWidth, innerHeight);
    }
    for (const resident of residents.values()) {
      resident.box = resident.element.getBoundingClientRect();
      const b = resident.box;
      resident.mask
        .clear()
        .roundRect(b.x, b.y, b.width, b.height, Math.min(24, b.height * 0.1))
        .fill(0xffffff);
    }
    dirty = false;
  }
  for (const resident of residents.values()) {
    if (!resident.sprite) continue;
    const state = resident.read(),
      box = resident.box;
    resident.scene.visible =
      box.bottom > 0 && box.top < innerHeight && box.right > 0 && box.left < innerWidth;
    if (!resident.scene.visible) continue;
    if (!contextLost) resident.element.dataset.rendered = "true";
    if (resident.previous !== state.action) {
      resident.previous = state.action;
      resident.entered = now;
    }
    const time = now + resident.seed,
      age = now - resident.entered,
      dt = Math.min(0.1, app.ticker.deltaMS / 1000);
    const sleeping = state.action === "sleep" || state.action === "rest";
    const fly = ["fly", "soar"].includes(state.action);
    const moving =
      fly || ["wander", "swim", "dive", "climb", "hop", "slide", "play"].includes(state.action);
    const waking = state.action === "wake" ? Math.sin(Math.min(1, age / state.wake) * Math.PI) : 0;
    const pace = time * (fly ? 2.4 : state.action === "swim" ? 1.5 : 1.8);
    const travel = moving
      ? Math.sin(resident.seed + resident.entered) *
        Math.min(box.width * 0.12, 34) *
        Math.min(1, age / 10)
      : 0;
    const easing = 1 - Math.exp(-dt * 3.2);
    resident.offset += (travel - resident.offset) * easing;
    const hop = state.action === "hop" && age < 5 ? Math.abs(Math.sin((age * Math.PI) / 1.6)) : 0;
    const lift = fly
      ? -box.height * 0.1 + Math.sin(time * 0.8) * box.height * 0.13
      : hop
        ? -hop * box.height * 0.12
        : state.action === "climb"
          ? -Math.min(box.height * 0.16, age * 4)
          : 0;
    resident.lift += (lift - resident.lift) * easing;
    if (moving && Math.abs(travel - resident.offset) > 1)
      resident.facing = travel < resident.offset ? -1 : 1;
    const fit = Math.min(box.width / 320, box.height / 220) * 0.92;
    resident.group.position.set(
      box.x + box.width / 2 + resident.offset,
      box.y + box.height / 2 + resident.lift + (moving ? Math.sin(pace) * fit * 0.85 : 0),
    );
    resident.group.pivot.set(160, 110);
    resident.group.rotation =
      waking && ["otter", "dog", "quoll", "mink"].includes(state.animal.id)
        ? Math.sin(age * 4) * 0.012 * waking
        : 0;
    resident.group.scale.set(
      resident.facing * fit * (1 + waking * (state.animal.id.includes("pangolin") ? 0.035 : 0.008)),
      fit * (1 + waking * 0.018),
    );
    const shade = Math.round(255 * (0.55 + state.light * 0.45));
    const ground = resident.ground,
      effects = resident.effects;
    ground.clear();
    effects.clear();
    const dig = state.action === "dig" && diggers.has(state.animal.id);
    resident.burrow = Math.max(0, Math.min(1, resident.burrow + dt * (dig ? 0.22 : -0.12)));
    const earth = resident.burrow,
      gx = box.x + box.width * 0.42,
      gy = box.y + box.height * 0.78;
    if (earth > 0) {
      const radius = Math.min(32, box.width * 0.08) * earth;
      ground.ellipse(gx, gy, radius, radius * 0.26).fill({ color: 0x8b6746, alpha: 0.8 });
      ground
        .ellipse(gx, gy - 1, radius * 0.78, radius * 0.18)
        .fill({ color: 0x29221d, alpha: earth * 0.8 });
    }
    if ((dig && age < 9) || (state.action === "dust" && age < 6))
      for (let i = 0; i < 8; i++) {
        const t = (age - i * 0.17) % 1.5;
        if (t >= 0)
          effects
            .circle(gx + (i % 2 ? 1 : -1) * t * (13 + i * 4), gy - t * (1.5 - t) * 25, 1.5)
            .fill({ color: 0xa98052, alpha: 1 - t / 1.5 });
      }
    if (state.rain > 0.05 && ![2, 5, 7].includes(state.animal.scene)) {
      const snow = state.temperature !== undefined && state.temperature < 1;
      for (let i = 0; i < Math.min(32, 8 + state.rain * 5); i++) {
        const x = box.x + ((i * 0.618 + time * 0.04 + resident.seed) % 1) * box.width,
          y = box.y + ((i * 0.317 + time * (snow ? 0.08 : 0.6)) % 1) * box.height;
        if (snow) effects.circle(x, y, 1.5).fill({ color: 0xf5f3e9, alpha: 0.65 });
        else
          effects
            .moveTo(x, y)
            .lineTo(x - Math.min(7, state.wind * 0.4), y + 9)
            .stroke({ color: 0xd9e6eb, alpha: 0.38, width: 1 });
      }
    }
    if (resident.guest && resident.guests) {
      const cycle = (time * 0.015 + resident.seed * 0.37) % 1;
      const water = [2, 5, 7].includes(state.animal.scene),
        shore = [4, 16, 18].includes(state.animal.scene);
      const frame = water
        ? 4
        : shore
          ? 0
          : state.light < 0.3
            ? 5
            : [1, 11].includes(state.animal.scene)
              ? 3
              : state.animal.scene === 6
                ? 2
                : 1;
      const guest = resident.guest;
      guest.visible = cycle < 0.2 && (state.light > 0.2 || !water);
      guest.texture = resident.guests[frame];
      const width = Math.min(34, box.width * 0.075);
      guest.width = width;
      guest.height = (width * guest.texture.height) / guest.texture.width;
      const progress = cycle / 0.2;
      guest.position.set(
        box.x - 30 + progress * (box.width + 60),
        box.y + box.height * (frame === 2 ? 0.78 : water ? 0.65 : 0.28) + Math.sin(time * 1.8) * 5,
      );
      guest.scale.y *= [1, 3, 5].includes(frame) ? 0.72 + Math.abs(Math.sin(time * 8)) * 0.28 : 1;
      guest.alpha = Math.min(1, progress * 10, (1 - progress) * 10) * (0.5 + state.light * 0.5);
    }
    const sprite = resident.sprite;
    const frame = pose(state.animal, state.action);
    if (frame !== resident.frame) {
      if (resident.previousSprite) {
        resident.group.removeChild(resident.previousSprite);
        resident.previousSprite.destroy();
      }
      resident.previousSprite = new Sprite(sprite.texture);
      resident.previousSprite.width = 320;
      resident.previousSprite.height = 220;
      resident.group.addChildAt(resident.previousSprite, 0);
      resident.frame = frame;
      resident.changed = now;
      sprite.texture = resident.images[frame];
    }
    sprite.width = 320;
    sprite.height = 220;
    sprite.tint = (shade << 16) | (Math.min(255, shade + 5) << 8) | Math.min(255, shade + 10);
    if (resident.previousSprite) {
      const progress = Math.min(1, (now - resident.changed) / 0.38),
        blend = progress * progress * (3 - 2 * progress);
      sprite.alpha = blend;
      resident.previousSprite.alpha = 1 - blend;
      resident.previousSprite.tint = sprite.tint;
      if (progress === 1) {
        resident.group.removeChild(resident.previousSprite);
        resident.previousSprite.destroy();
        resident.previousSprite = undefined;
      }
    } else sprite.alpha = 1;
    resident.group.scale.y *=
      1 + Math.sin(time * (sleeping ? 1.2 : 2)) * (sleeping ? 0.004 : 0.002);
  }
}

/** Register one visible scene and release only its owned objects on unmount */
export function register(element: HTMLElement, read: () => Pose) {
  const first = read();
  const resident: Resident = {
    element,
    read,
    group: new Container(),
    mask: new Graphics(),
    box: element.getBoundingClientRect(),
    seed: [...first.animal.id].reduce((n, c) => n + c.charCodeAt(0) * 0.113, 0),
    resource: first.animal.id,
    released: false,
    entered: performance.now() / 1000,
    previous: first.action,
    frame: pose(first.animal, first.action),
    changed: performance.now() / 1000,
    images: [],
    offset: 0,
    lift: 0,
    scene: new Container(),
    ground: new Graphics(),
    effects: new Graphics(),
    burrow: 0,
    facing: 1,
  };
  residents.set(element, resident);
  resident.scene.addChild(resident.ground, resident.group, resident.effects);
  const textures = acquire(resident.resource);
  const guests = atlases.guests ? acquire("guests") : undefined;
  if (guests)
    void guests
      .then((images) => {
        if (resident.released) return;
        resident.guests = images;
        resident.guest = new Sprite(images[0]);
        resident.scene.addChild(resident.guest);
      })
      .catch((error) => console.warn("Habitat visitors could not load", error));
  void Promise.all([start(), textures])
    .then(([app, images]) => {
      if (resident.released) return;
      resident.images = images;
      resident.sprite = new Sprite(images[resident.frame]);
      resident.sprite.width = 320;
      resident.sprite.height = 220;
      resident.group.addChild(resident.sprite);
      resident.scene.mask = resident.mask;
      app.stage.addChild(resident.scene, resident.mask);
      observer?.observe(element);
      dirty = true;
    })
    .catch((error) => {
      if (!resident.released) {
        delete element.dataset.rendered;
        console.warn("Still wildlife is shown because animation could not start", error);
      }
    });
  return () => {
    if (resident.released) return;
    resident.released = true;
    residents.delete(element);
    observer?.unobserve(element);
    delete element.dataset.rendered;
    resident.scene.destroy({ children: true });
    resident.mask.destroy();
    release(resident.resource, textures);
    if (guests) release("guests", guests);
    queueMicrotask(() => {
      if (residents.size) return;
      observer?.disconnect();
      observer = undefined;
      layout?.disconnect();
      layout = undefined;
      window.removeEventListener("scroll", invalidate, true);
      window.removeEventListener("resize", invalidate);
      application?.destroy(true, { children: true });
      application = undefined;
      if (!starting)
        for (const [key, value] of resources) if (value.users === 0) unload(key, value);
    });
  };
}
