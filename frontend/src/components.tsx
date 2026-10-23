import React from "react";
import { t, formatNumber, getLocale } from "./i18n";
import type { History } from "./types";
export const pct = (n: number | null | undefined) =>
  n == null ? t("Indisponible") : `${formatNumber(n)} %`;
export function Card({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <article className="card">
      <p>{label}</p>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}
export function Graph({
  history,
  persistent = false,
}: {
  history: History;
  persistent?: boolean;
}) {
  function curve(field: "cpu_percent" | "memory_percent") {
    const first = Date.parse(history[0]?.collected_at || "");
    const last = Date.parse(history.at(-1)?.collected_at || "");
    let previous = NaN;
    return history
      .map((point, index) => {
        const value = point[field];
        const when = Date.parse(point.collected_at);
        const gap = when - previous > (persistent ? 90000 : 6000);
        const move = index === 0 || gap || !Number.isFinite(previous);
        previous = value == null ? NaN : when;
        if (value == null || !Number.isFinite(value)) return "";
        const x = last > first ? ((when - first) / (last - first)) * 800 : 0;
        return `${move ? "M" : "L"}${x},${150 - Math.max(0, Math.min(100, value)) * 1.5}`;
      })
      .join(" ");
  }
  return (
    <section className="panel">
      <h2>
        {t("Activité CPU")}{" "}
        <small>
          {persistent
            ? t("Historique local · résolution une minute")
            : t("15 min maximum · mémoire vive uniquement")}
        </small>
      </h2>
      <svg
        viewBox="0 0 800 150"
        role="img"
        aria-label={t("Utilisation CPU, de 0 à 100 pour cent")}
      >
        <path d="M0 1H800 M0 75H800 M0 149H800" className="grid" />
        <path className="line" d={curve("cpu_percent")} />
        {persistent && (
          <path className="memory-line" d={curve("memory_percent")} />
        )}
      </svg>
      <div className="graph-label">
        <span>{persistent ? "CPU · RAM · 0–100 %" : "0–100 %"}</span>
        <span>
          {history.length
            ? new Date(history[0].collected_at).toLocaleTimeString(getLocale())
            : t("En attente")}{" "}
          {t("→ maintenant")}{" "}
        </span>
      </div>
    </section>
  );
}
