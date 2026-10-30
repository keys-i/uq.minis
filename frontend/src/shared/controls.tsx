/** Shared actions and dialogs preserve focus and report failures beside the person's work */
import type { SheetProps } from "../study/model.ts";
import React, { useEffect, useEffectEvent, useId, useRef, useState } from "react";
import { Icon } from "./icons.tsx";
import { useNotice } from "./notice.ts";

export function Button({
  children,
  onClick,
  className = "",
  ...props
}: Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> & { onClick?: () => unknown }) {
  const [busy, setBusy] = useState(false),
    report = useNotice((state) => state.report);
  return (
    <button
      type="button"
      {...props}
      className={className}
      disabled={busy || props.disabled}
      aria-busy={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await onClick?.();
        } catch (error) {
          report((error as Error).message, true);
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Working…" : children}
    </button>
  );
}

export function Link({ href, children }: { href?: string; children: React.ReactNode }) {
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ) : null;
}

export function Field({
  label,
  name,
  value,
  type = "text",
  children,
  ...props
}: Pick<
  React.InputHTMLAttributes<HTMLInputElement>,
  "name" | "type" | "required" | "min" | "max" | "step" | "maxLength" | "inputMode" | "pattern"
> & { label: string; value?: string | number | null; children?: React.ReactNode }) {
  return (
    <label className={`field ${type === "textarea" ? "wide" : ""}`}>
      <span>{label}</span>
      {children ||
        (type === "textarea" ? (
          <textarea name={name} defaultValue={value || ""} {...props} />
        ) : (
          <input name={name} type={type} defaultValue={value ?? ""} {...props} />
        ))}
    </label>
  );
}

export function Dialog({
  title,
  children,
  close,
}: SheetProps & { title: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null),
    titleId = useId();
  const dismissed = useEffectEvent(close);
  useEffect(() => {
    const element = ref.current!;
    element.showModal();
    const cancel = (event: Event) => {
      event.preventDefault();
      dismissed();
    };
    element.addEventListener("cancel", cancel);
    return () => {
      element.removeEventListener("cancel", cancel);
      element.close();
    };
  }, []);
  return (
    <dialog ref={ref} aria-labelledby={titleId}>
      <div className="dialog-head">
        <h2 id={titleId}>{title}</h2>
        <Button className="icon-button" aria-label="Close dialog" onClick={close}>
          <Icon name="close" />
        </Button>
      </div>
      {children}
    </dialog>
  );
}

export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-mark" aria-hidden="true">
        ✳
      </div>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
