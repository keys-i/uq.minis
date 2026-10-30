// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { Timey } from "../src/timey/index.tsx";
import { Canvas } from "../src/timey/canvas.tsx";
import { json } from "./fixtures.ts";

const dialog = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
const close = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
const popover = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "hidePopover");

const first = "https://www.youtube.com/watch?v=abcdefghijk";
const second = "https://www.youtube.com/watch?v=lmnopqrstuv";
const clip = (source: string) => ({
  url: source === first ? "/download/first" : "/download/second",
  title: "Backdrop",
  kind: "video",
  width: 960,
  height: 540,
  duration: 20,
  complete: true,
});

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "hidePopover", {
    configurable: true,
    value: vi.fn(),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = true;
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = false;
    },
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL() {
        return "blob:timer";
      }
      static revokeObjectURL() {}
    },
  );
});
afterEach(() => {
  cleanup();
  if (dialog) Object.defineProperty(HTMLDialogElement.prototype, "showModal", dialog);
  else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  if (close) Object.defineProperty(HTMLDialogElement.prototype, "close", close);
  else Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  if (popover) Object.defineProperty(HTMLElement.prototype, "hidePopover", popover);
  else Reflect.deleteProperty(HTMLElement.prototype, "hidePopover");
});

test("the editor accepts edits before the server settings arrive", async () => {
  let finish: (response: Response) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      path === "/api/timey/youtube?status=1"
        ? Promise.resolve(json({ connected: true, open: false }))
        : new Promise<Response>((resolve) => {
            finish = resolve;
          }),
    ),
  );
  const { useDraft } = await import("../src/timey/draft.ts");
  render(<Timey />);
  expect(screen.getByRole("form", { name: "Timer studio" })).toBeVisible();
  expect(
    await screen.findByRole("combobox", { name: "Search YouTube or paste a link" }),
  ).toBeEnabled();
  fireEvent.keyDown(screen.getByRole("slider", { name: "Countdown length" }), {
    key: "ArrowRight",
  });
  const length = useDraft.getState().values.length;
  expect(length).toBeTruthy();
  await act(async () =>
    finish(json({ fields: [{ name: "length", label: "Length", value: "10m" }] })),
  );
  expect(useDraft.getState().values.length).toBe(length);
});

test("workspace preparation keeps edits made while identity loads", async () => {
  const { useSession } = await import("../src/shared/session.ts");
  const { useDraft } = await import("../src/timey/draft.ts");
  useSession.setState({ user: null, hosted: null, workspace: null });
  const workspace = "guest:" + "b".repeat(64);
  sessionStorage.setItem(
    `minis-timey-draft:${workspace}`,
    JSON.stringify({
      values: { length: "20m", label: "Saved label" },
      phase: "edit",
      movie: null,
    }),
  );
  useDraft.setState({ values: { length: "15m" } });
  useSession.setState({ user: "", hosted: true, workspace });
  expect(useDraft.getState().values).toEqual({ length: "15m", label: "Saved label" });
});

test("a cancelled playback request does not turn a cache swap into a broken backdrop", async () => {
  const user = userEvent.setup(),
    onError = vi.fn();
  const play = vi
    .spyOn(HTMLMediaElement.prototype, "play")
    .mockRejectedValue(new DOMException("Source changed", "AbortError"));
  render(
    <Canvas
      clip={{ ...clip(first), kind: "video", source: first, start: 0 }}
      image=""
      values={{ length: "10m" }}
      change={vi.fn()}
      onError={onError}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Play preview" }));
  expect(onError).not.toHaveBeenCalled();
  play.mockRejectedValue(new DOMException("Unsupported video", "NotSupportedError"));
  await user.click(screen.getByRole("button", { name: "Play preview" }));
  expect(onError).toHaveBeenCalledTimes(1);
});

test("a blocked YouTube download recovers through a file without losing edits", async () => {
  const user = userEvent.setup();
  const { useDraft } = await import("../src/timey/draft.ts");
  useDraft.setState({ values: { source: first, length: "10m", label: "Keep me" } });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path === "/api/timey/youtube?status=1") return json({ connected: true, open: false });
      if (path === "/api/minis/timey") return json({ fields: [] });
      if (path === "/api/timey/preview") return new Response(new Blob(["timer"]));
      if (path.startsWith("/api/timey/source?"))
        return json({ source: "upload:recovered", title: "Backdrop" });
      if (path === "/api/timey/clip" && options?.body instanceof FormData) {
        if (options.body.get("source") === first)
          return json(
            { error: "YouTube download failed: Sign in to confirm you’re not a bot" },
            400,
          );
        return json(clip(second));
      }
      throw new Error(`Unexpected request: ${path}`);
    }),
  );
  render(<Timey />);
  await screen.findByText(/YouTube is blocking this download/);
  expect(screen.queryByText(/cookies-from-browser|not a bot/)).not.toBeInTheDocument();
  const picker = screen.getByLabelText("Upload video or image");
  const opened = vi.spyOn(picker, "click");
  await user.click(screen.getByRole("button", { name: "Add a file" }));
  expect(opened).toHaveBeenCalledOnce();
  await user.upload(picker, new File(["video"], "backdrop.mp4", { type: "video/mp4" }));
  await waitFor(() => expect(useDraft.getState().values.source).toBe("upload:recovered"));
  await screen.findByLabelText("Cached backdrop preview");
  expect(screen.queryByText(/YouTube is blocking this download/)).not.toBeInTheDocument();
  expect(useDraft.getState().values.label).toBe("Keep me");
});

