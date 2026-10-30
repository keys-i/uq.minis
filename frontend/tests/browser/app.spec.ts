import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const tools = Object.fromEntries(
  ["planny", "buzzy", "scrappy", "clubby", "event", "timey"].map((name) => [
    name,
    { title: name[0].toUpperCase() + name.slice(1), about: `Your ${name} helper` },
  ]),
);
const plan = {
  revision: 0,
  courses: [],
  assessments: [],
  announcements: [],
  settings: { buffer: 2, target: 75 },
};
const pixel = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=",
  "base64",
);
const readiness = {
  status: "missing",
  missing: ["CSSE1001", "MATH1051"],
  incompatible: [],
  wording: "CSSE1001 and MATH1051",
  skills: [],
  required: ["CSSE1001", "MATH1051"],
  known: ["CSSE1001"],
};
const subject = {
  code: "CSSE2002",
  name: "Programming in the Large",
  faculty: "Engineering",
  metrics: {},
  readiness,
};

/** Keep interaction checks deterministic without contacting UQ or YouTube */
async function api(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith("/api/weather/")) {
      await route.fulfill({
        json: {
          habitat: path.split("/").at(-1),
          updated: new Date().toISOString(),
          expires: Date.now() / 1000 + 1800,
          stale: false,
          cloud: 20,
          rain: 0,
          wind: 2,
          temperature: 18,
        },
      });
      return;
    }
    let data: unknown;
    switch (path) {
      case "/api/minis":
        data = tools;
        break;
      case "/api/plan":
        data =
          route.request().method() === "POST"
            ? JSON.parse(route.request().postData() || "{}")
            : plan;
        break;
      case "/api/languages":
        data = { languages: { en: "English", ar: "Arabic", hi: "Hindi" }, configured: false };
        break;
      case "/api/session":
        data = { user: "" };
        break;
      case "/api/session/login":
        data = { user: "", window: "/api/session/window" };
        break;
      case "/api/session/logout":
        data = { user: "" };
        break;
      case "/api/minis/event":
      case "/api/minis/scrappy":
      case "/api/minis/clubby":
        data = { fields: [], about: "Prepare an event" };
        break;
      case "/api/clubs/feed":
        data = { rows: [], warning: "" };
        break;
      case "/api/search":
        data = { rows: [], total: 0, categories: [] };
        break;
      case "/api/minis/timey":
        if (route.request().method() === "POST") {
          data = {
            result: "Ready",
            downloads: [{ name: "timer.mp4", url: "/download/movie-timer" }],
          };
          break;
        }
        data = {
          fields: [
            { name: "length", label: "Countdown length", value: "10m" },
            { name: "start_gap", label: "Get-ready time", value: "5s" },
            { name: "end_gap", label: "Finishing hold", value: "5s" },
          ],
        };
        break;
      case "/api/timey/suggest":
        data = { suggestions: ["mario gameplay", "mario music"] };
        break;
      case "/api/timey/youtube":
        data = { connected: true, open: false };
        break;
      case "/api/timey/save":
        data = {
          result: "Ready",
          downloads: [{ name: "timer.mp4", url: "/download/movie-timer" }],
        };
        break;
      case "/api/research":
        data = {
          rows: [subject],
          total: 1,
          faculties: ["Engineering"],
          study_year: 2026,
          semester: "2",
        };
        break;
      case "/api/research/course":
        data = {
          course: subject,
          details: { "Course Code": subject.code, "Pre-Requisites": readiness.wording },
          readiness,
          reviews: [],
          secat: [],
          offerings: [
            {
              period: "Semester 2, 2026",
              campus: "St Lucia",
              profile: "https://course-profiles.uq.edu.au/current",
            },
            {
              period: "Semester 1, 2025",
              campus: "St Lucia",
              profile: "https://course-profiles.uq.edu.au/older",
            },
          ],
          url: "https://programs-courses.uq.edu.au/course.html?course_code=CSSE2002",
        };
        break;
      case "/api/profile":
        data = {
          assessments: [
            {
              title: "Software assignment",
              weight: 30,
              due: "",
              due_text: "Week 5",
              notes: "Review the official date",
            },
          ],
          rules: "",
          notice: "Review these details",
        };
        break;
      case "/api/research/trail":
        data = {
          nodes: [
            {
              code: "CSSE2002",
              name: subject.name,
              required: ["CSSE1001", "MATH1051"],
              loaded: true,
              depth: 0,
            },
            {
              code: "CSSE1001",
              name: "Introduction to Software Engineering",
              required: [],
              loaded: true,
              depth: 1,
            },
            { code: "MATH1051", name: "Calculus", required: [], loaded: true, depth: 1 },
          ],
        };
        break;
      case "/api/brand/uq.png":
        await route.fulfill({ body: pixel, contentType: "image/png" });
        return;
      case "/api/timey/preview":
        await route.fulfill({
          path: fileURLToPath(new URL("../fixtures/timer.png", import.meta.url)),
          contentType: "image/png",
        });
        return;
      case "/api/timey/clip":
        data = {
          source: "https://www.youtube.com/watch?v=jfKfPfyJRdk",
          url: "/sample.png",
          kind: "image",
          complete: true,
          start: 0,
          duration: 10,
          width: 960,
          height: 540,
        };
        break;
      default:
        throw new Error(`Unexpected API request: ${path}`);
    }
    await route.fulfill({ json: data });
  });
  await page.route("**/sample.png", (route) =>
    route.fulfill({ body: pixel, contentType: "image/png" }),
  );
  await page.route("**/download/movie-*", (route) =>
    route.fulfill({
      path: fileURLToPath(new URL("../fixtures/backdrop.webm", import.meta.url)),
      contentType: "video/webm",
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await api(page);
});

test("the language picker stays focused on language choices", async ({ page }) => {
  await page.goto("/");
  await page.locator(".language-trigger").click();
  const menu = page.getByRole("dialog", { name: "Choose your reading language" });
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("heading")).toHaveCount(0);
  await expect(menu.getByRole("button", { name: "Close languages" })).toHaveCount(0);
  await expect(menu.getByRole("radio", { name: "English" })).toBeVisible();
  await expect(menu).not.toContainText(
    /Your words|Browser favourites|Follow my browser|Original text|Translations keep/,
  );
});

