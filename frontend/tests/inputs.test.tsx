// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { Timey } from "../src/timey/index.tsx";
import { Look } from "../src/timey/look.tsx";
import { Sound } from "../src/timey/sound.tsx";
import { importMedia } from "../src/timey/media.ts";
import { Suggestions } from "../src/timey/suggest.tsx";
import { json } from "./fixtures.ts";

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
});
afterEach(cleanup);

test("suggestions ignore superseded queries and select with the keyboard", async () => {
  const user = userEvent.setup(),
    choose = vi.fn();
  let signal: AbortSignal | null | undefined;
  let finish: (response: Response) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path.includes("query=super")) {
        signal = options?.signal;
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      }
      return json({ suggestions: ["mario music", "mario gameplay"] });
    }),
  );
  function Search() {
    const [query, setQuery] = React.useState("super");
    return (
      <div>
        <input
          type="search"
          role="combobox"
          aria-label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Suggestions query={query} choose={choose} />
      </div>
    );
  }
  render(<Search />);
  await waitFor(() => expect(signal).toBeDefined());
  const input = screen.getByRole("combobox", { name: "Search" });
  await user.clear(input);
  await user.type(input, "mario");
  await screen.findByRole("option", { name: "mario music" });
  expect(signal?.aborted).toBe(true);
  await act(async () => finish(json({ suggestions: ["old result"] })));
  expect(screen.queryByRole("option", { name: "old result" })).not.toBeInTheDocument();
  await user.keyboard("{ArrowDown}{Enter}");
  expect(choose).toHaveBeenCalledWith("mario music");
  expect(input).toHaveAttribute("aria-expanded", "false");
});

test("pending font suggestions cannot cancel an upload", async () => {
  vi.useFakeTimers();
  const change = vi.fn();
  let signal: AbortSignal | null | undefined;
  let finish: (response: Response) => void = () => {};
  const fetch = vi.fn(async (_path: string, options?: RequestInit) => {
    signal = options?.signal;
    return new Promise<Response>((resolve) => {
      finish = resolve;
    });
  });
  vi.stubGlobal("fetch", fetch);
  render(<Look values={{}} change={change} />);
  fireEvent.change(screen.getByRole("searchbox", { name: "Search any font" }), {
    target: { value: "hand" },
  });
  fireEvent.change(screen.getByLabelText("Upload font"), {
    target: { files: [new File(["font"], "Hand.woff2", { type: "font/woff2" })] },
  });
  await act(async () => vi.advanceTimersByTimeAsync(250));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(signal?.aborted).toBe(false);
  await act(async () => finish(json({ source: "upload:hand", title: "Hand" })));
  expect(change).toHaveBeenCalledWith({ font: "upload:hand" });
});

test("font upload and pasted Google links use the same font selection", async () => {
  const user = userEvent.setup(),
    change = vi.fn();
  const fetch = vi.fn(async () => json({ source: "upload:font", title: "Hand.woff2" }));
  vi.stubGlobal("fetch", fetch);
  render(<Look values={{}} change={change} />);
  const file = new File(["font"], "Hand.woff2", { type: "font/woff2" });
  await user.upload(screen.getByLabelText("Upload font"), file);
  await waitFor(() => expect(change).toHaveBeenCalledWith({ font: "upload:font" }));
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("font=on"),
    expect.objectContaining({ body: file }),
  );
  await user.click(screen.getByRole("searchbox", { name: "Search any font" }));
  await user.paste("https://fonts.google.com/specimen/Patrick+Hand");
  expect(change).toHaveBeenLastCalledWith({
    font: "https://fonts.google.com/specimen/Patrick+Hand",
  });
});

test("music accepts pasted audio files and reports actionable upload errors in place", async () => {
  const change = vi.fn(),
    fetch = vi.fn(async () => json({ source: "upload:music", title: "song.aiff" }));
  vi.stubGlobal("fetch", fetch);
  render(<Sound values={{}} change={change} background={{ current: null }} onListen={() => {}} />);
  const file = new File(["audio"], "song.aiff", { type: "audio/aiff" });
  const clipboard = { files: Object.assign([file], { item: () => file }), getData: () => "" };
  fireEvent.paste(screen.getByRole("combobox", { name: "Search music or paste a link" }), {
    clipboardData: clipboard,
  });
  await waitFor(() => expect(change).toHaveBeenCalledWith({ music: "upload:music" }));
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("audio=on"),
    expect.objectContaining({ body: file }),
  );
  fetch.mockImplementation(async () =>
    json({ detail: "This file has no audio track. Choose a recording with sound" }, 400),
  );
  fireEvent.paste(screen.getByRole("combobox", { name: "Search music or paste a link" }), {
    clipboardData: clipboard,
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose a recording with sound");
  expect(screen.getByRole("button", { name: "Choose a file" })).toBeInTheDocument();
});

test("clearing a pending music search cancels its busy state", async () => {
  const user = userEvent.setup();
  let signal: AbortSignal | null | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      if (path.startsWith("/api/timey/search")) {
        signal = options?.signal;
        return new Promise<Response>(() => {});
      }
      return json({ suggestions: [] });
    }),
  );
  render(<Sound values={{}} change={vi.fn()} background={{ current: null }} onListen={() => {}} />);
  const search = screen.getByRole("combobox", { name: "Search music or paste a link" });
  await user.type(search, "forest{Enter}");
  await waitFor(() => expect(screen.getAllByText("Finding music…")).toHaveLength(2));
  await user.clear(search);
  await user.type(search, "{Enter}");
  expect(signal?.aborted).toBe(true);
  expect(screen.queryAllByText("Finding music…")).toHaveLength(0);
});

