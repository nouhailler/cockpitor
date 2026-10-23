import { t, useLanguage, getLocale, formatNumber } from "./i18n";
import React, { useEffect, useState } from "react";
import { api } from "./api";
import { bytes } from "./format";

type Engine = {
  name: string;
  status: string;
  message?: string;
  version?: string;
  containers: {
    id: string;
    name: string;
    image: string;
    state: string;
    status: string;
    ports: string[];
  }[];
};
type Detail = {
  id: string;
  engine: string;
  name: string;
  image: string;
  created: string | null;
  state: {
    Status: string;
    Running: boolean;
    ExitCode: number | null;
    OOMKilled: boolean | null;
    StartedAt: string | null;
    FinishedAt: string | null;
  };
  tty: boolean;
  collected_at: string;
};
type Stats = {
  cpu_percent: number | null;
  memory_usage_bytes: number | null;
  memory_limit_bytes: number | null;
  sample_at: string | null;
  collected_at: string;
  note: string;
};
type Logs = {
  items: { stream: string; message: string }[];
  collected_at: string;
  tty: boolean;
  ordering: string;
};
const statusLabel = (s: string) =>
  ({
    available: t("Disponible"),
    unavailable: t("Indisponible"),
    disabled: t("Désactivé"),
  })[s] || s;

