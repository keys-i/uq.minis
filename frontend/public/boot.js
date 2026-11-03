(() => {
  const cameras = {
    home: [0, 0, 1],
    planny: [-30, 6, 1.12],
    scrappy: [-18, -4, 1.15],
    buzzy: [-4, 7, 1.12],
    clubby: [10, 0, 1.14],
    event: [24, 5, 1.13],
    agent: [24, 5, 1.13],
    timey: [36, -10, 1.16],
  };
  let choice = "system";
  try {
    choice = JSON.parse(localStorage.getItem("minis.display") || "null")?.theme || choice;
  } catch {}
  if (!['system', 'light', 'dark'].includes(choice)) choice = "system";
  const scheme =
    choice === "system"
      ? matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : choice;
  const query = new URLSearchParams(location.search);
  const match = location.pathname.match(/\/mini\/([a-z0-9-]+)\/?$/);
  const route = match?.[1] || query.get("m") || query.get("mini") || "home";
  document.documentElement.dataset.theme = scheme;
  document.documentElement.dataset.bootRoute = cameras[route] ? route : "home";
  addEventListener(
    "DOMContentLoaded",
    () => {
      const camera = cameras[route] || cameras.home;
      document.querySelectorAll(".boot-layer").forEach((layer, index) => {
        const depth = [0.08, 0.18, 0.28, 0.42, 0.58, 0.76][index];
        layer.style.transform = `translate3d(${(camera[0] * depth).toFixed(2)}px, ${(camera[1] * depth).toFixed(2)}px, 0) scale(${camera[2].toFixed(3)})`;
      });
    },
    { once: true },
  );
})();
