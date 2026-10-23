import { t, useLanguage, getLocale, formatNumber } from "./i18n";
import React, { useEffect, useState } from "react";
import { api } from "./api";

type Service = {
  unit: string;
  description: string;
  load: string;
  active: string;
  sub: string;
};
type Inventory = { items: Service[]; total: number; collected_at: string };
type Detail = {
  unit: string;
  collected_at: string;
  properties: Record<string, string>;
};
type Logs = {
  unit: string;
  items: { message: string; priority: string; timestamp_us: string }[];
  scanned: number;
  next_cursor: string | null;
  collected_at: string;
};

export function ServicesView({
  token,
  refresh,
}: {
  token: string;
  refresh: number;
}) {
  useLanguage();
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  const [offset, setOffset] = useState(0);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [error, setError] = useState("");
  const [unit, setUnit] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [logs, setLogs] = useState<Logs | null>(null);
  const [logError, setLogError] = useState("");
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState("hour");
  const [priority, setPriority] = useState("7");
  const [text, setText] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setInventory(null);
    setError("");
    async function load() {
      try {
        const data = await api<Inventory>(
          `services?q=${encodeURIComponent(query)}&state=${state}&offset=${offset}`,
          token,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setInventory(data);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 10000);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, refresh, query, state, offset]);
  useEffect(() => {
    if (!unit) return;
    const controller = new AbortController();
    setDetail(null);
    setDetailError("");
    void api<Detail>(
      `services/${encodeURIComponent(unit)}`,
      token,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setDetail(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setDetailError((e as Error).message);
      });
    return () => controller.abort();
  }, [unit, token, refresh, reload]);
  useEffect(() => {
    if (!unit) return;
    const controller = new AbortController();
    setLoading(true);
    setLogs(null);
    setLogError("");
    const params = new URLSearchParams({ period, priority, q: text });
    if (cursor) params.set("cursor", cursor);
    void api<Logs>(
      `services/${encodeURIComponent(unit)}/logs?${params}`,
      token,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setLogs(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setLogError((e as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [unit, token, period, priority, text, cursor, refresh, reload]);
  function resetLogs() {
    setCursor(null);
    setReload((v) => v + 1);
  }
  return (
    <>
      <section className="panel">
        <h2>{t("Services système chargés")}</h2>
        <p>
          {t(
            "Lecture seule · inclut les unités inactives déjà chargées ; pas tous les fichiers installés.",
          )}{" "}
        </p>
        <div className="filters">
          <label>
            {t("Rechercher un service")}{" "}
            <input
              value={query}
              maxLength={100}
              placeholder={t("Nom ou description…")}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            {t("État")}{" "}
            <select
              value={t(state)}
              onChange={(e) => {
                setState(e.target.value);
                setOffset(0);
              }}
            >
              <option value="all">{t("Tous")}</option>
              <option value="active">{t("Actifs")}</option>
              <option value="inactive">{t("Inactifs")}</option>
              <option value="failed">{t("En échec")}</option>
            </select>
          </label>
        </div>
        {error && (
          <p role="alert" className="error">
            {t(error)}{" "}
            {inventory ? t("Les données précédentes sont anciennes.") : ""}
          </p>
        )}
        {!inventory && !error && (
          <p role="status">{t("Inventaire des services en cours…")}</p>
        )}
        {inventory && (
          <>
            <small>
              {t("Collecté à")}{" "}
              {new Date(inventory.collected_at).toLocaleTimeString(getLocale())}
            </small>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Service")}</th>
                    <th>{t("Description")}</th>
                    <th>{t("État")}</th>
                    <th>{t("Sous-état")}</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.items.map((service) => (
                    <tr key={service.unit}>
                      <td>
                        <button
                          onClick={() => {
                            setUnit(service.unit);
                            setCursor(null);
                          }}
                          aria-pressed={unit === service.unit}
                        >
                          {service.unit}
                        </button>
                      </td>
                      <td>{service.description}</td>
                      <td>{t(service.active)}</td>
                      <td>{t(service.sub)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!inventory.items.length && (
              <p>{t("Aucun service correspondant.")}</p>
            )}
            <div className="pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset((v) => Math.max(0, v - 50))}
              >
                {t("Services précédents")}{" "}
              </button>
              <span>
                {inventory.total} {t("services")}
              </span>
              <button
                disabled={offset + 50 >= inventory.total}
                onClick={() => setOffset((v) => v + 50)}
              >
                {t("Services suivants")}{" "}
              </button>
            </div>
          </>
        )}
      </section>
      {!unit && (
        <section className="panel">
          <h2>{t("Détails et journaux")}</h2>
          <p>
            {t(
              "Sélectionnez un service pour consulter son état et ses journaux.",
            )}{" "}
          </p>
        </section>
      )}
      {unit && (
        <>
          <section className="panel">
            <h2>{unit}</h2>
            <button onClick={resetLogs}>{t("Actualiser ce service")}</button>
            {detailError && (
              <p className="error" role="alert">
                {t(detailError)}
              </p>
            )}
            {!detail && !detailError && (
              <p role="status">{t("Lecture du service…")}</p>
            )}
            {detail && (
              <>
                <small>
                  {t("État collecté à")}{" "}
                  {new Date(detail.collected_at).toLocaleTimeString(
                    getLocale(),
                  )}
                </small>
                <dl className="properties">
                  {Object.entries(detail.properties).map(([key, value]) => (
                    <React.Fragment key={key}>
                      <dt>{key}</dt>
                      <dd>{value || t("Indisponible")}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              </>
            )}
          </section>
          <section className="panel">
            <h2>
              {t("Journaux de")} {unit}
            </h2>
            <p>
              {t(
                "50 entrées maximum par page, les plus récentes d’abord. La recherche de texte porte uniquement sur la page lue. Secrets connus masqués, sans garantie exhaustive.",
              )}{" "}
            </p>
            <div className="filters">
              <label>
                {t("Période")}{" "}
                <select
                  value={period}
                  onChange={(e) => {
                    setPeriod(e.target.value);
                    setCursor(null);
                  }}
                >
                  <option value="hour">{t("Dernière heure")}</option>
                  <option value="day">{t("Dernières 24 heures")}</option>
                </select>
              </label>
              <label>
                {t("Niveau maximum")}{" "}
                <select
                  value={priority}
                  onChange={(e) => {
                    setPriority(e.target.value);
                    setCursor(null);
                  }}
                >
                  <option value="7">{t("Tous les niveaux")}</option>
                  <option value="4">{t("Avertissement et plus grave")}</option>
                  <option value="3">{t("Erreur et plus grave")}</option>
                </select>
              </label>
              <label>
                {t("Texte dans la page")}{" "}
                <input
                  value={text}
                  maxLength={100}
                  onChange={(e) => {
                    setText(e.target.value);
                    setCursor(null);
                  }}
                />
              </label>
            </div>
            {loading && <p role="status">{t("Lecture des journaux…")}</p>}
            {logError && (
              <p className="error" role="alert">
                {t(logError)}
              </p>
            )}
            {logs && (
              <>
                <small>
                  {t("Lu à")}{" "}
                  {new Date(logs.collected_at).toLocaleTimeString(getLocale())}{" "}
                  · {logs.scanned} {t("entrées examinées")}{" "}
                </small>
                {!logs.items.length && (
                  <p>
                    {t(
                      "Aucune entrée visible correspondant à ces filtres sur cette page.",
                    )}{" "}
                  </p>
                )}
                <div className="log-list">
                  {logs.items.map((entry, index) => (
                    <article className="log-entry" key={index}>
                      <small>
                        {entry.timestamp_us &&
                        Number.isFinite(Number(entry.timestamp_us))
                          ? new Date(
                              Number(entry.timestamp_us) / 1000,
                            ).toLocaleString(getLocale())
                          : t("Horodatage indisponible")}{" "}
                        {t("· priorité")} {entry.priority}
                      </small>
                      <pre>{entry.message}</pre>
                    </article>
                  ))}
                </div>
                <div className="pagination">
                  <button onClick={resetLogs}>{t("Entrées récentes")}</button>
                  <button
                    disabled={!logs.next_cursor}
                    onClick={() => setCursor(logs.next_cursor)}
                  >
                    {t("Entrées plus anciennes")}{" "}
                  </button>
                </div>
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
