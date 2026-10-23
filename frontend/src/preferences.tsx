import { t, useLanguage, getLocale, formatNumber } from "./i18n";
import React, { useEffect, useState } from "react";
import { api, saveSettings } from "./api";

export type Rule = {
  id: string;
  metric: string;
  enabled: boolean;
  threshold: number;
  duration_seconds: number;
  severity: "warning" | "critical";
  target: string | null;
  engine: "docker" | "podman" | null;
};
export type Preferences = {
  language: "fr" | "en";
  theme: "dark" | "light" | "system";
  refresh_seconds: number;
  retention_days: number;
  rules: Rule[];
};
type Envelope = { settings: Preferences; csrf_token: string };
const metrics: Record<string, string> = {
  cpu_percent: t("CPU élevé"),
  memory_percent: t("RAM élevée"),
  swap_percent: t("Swap élevé"),
  disk_free_percent: t("Espace disque libre bas"),
  ollama_unavailable: t("Ollama indisponible"),
  service_failed: t("Service en échec"),
  container_stopped: t("Conteneur arrêté"),
};
const states: Record<string, string> = {
  active: t("Active"),
  resolved: t("Résolue"),
  pending: t("Seuil en attente"),
  healthy: t("Normal"),
  unavailable: t("Source indisponible"),
  disabled: t("Désactivée"),
};

