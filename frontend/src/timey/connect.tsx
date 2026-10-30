/** Keep the provider's real sign-in separate from timer drafts and UQ access */
import { type ReactNode, useEffect, useState } from "react";
import * as z from "zod/mini";
import { api } from "../shared/api.ts";
import { Dialog } from "../shared/controls.tsx";
import { Portal } from "../shared/portal.tsx";
import { Icon } from "../shared/icons.tsx";
import { Issue } from "./feedback.tsx";

const status = z.object({ connected: z.boolean(), open: z.boolean() });

function googleError(message: string) {
  if (/pop-?up|new window|blocked/i.test(message))
    return "Google couldn’t open. Allow pop-ups for this page and try again";
  if (/cancel|closed|denied|declined|access_denied/i.test(message))
    return "Sign-in was cancelled. Your timer is still here when you’re ready";
  if (/network|offline|failed to fetch|connection|disconnected|timed? out/i.test(message))
    return "We couldn’t reach Google. Check your connection and try again";
  return "Google couldn’t connect just now. Your timer is safe, so you can try again";
}

export function Connection({ ready, children }: { ready: () => void; children: ReactNode }) {
  const [open, setOpen] = useState(false),
    [connected, setConnected] = useState<boolean | null>(null),
    [error, setError] = useState("");
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    api("/api/timey/youtube?status=1", status, undefined, controller.signal)
      .then((saved) => setConnected(saved.connected))
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
  const manage = async () => {
    setError("");
    setOpen(true);
    setChecking(true);
    try {
      const saved = await api("/api/timey/youtube?status=1", status);
      setConnected(saved.connected);
    } catch (error) {
      setError((error as Error).message);
      setConnected(false);
      setOpen(false);
    } finally {
      setChecking(false);
    }
  };
  return (
    <>
      {connected ? (
        <>
          {children}
          <button type="button" className="quiet youtube-connect" onClick={() => void manage()}>
            <Icon name="link" />
            Google connected
          </button>
        </>
      ) : (
        <div className="timer-editor timer-google-frame" data-empty>
          <section className="timer-canvas timer-google-gate" aria-label="Connect Google">
            <div className="timer-google-reveal">
              <div className="timer-google-paper">
                <div className="timer-google-panel" data-error={(!open && !!error) || undefined}>
                  {open && !checking ? (
                    <div className="timer-google-window">
                      <Portal
                        provider="YouTube"
                        path="/api/timey/youtube?view=1"
                        cancel={() => setOpen(false)}
                        fail={(error) => {
                          setOpen(false);
                          setError(error);
                        }}
                        complete={() => {
                          setOpen(false);
                          setConnected(true);
                          ready();
                        }}
                      />
                    </div>
                  ) : (
                    <div
                      className="timer-google-content"
                      aria-hidden={!open && !!error}
                      inert={!open && !!error}
                    >
                      <span className="timer-google-mark" aria-hidden="true">
                        <Icon name="link" />
                      </span>
                      <h2>{checking ? "Checking Google…" : "Connect Google"}</h2>
                      {!checking && <p>Sign in to search YouTube and make your timer</p>}
                      {!checking && (
                        <button type="button" onClick={() => void manage()}>
                          Connect Google
                        </button>
                      )}
                      {checking && <p role="status">Checking your connection…</p>}
                    </div>
                  )}
                  {!open && error && (
                    <div className="timer-google-error">
                      <Issue title="Google didn’t connect" message={googleError(error)}>
                        <button type="button" autoFocus onClick={() => void manage()}>
                          Try again
                        </button>
                        <button type="button" className="quiet" onClick={() => setError("")}>
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
        <Dialog title="Connect Google" close={() => setOpen(false)}>
          {error ? (
            <Issue title="Google didn’t respond" message={googleError(error)}>
              <button type="button" autoFocus onClick={() => setError("")}>
                Back
              </button>
            </Issue>
          ) : checking ? (
            <p role="status">Checking your connection…</p>
          ) : (
            <>
              <p>Google is connected privately to this workspace</p>
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setConnected(false);
                }}
              >
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
                Disconnect Google
              </button>
            </>
          )}
        </Dialog>
      )}
    </>
  );
}