test.each(["ready", "failed", "cancelled"] as const)(
  "keeps the accepted backdrop while replacement is %s",
  async (outcome) => {
    const user = userEvent.setup();
    let signal: AbortSignal | null | undefined;
    let finish: (response: Response) => void = () => {
      throw new Error("The replacement was never requested");
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string, options?: RequestInit) => {
        if (path === "/api/timey/youtube?status=1") return json({ connected: true, open: false });
        if (path === "/api/minis/timey")
          return json({ fields: [{ name: "length", label: "Length", value: "10m" }] });
        if (path === "/api/timey/preview")
          return new Response(new Blob(["timer"], { type: "image/png" }));
        if (path === "/api/timey/clip") {
          if (!(options?.body instanceof FormData)) throw new Error("Expected a backdrop form");
          const source = options.body.get("source");
          if (source === second) {
            signal = options.signal;
            return new Promise<Response>((resolve) => {
              finish = resolve;
            });
          }
          return json(clip(first));
        }
        throw new Error(`Unexpected request: ${path}`);
      }),
    );
    render(<Timey />);
    await user.type(
      await screen.findByRole("combobox", { name: "Search YouTube or paste a link" }),
      first + "{Enter}",
    );
    const player = await screen.findByLabelText("Cached backdrop preview");
    expect(player).toHaveAttribute("src", "/download/first");
    await user.click(screen.getByRole("button", { name: "Change background" }));
    const search = screen.getByRole("combobox", { name: "Search YouTube or paste a link" });
    await user.clear(search);
    await user.type(search, second + "{Enter}");
    await screen.findByText("Caching your backdrop…");
    expect(screen.getByLabelText("Cached backdrop preview")).toHaveAttribute(
      "src",
      "/download/first",
    );
    if (outcome === "cancelled") {
      await user.click(screen.getByRole("button", { name: "Cancel" }));
      expect(signal?.aborted).toBe(true);
    }
    await act(async () =>
      finish(
        outcome === "failed"
          ? json({ detail: "The video could not be prepared" }, 503)
          : json(clip(second)),
      ),
    );
    if (outcome === "failed") await screen.findByText("The video could not be prepared");
    await waitFor(() =>
      expect(screen.getByLabelText("Cached backdrop preview")).toHaveAttribute(
        "src",
        outcome === "ready" ? "/download/second" : "/download/first",
      ),
    );
  },
);

test("preview, final video and guest saving keep one editable project", async () => {
  const { useDraft } = await import("../src/timey/draft.ts"),
    { useSession } = await import("../src/shared/session.ts");
  useSession.getState().complete("");
  const actions: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path === "/api/timey/youtube?status=1") return json({ connected: true, open: false });
      if (path === "/api/minis/timey" && !options?.body)
        return json({ fields: [{ name: "length", label: "Length", value: "10m" }] });
      if (path === "/api/timey/clip") return json({ ...clip(first), width: 3840, height: 2160 });
      if (path === "/api/timey/preview") {
        expect(options?.body).toBeInstanceOf(FormData);
        const form = options?.body as FormData;
        expect(Number(form.get("width"))).toBeLessThanOrEqual(960);
        expect(Number(form.get("height"))).toBeLessThanOrEqual(540);
        return new Response("timer");
      }
      if (path === "/api/minis/timey" && options?.body instanceof FormData) {
        const action = String(options.body.get("action"));
        actions.push(action);
        return json({
          result: "Ready",
          downloads: [{ name: "timer.mp4", url: `/download/${action}` }],
        });
      }
      if (path === "/api/session/login") return json({ user: "student@student.uq.edu.au" });
      throw new Error(`Unexpected request: ${path}`);
    }),
  );
  const user = userEvent.setup();
  render(<Timey />);
  await user.type(
    await screen.findByRole("combobox", { name: "Search YouTube or paste a link" }),
    first + "{Enter}",
  );
  fireEvent.click(await screen.findByRole("button", { name: "Move timer" }));
  await user.type(screen.getByPlaceholderText("Add a label"), "Focus session");
  await user.click(screen.getByRole("button", { name: "Watch preview" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Cached backdrop preview")).toHaveAttribute(
      "src",
      "/download/sample",
    ),
  );
  expect(screen.queryByRole("group", { name: "Timer look" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Make video" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Cached backdrop preview")).toHaveAttribute(
      "src",
      "/download/render",
    ),
  );
  await user.click(screen.getByRole("button", { name: "Save video" }));
  expect(await screen.findByRole("button", { name: "Save to this device" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Focus session");
  expect(useDraft.getState().values.label).toBe("Focus session");
  await user.click(screen.getByRole("button", { name: "Close save" }));
  await user.click(screen.getByRole("button", { name: "Edit video" }));
  fireEvent.click(await screen.findByRole("button", { name: "Move timer" }));
  expect(screen.getByPlaceholderText("Add a label")).toHaveValue("Focus session");
  expect(actions).toEqual(["sample", "render"]);
});

test("quality changes rebuild the watched video and preserve its draft", async () => {
  const { useDraft } = await import("../src/timey/draft.ts");
  useDraft.setState({
    values: { source: first, length: "10m", height: "720", fps: "30", label: "Keep me" },
    phase: "video",
    movie: {
      phase: "video",
      quality: "720:30",
      data: { result: "Ready", downloads: [{ name: "timer.mp4", url: "/download/old" }] },
    },
  });
  const profiles: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path === "/api/timey/youtube?status=1") return json({ connected: true, open: false });
      if (path === "/api/minis/timey" && !options?.body) return json({ fields: [] });
      if (path === "/api/minis/timey" && options?.body instanceof FormData) {
        profiles.push(`${options.body.get("height")}:${options.body.get("fps")}`);
        return json({ result: "Ready", downloads: [{ name: "timer.mp4", url: "/download/new" }] });
      }
      throw new Error(`Unexpected request: ${path}`);
    }),
  );
  render(<Timey />);
  await screen.findByRole("button", { name: "Save video" });
  act(() =>
    useDraft.setState((draft) => ({ values: { ...draft.values, height: "480", fps: "60" } })),
  );
  expect(screen.getByRole("button", { name: "Save video" })).toBeDisabled();
  await waitFor(() => expect(useDraft.getState().movie?.quality).toBe("480:60"));
  expect(profiles).toEqual(["480:60"]);
  expect(useDraft.getState().values.label).toBe("Keep me");
  expect(screen.getByLabelText("Cached backdrop preview")).toHaveAttribute("src", "/download/new");
});

