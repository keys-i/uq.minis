import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";
import { resolveConfig } from "vite";

test("roots production assets under /mini", async () => {
  const configFile = fileURLToPath(new URL("../vite.config.ts", import.meta.url));
  const config = await resolveConfig({ configFile }, "build");
  expect(config.base).toBe("/mini/");
});
