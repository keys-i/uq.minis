/** Short themed hints share one top-layer surface and leave controls in place */
import { useEffect, useId, useRef } from "react";

export function Tooltips() {
  const id = useId(),
    panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let target: HTMLElement | null = null,
      timer: ReturnType<typeof setTimeout> | undefined;
    const hide = () => {
      clearTimeout(timer);
      if (target) {
        const described = (target.getAttribute("aria-describedby") || "")
          .split(" ")
          .filter((value) => value && value !== id);
        if (described.length) target.setAttribute("aria-describedby", described.join(" "));
        else target.removeAttribute("aria-describedby");
      }
      target = null;
      panel.current?.hidePopover();
    };
    const show = (element: HTMLElement, immediate: boolean) => {
      if (element === target) return;
      hide();
      target = element;
      timer = setTimeout(
        () => {
          if (!element.isConnected || !element.dataset.tip || !element.getClientRects().length)
            return;
          const rect = element.getBoundingClientRect(),
            tip = panel.current!;
          tip.textContent = element.dataset.tip;
          tip.showPopover();
          const bounds = tip.getBoundingClientRect();
          tip.style.left = `${Math.max(8, Math.min(innerWidth - bounds.width - 8, rect.left + rect.width / 2 - bounds.width / 2))}px`;
          tip.style.top = `${rect.bottom + bounds.height + 12 < innerHeight ? rect.bottom + 8 : Math.max(8, rect.top - bounds.height - 8)}px`;
          element.setAttribute(
            "aria-describedby",
            [element.getAttribute("aria-describedby"), id].filter(Boolean).join(" "),
          );
        },
        immediate ? 0 : 380,
      );
    };
    const over = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const element =
        event.target instanceof Element ? event.target.closest<HTMLElement>("[data-tip]") : null;
      if (element) show(element, false);
      else hide();
    };
    const out = (event: PointerEvent) => {
      if (
        target &&
        event.target instanceof Node &&
        target.contains(event.target) &&
        !(event.relatedTarget instanceof Node && target.contains(event.relatedTarget))
      )
        hide();
    };
    const focus = (event: FocusEvent) => {
      const element =
        event.target instanceof Element ? event.target.closest<HTMLElement>("[data-tip]") : null;
      if (element) show(element, true);
      else hide();
    };
    const scroll = () => {
      // Focusing a control can scroll it into view after its focus event
      const focused = target === document.activeElement ? target : null;
      hide();
      if (focused) show(focused, true);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") hide();
    };
    document.addEventListener("pointermove", over);
    document.addEventListener("pointerout", out);
    document.addEventListener("focusin", focus);
    document.addEventListener("focusout", hide);
    document.addEventListener("keydown", key);
    document.addEventListener("click", hide);
    document.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", hide);
    return () => {
      hide();
      document.removeEventListener("pointermove", over);
      document.removeEventListener("pointerout", out);
      document.removeEventListener("focusin", focus);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("keydown", key);
      document.removeEventListener("click", hide);
      document.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", hide);
    };
  }, [id]);
  return <div id={id} ref={panel} popover="manual" role="tooltip" className="tooltip" />;
}
