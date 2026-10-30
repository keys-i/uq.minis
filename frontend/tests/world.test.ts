import { expect, test } from "vitest";
import { lighting } from "../src/wildlife/world.ts";

test("solar light blends through dawn and stale events fall back to the habitat clock", () => {
  const weather = {
    habitat: "otter",
    updated: "",
    expires: 0,
    stale: false,
    sunrise: "2026-10-21T06:00:00Z",
    sunset: "2026-10-21T18:00:00Z",
  };
  expect(lighting(new Date("2026-10-21T06:00:00Z"), 6, weather)).toEqual({
    amount: 0.5,
    phase: "dawn",
  });
  expect(lighting(new Date("2026-10-21T12:00:00Z"), 12, weather)).toEqual({
    amount: 1,
    phase: "day",
  });
  const dawn = ["05:30", "05:45", "06:00", "06:15", "06:30"].map(
    (time) => lighting(new Date(`2026-10-21T${time}:00Z`), 6, weather).amount,
  );
  expect(dawn).toEqual([...dawn].sort((a, b) => a - b));
  expect(dawn[0]).toBeLessThan(0.1);
  expect(dawn[2]).toBe(0.5);
  expect(dawn[4]).toBeGreaterThan(0.9);
  expect(lighting(new Date("2026-10-23T12:00:00Z"), 12, weather).amount).toBe(1);
  expect(lighting(new Date("2026-10-21T00:00:00Z"), 0, weather).phase).toBe("night");
  expect(
    lighting(new Date(), 0, { ...weather, sunrise: null, sunset: null, polar_day: true }).phase,
  ).toBe("day");
});