export function SettingsView({
  token,
  onSaved,
}: {
  token: string;
  onSaved: (settings: Preferences) => void;
}) {
  useLanguage();
  const [draft, setDraft] = useState<Preferences | null>(null);
  const [csrf, setCsrf] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void api<Envelope>("settings", token, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setDraft(data.settings);
          setCsrf(data.csrf_token);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError((e as Error).message);
      });
    return () => controller.abort();
  }, [token, reload]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setSaving(true);
    setError("");
    setSaved("");
    try {
      const result = await saveSettings<{
        settings: Preferences;
        operation_id: string;
      }>(draft, token, csrf);
      setDraft(result.settings);
      onSaved(result.settings);
      setSaved(
        t("Réglages enregistrés · opération {0}", { 0: result.operation_id }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  function change(index: number, patch: Partial<Rule>) {
    if (draft)
      setDraft({
        ...draft,
        rules: draft.rules.map((r, i) =>
          i === index ? { ...r, ...patch } : r,
        ),
      });
  }
  return (
    <section className="panel">
      <h2>{t("Préférences persistantes")}</h2>
      <p>
        {t(
          "Ces réglages concernent Cockpitor uniquement. Ils ne modifient aucun service, conteneur ou droit système.",
        )}{" "}
      </p>
      {error && (
        <p className="error" role="alert">
          {t(error)}
        </p>
      )}
      {error && !draft && (
        <button
          onClick={() => {
            setError("");
            setReload((v) => v + 1);
          }}
        >
          {t("Réessayer les paramètres")}{" "}
        </button>
      )}
      {saved && <p role="status">{t(saved)}</p>}
      {!draft && !error && (
        <p role="status">{t("Chargement des paramètres…")}</p>
      )}
      {draft && (
        <form onSubmit={save}>
          <div className="filters">
            <label>
              {t("Langue")}
              <select
                value={draft.language ?? "fr"}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    language: e.target.value as Preferences["language"],
                  })
                }
              >
                <option value="fr">Français</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              {t("Thème")}{" "}
              <select
                value={draft.theme}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    theme: e.target.value as Preferences["theme"],
                  })
                }
              >
                <option value="system">{t("Suivre le système")}</option>
                <option value="dark">{t("Sombre")}</option>
                <option value="light">{t("Clair")}</option>
              </select>
            </label>
            <label>
              {t("Actualisation système (secondes)")}{" "}
              <input
                type="number"
                min={3}
                max={60}
                required
                value={draft.refresh_seconds}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    refresh_seconds: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              {t("Rétention des alertes résolues (jours)")}{" "}
              <input
                type="number"
                min={1}
                max={90}
                required
                value={draft.retention_days}
                onChange={(e) =>
                  setDraft({ ...draft, retention_days: Number(e.target.value) })
                }
              />
            </label>
          </div>
          <h3>{t("Règles d’alerte")}</h3>
          <p>
            {t(
              "Un seuil doit rester franchi pendant la durée choisie, avec de nouveaux échantillons. Les sources absentes ne sont pas considérées saines. Modifier ou supprimer une règle résout son événement actif.",
            )}{" "}
          </p>
          {draft.rules.map((rule, index) => (
            <fieldset className="rule-editor" key={rule.id}>
              <legend>{rule.id}</legend>
              <div className="filters">
                <label>
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    onChange={(e) =>
                      change(index, { enabled: e.target.checked })
                    }
                  />{" "}
                  {t("Activer")} {rule.id}
                </label>
                <label>
                  {t("Mesure")} {rule.id}
                  <select
                    value={rule.metric}
                    onChange={(e) => {
                      const metric = e.target.value;
                      change(index, {
                        metric,
                        target:
                          metric === "disk_free_percent"
                            ? "/"
                            : metric === "service_failed"
                              ? "ssh.service"
                              : metric === "container_stopped"
                                ? ""
                                : null,
                        engine:
                          metric === "container_stopped" ? "docker" : null,
                      });
                    }}
                  >
                    {Object.entries(metrics).map(([key, label]) => (
                      <option key={key} value={key}>
                        {t(label)}
                      </option>
                    ))}
                  </select>
                </label>
                {[
                  "cpu_percent",
                  "memory_percent",
                  "swap_percent",
                  "disk_free_percent",
                ].includes(rule.metric) && (
                  <label>
                    {t("Seuil (%)")} {rule.id}
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step="0.1"
                      value={rule.threshold}
                      required
                      onChange={(e) =>
                        change(index, { threshold: Number(e.target.value) })
                      }
                    />
                  </label>
                )}
                <label>
                  {t("Durée (secondes)")} {rule.id}
                  <input
                    type="number"
                    min={0}
                    max={3600}
                    value={rule.duration_seconds}
                    required
                    onChange={(e) =>
                      change(index, {
                        duration_seconds: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label>
                  {t("Gravité")} {rule.id}
                  <select
                    value={rule.severity}
                    onChange={(e) =>
                      change(index, {
                        severity: e.target.value as Rule["severity"],
                      })
                    }
                  >
                    <option value="warning">{t("Avertissement")}</option>
                    <option value="critical">{t("Critique")}</option>
                  </select>
                </label>
                {rule.target !== null && (
                  <label>
                    {t("Cible exacte")} {rule.id}
                    <input
                      maxLength={200}
                      value={rule.target}
                      required
                      onChange={(e) =>
                        change(index, { target: e.target.value })
                      }
                    />
                  </label>
                )}
                {rule.metric === "container_stopped" && (
                  <label>
                    {t("Moteur")} {rule.id}
                    <select
                      value={rule.engine || "docker"}
                      onChange={(e) =>
                        change(index, {
                          engine: e.target.value as Rule["engine"],
                        })
                      }
                    >
                      <option value="docker">Docker</option>
                      <option value="podman">Podman</option>
                    </select>
                  </label>
                )}
                <button
                  type="button"
                  onClick={() =>
                    setDraft({
                      ...draft,
                      rules: draft.rules.filter((_, i) => i !== index),
                    })
                  }
                >
                  {t("Supprimer la règle")} {rule.id}
                </button>
              </div>
            </fieldset>
          ))}
          <div className="pagination">
            <button
              type="button"
              disabled={draft.rules.length >= 20}
              onClick={() =>
                setDraft({
                  ...draft,
                  rules: [
                    ...draft.rules,
                    {
                      id: `rule_${Date.now()}`,
                      metric: "cpu_percent",
                      enabled: false,
                      threshold: 90,
                      duration_seconds: 30,
                      severity: "warning",
                      target: null,
                      engine: null,
                    },
                  ],
                })
              }
            >
              {t("Ajouter une règle")}{" "}
            </button>
            <button type="submit" disabled={saving}>
              {saving ? t("Enregistrement…") : t("Enregistrer les réglages")}
            </button>
          </div>
          <p>
            {t(
              "Pas de notification externe ni de commande automatique. Les valeurs CPU/RAM sont en %, la règle disque porte sur le pourcentage libre. Un conteneur exige son identifiant complet de 64 caractères.",
            )}{" "}
          </p>
        </form>
      )}
    </section>
  );
}

