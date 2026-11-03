// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { Portal } from "../src/shared/portal.tsx";
import { json } from "./fixtures.ts";

afterEach(cleanup);

test("UQ form retains early input, submits once and clears its password", async () => {
  const sent: object[] = [];
  const connections: Socket[] = [];
  const connection = () => connections.at(-1)!;
  class Socket {
    static OPEN = 1;
    readyState = 1;
    bufferedAmount = 0;
    onopen = () => {};
    onmessage = (_event: { data: string }) => {};
    onerror = () => {};
    onclose = () => {};
    close = vi.fn();
    constructor() {
      connections.push(this);
    }
    send(value: string) {
      sent.push(JSON.parse(value));
    }
  }
  vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const complete = vi.fn(),
    user = userEvent.setup();
  const mounted = render(
    <Portal path="/api/session/window" complete={complete} fail={vi.fn()} cancel={vi.fn()} />,
  );
  await user.type(screen.getByLabelText("UQ username"), "s1234567");
  await user.type(screen.getByLabelText("Password"), "test-only");
  expect(sent).toEqual([]);
  const packet = {
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
  };
  await act(async () => connection().onmessage({ data: JSON.stringify(packet) }));
  expect(screen.getByLabelText("UQ username")).toHaveValue("s1234567");
  expect(document.querySelector(".portal-screen")).toBeNull();
  await user.click(screen.getByRole("button", { name: /^Sign in$/ }));
  expect(sent).toEqual([
    { kind: "submit", id: "go", fields: { name: "s1234567", secret: "test-only" } },
  ]);
  expect(screen.getByLabelText("Password")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
  await act(async () =>
    connection().onmessage({
      data: JSON.stringify({ ...packet, text: "Check your username or password" }),
    }),
  );
  expect(screen.getByRole("status")).toHaveTextContent("Check your username or password");
  expect(screen.getByRole("button", { name: /^Sign in$/ })).toBeEnabled();
  await act(async () =>
    connection().onmessage({ data: JSON.stringify({ user: "s1234567@student.uq.edu.au" }) }),
  );
  expect(complete).toHaveBeenCalledWith("s1234567@student.uq.edu.au");
  mounted.unmount();
  expect(connection().close).toHaveBeenCalled();
});

test("YouTube typing interrupts the idle view and avoids another pixel frame", async () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const calls: { body?: Record<string, unknown>; signal?: AbortSignal }[] = [];
  const view = {
    mode: "window",
    image: "frame",
    host: "accounts.google.com",
    title: "Google sign-in",
    text: "",
    width: 760,
    height: 480,
    controls: [
      {
        id: "email",
        type: "email",
        label: "Email",
        x: 100,
        y: 100,
        width: 300,
        height: 48,
        disabled: false,
        checked: false,
        options: [],
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((_path: string, init?: RequestInit) => {
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ body, signal: init?.signal || undefined });
      if (body?.kind === "open") return Promise.resolve(json(view));
      if (body?.kind === "resize") return Promise.resolve(json(view));
      if (body?.kind === "fill") return Promise.resolve(json({ acknowledged: true }));
      if (body?.kind === "cancel") return Promise.resolve(json({}));
      return new Promise<Response>((_resolve, reject) =>
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Cancelled", "AbortError")),
          { once: true },
        ),
      );
    }),
  );
  const mounted = render(
    <Portal
      provider="YouTube"
      path="/api/timey/youtube?view=1"
      complete={vi.fn()}
      fail={vi.fn()}
      cancel={vi.fn()}
    />,
  );
  const email = await screen.findByLabelText("Email");
  await waitFor(() => expect(calls.some((call) => call.body === undefined)).toBe(true));
  const idle = calls.find((call) => call.body === undefined)!;
  fireEvent.change(email, { target: { value: "member@example.org" } });
  await waitFor(() => expect(calls.some((call) => call.body?.kind === "fill")).toBe(true));
  expect(idle.signal?.aborted).toBe(true);
  expect(calls.filter((call) => call.body?.kind === "fill")).toHaveLength(1);
  mounted.unmount();
});
