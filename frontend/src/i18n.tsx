import React, { useSyncExternalStore } from "react";
import fr from "../../locales/fr.json";
import en from "../../locales/en.json";
export type Language = "fr" | "en";
const catalogs: Record<Language, Record<string, string>> = { fr, en };
const listeners = new Set<() => void>();
let language: Language = "fr";
try {
  if (localStorage.getItem("language") === "en") language = "en";
} catch {
  /* Storage can be unavailable. */
}
if (typeof document !== "undefined") document.documentElement.lang = language;
export const getLanguage = () => language;
export const getLocale = () => (language === "fr" ? "fr-FR" : "en-GB");
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export function useLanguage() {
  return useSyncExternalStore(subscribe, getLanguage, () => "fr" as Language);
}
export function setLanguage(value: Language) {
  if (value !== "fr" && value !== "en") return;
  language = value;
  if (typeof document !== "undefined") document.documentElement.lang = value;
  try {
    localStorage.setItem("language", value);
  } catch {
    /* Optional browser preference. */
  }
  listeners.forEach((listener) => listener());
}
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const patterns = Object.entries(en)
  .filter(([key]) => /\{\d+\}/.test(key))
  .map(([key, value]) => ({
    key,
    value,
    fr: new RegExp(
      "^" +
        key
          .split(/(\{\d+\})/)
          .map((part) => (/^\{\d+\}$/.test(part) ? "(.*?)" : escape(part)))
          .join("") +
        "$",
    ),
    en: new RegExp(
      "^" +
        value
          .split(/(\{\d+\})/)
          .map((part) => (/^\{\d+\}$/.test(part) ? "(.*?)" : escape(part)))
          .join("") +
        "$",
    ),
  }));
export function t(key: string, values: Record<string, unknown> = {}) {
  let result = catalogs[language][key];
  if (result === undefined && language === "fr") {
    const source = Object.keys(en).find(
      (k) => en[k as keyof typeof en] === key,
    );
    if (source) result = fr[source as keyof typeof fr];
  }
  if (result === undefined) {
    for (const pattern of patterns) {
      const match =
        key.match(pattern.fr) ||
        (language === "fr" ? key.match(pattern.en) : null);
      if (match) {
        result = language === "fr" ? pattern.key : pattern.value;
        match.slice(1).forEach((value, index) => {
          values = { ...values, [index]: value };
        });
        break;
      }
    }
  }
  return (result ?? key).replace(/\{(\d+)\}/g, (placeholder, index) =>
    values[index] === undefined ? placeholder : String(values[index]),
  );
}
export const formatNumber = (value: number, digits = 1) =>
  new Intl.NumberFormat(getLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
export function LanguagePicker() {
  const language = useLanguage();
  return (
    <label className="language-picker">
      {t("Langue de la session")}
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value as Language)}
      >
        <option value="fr">Français</option>
        <option value="en">English</option>
      </select>
    </label>
  );
}
