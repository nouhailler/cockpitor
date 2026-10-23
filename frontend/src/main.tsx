import {
  t,
  useLanguage,
  getLocale,
  formatNumber,
  LanguagePicker,
  setLanguage,
} from "./i18n";
import React, { useEffect, useState } from "react";
import "./style.css";
import { DiagnosticView } from "./diagnostics";
import { SettingsView, AlertsView, type Preferences } from "./preferences";
import { bytes } from "./format";
export { bytes } from "./format";
import { ContainersView } from "./containers";
import { api, post } from "./api";
import { LoginView } from "./login";
import { MonitoringView, AuditView } from "./monitoring";
import { AssistantView } from "./assistant";
import { navigation } from "./navigation";
export { api } from "./api";
import { ServicesView } from "./services";

import type { Metrics, Process, History, Module } from "./types";
import { Card, Graph, pct } from "./components";
import { AIView } from "./ai-status";
export function App() {
  useLanguage();
  const [token, setToken] = useState("");
  const [csrf, setCsrf] = useState("");
  const [sessionNotice, setSessionNotice] = useState("");
  const [page, setPage] = useState("Vue d’ensemble");
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [history, setHistory] = useState<History>([]);
  const [processes, setProcesses] = useState<Process[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [module, setModule] = useState<Module | null>(null);
  const [moduleError, setModuleError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");
  const [refreshSeconds, setRefreshSeconds] = useState(3);
  const [preferencesError, setPreferencesError] = useState("");
  function applyPreferences(settings: Preferences) {
    setTheme(settings.theme);
    setLanguage(settings.language ?? "fr");
    setRefreshSeconds(settings.refresh_seconds);
  }
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const data = await api<{ settings: Preferences }>(
          "settings",
          token,
          controller.signal,
        );
        if (data.settings && !controller.signal.aborted) {
          applyPreferences(data.settings);
          setPreferencesError("");
        }
      } catch {
        if (!controller.signal.aborted) {
          setPreferencesError(t("Réglages persistants indisponibles"));
          timer = setTimeout(load, 3000);
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token]);
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const update = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (media?.matches ? "dark" : "light") : theme;
    };
    update();
    media?.addEventListener("change", update);
    localStorage.setItem("theme", theme);
    return () => media?.removeEventListener("change", update);
  }, [theme]);
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const [m, h] = await Promise.all([
          api<Metrics>("system/metrics", token, controller.signal),
          api<History>("system/history", token, controller.signal),
        ]);
        if (!controller.signal.aborted) {
          setMetrics(m);
          setHistory(h);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted)
          timer = setTimeout(load, refreshSeconds * 1000);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, refresh, refreshSeconds]);
  useEffect(() => {
    if (!token || page !== "Processus") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const data = await api<{ items: Process[]; total: number }>(
          `system/processes?q=${encodeURIComponent(query)}&offset=${offset}`,
          token,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setProcesses(data.items);
          setTotal(data.total);
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted)
          timer = setTimeout(load, refreshSeconds * 1000);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, page, query, offset, refresh, refreshSeconds]);
  useEffect(() => {
    if (!token || !["IA locale", "Conteneurs"].includes(page)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setModule(null);
    setModuleError("");
    const load = async () => {
      try {
        const data = await api<Module>(
          page === "IA locale" ? "ai/status" : "containers",
          token,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setModule(data);
          setModuleError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setModuleError((e as Error).message);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 10000);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, page, refresh]);
  useEffect(() => {
    function expired() {
      setToken("");
      setCsrf("");
      setMetrics(null);
      setHistory([]);
      setProcesses([]);
      setModule(null);
      setSessionNotice(t("Session expirée ; reconnectez-vous."));
    }
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    if (!token) return;
    let last = 0;
    function activity() {
      if (Date.now() - last < 30000) return;
      last = Date.now();
      void post("auth/activity", token, csrf).catch(() => {});
    }
    window.addEventListener("pointerdown", activity);
    window.addEventListener("keydown", activity);
    return () => {
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity);
    };
  }, [token, csrf]);
  if (!token)
    return (
      <LoginView
        notice={sessionNotice}
        onLogin={(value, protection) => {
          setToken(value);
          setCsrf(protection);
          setError("");
          setSessionNotice("");
        }}
      />
    );
  const stale = metrics
    ? Date.now() - Date.parse(metrics.collected_at) > 15000
    : false;
  return (
    <div className="layout">
      <aside>
        <div className="brand">◈ LocalCockpit</div>
        <LanguagePicker />
        <span className="eyebrow">{t("ESPACE PERSONNEL")}</span>
        <nav aria-label={t("Navigation principale")}>
          {navigation.map((group) => (
            <React.Fragment key={group.group}>
              <span className="nav-group">{t(group.group)}</span>
              {group.entries.map(([p, icon]) => (
                <button
                  key={p}
                  className={page === p ? "active" : ""}
                  aria-current={page === p ? "page" : undefined}
                  onClick={() => setPage(p)}
                >
                  <span>{icon}</span>
                  {t(p)}
                </button>
              ))}
            </React.Fragment>
          ))}
        </nav>
        <div className="aside-bottom">
          <p>{t("● Système en lecture seule")}</p>
          <small>{t("Aucune action système autorisée")}</small>
          <button
            onClick={async () => {
              try {
                await post("auth/logout", token, csrf);
                setToken("");
                setCsrf("");
                setMetrics(null);
                setHistory([]);
                setProcesses([]);
                setModule(null);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            {t("Déconnexion")}{" "}
          </button>
        </div>
      </aside>
      <main>
        <header>
          <span>
            {t("POSTE LOCAL /")} {metrics?.hostname || t("Connexion")}
            {preferencesError && <small> · {t(preferencesError)}</small>}
          </span>
          <div>
            <span className={t(error) || stale ? "badge warning" : "badge"}>
              {t(error) || stale
                ? t("● Données indisponibles ou anciennes")
                : t("● Connecté en local")}
            </span>
            <button onClick={() => setRefresh((v) => v + 1)}>
              {t("Actualiser")}
            </button>
          </div>
        </header>
        <div className="heading">
          <div>
            <span className="eyebrow">{t("LOCALCOCKPIT / SUPERVISION")}</span>
            <h1>{t(page)}</h1>
            <p>
              {page === "Vue d’ensemble"
                ? t("L’essentiel de votre machine, en un coup d’œil.")
                : t("Données locales observées, sans modification du système.")}
            </p>
          </div>
          <small>
            {t("Dernière collecte système")} <br />
            {metrics
              ? new Date(metrics.collected_at).toLocaleTimeString(getLocale())
              : t("En attente")}
          </small>
        </div>
        {(error || stale) && (
          <div className="error" role="alert">
            {t(error) ||
              t(
                "La collecte est interrompue. Les dernières valeurs ci-dessous sont anciennes.",
              )}
          </div>
        )}
        {["Vue d’ensemble", "Système"].includes(page) && (
          <>
            {!metrics ? (
              <p role="status">{t("Collecte des métriques en cours…")}</p>
            ) : (
              <>
                <div className="cards">
                  <Card
                    label={t("PROCESSEUR")}
                    value={pct(metrics.cpu_percent)}
                    detail={t("{0} cœurs logiques", {
                      0: metrics.cpu_cores.length || "—",
                    })}
                  />
                  <Card
                    label={t("MÉMOIRE")}
                    value={pct(metrics.memory.percent)}
                    detail={`${bytes(metrics.memory.used)} / ${bytes(metrics.memory.total)}`}
                  />
                  <Card
                    label={t("STOCKAGE PRINCIPAL")}
                    value={pct(
                      (
                        metrics.disks.find((d) => d.mount === "/") ||
                        metrics.disks[0]
                      )?.percent,
                    )}
                    detail={t("Système de fichiers /")}
                  />
                  <Card
                    label={t("TEMPS DE FONCTIONNEMENT")}
                    value={`${Math.floor(metrics.uptime_seconds / 3600)} h`}
                    detail={t("Charge : {0}", {
                      0: metrics.load
                        .map((v) => formatNumber(v, 2))
                        .join(" · "),
                    })}
                  />
                </div>
                <div className="split">
                  <Graph history={history} />
                  <section className="panel">
                    <h2>{t("Réseau")}</h2>
                    <p className="network">
                      ↓ {bytes(metrics.network.received_bps)}/s
                    </p>
                    <p className="network">
                      ↑ {bytes(metrics.network.sent_bps)}/s
                    </p>
                    <small>{t("Débit agrégé des interfaces · octets/s")}</small>
                    <h2>Swap</h2>
                    <p>
                      {bytes(metrics.swap.used)} / {bytes(metrics.swap.total)}
                    </p>
                  </section>
                </div>
                <section className="panel">
                  <h2>{t("Systèmes de fichiers")}</h2>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>{t("Point de montage")}</th>
                          <th>{t("Utilisé")}</th>
                          <th>{t("Capacité")}</th>
                          <th>{t("Occupation")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.disks.map((d) => (
                          <tr key={d.mount}>
                            <td>{d.mount}</td>
                            <td>{bytes(d.used)}</td>
                            <td>{bytes(d.total)}</td>
                            <td>
                              {(d.error ? t(d.error) : null) || pct(d.percent)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
                {page === "Système" && (
                  <section className="panel">
                    <h2>{t("Informations et capteurs")}</h2>
                    <p>{metrics.os}</p>
                    {metrics.temperatures.length ? (
                      metrics.temperatures.map((t, i) => (
                        <p key={i}>
                          {t.name} : {formatNumber(t.celsius)} °C
                        </p>
                      ))
                    ) : (
                      <p>
                        {t(
                          "Températures indisponibles : aucun capteur accessible.",
                        )}{" "}
                      </p>
                    )}
                    <h3>{t("CPU par cœur")}</h3>
                    <div className="core-grid">
                      {metrics.cpu_cores.map((value, index) => (
                        <p key={index}>
                          {index + 1} · {pct(value)}
                        </p>
                      ))}
                    </div>
                    <p>
                      {t("GPU, disques et réseau détaillé : page Supervision.")}
                    </p>
                  </section>
                )}
              </>
            )}
          </>
        )}
        {page === "Processus" && (
          <section className="panel">
            <h2>
              {t("Processus")}{" "}
              <small>
                {t(
                  "Triés par mémoire · CPU par cœur, peut dépasser 100 %",
                )}{" "}
              </small>
            </h2>
            <input
              aria-label={t("Rechercher un processus")}
              placeholder={t("Rechercher par nom…")}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
            />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>PID</th>
                    <th>{t("Nom")}</th>
                    <th>{t("Utilisateur")}</th>
                    <th>CPU</th>
                    <th>RAM</th>
                    <th>{t("État")}</th>
                  </tr>
                </thead>
                <tbody>
                  {processes.map((p) => (
                    <tr key={p.pid}>
                      <td>{p.pid}</td>
                      <td>{p.name}</td>
                      <td>{p.user}</td>
                      <td>{pct(p.cpu_percent)}</td>
                      <td>{pct(p.memory_percent)}</td>
                      <td>{t(p.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!processes.length && <p>{t("Aucun résultat disponible.")}</p>}
            <div className="pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset((v) => Math.max(0, v - 50))}
              >
                {t("Précédent")}{" "}
              </button>
              <span>
                {total} {t("processus")}
              </span>
              <button
                disabled={offset + 50 >= total}
                onClick={() => setOffset((v) => v + 50)}
              >
                {t("Suivant")}{" "}
              </button>
            </div>
          </section>
        )}
        {["IA locale", "Conteneurs"].includes(page) && (
          <>
            {moduleError && (
              <p className="error" role="alert">
                {t(moduleError)}{" "}
                {t("— les données précédentes sont anciennes.")}{" "}
              </p>
            )}
            {!module && !moduleError && (
              <p role="status">{t("Vérification des intégrations…")}</p>
            )}
            {module && (
              <>
                <p className="module-time">
                  {t("Vérification :")}{" "}
                  {new Date(module.collected_at).toLocaleTimeString(
                    getLocale(),
                  )}
                </p>
                {page === "IA locale" ? (
                  <AIView data={module} />
                ) : (
                  <ContainersView
                    engines={module.engines || []}
                    token={token}
                    refresh={refresh}
                  />
                )}
              </>
            )}
          </>
        )}
        {page === "Services" && (
          <ServicesView token={token} refresh={refresh} />
        )}
        {page === "Paramètres" && (
          <SettingsView
            token={token}
            onSaved={(settings) => {
              applyPreferences(settings);
              setPreferencesError("");
            }}
          />
        )}
        {page === "Alertes" && <AlertsView token={token} refresh={refresh} />}
        {page === "Supervision" && <MonitoringView token={token} />}
        {page === "Audit" && <AuditView token={token} />}
        {page === "Assistant IA" && <AssistantView token={token} csrf={csrf} />}
        {page === "Diagnostic" && <DiagnosticView token={token} />}
        <footer>
          {t(
            "Lecture seule · Données conservées localement · Aucun service cloud",
          )}{" "}
        </footer>
      </main>
    </div>
  );
}
