export function matchLanguage(languages: Record<string, string>, tag: string) {
  try {
    const locale = new Intl.Locale(tag),
      code = locale.baseName.toLowerCase();
    const exact = Object.keys(languages).find((key) => key.toLowerCase() === code);
    if (exact) return exact;
    if (languages[locale.language]) return locale.language;
    const expanded = locale.maximize();
    return (
      Object.keys(languages).find(
        (key) => key.toLowerCase() === `${locale.language}-${expanded.script}`.toLowerCase(),
      ) || Object.keys(languages).find((key) => key.toLowerCase().startsWith(`${locale.language}-`))
    );
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
  }
}

export function orderLanguages(languages: Record<string, string>, preferred: string[] = []) {
  const first = [
    ...new Set([
      ...preferred
        .map((tag) => matchLanguage(languages, tag))
        .filter((code): code is string => !!code),
      "en",
    ]),
  ].filter((code) => languages[code]);
  const collator = new Intl.Collator(first[0] || "en");
  const rest = Object.keys(languages)
    .filter((code) => !first.includes(code))
    .sort((left, right) => collator.compare(languages[left], languages[right]));
  return [...first, ...rest];
}
