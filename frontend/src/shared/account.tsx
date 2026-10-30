import React, { useState } from "react";
import { CalendarSettings } from "../study/calendar.tsx";
import { UniGate } from "./access.tsx";
import { Button } from "./controls.tsx";
import { Mini } from "./mini.tsx";

export function Account() {
  const [connection, setConnection] = useState("");
  return (
    <div className="account-settings">
      <section>
        <h3>Eventy access</h3>
        <UniGate>
          <p>UQ access is connected</p>
          <div className="row">
            <Button className="secondary" onClick={() => setConnection("auth")}>
              Connect event forms
            </Button>
            <Button className="secondary" onClick={() => setConnection("agent")}>
              Connect Outlook
            </Button>
          </div>
          {connection && (
            <Mini
              key={connection}
              name={connection}
              action={connection === "agent" ? "login" : undefined}
            />
          )}
        </UniGate>
      </section>
      <details>
        <summary>Calendar & private backup</summary>
        <CalendarSettings base={`${location.origin}${location.pathname}`} />
      </details>
    </div>
  );
}
