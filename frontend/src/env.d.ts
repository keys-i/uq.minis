import "react";

declare module "react" {
  interface CSSProperties {
    [property: `--${string}`]: string | number;
    anchorName?: string;
    positionAnchor?: string;
  }
}

declare global {
  interface Navigator {
    connection?: { readonly saveData?: boolean };
  }
}