test("only Timey keeps the paper background around its mini", async ({ page }) => {
  for (const mini of ["planny", "buzzy", "scrappy", "clubby", "event"]) {
    await page.goto(`/?m=${mini}`);
    await expect(page.locator(".habitat-page")).toHaveCSS("background-color", "rgb(244, 247, 251)");
    await expect(page.locator(".habitat-content")).toHaveCSS(
      "background-color",
      "rgba(0, 0, 0, 0)",
    );
    await expect(page.locator(".site-footer")).toHaveCSS("background-color", "rgb(244, 247, 251)");
  }
  await page.goto("/?m=timey");
  await expect(page.locator(".habitat-page")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(page.locator("html")).toHaveCSS("background-color", "rgb(255, 251, 239)");
});

test("Timey uses its whole preview as the Google connection step", async ({ page }) => {
  const actions: string[] = [];
  await page.route("**/api/timey/youtube?status=1", (route) =>
    route.fulfill({ json: { connected: false, open: false } }),
  );
  await page.route("**/api/timey/youtube?view=1", (route) => {
    if (route.request().method() === "POST")
      actions.push((route.request().postDataJSON() as { kind: string }).kind);
    return route.fulfill({
      json: {
        mode: "window",
        image: pixel.toString("base64"),
        host: "accounts.google.com",
        title: "Google sign-in",
        text: "",
        width: 760,
        height: 480,
        controls: [],
      },
    });
  });
  await page.goto("/?mini=timey");
  const preview = page.getByRole("region", { name: "Connect Google" });
  await expect(preview).toBeVisible();
  await expect(preview).toHaveClass(/timer-canvas/);
  const reveal = preview.locator(".timer-google-reveal"),
    paper = preview.locator(".timer-google-paper");
  await expect(reveal).toHaveCSS("background-image", "none");
  await expect(paper).toHaveCSS("mask-image", /rip\.svg/);
  await expect
    .poll(() => preview.evaluate((node) => getComputedStyle(node, "::before").maskImage))
    .toContain("hole.svg");
  await expect
    .poll(() => preview.evaluate((node) => getComputedStyle(node, "::after").maskImage))
    .toContain("hole.svg");
  const panel = preview.locator(".timer-google-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toHaveCSS("mask-image", /panel\.svg/);
  await expect(panel).toHaveCSS("mask-image", /feather\.svg/);
  await expect(preview.getByRole("button", { name: "Connect Google" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Background preview" })).toHaveCount(0);
  await expect(page.locator(".timer-connect-step")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  const previewBox = await preview.boundingBox(),
    paperBox = await paper.boundingBox();
  expect(previewBox).not.toBeNull();
  expect(paperBox).not.toBeNull();
  expect(paperBox!.width).toBeLessThan(previewBox!.width * 0.94);
  expect(paperBox!.height).toBeLessThan(previewBox!.height * 0.86);
  await preview.getByRole("button", { name: "Connect Google" }).click();
  const window = panel.locator(".portal-window");
  await expect(window).toBeVisible();
  await expect(page.locator("dialog")).toHaveCount(0);
  await expect(window.getByText(/^Up$|^Down$/)).toHaveCount(0);
  await expect(window.locator(".portal-screen > img")).toHaveAttribute(
    "src",
    /^data:image\/png;base64,/,
  );
  await window.locator(".portal-screen").dispatchEvent("wheel", { deltaY: 360 });
  await expect.poll(() => actions).toContain("scroll");
  await expect(page.getByText("Sign in with Google to search and use YouTube videos")).toHaveCount(
    0,
  );
});

test("Timey keeps Google failures inside its connection panel", async ({ page }) => {
  await page.route("**/api/timey/youtube?status=1", (route) =>
    route.fulfill({
      status: 503,
      json: { error: "OAuthError: invalid_grant from upstream trace 43" },
    }),
  );
  await page.goto("/?mini=timey");
  const panel = page.locator(".timer-google-panel"),
    popup = panel.locator(".timer-google-error"),
    alert = popup.getByRole("alert");
  await expect(alert).toContainText("Google didn’t connect");
  await expect(alert).toContainText("Your timer is safe");
  await expect(page.getByText(/invalid_grant|upstream trace/i)).toHaveCount(0);
  await expect(popup).toHaveCSS("position", "absolute");
  await expect(popup.getByRole("button", { name: "Try again" })).toBeFocused();
  const panelBox = await panel.boundingBox(),
    popupBox = await popup.boundingBox();
  expect(panelBox).not.toBeNull();
  expect(popupBox).not.toBeNull();
  expect(Math.abs(popupBox!.x - panelBox!.x)).toBeLessThan(1);
  expect(Math.abs(popupBox!.y - panelBox!.y)).toBeLessThan(1);
  expect(Math.abs(popupBox!.width - panelBox!.width)).toBeLessThan(1);
  expect(Math.abs(popupBox!.height - panelBox!.height)).toBeLessThan(1);
});

test("the public shelf paints while the catalogue is still pending", async ({ page }) => {
  let finish: (() => Promise<void>) | undefined;
  await page.route("**/api/minis", async (route) => {
    await new Promise<void>((resolve) => {
      finish = async () => {
        await route.fulfill({ json: tools });
        resolve();
      };
    });
  });
  await page.goto("/");
  await expect(page.locator(".mini-card")).toHaveCount(6);
  await expect(page.getByRole("link", { name: "Timey", exact: true })).toBeVisible();
  await expect.poll(() => !!finish).toBe(true);
  await finish!();
});

test("custom revisions, watching and sign-in preserve the project", async ({ page }) => {
  const errors: string[] = [],
    briefs: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/session/login", (route) =>
    route.fulfill({ json: { user: "student@student.uq.edu.au" } }),
  );
  await page.route("**/api/minis/timey", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const body = route.request().postData() || "";
    briefs.push(body);
    await route.fulfill({
      json:
        briefs.length === 1
          ? { result: "A question", questions: ["Which shades would you like?"] }
          : {
              result: "Ready",
              design: { id: "ocean", name: "Ocean" },
              downloads: [{ name: "timer.mp4", url: "/download/movie-timer" }],
            },
    });
  });
  await page.goto("/?mini=timey");
  await page
    .getByRole("combobox", { name: "Search YouTube or paste a link" })
    .fill("https://youtu.be/abcdefghijk");
  await page.keyboard.press("Enter");
  const overlay = page.getByRole("button", { name: "Move timer", exact: true });
  await overlay.click();
  await page.getByRole("textbox", { name: "Timer label" }).fill("Ocean study");
  await page.getByRole("button", { name: "Custom", exact: true }).click();
  const custom = page.getByRole("dialog", { name: "Custom artwork" });
  await custom.getByRole("textbox", { name: "Name", exact: true }).fill("Ocean");
  await custom.getByRole("textbox", { name: "Name", exact: true }).press("Enter");
  expect(briefs).toHaveLength(0);
  await custom
    .getByRole("textbox", { name: "What should it look like?" })
    .fill("Waves around open digits; ask me about the colours");
  await custom.getByRole("button", { name: "Try this look" }).click();
  await custom
    .getByRole("textbox", { name: "Which shades would you like?" })
    .fill("Deep blue with warm sand");
  await custom.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.locator(".timer-studio")).toHaveAttribute("data-stage", "preview");
  await expect(page.getByRole("group", { name: "Timer look", exact: true })).toHaveCount(0);
  expect(briefs[1]).toContain("Deep blue with warm sand");
  await page.getByRole("button", { name: "Edit video", exact: true }).click();
  await page.getByRole("button", { name: "Custom", exact: true }).click();
  await custom
    .getByRole("textbox", { name: "What would you like to change?" })
    .fill("Keep the waves, make the digits lighter");
  await custom.getByRole("button", { name: "Update this look" }).click();
  await expect(page.locator(".timer-studio")).toHaveAttribute("data-stage", "preview");
  expect(briefs[2]).toContain("Keep the waves");
  expect(briefs[2]).toContain("ocean");
  await page.getByRole("button", { name: "Make video", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save video", exact: true })).toBeEnabled();
  await page.screenshot({
    path: test.info().outputPath("timey-final-desktop.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Save video", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Save video", exact: true }).click();
  const save = page.getByRole("dialog", { name: "Save your video", exact: true });
  await expect(save.getByRole("textbox", { name: "Name", exact: true })).toHaveValue("Ocean study");
  await save.getByRole("button", { name: "Upload a copy", exact: true }).click();
  await expect(save.getByRole("button", { name: "YouTube", exact: true })).toBeEnabled();
  await expect(save.getByRole("button", { name: "Keysi CDN", exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: test.info().outputPath("timey-save-mobile.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await save.getByRole("button", { name: "Close save", exact: true }).click();
  await page.getByRole("button", { name: "Edit video", exact: true }).click();
  await overlay.click();
  await expect(page.getByRole("textbox", { name: "Timer label", exact: true })).toHaveValue(
    "Ocean study",
  );
  expect(errors).toEqual([]);
});

test("changing videos keeps a decoded backdrop and a legible themed picker", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.route("https://i.ytimg.com/vi/*/default.jpg", (route) =>
    route.fulfill({
      path: fileURLToPath(new URL("../fixtures/poster.jpg", import.meta.url)),
      contentType: "image/jpeg",
    }),
  );
  await page.route("**/video/*.webm", (route) =>
    route.fulfill({
      path: fileURLToPath(new URL("../fixtures/backdrop.webm", import.meta.url)),
      contentType: "video/webm",
    }),
  );
  let finish: (() => Promise<void>) | undefined;
  await page.route("**/api/timey/clip", async (route) => {
    const second = route.request().postData()?.includes("lmnopqrstuv");
    const response = {
      url: second ? "/video/second.webm" : "/video/first.webm",
      kind: "video",
      width: 96,
      height: 64,
      duration: 1,
      complete: true,
    };
    if (!second) return route.fulfill({ json: response });
    await new Promise<void>((resolve) => {
      finish = async () => {
        await route.fulfill({ json: response });
        resolve();
      };
    });
  });
  await page.goto("/?mini=timey");
  const search = page.getByRole("combobox", { name: "Search YouTube or paste a link" });
  await search.fill("https://www.youtube.com/watch?v=abcdefghijk");
  await search.press("Enter");
  const player = page.getByLabel("Cached backdrop preview");
  await expect
    .poll(() => player.evaluate((node: HTMLVideoElement) => node.readyState))
    .toBeGreaterThanOrEqual(2);
  await page.getByRole("group", { name: "Background preview", exact: true }).hover();
  const picker = page.getByRole("button", { name: "Change background", exact: true });
  const icon = picker.locator(".icon");
  await expect
    .poll(() => icon.evaluate((node) => node.getBoundingClientRect().width))
    .toBeGreaterThan(14);
  expect(await picker.evaluate((node) => getComputedStyle(node).color)).toBe(
    await picker.evaluate((node) => getComputedStyle(node.parentElement!).color),
  );
  await picker.focus();
  await expect(page.getByRole("tooltip")).toHaveText("Change background");
  await expect(picker).not.toHaveAttribute("title");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await picker.click();
  await expect(page.getByRole("button", { name: "Close background search" })).toHaveCount(1);
  await search.focus();
  await search.press("ControlOrMeta+A");
  await search.press("Backspace");
  await expect(search).toHaveValue("");
  await search.fill("https://www.youtube.com/watch?v=abcdefghijk");
  await page.screenshot({ path: test.info().outputPath("background-search.png"), fullPage: true });
  await page.getByRole("button", { name: "Close background search" }).click();
  await expect(search).toHaveCount(0);
  await expect(player).toHaveAttribute("src", "/video/first.webm");
  await page.getByRole("group", { name: "Background preview", exact: true }).hover();
  await picker.click();
  await search.fill("https://www.youtube.com/watch?v=lmnopqrstuv");
  await search.press("Enter");
  await expect.poll(() => !!finish).toBe(true);
  await expect(player).toHaveAttribute("src", "/video/first.webm");
  await expect(page.locator(".timer-mist[data-active]")).toBeVisible();
  const stage = page.getByRole("group", { name: "Background preview", exact: true });
  await stage.hover({ position: { x: 80, y: 80 } });
  expect(
    Number.parseFloat(await stage.evaluate((node) => node.style.getPropertyValue("--mist-x"))),
  ).toBeCloseTo(80, 0);
  await expect(page.getByRole("status").filter({ hasText: "Caching your backdrop" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("mist-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.locator(".sidebar").evaluate((node) => node.getBoundingClientRect().width))
    .toBeGreaterThan(300);
  await page.screenshot({ path: test.info().outputPath("mist-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await finish!();
  await expect(player).toHaveAttribute("src", "/video/second.webm");
  await expect
    .poll(() => player.evaluate((node: HTMLVideoElement) => node.readyState))
    .toBeGreaterThanOrEqual(2);
  const pixel = await player.evaluate((node: HTMLVideoElement) => {
    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    const context = canvas.getContext("2d")!;
    context.drawImage(node, 0, 0, 1, 1);
    return [...context.getImageData(0, 0, 1, 1).data];
  });
  expect(pixel[2]).toBeGreaterThan(150);
  await picker.hover();
  await page.screenshot({ path: test.info().outputPath("backdrop-light.png"), fullPage: true });
  const theme = page.getByRole("button", { name: /App theme/ });
  await theme.focus();
  await expect(page.getByRole("tooltip")).toHaveText("Switch to dark mode");
  await expect(theme).not.toHaveAttribute("title");
  await theme.click();
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await theme.blur();
  await theme.focus();
  await expect(page.getByRole("tooltip")).toHaveText("Switch to light mode");
  await page.getByRole("group", { name: "Background preview", exact: true }).hover();
  await picker.hover();
  expect(await picker.evaluate((node) => getComputedStyle(node).color)).toBe(
    await picker.evaluate((node) => getComputedStyle(node.parentElement!).color),
  );
  await expect(icon).toBeVisible();
  const edge = () =>
    player.evaluate((node) => ({
      mask: getComputedStyle(node).maskImage,
      size: getComputedStyle(node).maskSize,
      width: node.getBoundingClientRect().width,
      height: node.getBoundingClientRect().height,
    }));
  const normal = await edge();
  expect(normal.mask).toContain("feather.svg");
  await page.getByRole("group", { name: "Background preview", exact: true }).focus();
  expect(await edge()).toEqual(normal);
  await page.getByRole("button", { name: "Move timer", exact: true }).click();
  expect(await edge()).toEqual(normal);
  await page.screenshot({ path: test.info().outputPath("backdrop-dark.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("mist shows a skeleton and softly gains detail without tile boundaries", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.route("https://i.ytimg.com/**", (route) => route.abort());
  await page.route("**/sharp.png", (route) =>
    route.fulfill({
      path: fileURLToPath(new URL("../../assets/images/wallpaper.png", import.meta.url)),
      contentType: "image/png",
    }),
  );
  let finish: (() => Promise<void>) | undefined;
  await page.route("**/api/timey/clip", async (route) => {
    await new Promise<void>((resolve) => {
      finish = async () => {
        await route.fulfill({
          json: {
            url: "/sharp.png",
            kind: "image",
            width: 447,
            height: 447,
            duration: 0,
            complete: true,
          },
        });
        resolve();
      };
    });
  });
  await page.goto("/?mini=timey");
  const search = page.getByRole("combobox", { name: "Search YouTube or paste a link" });
  await search.fill("https://youtu.be/abcdefghijk");
  await search.press("Enter");
  await expect.poll(() => !!finish).toBe(true);
  const now = Date.now();
  await page.clock.install({ time: new Date(now) });
  await page.clock.pauseAt(new Date(now + 1000));
  const skeleton = page.locator(".mist-skeleton");
  await expect(skeleton).toBeVisible();
  await expect(skeleton).toContainText("10:00");
  expect(Number(await skeleton.evaluate((node) => getComputedStyle(node).opacity))).toBeGreaterThan(
    0.8,
  );
  await page.screenshot({ path: test.info().outputPath("skeleton-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: test.info().outputPath("skeleton-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const monitor = await page.context().newCDPSession(page);
  await monitor.send("Performance.enable");
  const baseline = (await monitor.send("Performance.getMetrics")).metrics;
  await finish!();
  const mist = page.locator(".timer-mist"),
    pixels = page.locator(".mist-pixels");
  await expect(mist).toHaveAttribute("data-refining", "");
  const sample = () =>
    pixels.evaluate((node: HTMLCanvasElement) => {
      const data = node.getContext("2d")!.getImageData(0, 0, node.width, node.height).data,
        colours = new Set<number>();
      let transparent = 0;
      for (let offset = 0; offset < data.length; offset += 4) {
        if (!data[offset + 3]) transparent++;
        else colours.add((data[offset] << 16) | (data[offset + 1] << 8) | data[offset + 2]);
      }
      return { colours: colours.size, transparent, bytes: data.length };
    });
  const coarse = await sample();
  expect(coarse.colours).toBeLessThanOrEqual(8 * 8);
  expect(coarse.transparent).toBe(0);
  expect(coarse.bytes).toBeLessThanOrEqual(960 * 540 * 4);
  await page.clock.runFor(180);
  expect((await sample()).colours).toBeGreaterThan(coarse.colours);
  await page.clock.runFor(380);
  await expect(mist).toHaveAttribute("data-refining", "");
  expect((await sample()).transparent).toBe(0);
  expect(Number(await skeleton.evaluate((node) => getComputedStyle(node).opacity))).toBeLessThan(
    0.65,
  );
  await page.screenshot({
    path: test.info().outputPath("media-refining-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: test.info().outputPath("media-refining-mobile.png"),
    fullPage: true,
  });
  await page.clock.runFor(1000);
  await expect(mist).not.toHaveAttribute("data-refining");
  await expect(mist.locator(".mist-grains")).toHaveCSS("animation-play-state", "paused");
  await expect(pixels).toHaveAttribute("width", "0");
  await expect(pixels).toHaveAttribute("height", "0");
  await expect(skeleton).toBeHidden();
  const measured = (await monitor.send("Performance.getMetrics")).metrics;
  console.info(
    "Mist workload, including assertions and captures",
    Object.fromEntries(
      ["ScriptDuration", "TaskDuration"].map((name) => [
        `${name}Ms`,
        1000 *
          (measured.find((item) => item.name === name)!.value -
            baseline.find((item) => item.name === name)!.value),
      ]),
    ),
  );
  await monitor.detach();

  await page.clock.resume();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("group", { name: "Background preview", exact: true }).hover();
  await page.getByRole("button", { name: "Change background", exact: true }).click();
  finish = undefined;
  await search.fill("https://youtu.be/lmnopqrstuv");
  await search.press("Enter");
  await expect.poll(() => !!finish).toBe(true);
  await finish!();
  await expect(
    page.getByRole("group", { name: "Background preview", exact: true }),
  ).toHaveAttribute("data-gentle", "true");
  await expect(mist).not.toHaveAttribute("data-active");
  await expect(pixels).toHaveAttribute("width", "0");
  await expect(mist).not.toHaveAttribute("data-refining");
  expect(errors).toEqual([]);
});

test("background search keeps themed recovery and a usable mobile layout", async ({ page }) => {
  await page.route("**/api/timey/search?*", (route) =>
    route.fulfill({
      status: 503,
      json: {
        detail: "The video search is offline. Try a local file or search again when connected",
      },
    }),
  );
  await page.goto("/?mini=timey");
  const search = page.getByRole("combobox", { name: "Search YouTube or paste a link" });
  await search.fill("quiet forest");
  await search.press("Enter");
  await expect(page.getByRole("alert")).toContainText("Try a local file");
  await page.getByRole("button", { name: "Edit search" }).click();
  await expect(search).toBeFocused();
  await page.screenshot({
    path: test.info().outputPath("media-error-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("alert")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({ path: test.info().outputPath("media-error-mobile.png"), fullPage: true });
});

test("malformed saved data shows a recoverable error instead of reaching a mini", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/plan", (route) => route.fulfill({ json: { ...plan, courses: null } }));
  await page.goto("/?mini=planny");
  await expect(page.getByRole("alert")).toContainText(
    "The server returned unexpected data; try again shortly",
  );
  await expect(page.getByRole("heading", { name: /What if the rest/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("home artwork loads and theme changes leave habitat clocks alone", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Big plans/ })).toBeVisible();
  await expect(page.locator(".mini-card")).toHaveCount(6);
  const residents = await page
    .locator(".mini-card .pal")
    .evaluateAll((cards) => cards.map((card) => card.getAttribute("data-resident")));
  expect(new Set(residents).size).toBe(residents.length);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const card = page.locator('[data-mini="buzzy"]');
  await card.hover();
  await expect(card).toHaveClass(/is-featured/);
  await expect(card.locator(".preview-copy")).toContainText(
    "See deadlines and club events in one calendar",
  );
  const widths = await page
    .locator(".mini-card")
    .evaluateAll((cards) =>
      Object.fromEntries(cards.map((card) => [card.getAttribute("data-mini"), card.clientWidth])),
    );
  expect(widths.buzzy).toBeGreaterThan(widths.planny);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator("svg")).toHaveCount(0);
  const lights = await page
    .locator(".habitat")
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-light")));
  await page.getByRole("button", { name: /App theme/ }).click();
  await expect(page.getByRole("button", { name: /switch to light/ })).toBeVisible();
  expect(
    await page
      .locator(".habitat")
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-light"))),
  ).toEqual(lights);
  const broken = await page
    .locator("img")
    .evaluateAll((nodes: HTMLImageElement[]) =>
      nodes.filter((img) => img.complete && img.naturalWidth === 0).map((img) => img.src),
    );
  expect(broken).toEqual([]);
  expect(errors).toEqual([]);
  const animal = page.getByRole("button", { name: "Gently pat the illustrated Giant otter" });
  await animal.click();
  await expect(page.locator('[data-animal="otter"]')).not.toHaveAttribute("data-action", "listen");
  await page.screenshot({ path: test.info().outputPath("home.png"), fullPage: true });
});

test("course paths remain keyboard-readable and highlight prerequisites without inline SVG", async ({
  page,
}) => {
  await page.goto("/?mini=scrappy");
  await page.getByRole("button", { name: subject.name, exact: true }).click();
  await page.getByText("Requirements and student feedback", { exact: true }).click();
  const nodes = page.locator(".trail-node");
  await expect(nodes).toHaveCount(3);
  const first = page.getByRole("button", { name: /CSSE1001 \/ Introduction/ });
  await first.focus();
  await expect(page.locator(".trail-node.is-muted")).toHaveCount(1);
  await expect(page.locator(".prereq-wording")).toContainText("CSSE1001");
  await expect(page.locator(".trail-node.current")).not.toHaveClass(/is-muted/);
  await expect(page.locator("canvas.trail-links")).toBeVisible();
  await expect(page.locator("svg")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("courses.png"), fullPage: true });
  await page.getByRole("button", { name: "Close course", exact: true }).click();
  await expect(page.getByRole("button", { name: subject.name, exact: true })).toBeFocused();
});

test("Scrappy keeps profile syncing in the background", async ({ page }) => {
  await page.goto("/?mini=scrappy");
  await expect(page.getByText("Catalogue tools", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Add course", exact: true }).click();
  await expect(page.getByRole("link", { name: "View CSSE2002 on UQ" })).toHaveAttribute(
    "href",
    "https://course-profiles.uq.edu.au/current",
  );
  await expect(page.getByRole("button", { name: /View assessments|Read profile/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Plan my assessments" }).click();
  await expect(page.getByText("Software assignment", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /View CSSE2002 .* marks/ })).toBeVisible();
});

test("timer supports keyboard timing, labels, music and corner resizing", async ({ page }) => {
  await page.goto("/?mini=timey");
  const dial = page.getByRole("slider", { name: "Countdown length", exact: true });
  await expect(dial).toHaveAttribute("aria-valuenow", "600");
  await dial.focus();
  await page.keyboard.press("ArrowRight");
  await expect(dial).toHaveAttribute("aria-valuenow", "660");
  for (const [label, seconds] of [
    ["Get-ready time", "45"],
    ["Finishing hold", "15"],
  ]) {
    const gap = page.getByRole("slider", { name: label, exact: true });
    const bounds = await gap.boundingBox();
    await gap.click({ position: { x: bounds!.width * 0.92, y: bounds!.height / 2 } });
    await expect(gap).toHaveAttribute("aria-valuenow", seconds);
  }
  await expect(page.getByRole("button", { name: "Move timer", exact: true })).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Search YouTube or paste a link" })
    .fill("https://www.youtube.com/watch?v=jfKfPfyJRdk");
  await page.keyboard.press("Enter");
  const overlay = page.getByRole("button", { name: "Move timer", exact: true });
  await expect(overlay).toBeVisible();
  await overlay.click();
  await page.getByRole("textbox", { name: "Timer label" }).fill("Focus time");
  await page.getByRole("button", { name: "Music & sound", exact: true }).click();
  await expect(page.getByRole("slider", { name: /Music volume/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await overlay.focus();
  await page.keyboard.press("Home");
  const before = await overlay.boundingBox();
  const grip = page.getByRole("button", { name: "Resize bottom right", exact: true });
  const corner = await grip.boundingBox();
  await page.mouse.move(corner!.x + corner!.width / 2, corner!.y + corner!.height / 2);
  await page.mouse.down();
  await page.mouse.move(corner!.x + 45, corner!.y + 30, { steps: 8 });
  await page.mouse.up();
  const after = await overlay.boundingBox();
  expect(after!.width).toBeGreaterThan(before!.width);
  expect(after!.height).toBeGreaterThan(before!.height);
  await expect(page.locator("svg")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("timey.png"), fullPage: true });
});

test("UQ window supports labelled input, retry, cancellation and verified completion", async ({
  page,
}) => {
  let attempts = 0;
  const closed = new Set<number>();
  const actions: unknown[] = [];
  await page.routeWebSocket("**/api/session/window", (socket) => {
    const attempt = ++attempts;
    socket.onClose(() => {
      closed.add(attempt);
    });
    if (attempts === 1) {
      socket.send(JSON.stringify({ error: "UQ is busy; try again" }));
      return;
    }
    socket.send(
      JSON.stringify({
        image: pixel.toString("base64"),
        host: "auth.uq.edu.au",
        title: "UQ Authenticate",
        text: "Sign in",
        width: 760,
        height: 760,
        controls: [
          {
            id: "username",
            type: "text",
            label: "Username",
            x: 100,
            y: 100,
            width: 400,
            height: 40,
            disabled: false,
            checked: false,
            options: [],
          },
          {
            id: "login",
            type: "button",
            label: "Log in",
            x: 100,
            y: 170,
            width: 200,
            height: 40,
            disabled: false,
            checked: false,
            options: [],
          },
        ],
      }),
    );
    socket.onMessage((message) => {
      const action = JSON.parse(String(message));
      actions.push(action);
      if (action.kind === "click")
        socket.send(JSON.stringify({ user: "s1234567@student.uq.edu.au" }));
    });
  });
  await page.goto("/?mini=auth");
  await page.getByRole("button", { name: "Check UQ access" }).click();
  await expect(page.getByRole("alert")).toContainText("UQ is busy");
  await page.getByRole("button", { name: "Check UQ access" }).click();
  await page.getByRole("textbox", { name: "Username", exact: true }).fill("s1234567");
  await expect
    .poll(() => actions)
    .toContainEqual({ kind: "fill", id: "username", value: "s1234567" });
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect.poll(() => closed.has(2)).toBe(true);
  await expect(page.getByRole("region", { name: "UQ sign-in" })).toHaveCount(0);
  await page.getByRole("button", { name: "Check UQ access" }).click();
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByText("Signed in as s1234567@student.uq.edu.au")).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("button", { name: "Check UQ access" })).toBeVisible();
});

test("guests open ordinary minis while only Eventy asks for UQ", async ({ page }) => {
  const privateRequests: string[] = [];
  await page.route("**/api/session", (route) =>
    route.fulfill({ json: { user: "", hosted: true, workspace: "guest:" + "a".repeat(64) } }),
  );
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (["/api/plan", "/api/minis/timey"].includes(path)) privateRequests.push(path);
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Big plans/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Check UQ access" })).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("home-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "Timey", exact: true }).click();
  await expect(page.getByRole("form", { name: "Timer studio" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Check UQ access" })).toHaveCount(0);
  await expect(page).toHaveURL(/\?m=timey$/);
  await expect(page.getByRole("heading", { name: "Timey", exact: true })).toBeVisible();
  expect(privateRequests).not.toContain("/api/plan");
  for (const name of ["Scrappy", "Planny", "Buzzy", "Clubby"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByRole("heading", { name, exact: true, level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Check UQ access" })).toHaveCount(0);
    await expect(page.getByText("Opening your workspace…")).toHaveCount(0);
    await expect(page.getByText("Opening your saved plan…")).toHaveCount(0);
  }
  expect(privateRequests).toContain("/api/plan");
  await page.getByRole("button", { name: "Event", exact: true }).click();
  await expect(page.getByRole("button", { name: "Check UQ access" })).toBeVisible();
  await page.getByRole("link", { name: "minis home" }).click();
  await expect(page.getByRole("heading", { name: /Big plans/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({ path: test.info().outputPath("home-mobile.png"), fullPage: true });
});

test("navigation keeps the page visible while an editor module loads", async ({ page }) => {
  let release = () => {};
  const ready = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/src/timey/index.tsx*", async (route) => {
    await ready;
    await route.continue();
  });
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "Timey", exact: true }).click();
    await expect(page).toHaveURL(/\?m=timey$/);
    await expect(page.getByRole("heading", { name: /Big plans/ })).toBeVisible();
    await expect(page.getByText("Opening Timey…", { exact: true })).toHaveCount(0);
  } finally {
    release();
  }
  await expect(page.getByRole("form", { name: "Timer studio" })).toBeVisible();
});

test("guest timer edits survive reload and Eventy sign-in", async ({ page }) => {
  let user = "";
  const workspace = "guest:" + "a".repeat(64);
  await page.route("**/api/session", (route) =>
    route.fulfill({ json: { user, hosted: true, workspace } }),
  );
  await page.route("**/api/session/login", async (route) => {
    user = "student@student.uq.edu.au";
    await route.fulfill({ json: { user, hosted: true, workspace } });
  });
  await page.goto("/?m=timey");
  const search = page.getByRole("combobox", { name: "Search YouTube or paste a link" });
  await search.fill("https://www.youtube.com/watch?v=jfKfPfyJRdk");
  await search.press("Enter");
  await page.getByRole("button", { name: "Move timer" }).click();
  await page.getByPlaceholder("Add a label").fill("Keep this session");
  await page.reload();
  await expect(page.getByRole("form", { name: "Timer studio" })).toBeVisible();
  await page.getByRole("button", { name: "Event", exact: true }).click();
  await expect(page.getByRole("button", { name: "Check UQ access" })).toBeVisible();
  await page.getByRole("button", { name: "Check UQ access" }).click();
  await expect(page.getByText("Signed in as " + user)).toBeVisible();
  await page.getByRole("button", { name: "Timey", exact: true }).click();
  await page.getByRole("button", { name: "Move timer" }).click();
  await expect(page.getByPlaceholder("Add a label")).toHaveValue("Keep this session");
});

test("workspace and plan failures recover without signing in", async ({ page }) => {
  let sessions = 0,
    plans = 0;
  await page.route("**/api/session", (route) =>
    route.fulfill(
      ++sessions === 1
        ? { status: 503, json: { error: "Workspace connection interrupted" } }
        : { json: { user: "", hosted: true, workspace: "guest:" + "c".repeat(64) } },
    ),
  );
  await page.route("**/api/plan", (route) =>
    route.fulfill(
      ++plans === 1
        ? { status: 503, json: { error: "Plan connection interrupted" } }
        : { json: plan },
    ),
  );
  await page.goto("/?m=planny");
  await expect(page.getByRole("alert")).toContainText("Workspace connection interrupted");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Plan connection interrupted");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("Opening your saved plan…")).toHaveCount(0);
  expect(plans).toBe(2);
  await expect(page.getByRole("button", { name: "Check UQ access" })).toHaveCount(0);
});

test("our UQ form renders before the remote page and submits without a screenshot", async ({
  page,
}) => {
  const actions: unknown[] = [];
  let ready: (() => void) | undefined;
  await page.route("**/api/session", (route) =>
    route.fulfill({ json: { user: "", hosted: true, workspace: "guest:" + "a".repeat(64) } }),
  );
  await page.routeWebSocket("**/api/session/window", (socket) => {
    ready = () =>
      socket.send(
        JSON.stringify({
          mode: "form",
          image: "",
          host: "auth.uq.edu.au",
          title: "UQ Authenticate",
          text: "",
          width: 760,
          height: 760,
          controls: [
            ["name", "text"],
            ["secret", "password"],
            ["go", "submit"],
          ].map(([id, type]) => ({
            id,
            type,
            label: id,
            x: 0,
            y: 0,
            width: 100,
            height: 40,
            disabled: false,
            checked: false,
            options: [],
          })),
        }),
      );
    socket.onMessage((raw) => {
      const message = JSON.parse(String(raw));
      actions.push(message);
      if (message.kind === "submit")
        socket.send(JSON.stringify({ user: "s1234567@student.uq.edu.au" }));
    });
  });
  await page.goto("/?m=event");
  await page.getByRole("button", { name: "Check UQ access" }).click();
  await expect(page.getByLabel("UQ username")).toBeVisible();
  await page.getByLabel("UQ username").fill("s1234567");
  await page.getByLabel("Password", { exact: true }).fill("test-only");
  expect(actions).toEqual([]);
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeDisabled();
  await expect.poll(() => ready !== undefined).toBe(true);
  ready!();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  await expect(page.locator(".portal-screen")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("login-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({ path: test.info().outputPath("login-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect
    .poll(() => actions)
    .toEqual([{ kind: "submit", id: "go", fields: { name: "s1234567", secret: "test-only" } }]);
  await expect(page.getByRole("region", { name: "UQ sign-in" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Event", exact: true })).toBeVisible();
});

test("mobile and zoom layouts retain keyboard access without page overflow", async ({ page }) => {
  for (const width of [390, 720]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/?mini=timey");
    await expect(page.getByRole("slider", { name: "Countdown length", exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - innerWidth),
    ).toBeLessThanOrEqual(1);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to your tools" })).toBeFocused();
  }
});

test("country flags wave with habitat wind and stop for reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/?m=scrappy");
  await page.getByRole("button", { name: "My story: Numbat", exact: true }).click();
  let cloth = page
    .getByRole("dialog", { name: "Numbat's story", exact: true })
    .locator('.flag-cloth[data-live="true"]');
  await expect(cloth).toHaveCSS("animation-name", "flag-wave");
  await expect(cloth).toHaveCSS("animation-duration", "3.84s");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await page.getByRole("button", { name: "My story: Numbat", exact: true }).click();
  cloth = page.getByRole("dialog", { name: "Numbat's story", exact: true }).locator(".flag-cloth");
  await expect(cloth).not.toHaveAttribute("data-live");
  await expect(cloth).toHaveCSS("animation-name", "none");
});

test("story clocks tick without repeated controls and light sleepers complain", async ({
  page,
}) => {
  await page.clock.install();
  await page.goto("/?m=planny");
  const resident = page.locator(".habitat-page [data-animal]");
  await page.getByRole("button", { name: "My story: Giant otter", exact: true }).click();
  const story = page.getByRole("dialog", { name: "Giant otter's story", exact: true });
  await expect(story.getByRole("heading", { name: "Giant otter" })).toHaveCount(0);
  await expect(story.getByText(/Habitat weather|Choose a resident/)).toHaveCount(0);
  await expect(story.getByRole("link", { name: "Meet my protectors" })).toBeVisible();
  const closeBox = await story.getByRole("button", { name: "Close my story" }).boundingBox(),
    badge = story.locator(".status-badge"),
    badgeBox = await badge.boundingBox();
  expect(closeBox).not.toBeNull();
  expect(badgeBox).not.toBeNull();
  expect(badgeBox!.y).toBeGreaterThanOrEqual(closeBox!.y + closeBox!.height);
  const clock = story.locator(".home-clock"),
    initial = await clock.textContent();
  await page.clock.fastForward(1001);
  await expect(clock).not.toHaveText(initial!);
  await page.keyboard.press("Escape");
  await page.keyboard.press("Shift");
  await page.clock.fastForward(120_001);
  await expect(resident).toHaveAttribute("data-action", "sleep");
  await page.keyboard.press("Shift");
  await expect(resident).toHaveAttribute("data-action", "wake");
  await expect(page.locator(".habitat-clearing .animal-call")).toHaveText("Ughhh… you woke me up");
  await page.clock.fastForward(1801);
  await expect(resident).not.toHaveAttribute("data-action", "wake");
});

test("one wildlife canvas works without eval and yields to reduced motion", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.route("http://127.0.0.1:5174/", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      // Vite's inline refresh preamble stays usable while dynamic evaluation is forbidden
      headers: {
        ...response.headers(),
        "Content-Security-Policy": "script-src 'self' 'unsafe-inline'",
      },
    });
  });
  await page.goto("/");
  const canvas = page.locator(".wildlife-canvas");
  await expect(canvas).toHaveCount(1);
  await expect(page.locator("[data-rendered=true]").first()).toBeVisible();
  expect(
    await canvas.evaluate((node: HTMLCanvasElement) => node.width * node.height),
  ).toBeLessThanOrEqual(4_000_000);
  await page.setViewportSize({ width: 390, height: 840 });
  expect(
    await page.locator(".sidebar").evaluate((node) => node.getBoundingClientRect().width),
  ).toBe(390);
  await expect(page.locator("[data-rendered=true]").first()).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(canvas).toHaveCount(0);
  await expect(page.locator("[data-rendered=true]")).toHaveCount(0);
  await expect(page.locator(".cartoon-still").first()).toHaveCSS("opacity", "1");
  expect(errors).toEqual([]);
});
