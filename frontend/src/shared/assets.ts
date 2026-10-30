// Import URLs rather than SVG markup so artwork stays cacheable and outside the document
export const vectors = import.meta.glob<string>("../../assets/**/*.svg", {
  eager: true,
  query: "?url",
  import: "default",
});

/** Resolve only bundled artwork; missing names fail during development instead of hiding an icon */
export function vector(name: string): string {
  const url = vectors[`../../assets/${name}.svg`];
  if (!url) throw new Error(`Missing bundled artwork: ${name}`);
  return url;
}