export function ContainersView({
  engines,
  token,
  refresh,
}: {
  engines: Engine[];
  token: string;
  refresh: number;
}) {
  useLanguage();
  const [selected, setSelected] = useState<{
    engine: string;
    id: string;
  } | null>(null);
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  return (
    <>
      <section className="panel">
        <h2>{t("Inventaire des conteneurs")}</h2>
        <div className="filters">
          <label>
            {t("Rechercher un conteneur")}{" "}
            <input
              value={query}
              maxLength={100}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label>
            {t("État des conteneurs")}{" "}
            <select value={t(state)} onChange={(e) => setState(e.target.value)}>
              <option value="all">{t("Tous")}</option>
              <option value="running">{t("En cours")}</option>
              <option value="stopped">{t("Arrêtés")}</option>
              <option value="error">{t("En erreur")}</option>
            </select>
          </label>
        </div>
        <p>
          {t(
            "Lecture seule. Sélectionnez un conteneur pour consulter ses détails, statistiques et journaux.",
          )}{" "}
        </p>
      </section>
      {engines.map((engine) => {
        const rows = engine.containers.filter(
          (c) =>
            (c.name + " " + c.image)
              .toLowerCase()
              .includes(query.toLowerCase()) &&
            (state === "all" ||
              (state === "running"
                ? c.state === "running"
                : state === "stopped"
                  ? ["exited", "created", "paused"].includes(c.state)
                  : ["dead", "restarting", "removing"].includes(c.state))),
        );
        return (
          <section className="panel" key={engine.name}>
            <h2>
              {engine.name}{" "}
              <span className="badge">{statusLabel(engine.status)}</span>
            </h2>
            <p>
              {(engine.message ? t(engine.message) : null) ||
                t("Version {0}", { 0: engine.version })}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Nom")}</th>
                    <th>{t("Image")}</th>
                    <th>{t("État")}</th>
                    <th>{t("Ports publiés")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <button
                          onClick={() =>
                            setSelected({ engine: engine.name, id: c.id })
                          }
                          aria-pressed={
                            selected?.id === c.id &&
                            selected.engine === engine.name
                          }
                        >
                          {c.name}
                        </button>
                      </td>
                      <td>{c.image}</td>
                      <td>{c.status || t(c.state)}</td>
                      <td>{c.ports.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {engine.status === "available" && !rows.length && (
              <p>{t("Aucun conteneur correspondant.")}</p>
            )}
          </section>
        );
      })}
      {selected && (
        <ContainerInspector
          key={selected.engine + selected.id}
          engine={selected.engine}
          id={selected.id}
          token={token}
          refresh={refresh}
        />
      )}
    </>
  );
}

function ContainerInspector({
  engine,
  id,
  token,
  refresh,
}: {
  engine: string;
  id: string;
  token: string;
  refresh: number;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [stats, setStats] = useState<Stats | null>(null);
  const [statsError, setStatsError] = useState("");
  const [logs, setLogs] = useState<Logs | null>(null);
  const [logError, setLogError] = useState("");
  const [tail, setTail] = useState("100");
  const [period, setPeriod] = useState("hour");
  const [reload, setReload] = useState(0);
  const base = `containers/${engine}/${id}`;
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setDetailError("");
    setStats(null);
    setLogs(null);
    void api<Detail>(base, token, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setDetail(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setDetailError((e as Error).message);
      });
    return () => controller.abort();
  }, [base, token, refresh, reload]);
  useEffect(() => {
    if (!detail) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const data = await api<Stats>(
          `${base}/stats`,
          token,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setStats(data);
          setStatsError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setStats(null);
          setStatsError((e as Error).message);
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 5000);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [base, token, detail]);
  useEffect(() => {
    if (!detail) return;
    const controller = new AbortController();
    setLogs(null);
    setLogError("");
    void api<Logs>(
      `${base}/logs?tail=${tail}&period=${period}`,
      token,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setLogs(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setLogError((e as Error).message);
      });
    return () => controller.abort();
  }, [base, token, detail, tail, period]);
  return (
    <section className="panel">
      <h2>
        {t("Détails du conteneur ·")} {engine}
      </h2>
      <button onClick={() => setReload((v) => v + 1)}>
        {t("Actualiser ce conteneur")}{" "}
      </button>
      {detailError && (
        <p className="error" role="alert">
          {t(detailError)}
        </p>
      )}
      {!detail && !detailError && (
        <p role="status">{t("Lecture du conteneur…")}</p>
      )}
      {detail && (
        <>
          <h3>{detail.name}</h3>
          <small>
            {t("État collecté à")}{" "}
            {new Date(detail.collected_at).toLocaleTimeString(getLocale())}
          </small>
          <dl className="properties">
            <dt>{t("Identifiant")}</dt>
            <dd>{detail.id}</dd>
            <dt>{t("Image")}</dt>
            <dd>{detail.image}</dd>
            <dt>{t("État")}</dt>
            <dd>{t(detail.state.Status)}</dd>
            <dt>{t("Créé")}</dt>
            <dd>{detail.created || t("Indisponible")}</dd>
            <dt>{t("Démarré")}</dt>
            <dd>{detail.state.StartedAt || t("Indisponible")}</dd>
            <dt>{t("Code de sortie")}</dt>
            <dd>
              {detail.state.Running
                ? t("Sans objet")
                : (detail.state.ExitCode ?? t("Indisponible"))}
            </dd>
            <dt>{t("Arrêt par manque de mémoire")}</dt>
            <dd>
              {detail.state.OOMKilled == null
                ? t("Indisponible")
                : detail.state.OOMKilled
                  ? t("Oui")
                  : t("Non")}
            </dd>
          </dl>
          <h3>{t("Statistiques")}</h3>
          {statsError && (
            <p className="error" role="alert">
              {t("Statistiques :")} {t(statsError)}
            </p>
          )}
          {!stats && !statsError && (
            <p role="status">{t("Mesure des ressources…")}</p>
          )}
          {stats && (
            <>
              <small>
                {t("Collecté à")}{" "}
                {new Date(stats.collected_at).toLocaleTimeString(getLocale())}
              </small>
              <div className="cards">
                <article className="card">
                  <p>CPU</p>
                  <strong>
                    {stats.cpu_percent == null
                      ? t("Indisponible")
                      : `${formatNumber(stats.cpu_percent)} %`}
                  </strong>
                </article>
                <article className="card">
                  <p>{t("MÉMOIRE BRUTE")}</p>
                  <strong>{bytes(stats.memory_usage_bytes)}</strong>
                  <small>
                    {t("Limite :")} {bytes(stats.memory_limit_bytes)}
                  </small>
                </article>
              </div>
              <p>{t(stats.note)}</p>
            </>
          )}
          <h3>{t("Journaux récents")}</h3>
          <p>
            {t(
              "Lecture bornée, sans suivi continu. Flux stdout et stderr regroupés séparément ; ordre global non reconstruit. Les secrets connus sont masqués, sans garantie exhaustive.",
            )}{" "}
          </p>
          <div className="filters">
            <label>
              {t("Lignes par flux")}{" "}
              <select value={tail} onChange={(e) => setTail(e.target.value)}>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="200">200</option>
              </select>
            </label>
            <label>
              {t("Période des conteneurs")}{" "}
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              >
                <option value="hour">{t("Dernière heure")}</option>
                <option value="day">{t("Dernières 24 heures")}</option>
              </select>
            </label>
          </div>
          {logError && (
            <p className="error" role="alert">
              {t("Journaux :")} {t(logError)}
            </p>
          )}
          {!logs && !logError && (
            <p role="status">{t("Lecture des journaux du conteneur…")}</p>
          )}
          {logs && (
            <>
              <small>
                {t("Lu à")}{" "}
                {new Date(logs.collected_at).toLocaleTimeString(getLocale())}
                {logs.tty ? t(" · TTY : flux fusionné") : ""}
              </small>
              {!logs.items.length && (
                <p>{t("Aucune entrée visible sur cette période.")}</p>
              )}
              <div className="log-list">
                {logs.items.map((line, i) => (
                  <article className="log-entry" key={i}>
                    <small>{line.stream}</small>
                    <pre>{line.message}</pre>
                  </article>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
