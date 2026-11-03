import type { Tools } from "../study/model.ts";
import React, { useId, useState } from "react";
import { Icon } from "./icons.tsx";
import { Bubble } from "./bubble.tsx";
import { MotionSettings } from "./display.tsx";

export function Menu({
  tools,
  tool,
  choose,
  account,
}: {
  tools: Tools;
  tool: string;
  choose: (name: string) => void;
  account: () => void;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <aside
      className="sidebar"
      data-open={opened}
      onKeyDown={(event) => {
        if (event.key === "Escape" && opened) {
          setOpened(false);
          event.currentTarget.querySelector<HTMLButtonElement>(".menu-trigger")?.focus();
        }
      }}
    >
      <div className="menu-top">
        <a
          className="brand"
          href={import.meta.env.BASE_URL}
          aria-label="minis home"
          onClick={(event) => {
            if (event.metaKey || event.ctrlKey) return;
            event.preventDefault();
            choose("home");
          }}
        >
          <span className="brand-mark" aria-hidden="true">
            ✦
          </span>
          <span className="nav-label">
            minis<small>little tools, good days</small>
          </span>
        </a>
        <button
          type="button"
          className="menu-trigger"
          aria-label={opened ? "Close mini menu" : "Open mini menu"}
          aria-expanded={opened}
          aria-controls="mini-menu"
          onClick={() => setOpened(!opened)}
        >
          <Icon name="menu" />
        </button>
      </div>
      <nav id="mini-menu" aria-label="Your minis">
        {Object.entries(tools).map(([key, item]) => (
          <button
            type="button"
            key={key}
            className={tool === key ? "active" : ""}
            aria-label={item.title}
            data-tip={item.title}
            aria-current={tool === key ? "page" : undefined}
            onClick={() => {
              choose(key);
              setOpened(false);
            }}
          >
            <Icon name={key} />
            <span className="nav-label">
              {item.title}
              <small>{item.about}</small>
            </span>
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <button
          type="button"
          className="menu-account quiet"
          aria-label="Account and settings"
          data-tip="Account and settings"
          aria-haspopup="dialog"
          onClick={account}
        >
          <span className="account-avatar">
            <Icon name="account" />
          </span>
          <span className="nav-label">Account & settings</span>
        </button>
      </div>
    </aside>
  );
}

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