type AlertData = {
  items: {
    id: string;
    rule_id: string;
    severity: string;
    status: string;
    message: string;
    created_at: string;
    resolved_at: string | null;
  }[];
  total: number;
  evaluated_at: string | null;
  rules: {
    rule_id: string;
    metric: string;
    status: string;
    active: boolean;
    value: number | null;
    message: string;
  }[];
};
export function AlertsView({
  token,
  refresh,
}: {
  token: string;
  refresh: number;
}) {
  useLanguage();
  const [data, setData] = useState<AlertData | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("all");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    setError("");
    async function load() {
      try {
        const value = await api<AlertData>(
          `alerts?status=${status}&offset=${offset}`,
          token,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setData(value);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 5000);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, refresh, status, offset]);
  return (
    <>
      <section className="panel">
        <h2>{t("Alertes locales")}</h2>
        <p>
          {t(
            "Les règles observent uniquement les sources disponibles. Une alerte active est conservée si sa source devient indisponible ; aucune action système n’est exécutée.",
          )}{" "}
        </p>
        <div className="filters">
          <label>
            {t("État des alertes")}{" "}
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="all">{t("Toutes")}</option>
              <option value="active">{t("Actives")}</option>
              <option value="resolved">{t("Résolues")}</option>
            </select>
          </label>
        </div>
        {error && (
          <p className="error" role="alert">
            {t(error)}
            {data ? t(" · les données précédentes sont anciennes") : ""}
          </p>
        )}
        {!data && !error && <p role="status">{t("Chargement des alertes…")}</p>}
        {data && (
          <>
            <small>
              {t("Évaluation :")}{" "}
              {data.evaluated_at
                ? new Date(data.evaluated_at).toLocaleTimeString(getLocale())
                : t("En attente")}
            </small>
            {!data.items.length && <p>{t("Aucune alerte pour ce filtre.")}</p>}
            {data.items.map((event) => (
              <article className="log-entry" key={event.id}>
                <strong>
                  {event.rule_id} · {t(states[event.status] || event.status)} ·{" "}
                  {event.severity === "critical"
                    ? t("Critique")
                    : t("Avertissement")}
                </strong>
                <p>{t(event.message)}</p>
                <p>
                  {t(
                    "À vérifier : consulter les métriques ou journaux de la source concernée.",
                  )}{" "}
                </p>
                <small>
                  {t("Début :")}{" "}
                  {new Date(event.created_at).toLocaleString(getLocale())}
                  {event.resolved_at
                    ? t(" · Résolution : {0}", {
                        0: new Date(event.resolved_at).toLocaleString(
                          getLocale(),
                        ),
                      })
                    : ""}
                </small>
              </article>
            ))}
            <div className="pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset((v) => Math.max(0, v - 50))}
              >
                {t("Alertes précédentes")}{" "}
              </button>
              <span>
                {data.total} {t("événements")}
              </span>
              <button
                disabled={offset + 50 >= data.total}
                onClick={() => setOffset((v) => v + 50)}
              >
                {t("Alertes suivantes")}{" "}
              </button>
            </div>
          </>
        )}
      </section>
      {data && (
        <section className="panel">
          <h2>{t("Observabilité des règles")}</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("Règle")}</th>
                  <th>{t("Mesure")}</th>
                  <th>{t("État")}</th>
                  <th>{t("Valeur")}</th>
                </tr>
              </thead>
              <tbody>
                {data.rules.map((rule) => (
                  <tr key={rule.rule_id}>
                    <td>{rule.rule_id}</td>
                    <td>{t(metrics[rule.metric] || rule.metric)}</td>
                    <td>
                      {t(states[rule.status] || rule.status)}
                      {rule.active && rule.status === "unavailable"
                        ? t(" · alerte active conservée")
                        : ""}
                      {rule.message ? ` · ${t(rule.message)}` : ""}
                    </td>
                    <td>
                      {rule.value == null
                        ? t("Indisponible")
                        : [
                              "cpu_percent",
                              "memory_percent",
                              "swap_percent",
                              "disk_free_percent",
                            ].includes(rule.metric)
                          ? `${formatNumber(rule.value)} %`
                          : rule.value === 1
                            ? t("Détectée")
                            : t("Non détectée")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
