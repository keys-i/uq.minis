import { roomsSchema } from "./schema.ts";
import React, { useEffect, useRef, useState } from "react";
import { T } from "./language.tsx";
export type Values = Record<string, string>;

export type { Field, Schema } from "./schema.ts";
import type { Field, Schema, Room } from "./schema.ts";
import { api } from "./api.ts";
import { autocomplete, clearDraft, restoreDraft, saveDraft } from "./draft.ts";
import { Phrase } from "./phrase.tsx";

function Rooms({ field, catalogue }: { field: Field; catalogue?: string }) {
  const [query, setQuery] = useState(""),
    [seats, setSeats] = useState(0),
    [selected, setSelected] = useState(""),
    [result, setResult] = useState<{ rows: Room[]; total: number; maximum: number }>({
      rows: [],
      total: 0,
      maximum: 500,
    }),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(
      () =>
        api(
          `/api/rooms?${new URLSearchParams({ q: query, seats: String(seats), catalogue: catalogue || "" })}`,
          roomsSchema,
          undefined,
          controller.signal,
        )
          .then((data) => {
            setResult(data);
            setError("");
          })
          .catch((error) => {
            if (error.name !== "AbortError") setError(error.message);
          }),
      query ? 100 : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, seats, catalogue]);
  return (
    <fieldset className="room-picker">
      <legend>
        <T>Find room to gather</T>
      </legend>
      <div className="form-grid">
        <label className="field">
          <span>Find a room</span>
          <input
            type="search"
            value={query}
            maxLength={200}
            placeholder="A room at St Lucia for 50 people"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="field">
          <span>At least {seats} seats</span>
          <input
            type="range"
            min="0"
            max={result.maximum}
            value={seats}
            onChange={(event) => setSeats(Number(event.target.value))}
          />
        </label>
      </div>
      <input type="hidden" name={field.name} value={selected} />
      <button type="button" className="quiet" onClick={() => setSelected("")}>
        {selected
          ? `Selected ${selected.replace("|", " / ")} / use event's original venue instead`
          : "Keeping the venue in your event"}
      </button>
      {error && <p role="alert">{error}</p>}
      <div className="room-options">
        {result.rows.map((room) => {
          const id = `${room.campus}|${room.room}`;
          return (
            <div key={id}>
              <label>
                <input
                  type="radio"
                  name="room-choice"
                  value={id}
                  checked={selected === id}
                  onChange={() => setSelected(id)}
                />
                <span>
                  <strong>
                    {room.room} / {room.seats} seats
                  </strong>
                  <small>
                    {room.campus} / {room.building} / {room.kind}
                  </small>
                </span>
              </label>
              <div>
                {room.photo && (
                  <a
                    href={room.photo}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Photo of room ${room.room}`}
                  >
                    Photo
                  </a>
                )}
                {room.tour && (
                  <a
                    href={room.tour}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Tour room ${room.room}`}
                  >
                    Tour
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <small>
        {result.total} rooms match{result.total > 20 ? " / narrow your search to see more" : ""} /
        capacity does not confirm availability
      </small>
    </fieldset>
  );
}

export function Input({
  field,
  values,
  change,
}: {
  field: Field;
  values: Values;
  change: (name: string, value: string) => void;
}) {
  if (field.type === "room") return <Rooms field={field} catalogue={values.rooms} />;
  const update = (
    event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) =>
    change(
      field.name,
      event.target.type === "checkbox"
        ? (event.target as HTMLInputElement).checked
          ? "on"
          : ""
        : event.target.value,
    );
  const common = {
    id: `mini-field-${field.name.replaceAll(/[^a-z0-9_-]/gi, "-")}`,
    name: field.name,
    min: field.min,
    max: field.max,
    step: field.step,
    maxLength: field.maxLength,
    required: field.required,
    autoComplete: autocomplete(field),
    onChange: update,
  };
  return (
    <label className={`field ${field.type === "textarea" ? "wide" : ""}`}>
      <span>
        <T>{field.label}</T>
      </span>
      {field.type === "select" ? (
        <select {...common} value={values[field.name]}>
          {field.options?.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      ) : field.type === "textarea" ? (
        <textarea {...common} value={values[field.name]} maxLength={field.maxLength || 6000} />
      ) : field.type === "range" ? (
        <div className="tactile-input">
          <input {...common} type="range" value={values[field.name]} />
          <input
            type="number"
            aria-label={`${field.label} / exact value`}
            min={field.min}
            max={field.max}
            step={field.step || 1}
            value={values[field.name]}
            onChange={update}
            required
          />
        </div>
      ) : field.type === "file" ? (
        <input id={common.id} name={field.name} type="file" required={field.required} />
      ) : field.type === "checkbox" ? (
        <input
          id={common.id}
          name={field.name}
          type="checkbox"
          value="on"
          checked={values[field.name] === "on"}
          onChange={update}
        />
      ) : (
        <input {...common} type={field.type || "text"} value={values[field.name]} />
      )}
      {field.help && (
        <small>
          <T>{field.help}</T>
        </small>
      )}
    </label>
  );
}

export function initial(schema: Schema): Values {
  return Object.fromEntries(
    schema.fields.map((field) => [
      field.name,
      field.type === "checkbox"
        ? field.checked
          ? "on"
          : ""
        : String(field.value ?? field.options?.[0]?.[0] ?? field.min ?? ""),
    ]),
  );
}

export function MiniForm({
  schema,
  busy = false,
  draft,
  submit,
}: {
  schema: Schema;
  busy?: boolean;
  draft?: { workspace: string; mini: string };
  submit: (data: FormData) => void;
}) {
  const restored = useRef(
      draft
        ? restoreDraft(draft.workspace, draft.mini, schema, initial(schema))
        : { values: initial(schema), found: false },
    ).current,
    [values, setValues] = useState(restored.values),
    [dirty, setDirty] = useState(false),
    [saved, setSaved] = useState(restored.found);
  const change = (name: string, value: string) => {
    setDirty(true);
    setValues((old) => ({ ...old, [name]: value }));
  };
  useEffect(() => {
    if (!draft || !dirty) return;
    const save = () => saveDraft(draft.workspace, draft.mini, schema, values);
    const timer = setTimeout(() => {
      save();
      setSaved(true);
    }, 250);
    addEventListener("pagehide", save, { once: true });
    return () => {
      clearTimeout(timer);
      removeEventListener("pagehide", save);
    };
  }, [dirty, draft, schema, values]);
  const fields = schema.fields.filter(
    (field) =>
      !field.when ||
      Object.entries(field.when).every(([key, choices]) => choices.includes(values[key])),
  );
  const groups = [...new Set(fields.map((field) => field.group).filter(Boolean))];
  return (
    <form
      onInvalidCapture={(event) => {
        for (
          let section = (event.target as HTMLElement).closest("details");
          section;
          section = section.parentElement?.closest("details") ?? null
        )
          section.open = true;
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (!busy) submit(new FormData(event.currentTarget));
      }}
    >
      {schema.fields.some((field) => ["event.title", "query"].includes(field.name)) && (
        <Phrase
          fields={schema.fields}
          values={() => values}
          change={(next) => {
            setDirty(true);
            setValues((old) => ({ ...old, ...next }));
          }}
          example={
            schema.fields.some((field) => field.name === "event.title")
              ? "Movie night for 50 people on Friday from 6pm to 8pm"
              : "Find coding courses"
          }
        />
      )}
      <div className="form-grid">
        {fields
          .filter((field) => !field.group)
          .map((field) => (
            <Input key={field.name} field={field} values={values} change={change} />
          ))}
      </div>
      {groups.map((group) => {
        const entries = fields.filter((field) => field.group === group),
          content = (
            <div className="form-grid">
              {entries.map((field) => (
                <Input key={field.name} field={field} values={values} change={change} />
              ))}
            </div>
          );
        return entries.some((field) => field.required) ? (
          <section className="form-settings" key={group}>
            <h3>
              <T>{group}</T>
            </h3>
            {content}
          </section>
        ) : (
          <details className="form-settings" key={group}>
            <summary>
              <T>{group}</T>
            </summary>
            {content}
          </details>
        );
      })}
      <div className="form-actions">
        <button disabled={busy} aria-busy={busy}>
          {busy ? "Working - keep this page open" : schema.submit || "Continue"}
        </button>
        {draft && (dirty || saved) && (
          <button
            type="button"
            className="quiet"
            onClick={() => {
              clearDraft(draft.workspace, draft.mini);
              setValues(initial(schema));
              setDirty(false);
              setSaved(false);
            }}
          >
            Clear saved draft
          </button>
        )}
      </div>
    </form>
  );
}
