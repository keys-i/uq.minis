import { sessionSchema } from "./schema.ts";
import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.ts";
import { Icon } from "./icons.tsx";
import { T } from "./language.tsx";
import { Portal } from "./portal.tsx";
import { useSession } from "./session.ts";

/** Gate university workflows while keeping a single shared, backend-verified identity */
export function UniGate({ children }: { children: React.ReactNode }) {
  const user = useSession((state) => state.user),
    statusError = useSession((state) => state.error);
  const [error, setError] = useState(""),
    [checking, setChecking] = useState(false),
    [portal, setPortal] = useState("");
  const login = useRef<AbortController | null>(null);
  useEffect(() => {
    void useSession.getState().load();
    return () => login.current?.abort();
  }, []);

  function complete(user: string) {
    setPortal("");
    setChecking(false);
    useSession.getState().complete(user);
  }

  async function verify() {
    if (login.current) return;
    const controller = new AbortController();
    login.current = controller;
    setChecking(true);
    setError("");
    try {
      const result = await api("/api/session/login", sessionSchema, {}, controller.signal);
      if (!controller.signal.aborted) {
        if (result.user) complete(result.user);
        else setPortal(result.window || "/api/session/window");
      }
    } catch (error) {
      if (!controller.signal.aborted) setError((error as Error).message);
    } finally {
      login.current = null;
      if (!controller.signal.aborted) setChecking(false);
    }
  }

  const problem = error || statusError;
  if (user === null)
    return (
      <div>
        <p role={problem ? "alert" : "status"}>{problem || "Checking UQ access…"}</p>
        {problem && (
          <button type="button" onClick={() => void useSession.getState().load()}>
            Try again
          </button>
        )}
      </div>
    );
  if (portal)
    return (
      <Portal
        path={portal}
        complete={complete}
        fail={(message) => {
          setPortal("");
          setError(message);
        }}
        cancel={() => {
          setPortal("");
          setChecking(false);
        }}
      />
    );
  if (!user)
    return (
      <section className="uni-gate">
        <Icon name="auth" />
        <h2>
          <T>Your uni account opens this door</T>
        </h2>
        <p>
          <T>Verify access through UQ's portal to unlock university workflows</T>
        </p>
        <button type="button" className="subscribe-link" disabled={checking} onClick={verify}>
          {checking ? "Connecting to UQ…" : "Check UQ access"}
        </button>
        {problem && (
          <p role="alert" className="notice error">
            {problem}
          </p>
        )}
      </section>
    );
  return (
    <>
      {problem && (
        <p role="alert" className="notice error">
          {problem}
        </p>
      )}
      <div className="uni-session">
        <small>Signed in as {user}</small>
        <button type="button" className="quiet" onClick={() => void useSession.getState().logout()}>
          Sign out
        </button>
      </div>
      {children}
    </>
  );
}
