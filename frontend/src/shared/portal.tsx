import React, { useEffect, useEffectEvent, useRef, useState } from "react";
import { api } from "./api.ts";
import { Icon } from "./icons.tsx";

import {
  acknowledgement,
  connectionSchema,
  portalSchema,
  type PortalView,
  type PortalMessage,
} from "./schema.ts";

/** Present our form while UQ owns verification and the original MFA controls */
export function Portal({
  path,
  complete,
  fail,
  cancel,
  provider = "UQ",
}: {
  path: string;
  provider?: "UQ" | "YouTube";
  complete: (user: string) => void;
  fail: (error: string) => void;
  cancel: () => void;
}) {
  const [view, setView] = useState<PortalView | null>(null),
    [submitting, setSubmitting] = useState(false),
    socket = useRef<WebSocket | null>(null),
    screen = useRef<HTMLDivElement>(null),
    queued = useRef<((event: object) => boolean) | null>(null),
    windowView = view !== null && view.mode !== "form";
  const finished = useEffectEvent(complete),
    failed = useEffectEvent(fail);
  useEffect(() => {
    if (provider === "YouTube") {
      let ended = false,
        waiting = false,
        request: AbortController | null = null,
        timer: ReturnType<typeof setTimeout>;
      const events: object[] = [{ kind: "open" }];
      queued.current = (event) => {
        if (ended || events.length >= 32) return false;
        const next = event as { kind: string; id?: string };
        if (next.kind === "fill" || next.kind === "resize") {
          const previous = events.findIndex(
            (item) =>
              (item as typeof next).kind === next.kind &&
              (next.kind === "resize" || (item as typeof next).id === next.id),
          );
          if (previous >= 0) events.splice(previous, 1);
        }
        events.push(event);
        if (waiting) request?.abort();
        else if (request === null) {
          clearTimeout(timer);
          timer = setTimeout(poll, 0);
        }
        return true;
      };
      const poll = async () => {
        const event = events.shift();
        request = new AbortController();
        waiting = event === undefined;
        try {
          const result = await api(path, connectionSchema, event, request.signal);
          if ("connected" in result || "error" in result) {
            ended = true;
            if ("connected" in result) finished("");
            else failed(result.error);
          } else if (!("acknowledged" in result)) {
            setSubmitting(false);
            setView(result);
          }
        } catch (error) {
          if (!ended && (error as Error).name !== "AbortError") {
            ended = true;
            failed((error as Error).message);
          }
        }
        request = null;
        waiting = false;
        if (!ended) timer = setTimeout(poll, events.length ? 0 : 200);
      };
      void poll();
      return () => {
        ended = true;
        clearTimeout(timer);
        request?.abort();
        queued.current = null;
        void api(path, acknowledgement, { kind: "cancel" }).catch(() => {});
      };
    }
    const url = new URL(path, location.origin);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const connection = new WebSocket(url);
    socket.current = connection;
    let ended = false;
    const observer = new ResizeObserver(() => resize());
    function resize() {
      if (connection.readyState === WebSocket.OPEN && screen.current?.dataset.mode === "window")
        connection.send(
          JSON.stringify({
            kind: "resize",
            width: Math.round(screen.current.clientWidth),
            height: Math.max(480, Math.min(800, window.innerHeight - 180)),
          }),
        );
    }
    connection.onopen = resize;
    connection.onmessage = (event) => {
      let result: PortalMessage;
      try {
        result = portalSchema.parse(JSON.parse(event.data));
      } catch {
        ended = true;
        failed("The UQ window returned an unreadable response; try again");
        connection.close();
        return;
      }
      if ("user" in result || "error" in result) {
        ended = true;
        if ("user" in result) finished(result.user);
        else failed(result.error);
        connection.close();
      } else {
        setSubmitting(false);
        setView(result);
      }
    };
    connection.onerror = () => {
      if (!ended) {
        ended = true;
        failed("The UQ window couldn't connect; try again");
      }
    };
    connection.onclose = () => {
      if (!ended) {
        ended = true;
        failed("The UQ window disconnected; try signing in again");
      }
    };
    if (screen.current) observer.observe(screen.current);
    return () => {
      ended = true;
      observer.disconnect();
      connection.close();
      socket.current = null;
    };
  }, [path, provider]);
  useEffect(() => {
    if (provider !== "YouTube" || !windowView || !screen.current) return;
    const element = screen.current,
      resize = () =>
        queued.current?.({
          kind: "resize",
          width: Math.round(element.clientWidth),
          height: Math.round(element.clientHeight),
        }),
      observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    return () => observer.disconnect();
  }, [provider, windowView]);
  function send(event: object) {
    if (queued.current) return queued.current(event);
    const connection = socket.current;
    if (connection?.readyState !== WebSocket.OPEN) return false;
    if (connection.bufferedAmount > 65536) {
      connection.close();
      return false;
    }
    connection.send(JSON.stringify(event));
    return true;
  }
  function scroll(y: number) {
    send({ kind: "scroll", y: Math.max(-900, Math.min(900, Math.round(y))) });
  }
  const fields = view?.controls.map((control) => control.id).join();
  const form = provider === "UQ" && (!view || view.mode === "form");
  useEffect(() => {
    if (screen.current && !screen.current.contains(document.activeElement))
      (
        screen.current.querySelector<HTMLInputElement>(
          "input:not([disabled]),select:not([disabled])",
        ) || screen.current.querySelector<HTMLButtonElement>("button:not([disabled])")
      )?.focus({ preventScroll: true });
  }, [fields]);
  return (
    <section className="portal-window" aria-label={`${provider} sign-in`}>
      <div className="portal-head">
        <span>
          <Icon name="auth" />
          {form ? "Sign in with UQ" : view?.host || provider}
        </span>
        <button type="button" className="quiet" onClick={cancel}>
          Cancel
        </button>
      </div>
      <p className={form || !view ? "portal-status" : "sr-only"} role="status" aria-live="polite">
        {submitting
          ? "Checking your details…"
          : view?.text || (!view ? `Connecting to ${provider}…` : "")}
      </p>
      <div
        ref={screen}
        className={form ? "portal-form" : "portal-screen"}
        data-mode={form ? "form" : "window"}
        role="group"
        aria-label={view?.title || `${provider} sign-in`}
        tabIndex={form ? undefined : 0}
        onClick={
          form
            ? undefined
            : (event) => {
                if (event.target === event.currentTarget)
                  event.currentTarget.focus({ preventScroll: true });
              }
        }
        onWheelCapture={
          form
            ? undefined
            : (event) => {
                if (!event.deltaY) return;
                event.preventDefault();
                scroll(event.deltaY);
              }
        }
        onKeyDown={
          form
            ? undefined
            : (event) => {
                if (event.target !== event.currentTarget) return;
                const y =
                  event.key === "ArrowUp"
                    ? -180
                    : event.key === "ArrowDown"
                      ? 180
                      : event.key === "PageUp"
                        ? -450
                        : event.key === "PageDown"
                          ? 450
                          : 0;
                if (!y) return;
                event.preventDefault();
                scroll(y);
              }
        }
        style={form ? undefined : { aspectRatio: `${view?.width}/${view?.height}` }}
      >
        {form ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!view || submitting) return;
              const username = view.controls.find((control) =>
                  ["text", "email"].includes(control.type),
                ),
                password = view.controls.find((control) => control.type === "password"),
                submit = view.controls.find((control) => control.type === "submit");
              if (!username || !password || !submit) return;
              const values = new FormData(event.currentTarget);
              const sent = send({
                kind: "submit",
                id: submit.id,
                fields: {
                  [username.id]: values.get("username"),
                  [password.id]: values.get("password"),
                },
              });
              if (!sent) return;
              event.currentTarget.querySelector<HTMLInputElement>("input[type=password]")!.value =
                "";
              setSubmitting(true);
            }}
          >
            <label htmlFor="uq-username">UQ username</label>
            <input
              id="uq-username"
              name="username"
              autoComplete="username"
              autoCapitalize="off"
              spellCheck={false}
              placeholder="s1234567"
              maxLength={4096}
              required
            />
            <label htmlFor="uq-password">Password</label>
            <input
              id="uq-password"
              name="password"
              type="password"
              autoComplete="current-password"
              maxLength={4096}
              required
            />
            <button
              type="submit"
              disabled={
                !view ||
                submitting ||
                view.controls.some((control) => control.type === "submit" && control.disabled)
              }
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
            <small>UQ verifies your account and MFA - Minis doesn’t save your password</small>
          </form>
        ) : (
          view && (
            <>
              <img src={`data:image/png;base64,${view.image}`} alt="" draggable="false" />
              {view.controls.map((control) => {
                const style: React.CSSProperties = {
                  left: `${(control.x / view.width) * 100}%`,
                  top: `${(control.y / view.height) * 100}%`,
                  width: `${(control.width / view.width) * 100}%`,
                  height: `${(control.height / view.height) * 100}%`,
                };
                const common = {
                  style,
                  "aria-label": control.label,
                  disabled: control.disabled,
                };
                if (control.type === "select")
                  return (
                    <select
                      key={control.id}
                      {...common}
                      className="portal-field"
                      defaultValue={control.options.find((option) => option.selected)?.value}
                      onChange={(event) =>
                        send({ kind: "select", id: control.id, value: event.target.value })
                      }
                    >
                      {control.options.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  );
                if (["button", "submit", "reset", "checkbox", "radio"].includes(control.type))
                  return (
                    <button
                      key={control.id}
                      {...common}
                      type="button"
                      className="portal-action"
                      role={["checkbox", "radio"].includes(control.type) ? control.type : undefined}
                      aria-checked={
                        ["checkbox", "radio"].includes(control.type) ? control.checked : undefined
                      }
                      onClick={() => send({ kind: "click", id: control.id })}
                    >
                      <span className="sr-only">{control.label}</span>
                    </button>
                  );
                return (
                  <input
                    key={control.id}
                    {...common}
                    className="portal-field"
                    type={control.type === "password" ? "password" : "text"}
                    placeholder={control.label}
                    autoComplete="off"
                    autoCapitalize="off"
                    spellCheck={false}
                    onChange={(event) =>
                      send({ kind: "fill", id: control.id, value: event.target.value })
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        send({ kind: "enter", id: control.id });
                      }
                    }}
                  />
                );
              })}
            </>
          )
        )}
      </div>
    </section>
  );
}
