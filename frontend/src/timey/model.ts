import type { Values } from "../shared/forms.tsx";
import * as z from "zod/mini";
export type { Values } from "../shared/forms.tsx";
export const clipSchema = z.object({
  url: z.string(),
  title: z.optional(z.string()),
  kind: z.enum(["image", "video", "audio"]),
  width: z.number().check(z.positive()),
  height: z.number().check(z.positive()),
  duration: z.number().check(z.nonnegative()),
  complete: z.boolean(),
});
export const videoSchema = z.object({ url: z.string(), title: z.string(), length: z.string() });
export const videosSchema = z.object({ rows: z.array(videoSchema) });
export const uploadSchema = z.object({
  source: z.string().check(z.startsWith("upload:")),
  title: z.string(),
});
const fontSchema = z.object({ name: z.string(), description: z.string(), source: z.string() });
export const fontsSchema = z.object({
  rows: z.array(fontSchema),
  total: z.number(),
  notice: z.string(),
});
export type Font = z.infer<typeof fontSchema>;
export type Video = z.infer<typeof videoSchema>;
export type Clip = z.infer<typeof clipSchema> & { source: string; start: number };

export function configuration(values: Values, action = "render"): Values {
  const { custom_style, instructions, designer, ...settings } = values;
  if (values.style === "custom")
    Object.assign(settings, { style: "minimal", custom_style, instructions, designer });
  if (action !== "render") {
    delete settings.metadata;
    delete settings.first_frame;
  }
  return settings;
}

export function seconds(value: string | number | null | undefined) {
  const text = String(value).trim().toLowerCase();
  if (/^\d+$/.test(text)) return Number(text);
  if (/^\d+:\d{2}(?::\d{2})?$/.test(text)) {
    const parts = text.split(":").map(Number);
    return parts.slice(1).some((part) => part >= 60)
      ? null
      : parts.reduce((sum, part) => sum * 60 + part, 0);
  }
  const match = text.match(/^(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s\s*)?$/);
  return match && match.slice(1).some(Boolean)
    ? Number(match[1] || 0) * 3600 + Number(match[2] || 0) * 60 + Number(match[3] || 0)
    : null;
}

export function video(value: string) {
  try {
    const url = new URL(value);
    if (!/^https?:$/.test(url.protocol) || url.username || url.password) return null;
    const host = url.hostname,
      parts = url.pathname.split("/").filter(Boolean);
    const id =
      host === "youtu.be"
        ? parts[0]
        : ["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"].includes(host)
          ? url.pathname === "/watch"
            ? url.searchParams.get("v")
            : ["shorts", "embed", "live"].includes(parts[0]) && parts.length === 2
              ? parts[1]
              : null
          : null;
    if (!id || !/^[\w-]{11}$/.test(id)) return null;
    return {
      id,
      start: seconds(url.searchParams.get("t") || url.searchParams.get("start") || "0") ?? 0,
      url: `https://www.youtube.com/watch?v=${id}`,
    };
  } catch {
    return null;
  }
}

export const clamp = (value: number, low: number, high: number) =>
  Math.max(low, Math.min(high, value));

export function resume(
  previous: { source: string; time: number },
  clip: Clip,
  duration: number,
  origin: number,
): number {
  const start = clip.start || 0;
  const covered =
    previous.source === clip.source &&
    previous.time >= start &&
    (clip.complete || previous.time < start + duration);
  return clamp((covered ? previous.time : origin) - start, 0, Math.max(0, duration - 0.1));
}

/** Read clipboard and drop data in the same order, without intercepting keyboard shortcuts */
export function transferred(transfer: Pick<DataTransfer, "files" | "getData">): File | string {
  const files = Array.from(transfer.files || []);
  if (files.length > 1) throw new Error("Add one file at a time so each can be checked");
  if (files.length) return files[0];
  return (
    transfer
      .getData("text/uri-list")
      .split(/\r?\n/)
      .find((line) => line && !line.startsWith("#")) || transfer.getData("text/plain")
  );
}

export const pictures = "image/*,video/*,.heic,.heif,.avif,.gif,.webp,.apng,.mkv,.avi";
export const music =
  "audio/*,video/*,.mp3,.m4a,.wav,.flac,.ogg,.opus,.aac,.aiff,.aif,.alac,.wma,.amr";
export const fonts = "font/*,.ttf,.otf,.ttc,.woff,.woff2";

export function clock(value: number | null | undefined) {
  const time = Math.max(0, Math.floor(value || 0));
  return [time >= 3600 ? Math.floor(time / 3600) : null, Math.floor(time / 60) % 60, time % 60]
    .filter((part) => part !== null)
    .map((part, i) => (i ? String(part).padStart(2, "0") : String(part)))
    .join(":");
}

