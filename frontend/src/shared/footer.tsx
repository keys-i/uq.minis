import { useId } from "react";
import { Bubble } from "./bubble.tsx";
import { MotionSettings } from "./display.tsx";
import { Icon } from "./icons.tsx";

export function Footer() {
  const help = useId();
  return (
    <footer className="site-footer tectonic-footer">
      <div className="tectonic-field" aria-hidden="true">
        <span className="tectonic-plate plate-west" />
        <span className="tectonic-plate plate-east" />
        <span className="tectonic-plate plate-ridge" />
      </div>
      <a className="footer-wordmark" href="https://keysi.dev">
        keysi.dev
      </a>
      <nav aria-label="Footer">
        <a
          className="footer-symbol"
          href="https://github.com/keys-i"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="GitHub"
          data-tip="GitHub"
        >
          <Icon name="github" />
        </a>
        <a
          className="footer-symbol"
          href="https://linkedin.com/in/radhesh-g"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="LinkedIn"
          data-tip="LinkedIn"
        >
          <Icon name="linkedin" />
        </a>
        <button
          type="button"
          className="footer-symbol footer-preferences quiet"
          aria-label="Accessibility and sound"
          aria-haspopup="dialog"
          data-tip="Accessibility and sound"
          popoverTarget={help}
        >
          <Icon name="look" />
          <Icon name="volume" />
        </button>
      </nav>
      <Bubble id={help} label="Accessibility and sound" className="speech-bubble access-panel">
        <MotionSettings />
      </Bubble>
    </footer>
  );
}
