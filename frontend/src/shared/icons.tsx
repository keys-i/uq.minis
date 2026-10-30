import { vector, vectors } from "./assets.ts";

/** External masks keep the shared icon palette while SVG geometry stays in asset files */
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  const icon = name === "clubs" ? "clubby" : name;
  const source = vectors[`../../assets/icons/${icon}.svg`] || vector("icons/planny");
  return (
    <span
      className={`icon ${className}`}
      aria-hidden="true"
      style={{ maskImage: `url("${source}")` }}
    />
  );
}
