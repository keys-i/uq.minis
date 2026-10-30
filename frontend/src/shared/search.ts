/** Compile everyday wording once, then reuse it across local result rows */
import language from "../../../out/tools/search.json";

export function terms(query: string, domain: keyof typeof language.domains) {
  const stop = new Set(`${language.stop} ${language.domains[domain]}`.split(" "));
  let excluded = false,
    either = false;
  const topics: { words: string[]; excluded: boolean }[] = [];
  for (const word of query
    .slice(0, 500)
    .normalize("NFKC")
    .toLowerCase()
    .match(/[\p{L}\p{N}_]+/gu) || []) {
    if (["not", "without", "except", "excluding"].includes(word)) excluded = true;
    else if (word === "or") either = true;
    else if (["but", "with"].includes(word)) excluded = false;
    else if (!stop.has(word)) {
      const words = Object.values(language.synonyms).find((words) => words.includes(word)) || [
        word,
      ];
      const previous = topics.at(-1);
      if (either && previous?.excluded === excluded) previous.words.push(...words);
      else topics.push({ words: [...words], excluded });
      either = false;
    }
  }
  return topics;
}

export function matches(text: string, topics: ReturnType<typeof terms>) {
  const normal = text.normalize("NFKC").toLowerCase();
  return topics.every(
    ({ words, excluded }) => words.some((word) => normal.includes(word)) !== excluded,
  );
}
