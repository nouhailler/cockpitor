import React from "react";
import { t, formatNumber } from "./i18n";
import { bytes } from "./format";
import type { Module } from "./types";
const statusLabel = (status: string) =>
  ({
    available: t("Disponible"),
    unavailable: t("Indisponible"),
    disabled: t("Désactivé"),
  })[status] || status;
type AIStatus = Module & { ollama?: Module; openwebui?: Module };
export function AIView({ data }: { data: AIStatus }) {
  return (
    <>
      {[data.ollama, data.openwebui].map(
        (m, i) =>
          m && (
            <section className="panel" key={i}>
              <h2>
                {i === 0 ? "Ollama" : "OpenWebUI"}{" "}
                <span className="badge">{statusLabel(m.status)}</span>
              </h2>
              <p>
                {(m.message ? t(m.message) : null) ||
                  `${m.latency_ms == null ? t("Indisponible") : formatNumber(m.latency_ms, 0)} ms`}
              </p>
              {m.url && (
                <a href={m.url} target="_blank" rel="noreferrer">
                  {t("Ouvrir")} {m.url} ↗
                </a>
              )}
              {m.models && (
                <>
                  <h3>{t("Modèles installés")}</h3>
                  {!m.models.length && <p>{t("Aucun modèle installé.")}</p>}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>{t("Nom")}</th>
                          <th>{t("Taille")}</th>
                          <th>{t("Famille")}</th>
                          <th>{t("Quantification")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {m.models.map((model) => (
                          <tr key={model.name}>
                            <td>{model.name}</td>
                            <td>{bytes(model.size)}</td>
                            <td>{model.family || t("Indisponible")}</td>
                            <td>{model.quantization || t("Indisponible")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {m.loaded && (
                <p>
                  {t("Modèles chargés :")}{" "}
                  {m.loaded.map((model) => model.name).join(", ") || t("aucun")}
                </p>
              )}
            </section>
          ),
      )}
    </>
  );
}
