// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { Portal } from "../src/shared/portal.tsx";

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
