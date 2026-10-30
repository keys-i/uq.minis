import { translationSchema } from "./schema.ts";
import type { Failure } from "./api.ts";
import { api } from "./api.ts";

interface TranslatorEngine {
  translate: (text: string, options?: { signal?: AbortSignal }) => Promise<string>;
  destroy: () => void;
}
interface DetectorEngine {
  detect: (text: string) => Promise<{ detectedLanguage: string }[]>;
  destroy: () => void;
}
declare global {
  var Translator:
    | {
        create: (options: {
          sourceLanguage: string;
          targetLanguage: string;
        }) => Promise<TranslatorEngine>;
      }
    | undefined;
  var LanguageDetector: { create: () => Promise<DetectorEngine> } | undefined;
}

export class Translations {
  engines = new Map<string, Promise<TranslatorEngine | DetectorEngine>>();
  cache = new Map<string, string>();
  queue: Promise<unknown> = Promise.resolve();
  generation = 0;
  failure: { until: number; error: Failure } | null = null;

  engine(source: "auto"): Promise<DetectorEngine>;
  engine(source: string, target: string): Promise<TranslatorEngine>;
  engine(source: string, target?: string): Promise<TranslatorEngine | DetectorEngine> {
    const key = target ? `${source}:${target}` : "detect";
    if (!this.engines.has(key)) {
      if (this.engines.size >= 3) {
        const [old, pending] = this.engines.entries().next().value!;
        this.engines.delete(old);
        Promise.resolve(pending)
          .then((value) => value.destroy())
          .catch(() => {});
      }
      const pending = target
        ? globalThis.Translator!.create({ sourceLanguage: source, targetLanguage: target })
        : globalThis.LanguageDetector!.create();
      this.engines.set(key, pending);
      pending.catch(() => {
        if (this.engines.get(key) === pending) this.engines.delete(key);
      });
    }
    return this.engines.get(key)!;
  }

  async prepare(target: string) {
    const tasks: Promise<TranslatorEngine | DetectorEngine>[] = [];
    if (globalThis.LanguageDetector) tasks.push(this.engine("auto"));
    if (target !== "en" && globalThis.Translator) tasks.push(this.engine("en", target));
    return Promise.all(tasks);
  }

  reset() {
    this.generation++;
    this.cache.clear();
  }

  read(
    text: string,
    source: string,
    target: string,
    {
      signal,
      server = false,
      alternate = false,
    }: { signal?: AbortSignal; server?: boolean; alternate?: boolean } = {},
  ): Promise<string> {
    if (!text || source === target) return Promise.resolve(text);
    const key = `${target}:${source}:${alternate}:${text}`,
      generation = this.generation;
    const work = this.queue.then(async () => {
      if (signal?.aborted || generation !== this.generation)
        throw new DOMException("Translation changed", "AbortError");
      if (this.cache.has(key)) return this.cache.get(key)!;
      let translated;
      if (!alternate && globalThis.Translator) {
        try {
          let from = source;
          if (from === "auto" && globalThis.LanguageDetector)
            from = (await (await this.engine("auto")).detect(text))[0].detectedLanguage;
          if (signal?.aborted || generation !== this.generation)
            throw new DOMException("Translation changed", "AbortError");
          if (from === target) return text;
          if (from !== "auto")
            translated = await (await this.engine(from, target)).translate(text, { signal });
        } catch (error) {
          if (signal?.aborted || generation !== this.generation)
            throw new DOMException("Translation changed", "AbortError");
          if (!server) throw error;
        }
      }
      if (typeof translated !== "string" || !translated.trim()) {
        if (!server)
          throw new Error(
            "Your browser can't translate this text yet; choose a reading language to prepare it",
          );
        if (this.failure && this.failure.until > performance.now()) throw this.failure.error;
        try {
          translated = (
            await api("/api/translate", translationSchema, { text, target, source }, signal)
          ).text;
          if (typeof translated !== "string" || !translated.trim() || translated.length > 12000)
            throw Object.assign(
              new Error(
                "The translation service returned an invalid result; the original is still available",
              ),
              { status: 502 },
            );
        } catch (caught) {
          const error = caught as Failure;
          if (signal?.aborted || generation !== this.generation)
            throw new DOMException("Translation changed", "AbortError");
          if (
            error.name !== "AbortError" &&
            !signal?.aborted &&
            ((error.retryAfter || 0) > 0 ||
              (error.status || 0) >= 500 ||
              error instanceof TypeError)
          )
            this.failure = { until: performance.now() + (error.retryAfter || 5) * 1000, error };
          throw error;
        }
      }
      if (signal?.aborted || generation !== this.generation)
        throw new DOMException("Translation changed", "AbortError");
      this.cache.set(key, translated);
      while (this.cache.size > 128) this.cache.delete(this.cache.keys().next().value!);
      return translated;
    });
    this.queue = work.catch(() => {});
    return work;
  }

  dispose() {
    this.reset();
    for (const pending of this.engines.values())
      Promise.resolve(pending)
        .then((value) => value.destroy())
        .catch(() => {});
    this.engines.clear();
  }
}
