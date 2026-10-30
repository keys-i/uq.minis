/** Open the public home while identity loads independently */
import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import App from "./app.tsx";
import { useSession } from "./shared/session.ts";
import { QueryClientProvider } from "@tanstack/react-query";
import { queries } from "./shared/query.ts";
import "./style.css";
import "./shared/cards.css";
import "./wildlife/scene.css";
import "./shared/bubble.css";

/** Share account changes across tabs without blocking the public app shell */
function Workspace() {
  const hosted = useSession((state) => state.hosted);
  const user = useSession((state) => state.user);
  useEffect(() => {
    void useSession.getState().load();
  }, []);
  useEffect(() => {
    if (!hosted || !user) return;
    // Other tabs must discard volatile state after an account switches
    const changed = (event: StorageEvent) => {
      if (event.key === "minis-account" && event.newValue !== user) location.reload();
    };
    try {
      localStorage.setItem("minis-account", user);
    } catch {
      /* Storage is optional */
    }
    addEventListener("storage", changed);
    return () => removeEventListener("storage", changed);
  }, [hosted, user]);
  return <App />;
}

if (!import.meta.env.SSR)
  createRoot(document.getElementById("root")!).render(
    <QueryClientProvider client={queries}>
      <Workspace />
    </QueryClientProvider>,
  );
