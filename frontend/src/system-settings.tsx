import React, { useEffect, useState } from "react";
import { api } from "./api";
import { getLocale, t, useLanguage } from "./i18n";

const moduleLabels: Record<string, string> = {
  system: "Système",
  monitoring: "Supervision",
  services: "Services",
  ollama: "Ollama",
  openwebui: "OpenWebUI",
  docker: "Docker",
  podman: "Podman",
};
const statusLabels: Record<string, string> = {
  available: "Disponible",
  unavailable: "Indisponible",
  disabled: "Non configuré",
  collecting: "En attente",
  stale: "Données anciennes",
};
type Health = {
  environment?: {
    os: string;
    kernel_version: string | null;
    python_version: string;
  };
  modules?: { id: string; status: string }[];
  version: string;
  release_date: string | null;
  checked_at: string;
  read_only: boolean;
  storage: { status: string };
};
export function SystemSettingsView({ token }: { token: string }) {
  useLanguage();
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError("");
    void api<Health>("health", token, controller.signal)
      .then((data) => {
        if (
          !data ||
          typeof data.version !== "string" ||
          !Number.isFinite(Date.parse(data.checked_at)) ||
          !(
            data.release_date === null ||
            (typeof data.release_date === "string" &&
              /^\d{4}-\d{2}-\d{2}$/.test(data.release_date))
          ) ||
          typeof data.read_only !== "boolean" ||
          !["available", "unavailable"].includes(data.storage?.status)
        )
          throw new Error(t("Réponse de vérification invalide"));
        if (
          data.environment &&
          (typeof data.environment.os !== "string" ||
            typeof data.environment.python_version !== "string" ||
            !(
              data.environment.kernel_version === null ||
              typeof data.environment.kernel_version === "string"
            ))
        )
          throw new Error(t("Réponse de vérification invalide"));
        if (
          data.modules &&
          (!Array.isArray(data.modules) ||
            data.modules.length > 7 ||
            new Set(data.modules.map((row) => row?.id)).size !==
              data.modules.length ||
            data.modules.some(
              (row) =>
                !row ||
                !Object.prototype.hasOwnProperty.call(moduleLabels, row.id) ||
                !Object.prototype.hasOwnProperty.call(statusLabels, row.status),
            ))
        )
          throw new Error(t("Réponse de vérification invalide"));
        if (!controller.signal.aborted) setHealth(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError((e as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [token, refresh]);
  return (
    <section className="panel">
      <h2>{t("Paramètres système")}</h2>
      <p>
        {t(
          "Ce contrôle vérifie la disponibilité de l’application et du stockage local. Il ne valide ni les mises à jour, ni les tests, ni les opérations système.",
        )}
      </p>
      <button disabled={busy} onClick={() => setRefresh((value) => value + 1)}>
        {t("Vérifier maintenant")}
      </button>
      {busy && (
        <p role="status">{t("Vérification de disponibilité en cours…")}</p>
      )}
      {error && (
        <p role="alert">
          {t(error)} {health && t("— les données précédentes sont anciennes.")}
        </p>
      )}
      {health && (
        <dl>
          <dt>{t("Version de l’application")}</dt>
          <dd>{health.version}</dd>
          <dt>{t("Date de sortie")}</dt>
          <dd>
            {health.release_date
              ? new Date(`${health.release_date}T00:00:00Z`).toLocaleDateString(
                  getLocale(),
                  { timeZone: "UTC" },
                )
              : t("Non publiée (prototype)")}
          </dd>
          <dt>{t("Date de la dernière vérification")}</dt>
          <dd>
            <time dateTime={health.checked_at}>
              {new Date(health.checked_at).toLocaleString(getLocale())}
            </time>
          </dd>
          <dt>{t("Stockage local")}</dt>
          <dd>
            {t(
              health.storage.status === "available"
                ? "Disponible"
                : "Indisponible",
            )}
          </dd>
          <dt>{t("État des opérations système")}</dt>
          <dd>{t(health.read_only ? "Désactivées" : "Indisponible")}</dd>
        </dl>
      )}
      {health?.environment && (
        <section aria-label={t("Environnement d’exécution")}>
          <h3>{t("Environnement d’exécution")}</h3>
          <dl>
            <dt>{t("Système d’exploitation")}</dt>
            <dd>{health.environment.os}</dd>
            <dt>{t("Version du noyau")}</dt>
            <dd>{health.environment.kernel_version || t("Indisponible")}</dd>
            <dt>Python</dt>
            <dd>{health.environment.python_version}</dd>
          </dl>
        </section>
      )}
      {health?.modules && (
        <section aria-label={t("Disponibilité des modules")}>
          <h3>{t("Disponibilité des modules")}</h3>
          <p>
            {t(
              "Résumé des dernières collectes. Vérifier maintenant ne relance pas les sondes et n’active aucune intégration.",
            )}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("Module")}</th>
                  <th>{t("État")}</th>
                </tr>
              </thead>
              <tbody>
                {health.modules.map((module) => (
                  <tr key={module.id}>
                    <td>{t(moduleLabels[module.id] || "Indisponible")}</td>
                    <td>{t(statusLabels[module.status] || "Indisponible")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}
