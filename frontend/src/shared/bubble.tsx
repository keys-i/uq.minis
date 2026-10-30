import { useLayoutEffect, useRef, useState } from "react";

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function Bubble({
  id,
  label,
  children,
  className = "timer-settings timer-controls",
  ref,
  focus = true,
  onToggle,
  onPointerEnter,
  onPointerLeave,
  onFocusCapture,
  onBlur,
  region,
}: {
  region?: string;
  id: string;
  label: string;
  children: React.ReactNode;
  className?: string;
  ref?: React.RefObject<HTMLElement | null>;
  focus?: boolean;
  onToggle?: (open: boolean) => void;
  onPointerEnter?: React.PointerEventHandler<HTMLElement>;
  onPointerLeave?: React.PointerEventHandler<HTMLElement>;
  onFocusCapture?: React.FocusEventHandler<HTMLElement>;
  onBlur?: React.FocusEventHandler<HTMLElement>;
}) {
  const local = useRef<HTMLElement>(null),
    panel = ref || local,
    [open, setOpen] = useState(false);
  useLayoutEffect(() => {
    if (!open) return;
    const element = panel.current!,
      trigger = document.querySelector<HTMLElement>(`[popovertarget="${id}"]`);
    if (!trigger) return;
    const position = () => {
      const anchor = trigger.getBoundingClientRect(),
        bounds = element.getBoundingClientRect();
      const left = clamp(
        anchor.left + anchor.width / 2 - bounds.width / 2,
        12,
        innerWidth - bounds.width - 12,
      );
      const below =
        innerHeight - anchor.bottom >= bounds.height + 22 || anchor.top < bounds.height + 22;
      element.dataset.side = below ? "below" : "above";
      element.style.left = `${left}px`;
      element.style.top = `${clamp(below ? anchor.bottom + 12 : anchor.top - bounds.height - 12, 12, innerHeight - bounds.height - 12)}px`;
      element.style.setProperty(
        "--bubble-tip",
        `${clamp(anchor.left + anchor.width / 2 - left, 28, bounds.width - 28)}px`,
      );
    };
    position();
    if (focus)
      element
        .querySelector<HTMLElement>(
          "[aria-pressed=true],input,select,button,textarea,[role=slider]",
        )
        ?.focus({ preventScroll: true });
    const observer = new ResizeObserver(position);
    observer.observe(element);
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
  }, [open, id, focus, panel]);
  return (
    <section
      ref={panel}
      id={id}
      data-region={region}
      className={className}
      popover="auto"
      role="dialog"
      aria-label={label}
      onToggle={(event) => {
        const expanded = event.newState === "open";
        setOpen(expanded);
        onToggle?.(expanded);
      }}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      onFocusCapture={onFocusCapture}
      onBlur={onBlur}
      onInvalidCapture={(event) => event.currentTarget.showPopover()}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          panel.current?.hidePopover();
          document.querySelector<HTMLElement>(`[popovertarget="${id}"]`)?.focus();
        }
      }}
    >
      <div className={`bubble-body${className.includes("timer-") ? " timer-settings-body" : ""}`}>
        {children}
      </div>
    </section>
  );
}
