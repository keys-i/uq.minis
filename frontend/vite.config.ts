import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vitest/config";
import type { UserConfig } from "vite";

// TOML owns settings; this adapter owns the executable React plugin
const settings = JSON.parse(
  readFileSync(new URL("../out/tools/vite.json", import.meta.url), "utf8"),
) as UserConfig;

export default defineConfig({ ...settings, plugins: [react()] });