export function placement(values: Values, width: number, height: number) {
  const margin = Math.max(1, Math.round(Math.min(width, height) * 0.025));
  const scale = Math.min(
    Math.min(width / (height > width ? 1000 : 1920), height / 1080) * Number(values.size || 2.4),
    (width - margin * 2) / 540,
    (height - margin * 2) / 234,
  );
  const w = values.overlay_width
    ? Math.min(Math.round(Number(values.overlay_width) * width), width - margin * 2)
    : Math.round(540 * scale);
  const h = values.overlay_height
      ? Math.min(Math.round(Number(values.overlay_height) * height), height - margin * 2)
      : Math.round(234 * scale),
    dx = width - w - 2 * margin,
    dy = height - h - 2 * margin;
  const custom = values.x !== "" && values.x != null && values.y !== "" && values.y != null;
  const x = custom
    ? Number(values.x)
    : values.position?.endsWith("left")
      ? 0
      : ["centre", "bottom-centre"].includes(values.position)
        ? 0.5
        : 1;
  const y = custom
    ? Number(values.y)
    : values.position?.startsWith("bottom")
      ? 1
      : values.position === "centre"
        ? 0.5
        : 0;
  return {
    left:
      !custom && x === 0.5 ? Math.floor((width - w) / 2) : margin + Math.round(clamp(x, 0, 1) * dx),
    top:
      !custom && y === 0.5
        ? Math.floor((height - h) / 2)
        : margin + Math.round(clamp(y, 0, 1) * dy),
    w,
    h,
    margin,
    dx,
    dy,
    x,
    y,
  };
}

export function move(values: Values, width: number, height: number, dx: number, dy: number) {
  const box = placement(values, width, height);
  return {
    x: String(clamp(box.x + dx / Math.max(1, box.dx), 0, 1)),
    y: String(clamp(box.y + dy / Math.max(1, box.dy), 0, 1)),
  };
}

export function resize(
  values: Values,
  width: number,
  height: number,
  dx: number,
  dy: number,
  edge = "se",
) {
  const box = placement(values, width, height),
    sx = edge.includes("w") ? -1 : edge.includes("e") ? 1 : 0,
    sy = edge.includes("n") ? -1 : edge.includes("s") ? 1 : 0;
  const w = sx
    ? clamp(
        box.w + dx * sx,
        width * 0.05,
        sx > 0 ? width - box.margin - box.left : box.left + box.w - box.margin,
      )
    : box.w;
  const h = sy
    ? clamp(
        box.h + dy * sy,
        height * 0.05,
        sy > 0 ? height - box.margin - box.top : box.top + box.h - box.margin,
      )
    : box.h;
  const patch = { overlay_width: String(w / width), overlay_height: String(h / height) },
    next = placement({ ...values, ...patch }, width, height);
  const left = sx < 0 ? box.left + box.w - next.w : box.left,
    top = sy < 0 ? box.top + box.h - next.h : box.top;
  return {
    ...patch,
    x: String(clamp((left - box.margin) / Math.max(1, next.dx), 0, 1)),
    y: String(clamp((top - box.margin) / Math.max(1, next.dy), 0, 1)),
  };
}

export function scale(values: Values, width: number, height: number, size: number) {
  const patch: Values = { size: String(size) };
  if (values.overlay_width || values.overlay_height) {
    const box = placement(values, width, height);
    const ratio = clamp(
      Number(size) / Number(values.size || 2.4),
      Math.max(Math.round(width * 0.05) / box.w, Math.round(height * 0.05) / box.h),
      Math.min((width - box.margin * 2) / box.w, (height - box.margin * 2) / box.h),
    );
    patch.overlay_width = String(clamp((box.w * ratio) / width, 0.05, 1));
    patch.overlay_height = String(clamp((box.h * ratio) / height, 0.05, 1));
  }
  return patch;
}

export function dock(x: number, y: number, width: number, height: number, free = false) {
  if (free || width <= 0 || height <= 0 || x < 0 || y < 0 || x > width || y > height) return null;
  const edge = Math.min(24, width * 0.08, height * 0.08);
  const horizontal = x <= edge ? 0 : x >= width - edge ? 1 : null;
  const vertical = y <= edge ? 0 : y >= height - edge ? 1 : null;
  return horizontal == null && vertical == null
    ? null
    : { x: String(horizontal ?? 0.5), y: String(vertical ?? 0.5) };
}

export function dial(x: number, y: number, maximum = 7200, gap = false) {
  const step = gap ? 1 : 15;
  return clamp(Math.round((phase(x, y) * maximum) / step) * step, 0, maximum);
}

export const phase = (x: number, y: number) =>
  ((Math.atan2(x, -y) + Math.PI * 2) % (Math.PI * 2)) / (Math.PI * 2);

export function wind(previous: number, next: number) {
  const last = ((previous % 1) + 1) % 1;
  let delta = next - last;
  if (delta > 0.5) delta--;
  else if (delta < -0.5) delta++;
  return previous + delta;
}

export function recoil(pull: number): Keyframe[] {
  // An underdamped return preserves the release position, overshoots and settles
  return Array.from({ length: 25 }, (_, frame) => {
    const t = frame / 24;
    const spring = frame === 24 ? 0 : Math.exp(-7 * t) * Math.cos(13 * t);
    const stretch = Math.abs(pull) * spring;
    return {
      offset: t,
      transform: `rotate(${pull * 360 * spring}deg) scale(${1 + stretch},${1 - stretch * 0.65})`,
    };
  });
}
