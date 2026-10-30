// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { MiniShelf, MiniTitle } from "../src/shared/cards.tsx";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

test("focus expands a mini and leaving the shelf restores Planny", async () => {
  const user = userEvent.setup(),
    open = vi.fn();
  render(
    <>
      <MiniShelf
        tools={{
          planny: { title: "Planny", about: "Plan" },
          scrappy: { title: "Scrappy", about: "Courses" },
        }}
        open={open}
      />
      <button>Outside the shelf</button>
    </>,
  );
  const scrappy = screen.getByRole("link", { name: "Scrappy" });
  const featured = screen.getByRole("link", { name: "Planny" }).closest("article");
  expect(screen.getByRole("link", { name: "Planny" })).toBeInTheDocument();
  await user.click(scrappy);
  expect(open).toHaveBeenCalledWith("scrappy");
  expect(featured).not.toHaveClass("is-featured");
  expect(scrappy.closest("article")).toHaveClass("is-featured");
  await user.click(screen.getByRole("button", { name: "Outside the shelf" }));
  expect(featured).toHaveClass("is-featured");
  expect(scrappy.closest("article")).not.toHaveClass("is-featured");
});

test.each(["/", "/mini/"])("mini links preserve navigation beneath %s", async (base) => {
  vi.stubEnv("BASE_URL", base);
  const user = userEvent.setup(),
    open = vi.fn();
  render(<MiniTitle name="planny" title="Planny" open={open} />);
  const link = screen.getByRole("link", { name: "Planny" });
  expect(link).toHaveAttribute("href", `${base}?m=planny`);
  // Observe the app's decision, then prevent navigation beyond JSDOM's document
  const navigation = vi.fn((event: MouseEvent) => {
    const handled = event.defaultPrevented;
    event.preventDefault();
    return handled;
  });
  document.addEventListener("click", navigation);
  try {
    for (const modifier of ["metaKey", "ctrlKey", "shiftKey", "altKey"]) {
      fireEvent.click(link, { [modifier]: true });
      expect(navigation).toHaveLastReturnedWith(false);
    }
    expect(open).not.toHaveBeenCalled();
    await user.click(link);
    expect(navigation).toHaveLastReturnedWith(true);
    expect(open).toHaveBeenCalledExactlyOnceWith("planny");
  } finally {
    document.removeEventListener("click", navigation);
  }
});
