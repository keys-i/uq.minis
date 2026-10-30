import { vector } from "../shared/assets.ts";
import { useEffect, useId } from "react";
import type { Values } from "../shared/forms.tsx";
import { Bubble } from "../shared/bubble.tsx";

export const looks = [
  ["minimal", "Minimal"],
  ["glass", "Glass"],
  ["super-mario", "Super Mario"],
  ["minions", "Minions"],
  ["minecraft", "Minecraft"],
  ["sonic", "Sonic"],
  ["pac-man", "Pac-Man"],
  ["temple-run", "Temple Run"],
  ["subway-surfers", "Subway Surfers"],
  ["neon", "Neon"],
] as const;

export function Themes({
  values,
  change,
  questions = [],
  onDesign,
  busy = false,
}: {
  values: Values;
  change: (patch: Values) => void;
  questions?: string[];
  onDesign: () => void;
  busy?: boolean;
}) {
  const id = useId();
  useEffect(() => {
    if (questions.length) document.getElementById(id)?.showPopover();
  }, [questions, id]);
  const custom = (event: React.MouseEvent | React.KeyboardEvent) => {
    event.preventDefault();
    change({ style: "custom" });
    document.getElementById(id)?.showPopover();
  };
  return (
    <div className="timer-looks" role="group" aria-label="Timer look">
      {looks.map(([name, label]) => (
        <button
          type="button"
          key={name}
          aria-pressed={values.style === name}
          className="secondary timer-look"
          data-look={name}
          onClick={() => change({ style: name })}
        >
          <Symbol name={name} />
          {label}
        </button>
      ))}
      <button
        type="button"
        className="secondary timer-look"
        aria-pressed={values.style === "custom"}
        data-look="custom"
        popoverTarget={id}
        aria-haspopup="dialog"
        aria-controls={id}
        onClick={() => change({ style: "custom" })}
        onContextMenu={custom}
        onKeyDown={(event) => {
          if (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey)) custom(event);
        }}
      >
        <Symbol name="custom" />
        Custom
      </button>
      <Bubble id={id} label="Custom artwork">
        <label className="field">
          <span>Name</span>
          <input
            maxLength={100}
            value={values.design_name || ""}
            placeholder="My timer"
            onChange={(event) => change({ design_name: event.target.value })}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.preventDefault();
            }}
          />
        </label>
        <label className="field">
          <span>
            {values.custom_style ? "What would you like to change?" : "What should it look like?"}
          </span>
          <textarea
            maxLength={4000}
            value={values.draft_prompt ?? values.instructions ?? ""}
            placeholder="Describe the shapes, colours and details you have in mind…"
            onChange={(event) =>
              change({
                draft_prompt: event.target.value,
                instructions: event.target.value,
                design_context: "",
              })
            }
          />
        </label>
        {questions.map((question, index) => (
          <label className="field" key={question}>
            <span>{question}</span>
            <input
              maxLength={500}
              value={values[`answer_${index}`] || ""}
              onChange={(event) => change({ [`answer_${index}`]: event.target.value })}
            />
          </label>
        ))}
        <button
          type="button"
          disabled={busy || !(values.draft_prompt || values.instructions)?.trim()}
          onClick={onDesign}
        >
          {questions.length
            ? "Continue"
            : values.custom_style
              ? "Update this look"
              : "Try this look"}
        </button>
      </Bubble>
    </div>
  );
}

/** Theme symbols share their original artwork as independent, cacheable SVG assets */
export function Symbol({ name }: { name: string }) {
  return <img className="timer-symbol" src={vector(`timers/${name}`)} alt="" aria-hidden="true" />;
}
