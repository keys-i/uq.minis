// @vitest-environment jsdom
import { test, expect, vi } from "vitest";
import { typeText, watchHabitat, watchMotion, watchScene } from "../src/shared/motion.ts";

type Visibility = (entries: { isIntersecting: boolean }[]) => void;
const clock = () => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

test("off-screen habitats cancel cycling and release their observer", () => {
  clock();
  let visible: Visibility = () => {
    throw new Error("Observer was not created");
  };
  const disconnect = vi.fn(),
    advance = vi.fn();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: Visibility) {
        visible = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  const scene = document.createElement("div");
  const stop = watchScene(scene, true, 28000, advance);
  expect(scene.dataset.running).toBe("false");
  visible([{ isIntersecting: true }]);
  expect(scene.dataset.running).toBe("true");
  vi.advanceTimersByTime(27000);
  visible([{ isIntersecting: false }]);
  vi.advanceTimersByTime(30000);
  expect(advance).not.toHaveBeenCalled();
  visible([{ isIntersecting: true }]);
  visible([{ isIntersecting: true }]);
  vi.advanceTimersByTime(28000);
  expect(advance).toHaveBeenCalledTimes(1);
  visible([{ isIntersecting: true }]);
  expect(stop).toBeTypeOf("function");
  stop?.();
  vi.advanceTimersByTime(28000);
  expect(advance).toHaveBeenCalledTimes(1);
  expect(disconnect).toHaveBeenCalledOnce();
  expect(scene.dataset.running).toBe("false");
});

test("typing cancels obsolete text and respects reduced motion", () => {
  clock();
  const seen: string[] = [];
  const stop = typeText("Old preview", (value) => seen.push(value));
  expect(seen.at(-1)).toBe("Ol");
  vi.advanceTimersByTime(18);
  expect(seen.at(-1)).toBe("Old ");
  expect(stop).toBeTypeOf("function");
  stop?.();
  typeText("New", (value) => seen.push(value));
  vi.advanceTimersByTime(1000);
  expect(seen.at(-1)).toBe("New");
  expect(seen).not.toContain("Old preview");
  typeText("Full text", (value) => seen.push(value), false);
  expect(seen.at(-1)).toBe("Full text");
});

test("focused or patted animals stay alive without cycling away", () => {
  clock();
  const scene = document.createElement("div");
  const stop = watchScene(scene, true, 28000);
  expect(scene.dataset.running).toBe("true");
  vi.advanceTimersByTime(60000);
  expect(scene.dataset.running).toBe("true");
  expect(stop).toBeTypeOf("function");
  stop?.();
  expect(scene.dataset.running).toBe("false");
});

test("holding an animal defers cycling without restarting its observer", () => {
  clock();
  let held = true,
    changes = 0,
    starts = 0;
  let visible: Visibility = () => {};
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: Visibility) {
        visible = callback;
        starts++;
      }
      observe() {
        visible([{ isIntersecting: true }]);
      }
      disconnect() {}
    },
  );
  const stop = watchScene(document.createElement("div"), true, 28000, () => {
    if (held) return false;
    changes++;
  });
  vi.advanceTimersByTime(28000);
  expect(changes).toBe(0);
  expect(starts).toBe(1);
  held = false;
  vi.advanceTimersByTime(1000);
  expect(changes).toBe(1);
  expect(starts).toBe(1);
  stop?.();
});

test("activities recur until the scene closes", () => {
  clock();
  const advance = vi.fn();
  const stop = watchScene(document.createElement("div"), true, 6000, advance);
  vi.advanceTimersByTime(6000);
  expect(advance).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(6000);
  expect(advance).toHaveBeenCalledTimes(2);
  stop?.();
  vi.advanceTimersByTime(6000);
  expect(advance).toHaveBeenCalledTimes(2);
});

test("page habitats track form height and release their resize observer", () => {
  let resized: () => void = () => {
    throw new Error("Observer was not created");
  };
  const disconnect = vi.fn();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        resized = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  const element = document.createElement("div");
  Object.defineProperty(element, "clientHeight", { value: 830, configurable: true });
  const stop = watchHabitat(element);
  expect(element.style.getPropertyValue("--rise")).toBe("550px");
  Object.defineProperty(element, "clientHeight", { value: 250, configurable: true });
  resized();
  expect(element.style.getPropertyValue("--rise")).toBe("0px");
  stop?.();
  expect(disconnect).toHaveBeenCalledOnce();
});

test("disabled scenes remain still", () => {
  const element = document.createElement("div");
  watchScene(element, false, 5000);
  expect(element.dataset.running).toBe("false");
});

test("motion follows reduced-motion and tab visibility and removes listeners", () => {
  const preference = Object.assign(new EventTarget(), { matches: false });
  vi.stubGlobal("matchMedia", () => preference);
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  const states: { reduced: boolean; hidden: boolean }[] = [];
  const stop = watchMotion((state) => states.push(state));
  preference.matches = true;
  preference.dispatchEvent(new Event("change"));
  hidden.mockReturnValue(true);
  document.dispatchEvent(new Event("visibilitychange"));
  expect(states).toEqual([
    { reduced: false, hidden: false },
    { reduced: true, hidden: false },
    { reduced: true, hidden: true },
  ]);
  stop();
  document.dispatchEvent(new Event("visibilitychange"));
  expect(states).toHaveLength(3);
});

test("inactivity sleeps once, genuine activity wakes once, and cleanup releases the deadline", async () => {
  const { watchIdle } = await import("../src/shared/motion.ts");
  vi.useFakeTimers();
  const update = vi.fn();
  const stop = watchIdle(90_000, update);
  vi.advanceTimersByTime(80_000);
  window.dispatchEvent(new Event("pointermove"));
  vi.advanceTimersByTime(89_999);
  expect(update).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(update).toHaveBeenLastCalledWith(true);
  window.dispatchEvent(new Event("keydown"));
  expect(update).toHaveBeenLastCalledWith(false);
  window.dispatchEvent(new Event("pointermove"));
  expect(update).toHaveBeenCalledTimes(2);
  stop();
  vi.advanceTimersByTime(180_000);
  expect(update).toHaveBeenCalledTimes(2);
});
