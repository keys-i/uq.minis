import { useId } from "react";
import { Bubble } from "./bubble.tsx";
import { MotionSettings } from "./display.tsx";
import { Icon } from "./icons.tsx";

export function Footer() {
  const help = useId();
  return (
    <footer className="site-footer">
      <span className="made-with">
        Made with <Icon name="love" /> love by{" "}
        <a href="https://github.com/keys-i" target="_blank" rel="noopener noreferrer">
          keys-i
        </a>
      </span>
      <nav aria-label="Footer">
        <button type="button" className="quiet" aria-haspopup="dialog" popoverTarget={help}>
          Accessibility & sound
        </button>
        <a
          className="github-link"
          href="https://github.com/keys-i/uq.minis"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="UQ minis on GitHub"
          data-tip="UQ minis on GitHub"
        >
          <Icon name="github" />
        </a>
      </nav>
      <Bubble id={help} label="Accessibility and sound" className="speech-bubble access-panel">
        <MotionSettings />
      </Bubble>
    </footer>
  );
}