test("direct file links are fetched through browser CORS and uploaded as files", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(async (path, options) => {
    if (String(path).startsWith("https://media.example/"))
      return new Response("audio", { headers: { "Content-Type": "audio/flac" } });
    expect(options?.body).toBeInstanceOf(File);
    return json({ source: "upload:track", title: "recording.flac" });
  });
  vi.stubGlobal("fetch", fetch);
  await expect(
    importMedia("https://media.example/recording.flac", "music", new AbortController().signal),
  ).resolves.toMatchObject({ source: "upload:track" });
  expect(fetch).toHaveBeenCalledWith(
    "https://media.example/recording.flac",
    expect.objectContaining({ credentials: "omit", referrerPolicy: "no-referrer" }),
  );
  fetch.mockRejectedValue(new TypeError("CORS blocked"));
  await expect(
    importMedia("https://media.example/recording.flac", "music", new AbortController().signal),
  ).rejects.toThrow("Download it, then drop or paste");
});

test.each(["paste", "drop"])(
  "background %s imports media and releases its listener",
  async (action) => {
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
          return "blob:picture";
        }
        static revokeObjectURL() {}
      },
    );
    const fetch = vi.fn<typeof globalThis.fetch>(async (path) => {
      if (path === "/api/session") return json({ user: "" });
      if (path === "/api/timey/youtube?status=1") return json({ connected: true, open: false });
      if (path === "https://media.example/photo.heic")
        return new Response("photo", { headers: { "Content-Type": "image/heic" } });
      if (path === "/api/minis/timey")
        return json({ fields: [{ name: "length", label: "Length", value: "10m" }] });
      if (String(path).startsWith("/api/timey/source"))
        return json({ source: "upload:picture", title: "photo.heic" });
      if (path === "/api/timey/clip")
        return json({
          url: "/download/picture",
          kind: "image",
          width: 32,
          height: 24,
          duration: 0,
          complete: true,
        });
      if (path === "/api/timey/preview") return new Response("preview");
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetch);
    const view = render(<Timey />);
    await screen.findByRole("combobox", { name: "Search YouTube or paste a link" });
    const file = new File(["photo"], "photo.heic", { type: "image/heic" });
    const clipboardData = { files: Object.assign([file], { item: () => file }), getData: () => "" };
    if (action === "paste") fireEvent.paste(document.body, { clipboardData });
    else
      fireEvent.drop(screen.getByRole("group", { name: "Background preview" }), {
        dataTransfer: {
          files: [],
          types: ["text/uri-list"],
          getData: () => "https://media.example/photo.heic",
        },
      });
    expect(await screen.findByAltText("Your background")).toHaveAttribute(
      "src",
      "/download/picture",
    );
    fireEvent.error(screen.getByAltText("Your background"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try preparing it again");
    expect(screen.getByRole("group", { name: "Background preview" })).not.toHaveAttribute(
      "data-misty",
    );
    view.unmount();
    const requests = fetch.mock.calls.length;
    fireEvent.paste(document.body, { clipboardData });
    expect(fetch).toHaveBeenCalledTimes(requests);
  },
);

test("cancelling music stops preparation and ignores its late response", async () => {
  const user = userEvent.setup();
  let signal: AbortSignal | null | undefined;
  let finish: (response: Response) => void = () => {
    throw new Error("Music did not start preparing");
  };
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof globalThis.fetch>(async (_path, options) => {
      signal = options?.signal;
      return new Promise<Response>((resolve) => {
        finish = resolve;
      });
    }),
  );
  function Studio() {
    const [values, setValues] = React.useState({ music: "upload:music" });
    return (
      <Sound
        values={values}
        change={(patch) => setValues((old) => ({ ...old, ...patch }))}
        background={{ current: null }}
        onListen={() => {}}
      />
    );
  }
  render(<Studio />);
  await user.click(await screen.findByRole("button", { name: "Cancel" }));
  expect(signal?.aborted).toBe(true);
  await act(async () =>
    finish(
      json({
        url: "/download/music",
        kind: "audio",
        width: 2,
        height: 2,
        duration: 10,
        complete: true,
      }),
    ),
  );
  expect(screen.queryByRole("button", { name: "Play music preview" })).not.toBeInTheDocument();
});