test("YouTube uses the real provider window, saves once and closes its connection", async () => {
  const { Connection } = await import("../src/timey/connect.tsx");
  const user = userEvent.setup(),
    ready = vi.fn();
  const actions: string[] = [];
  let filled = false;
  const frame = {
    mode: "window",
    image: "eA==",
    host: "accounts.google.com",
    title: "Google sign-in",
    text: "",
    width: 760,
    height: 760,
    controls: [
      {
        id: "email",
        type: "email",
        label: "Google email",
        x: 10,
        y: 10,
        width: 200,
        height: 44,
        disabled: false,
        checked: false,
        options: [],
      },
    ],
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_path, init) => {
    if (!init?.body && String(_path).includes("status=1"))
      return json({ connected: false, open: false });
    const kind = init?.body ? JSON.parse(String(init.body)).kind : "view";
    actions.push(kind);
    if (kind === "fill") filled = true;
    return json(
      kind === "view" && filled
        ? { connected: true }
        : kind === "cancel"
          ? { connected: true, open: false }
          : frame,
    );
  });
  render(
    <Connection ready={ready}>
      <p>Timer ready</p>
    </Connection>,
  );
  const gate = await screen.findByRole("region", { name: "Connect Google" });
  expect(gate).toBeVisible();
  expect(screen.queryByText("Timer ready")).not.toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Connect Google" }));
  expect(document.querySelector(".timer-google-panel .portal-window")).not.toBeNull();
  await screen.findByLabelText("Google email");
  expect(document.querySelector(".portal-screen > img")).toHaveAttribute(
    "src",
    "data:image/png;base64,eA==",
  );
  await user.type(screen.getByLabelText("Google email"), "test-only@example.invalid");
  await waitFor(() => expect(ready).toHaveBeenCalledOnce(), { timeout: 3000 });
  expect(screen.getByText("Timer ready")).toBeVisible();
  expect(screen.queryByRole("region", { name: "Connect Google" })).not.toBeInTheDocument();
  expect(actions.filter((kind) => kind === "open")).toHaveLength(1);
  expect(actions).not.toContain("finish");
  expect(actions).toContain("cancel");
  expect(document.querySelector("dialog")).toBeNull();
});

test("Google connection failures open as friendly recovery inside the panel", async () => {
  const { Connection } = await import("../src/timey/connect.tsx");
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(json({ error: "OAuthError: invalid_grant from upstream trace 43" }, 503)),
  );
  render(
    <Connection ready={vi.fn()}>
      <p>Timer ready</p>
    </Connection>,
  );
  const alert = await screen.findByRole("alert");
  expect(alert.closest(".timer-google-panel")).not.toBeNull();
  expect(alert).toHaveTextContent("Google didn’t connect");
  expect(alert).toHaveTextContent(
    "Google couldn’t connect just now. Your timer is safe, so you can try again",
  );
  expect(screen.queryByText(/invalid_grant|upstream trace/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
