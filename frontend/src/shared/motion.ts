export function watchMotion(update: (environment: { reduced: boolean; hidden: boolean }) => void) {
  const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
  const refresh = () => update({ reduced: preference.matches, hidden: document.hidden });
  refresh();
  preference.addEventListener("change", refresh);
  document.addEventListener("visibilitychange", refresh);
  return () => {
    preference.removeEventListener("change", refresh);
    document.removeEventListener("visibilitychange", refresh);
  };
}

export function typeText(text: string, update: (text: string) => void, animate = true) {
  if (!animate) {
    update(text);
    return;
  }
  let length = 0,
    timer: ReturnType<typeof setTimeout> | undefined;
  const next = () => {
    length = Math.min(length + 2, text.length);
    update(text.slice(0, length));
    if (length < text.length) timer = setTimeout(next, 18);
  };
  next();
  return () => clearTimeout(timer);
}

export function watchHabitat(element: HTMLElement) {
  const size = () =>
    element.style.setProperty("--rise", `${Math.max(0, element.clientHeight - 280)}px`);
  size();
  if (typeof ResizeObserver === "undefined") return;
  const observer = new ResizeObserver(size);
  observer.observe(element);
  return () => observer.disconnect();
}

export function watchScene(
  element: HTMLElement,
  enabled: boolean,
  delay: number | (() => number),
  advance?: () => boolean | void,
) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const running = (shown: boolean) => {
    element.dataset.running = String(shown);
  };
  running(false);
  if (!enabled) return;
  const next = () => (typeof delay === "function" ? delay() : delay);
  const cycle = () => {
    timer = setTimeout(cycle, advance!() === false ? 1000 : next());
  };
  const visible = (shown: boolean) => {
    clearTimeout(timer);
    running(shown);
    if (shown && advance) timer = setTimeout(cycle, next());
  };
  const observer =
    typeof IntersectionObserver === "undefined"
      ? null
      : new IntersectionObserver(([entry]) => visible(entry.isIntersecting), { threshold: 0.15 });
  if (observer) observer.observe(element);
  else visible(true);
  return () => {
    clearTimeout(timer);
    observer?.disconnect();
    running(false);
  };
}

/** Observe activity without recording input or rebuilding a page on every pointer movement */
export function watchIdle(delay: number, update: (sleeping: boolean) => void) {
  let timer: ReturnType<typeof setTimeout>,
    last = -Infinity,
    asleep = false;
  const active = () => {
    const now = performance.now();
    if (!asleep && now - last < 500) return;
    last = now;
    clearTimeout(timer);
    if (asleep) {
      asleep = false;
      update(false);
    }
    timer = setTimeout(() => {
      asleep = true;
      update(true);
    }, delay);
  };
  const events = ["pointermove", "pointerdown", "keydown", "input", "scroll", "focus"] as const;
  for (const name of events) window.addEventListener(name, active, { passive: true });
  active();
  return () => {
    clearTimeout(timer);
    for (const name of events) window.removeEventListener(name, active);
  };
}
