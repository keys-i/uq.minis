import type { TrailNode } from "./model.ts";

export function layout(nodes: TrailNode[]) {
  const depth = Math.max(0, ...nodes.map((node) => node.depth)),
    rows = Math.max(
      1,
      ...Array.from(
        { length: depth + 1 },
        (_, i) => nodes.filter((node) => node.depth === i).length,
      ),
    );
  const width = (depth + 1) * 250,
    height = rows * 116 + 24;
  const points = new Map<string, { x: number; y: number }>();
  for (let level = 0; level <= depth; level++) {
    const column = nodes.filter((node) => node.depth === level);
    column.forEach((node, i) =>
      points.set(node.code, {
        x: (depth - level) * 250 + 125,
        y: ((i + 0.5) * height) / column.length,
      }),
    );
  }
  return { width, height, points };
}

export function connected(nodes: Pick<TrailNode, "code" | "required">[], code: string) {
  const active = new Set<string>(),
    byCode = new Map(nodes.map((node) => [node.code, node]));
  const visit = (current: string) => {
    if (active.has(current)) return;
    active.add(current);
    for (const next of byCode.get(current)?.required || []) visit(next);
  };
  visit(code);
  const pending = [code],
    seen = new Set(pending);
  for (const current of pending)
    for (const node of nodes)
      if (node.required.includes(current) && !seen.has(node.code)) {
        seen.add(node.code);
        active.add(node.code);
        pending.push(node.code);
      }
  return active;
}
