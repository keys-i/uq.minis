/** A brief fills ordinary editable fields; saving remains the form's own action */
import React, { useEffect, useRef, useState } from "react";
import type { Field } from "./schema.ts";
import { Icon } from "./icons.tsx";

export function Phrase({
  fields,
  values,
  change,
  example,
}: {
  fields: Field[];
  values: () => Record<string, string>;
  change: (values: Record<string, string>) => void;
  example: string;
}) {
  const [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const request = useRef(0);
  useEffect(
    () => () => {
      request.current++;
    },
    [],
  );
  return (
    <div className="phrase">
      <label className="field">
        <span>Tell me what you have in mind</span>
        <input
          type="text"
          value={text}
          maxLength={2000}
          placeholder={example}
          onChange={(event) => {
            request.current++;
            setText(event.target.value);
            setBusy(false);
            setMessage("");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              event.currentTarget
                .closest(".phrase")
                ?.querySelector<HTMLButtonElement>("button")
                ?.click();
            }
          }}
        />
      </label>
      <button
        type="button"
        className="secondary"
        disabled={busy || !text.trim()}
        aria-busy={busy}
        onClick={async () => {
          const version = ++request.current;
          setBusy(true);
          try {
            const { interpret } = await import("./interpret.ts");
            if (version !== request.current) return;
            const result = interpret(text, fields, values());
            if (version !== request.current) return;
            change(result.values);
            const count = Object.keys(result.values).length;
            setMessage(
              [
                count
                  ? "Details filled in below for you to check"
                  : "I couldn't pick out those details. Try a name, date, time or percentage",
                ...result.notes,
              ].join(" / "),
            );
          } catch {
            if (version === request.current)
              setMessage("The writing helper couldn't open. Your fields still work below");
          } finally {
            if (version === request.current) setBusy(false);
          }
        }}
      >
        <Icon name="edit" /> {busy ? "Reading…" : "Fill details"}
      </button>
      {message && <p role="status">{message}</p>}
    </div>
  );
}
