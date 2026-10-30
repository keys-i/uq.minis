import { languagesSchema } from "./schema.ts";
import { Icon } from "./icons.tsx";
import React, { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { api } from "./api.ts";
import { orderLanguages } from "./locale.ts";
import { Translations } from "./translate.ts";
import { useSession } from "./session.ts";

interface LanguageState {
  language: string;
  languages: Record<string, string>;
  translate: (
    text: string,
    source?: string,
    signal?: AbortSignal,
    alternate?: boolean,
  ) => Promise<string>;
  choice?: string;
  ordered?: string[];
  setLanguage: (code: string) => void;
  configured?: boolean;
  provider?: string;
  device?: boolean;
  revision?: number;
  error?: string;
  enable: () => void;
}
const Context = createContext<LanguageState>({
  language: "en",
  translate: async (text: string) => text,
  languages: { en: "English" },
  setLanguage: () => {},
  enable: () => {},
});

export function Language({ children }: { children: React.ReactNode }) {
  const hosted = useSession((state) => state.hosted),
    user = useSession((state) => state.user);
  const [choice, setChoice] = useState(() => {
    try {
      return localStorage.getItem("minis.language") || "browser";
    } catch {
      return "browser";
    }
  });
  const preferred = typeof navigator === "undefined" ? ["en"] : [...navigator.languages];
  const [options, setOptions] = useState<{
      languages: Record<string, string>;
      configured: boolean;
      provider?: string;
    }>({ languages: { en: "English" }, configured: false }),
    [error, setError] = useState(""),
    [device, setDevice] = useState(() => !!globalThis.Translator),
    [revision, setRevision] = useState(0);
  const ordered = orderLanguages(options.languages, preferred),
    language = choice === "browser" ? ordered[0] : options.languages[choice] ? choice : "en",
    configured = options.configured && (hosted === false || !!user);
  const interpreter = useRef<Translations>(null);
  interpreter.current ??= new Translations();
  useEffect(() => {
    const controller = new AbortController();
    api("/api/languages", languagesSchema, undefined, controller.signal)
      .then((result) => {
        setOptions(result);
        if (choice !== "browser" && !result.languages[choice]) setChoice("browser");
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    setError("");
    try {
      localStorage.setItem("minis.language", choice);
    } catch (error) {
      if (!["SecurityError", "QuotaExceededError"].includes((error as Error).name)) throw error;
    }
  }, [language, choice]);
  useEffect(() => () => interpreter.current?.dispose(), []);
  function translate(text: string, source = "en", signal?: AbortSignal, alternate = false) {
    if (!configured && !globalThis.Translator) return Promise.resolve(text);
    return interpreter
      .current!.read(text, source, language, { signal, alternate, server: configured })
      .catch((error) => {
        if (error.name !== "AbortError")
          setError(
            ["NotSupportedError", "NotAllowedError"].includes((error as Error).name)
              ? "Your browser can't translate this text yet. The original is still available"
              : error.message,
          );
        throw error;
      });
  }
  function choose(code: string) {
    const target = code === "browser" ? ordered[0] : code;
    setChoice(code);
    setError("");
    if (!globalThis.Translator) {
      setDevice(false);
      setRevision((value) => value + 1);
      return;
    }
    setDevice(true);
    interpreter.current!.prepare(target).then(
      () => setRevision((value) => value + 1),
      () => {
        setRevision((value) => value + 1);
        if (!configured)
          setError(
            "Your browser can't prepare this language pair yet; the original is still available",
          );
      },
    );
  }
  return (
    <Context.Provider
      value={{
        language,
        choice,
        ordered,
        languages: options.languages,
        setLanguage: choose,
        configured,
        provider: options.provider,
        device,
        revision,
        error,
        translate,
        enable: () => choose(choice),
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function LanguagePicker() {
  const {
      language,
      ordered = ["en"],
      languages,
      setLanguage,
      configured,
      error,
      enable,
    } = useContext(Context),
    id = useId(),
    [query, setQuery] = useState("");
  const visible = ordered.filter((code) =>
    `${languages[code]} ${code}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  return (
    <div className="language-picker">
      <button
        type="button"
        className="language-trigger secondary"
        popoverTarget={id}
        aria-haspopup="dialog"
      >
        <Icon name="language" />
        <span lang={language}>{languages[language]?.split(" / ")[0] || "English"}</span>
        <Icon name="chevron" className="menu-chevron" />
      </button>
      <section
        id={id}
        popover="auto"
        role="dialog"
        aria-label="Choose your reading language"
        className="language-menu"
        onToggle={(event) => {
          if (event.newState === "open")
            event.currentTarget.querySelector<HTMLInputElement>("input[type=search]")?.focus();
        }}
      >
        <label className="language-search">
          <Icon name="search-small" />
          <input
            type="search"
            aria-label="Find a language"
            placeholder="Find your language…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <fieldset className="language-choices">
          <legend className="sr-only">Reading language</legend>
          {visible.map((code) => (
            <label className="language-option" key={code} data-selected={code === language}>
              <input
                type="radio"
                name={`language-${id}`}
                value={code}
                checked={code === language}
                onChange={() => setLanguage(code)}
              />
              <span lang={code} dir="auto">
                {languages[code]}
              </span>
            </label>
          ))}
          {!visible.length && <p>No matching language / try its English name</p>}
        </fieldset>
        {error && (
          <div className="rule-note" role="status">
            <p>{error}</p>
            {configured && (
              <button type="button" className="quiet" onClick={enable}>
                Retry translation
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

export function T({
  children,
  source = "en",
  original = false,
}: {
  children?: React.ReactNode;
  source?: string;
  original?: boolean;
}) {
  const { language, translate, configured, device, revision } = useContext(Context),
    [result, setResult] = useState<{ identity: React.ReactNode; value: string } | null>(null),
    [alternate, setAlternate] = useState<React.ReactNode>(null),
    ref = useRef<HTMLSpanElement>(null);
  const identity = typeof children === "string" ? `${source}:${language}:${children}` : children,
    value = result && result.identity === identity ? result.value : children,
    useAlternate = alternate === identity;
  useEffect(() => {
    if (typeof children !== "string" || children.length > 4000) return;
    const controller = new AbortController();
    let observer: IntersectionObserver | undefined;
    const run = () =>
      translate(children, source, controller.signal, useAlternate)
        .then((text) => {
          if (!controller.signal.aborted) setResult({ identity, value: text });
        })
        .catch(() => {});
    if (typeof IntersectionObserver === "undefined") run();
    else {
      observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer?.disconnect();
          run();
        }
      });
      observer.observe(ref.current!);
    }
    return () => {
      observer?.disconnect();
      controller.abort();
    };
  }, [children, source, language, configured, device, revision, useAlternate]);
  const changed = value !== children;
  return (
    <span
      ref={ref}
      className="translation"
      lang={changed ? language : source === "auto" ? undefined : source}
      dir="auto"
    >
      <span
        key={typeof value === "string" || typeof value === "number" ? value : undefined}
        className={changed ? "script-morph" : undefined}
      >
        {value}
      </span>
      {original && changed && (
        <details className="original-text">
          <summary>Original / automatic translation</summary>
          <span dir="auto">{children}</span>
          {configured && !useAlternate && (
            <button type="button" className="quiet" onClick={() => setAlternate(identity)}>
              Try another translation
            </button>
          )}
        </details>
      )}
    </span>
  );
}
