import { useSyncExternalStore } from "react";
import en from "./locales/en.json";
import ru from "./locales/ru.json";
import es from "./locales/es.json";
import pt from "./locales/pt-BR.json";
import zh from "./locales/zh-CN.json";
import fr from "./locales/fr.json";
import it from "./locales/it.json";
import de from "./locales/de.json";
import ja from "./locales/ja.json";
import ko from "./locales/ko.json";
import ar from "./locales/ar.json";
import hi from "./locales/hi.json";

export const languages = {
  en: "English",
  ru: "Русский",
  es: "Español",
  "pt-BR": "Português (Brasil)",
  "zh-CN": "简体中文",
  fr: "Français",
  it: "Italiano",
  de: "Deutsch",
  ja: "日本語",
  ko: "한국어",
  ar: "العربية",
  hi: "हिन्दी",
};
export type Locale = keyof typeof languages;
const catalogs: Record<Locale, Record<string, string>> = {
  en,
  ru,
  es,
  "pt-BR": pt,
  "zh-CN": zh,
  fr,
  it,
  de,
  ja,
  ko,
  ar,
  hi,
};
export function detectLocale(value: string): Locale {
  const language = value.toLowerCase().split(/[-_]/)[0];
  if (language === "pt") return "pt-BR";
  if (language === "zh") return "zh-CN";
  return Object.hasOwn(languages, language) ? (language as Locale) : "en";
}
export function readPreference(key: string): string | null {
  try {
    return localStorage.getItem(`sherlock.${key}`);
  } catch {
    return null;
  }
}
export function savePreference(key: string, value: string) {
  try {
    localStorage.setItem(`sherlock.${key}`, value);
  } catch {
    /* Session preference remains usable. */
  }
}
const saved = readPreference("locale");
let locale: Locale =
  saved && Object.hasOwn(languages, saved)
    ? (saved as Locale)
    : detectLocale(navigator.language);
const listeners = new Set<() => void>();
export function setLocale(next: Locale) {
  if (!Object.hasOwn(languages, next)) return;
  locale = next;
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
  savePreference("locale", locale);
  listeners.forEach((listener) => listener());
}
export const currentLocale = () => locale;
export function useLocale() {
  return useSyncExternalStore((callback) => {
    listeners.add(callback);
    return () => {
      listeners.delete(callback);
    };
  }, currentLocale);
}
export function t(
  key: string,
  params: Record<string, string | number> = {},
): string {
  const template = Object.hasOwn(catalogs[locale], key)
    ? catalogs[locale][key]
    : Object.hasOwn(en, key)
      ? (en as Record<string, string>)[key]
      : key;
  return template.replace(/#?\{(\w+)\}/g, (match, name: string) => {
    if (!Object.hasOwn(params, name)) return match;
    const value = `${match.startsWith("#") ? "#" : ""}${params[name]}`;
    // Isolate inserted IDs, timestamps and Latin units in Arabic sentences.
    return locale === "ar" ? `\u2068${value}\u2069` : value;
  });
}
export const number = (value: number, digits = 0) =>
  new Intl.NumberFormat(locale, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
export const time = (value?: string) =>
  value
    ? new Date(value).toLocaleTimeString(locale, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";
export const date = (value: string) =>
  new Date(value).toLocaleDateString(locale);
export const size = (bytes: number) => `${number(bytes / 1024 / 1024, 1)} MiB`;
export function duration(seconds: number) {
  const unit = seconds >= 3600 ? "hour" : seconds >= 60 ? "minute" : "second";
  const amount =
    seconds >= 3600 ? seconds / 3600 : seconds >= 60 ? seconds / 60 : seconds;
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: unit === "hour" ? 1 : 0,
  }).format(
    Math.floor(amount * (unit === "hour" ? 10 : 1)) /
      (unit === "hour" ? 10 : 1),
  );
}
document.documentElement.lang = locale;
document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
