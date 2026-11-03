// @vitest-environment jsdom
import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, test, vi } from "vitest";
import { fingerprint, restoreDraft, saveDraft } from "../src/shared/draft.ts";
import { MiniForm, initial } from "../src/shared/forms.tsx";
import type { Schema } from "../src/shared/schema.ts";

const schema: Schema = {
  fields: [
    { name: "contact_email", label: "Email", type: "email" },
    { name: "title", label: "Event name" },
    { name: "password", label: "Password", type: "password" },
    { name: "oauth_device_code", label: "Device code" },
    { name: "confirmation", label: "Confirm", type: "checkbox" },
    { name: "attachment", label: "Receipt", type: "file" },
  ],
};

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.useRealTimers();
});

test("draft envelopes stay scoped, bounded to editable values and schema compatible", () => {
  saveDraft("person@example.test", "event", schema, {
    contact_email: "person@example.test",
    title: "Movie night",
    password: "do-not-store",
    oauth_device_code: "do-not-store",
    confirmation: "on",
    attachment: "do-not-store",
  });
  expect(localStorage).toHaveLength(1);
  const storageKey = localStorage.key(0)!;
  expect(storageKey).not.toContain("person@example.test");
  const envelope = JSON.parse(localStorage.getItem(storageKey)!);
  expect(envelope).toMatchObject({
    version: 2,
    mini: "event",
    form: "main",
    schema: fingerprint(schema),
    values: { contact_email: "person@example.test", title: "Movie night" },
  });
  expect(envelope.values).not.toHaveProperty("password");
  expect(envelope.values).not.toHaveProperty("oauth_device_code");
  expect(envelope.values).not.toHaveProperty("confirmation");

  expect(restoreDraft("person@example.test", "event", schema, initial(schema))).toMatchObject({
    found: true,
    values: { contact_email: "person@example.test", title: "Movie night", password: "" },
  });
  expect(
    restoreDraft(
      "person@example.test",
      "event",
      { fields: [...schema.fields, { name: "date", label: "Date", type: "date" }] },
      {},
    ).found,
  ).toBe(false);
  expect(localStorage).toHaveLength(0);
});

test("generated fields save after inactivity and expose a real clear action", () => {
  vi.useFakeTimers();
  render(
    <MiniForm
      schema={schema}
      draft={{ workspace: "guest:abc", mini: "event" }}
      submit={() => {}}
    />,
  );
  const email = screen.getByLabelText("Email");
  expect(email).toHaveAttribute("autocomplete", "email");
  fireEvent.change(email, { target: { value: "hello@example.test" } });
  act(() => vi.advanceTimersByTime(250));
  expect(localStorage).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Clear saved draft" }));
  expect(email).toHaveValue("");
  expect(localStorage).toHaveLength(0);
});
