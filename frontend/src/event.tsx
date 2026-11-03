import React, { useState } from "react";
import { Icon } from "./shared/icons.tsx";
import { UniGate } from "./shared/access.tsx";
import { Mini } from "./shared/mini.tsx";

export function Eventy({ follow = false }) {
  const [stage, setStage] = useState(follow ? "follow" : "prepare"),
    [visited, setVisited] = useState(new Set([follow ? "follow" : "prepare"]));
  return (
    <>
      <div className="planner-tabs" aria-label="Eventy workflow">
        {[
          ["prepare", "Prepare event", "event"],
          ["follow", "Booking & replies", "agent"],
        ].map(([id, label, icon]) => (
          <button
            type="button"
            key={id}
            aria-pressed={stage === id}
            className={stage === id ? "selected" : ""}
            onClick={() => {
              setStage(id);
              setVisited((old) => new Set([...old, id]));
            }}
          >
            <Icon name={icon} />
            {label}
          </button>
        ))}
      </div>
      <UniGate>
        {[...visited].map((id) => (
          <section key={id} hidden={stage !== id}>
            <Mini name={id === "prepare" ? "event" : "agent"} />
          </section>
        ))}
      </UniGate>
    </>
  );
}
import "./event.css";
