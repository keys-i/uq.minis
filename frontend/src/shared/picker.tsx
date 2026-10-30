import { Icon } from "./icons.tsx";
import React, { useId, useRef } from "react";
import { T } from "./language.tsx";

export function Picker({
  label,
  value,
  options,
  onChange,
  compact = false,
}: {
  compact?: boolean;
  label: string;
  value: string | number;
  options: ReadonlyArray<readonly [string | number, string]>;
  onChange: (value: string) => void;
}) {
  const id = useId(),
    panel = useRef<HTMLElement>(null),
    trigger = useRef<HTMLButtonElement>(null),
    selected = options.find((option) => String(option[0]) === String(value)) || options[0],
    anchor = `--picker-${id.replace(/[^a-z0-9_-]/gi, "")}`;
  return (
    <div className="picker">
      <span id={`${id}-label`} className="picker-label">
        <T>{label}</T>
      </span>
      <button
        ref={trigger}
        type="button"
        className="picker-trigger"
        style={{ anchorName: anchor }}
        popoverTarget={id}
        aria-haspopup="dialog"
        aria-labelledby={`${id}-label ${id}-value`}
      >
        <span id={`${id}-value`}>
          <T>{selected?.[1] || "Choose"}</T>
        </span>
        <Icon name="chevron" />
      </button>
      <section
        ref={panel}
        id={id}
        popover="auto"
        role="dialog"
        aria-label={`Choose ${label.toLowerCase()}`}
        className="picker-menu"
        data-compact={compact || undefined}
        onKeyDown={(event) => {
          if (compact && event.key === "Enter") {
            event.preventDefault();
            panel.current?.hidePopover();
            trigger.current?.focus();
          }
        }}
        style={{ positionAnchor: anchor }}
        onToggle={(event) => {
          if (event.newState === "open")
            event.currentTarget.querySelector<HTMLInputElement>("input:checked")?.focus();
        }}
      >
        {!compact && (
          <div className="picker-heading">
            <strong>
              <T>{label}</T>
            </strong>
            <button
              type="button"
              className="popover-close"
              popoverTarget={id}
              popoverTargetAction="hide"
              aria-label={`Close ${label.toLowerCase()} choices`}
            >
              <Icon name="close-small" />
            </button>
          </div>
        )}
        <fieldset>
          <legend className="sr-only">{label}</legend>
          {options.map(([code, text]) => (
            <label
              className="picker-option"
              key={code}
              data-selected={String(value) === String(code)}
            >
              <input
                type="radio"
                name={id}
                value={code}
                checked={String(value) === String(code)}
                onChange={() => onChange(String(code))}
                onClick={() => panel.current?.hidePopover()}
              />
              {compact && <Icon name="tick-small" className="picker-check" />}
              <T>{text}</T>
            </label>
          ))}
        </fieldset>
      </section>
    </div>
  );
}
