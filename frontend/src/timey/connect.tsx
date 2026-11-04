/** Keep Google authorisation separate from timer drafts and UQ access */
import { type ReactNode, useEffect, useRef, useState } from "react";
import * as z from "zod/mini";
import { api } from "../shared/api.ts";
import { Dialog } from "../shared/controls.tsx";
import { Icon } from "../shared/icons.tsx";
import { Issue } from "./feedback.tsx";

const status = z.object({
    connected: z.boolean(),
    configured: z.optional(z.boolean()),
  }),
  start = z.object({ url: z.string() });

function googleError(message: string) {
  if (/not configured|web oauth client|return address/i.test(message))
    return "YouTube sign-in is still being set up. Your timer is safe";
  if (/pop-?up|new window|blocked/i.test(message))
    return "Google couldn’t open. Allow pop-ups for this page and try again";
  if (/cancel|closed|denied|declined|access_denied/i.test(message))
    return "Sign-in was cancelled. Your timer is still here when you’re ready";
  if (/network|offline|failed to fetch|connection|disconnected|timed? out/i.test(message))
    return "We couldn’t reach Google. Check your connection and try again";
  return "YouTube couldn’t connect just now. Your timer is safe, so you can try again";
}

function consentUrl(value: string) {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.hostname !== "accounts.google.com")
    throw new Error("Google returned an invalid sign-in address");
  return url.href;
}

function wait(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const cancel = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", cancel);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
}

export function Connection({ ready, children }: { ready: () => void; children: ReactNode }) {
  const [open, setOpen] = useState(false),
    [connected, setConnected] = useState<boolean | null>(null),
    [configured, setConfigured] = useState(true),
    [error, setError] = useState(""),
    [checking, setChecking] = useState(true),
    [authorizing, setAuthorizing] = useState(false);
  const pending = useRef<AbortController>(null),
    provider = useRef<Window | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api("/api/timey/youtube?status=1", status, undefined, controller.signal)
      .then((saved) => {
        setConnected(saved.connected);
        setConfigured(saved.configured !== false);
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setConnected(false);
          setError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setChecking(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(
    () => () => {
      pending.current?.abort();
      provider.current?.close();
    },
    [],
  );

  const connect = async () => {
    setError("");
    setChecking(true);
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const popup = window.open("", "timey-youtube", "popup,width=560,height=720");
    if (!popup) {
      setChecking(false);
      setError("The Google pop-up was blocked");
      return;
    }
    provider.current = popup;
    setAuthorizing(true);
    try {
      const result = await api("/api/timey/youtube/start", start, {}, controller.signal);
      popup.location.href = consentUrl(result.url);
      const deadline = Date.now() + 5 * 60 * 1000;
      while (Date.now() < deadline) {
        await wait(600, controller.signal);
        const saved = await api(
          "/api/timey/youtube?status=1",
          status,
          undefined,
          controller.signal,
        );
        if (saved.connected) {
          popup.close();
          provider.current = null;
          setConnected(true);
          setConfigured(true);
          setOpen(false);
          ready();
          return;
        }
      }
      throw new Error("Google sign-in timed out");
    } catch (error) {
      popup.close();
      provider.current = null;
      if (!controller.signal.aborted) {
        setConnected(false);
        setError((error as Error).message);
      }
    } finally {
      if (pending.current === controller) pending.current = null;
      if (!controller.signal.aborted) setAuthorizing(false);
      if (!controller.signal.aborted) setChecking(false);
    }
  };

  const manage = () => {
    setError("");
    setOpen(true);
  };

  return (
    <>
      {connected ? (
        <>
          {children}
          <button type="button" className="quiet youtube-connect" onClick={manage}>
            <Icon name="link" />
            YouTube
          </button>
        </>
      ) : (
        <div className="timer-editor timer-google-frame" data-empty>
          <section className="timer-canvas timer-google-gate" aria-label="Connect YouTube">
            <div className="timer-google-reveal">
              <div className="timer-google-paper">
                <div className="timer-google-panel" data-error={!!error || undefined}>
                  <div className="timer-google-content" aria-hidden={!!error} inert={!!error}>
                    <span className="timer-google-mark" aria-hidden="true">
                      <Icon name="timey" />
                    </span>
                    <h2>{checking ? "Opening YouTube…" : "Connect YouTube"}</h2>
                    {!checking && (
                      <p>Allow Timey to upload videos you choose. Your password stays private</p>
                    )}
                    {!checking && configured && (
                      <button type="button" onClick={() => void connect()}>
                        Continue with Google
                      </button>
                    )}
                    {!checking && !configured && <p role="status">Sign-in isn’t available yet</p>}
                    {checking && <p role="status">Checking your connection…</p>}
                    {authorizing && (
                      <button
                        type="button"
                        className="quiet"
                        onClick={() => {
                          pending.current?.abort();
                          provider.current?.close();
                          provider.current = null;
                          setAuthorizing(false);
                          setChecking(false);
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                  {error && (
                    <div className="timer-google-error">
                      <Issue title="YouTube didn’t connect" message={googleError(error)}>
                        {configured && (
                          <button type="button" autoFocus onClick={() => void connect()}>
                            Try again
                          </button>
                        )}
                        <button
                          type="button"
                          className="quiet"
                          autoFocus={!configured}
                          onClick={() => setError("")}
                        >
                          Dismiss
                        </button>
                      </Issue>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
      {connected && open && (
        <Dialog title="YouTube" close={() => setOpen(false)}>
          {error ? (
            <Issue title="YouTube didn’t respond" message={googleError(error)}>
              <button type="button" autoFocus onClick={() => setError("")}>
                Back
              </button>
            </Issue>
          ) : checking ? (
            <p role="status">Opening Google…</p>
          ) : (
            <>
              <p>Timey uploads only when you choose to publish a finished video</p>
              <button type="button" onClick={() => void connect()}>
                Reconnect
              </button>
              <button
                type="button"
                className="quiet"
                onClick={async () => {
                  try {
                    await api("/api/timey/youtube", status, { kind: "disconnect" });
                    setConnected(false);
                    setOpen(false);
                  } catch (error) {
                    setError((error as Error).message);
                  }
                }}
              >
                Disconnect
              </button>
            </>
          )}
        </Dialog>
      )}
    </>
  );
}
