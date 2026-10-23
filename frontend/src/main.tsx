import React, { useEffect, useState } from "react";
import "./style.css";
import { bytes } from "./format";
export { bytes } from "./format";
import { ContainersView } from "./containers";
import { api } from "./api";
export { api } from "./api";
import { ServicesView } from "./services";

type Metrics = {
  collected_at: string;
  hostname: string;
  os: string;
  uptime_seconds: number;
  cpu_percent: number | null;
  cpu_cores: number[];
  load: number[];
  memory: { total: number; used: number; available: number; percent: number };
  swap: { total: number; used: number; percent: number };
  network: { received_bps: number | null; sent_bps: number | null };
  disks: {
    mount: string;
    device?: string;
    total?: number;
    used?: number;
    percent?: number;
    error: string | null;
  }[];
  temperatures: { name: string; celsius: number }[];
};
type Process = {
  pid: number;
  name: string;
  user: string;
  cpu_percent: number | null;
  memory_percent: number;
  status: string;
};
type History = {
  cpu_percent: number | null;
  memory_percent: number;
  collected_at: string;
}[];
type Module = {
  status: string;
  message?: string;
  collected_at: string;
  latency_ms?: number;
  url?: string;
  models?: {
    name: string;
    size?: number;
    family?: string;
    quantization?: string;
  }[];
  loaded?: { name: string; size_vram?: number }[];
  engines?: {
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
  }[];
};
const pct = (n: number | null | undefined) =>
  n == null ? "Indisponible" : `${n.toFixed(1)} %`;
const statusLabel = (status: string) =>
  ({
    available: "Disponible",
    unavailable: "Indisponible",
    disabled: "Désactivé",
  })[status] || status;
function Card({
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
function Graph({ history }: { history: History }) {
  return (
    <section className="panel">
      <h2>
        Activité CPU <small>15 min maximum · mémoire vive uniquement</small>
      </h2>
      <svg
        viewBox="0 0 800 150"
        role="img"
        aria-label="Utilisation CPU, de 0 à 100 pour cent"
      >
        <path d="M0 1H800 M0 75H800 M0 149H800" className="grid" />
        <polyline
          className="line"
          points={history
            .flatMap((p, i) =>
              p.cpu_percent == null
                ? []
                : [
                    `${history.length > 1 ? (i / (history.length - 1)) * 800 : 0},${150 - p.cpu_percent * 1.5}`,
                  ],
            )
            .join(" ")}
        />
      </svg>
      <div className="graph-label">
        <span>0–100 %</span>
        <span>
          {history.length
            ? new Date(history[0].collected_at).toLocaleTimeString()
            : "En attente"}{" "}
          → maintenant
        </span>
      </div>
    </section>
  );
}
export function App() {
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
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
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
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
        if (!controller.signal.aborted) timer = setTimeout(load, 3000);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, refresh]);
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
        if (!controller.signal.aborted) timer = setTimeout(load, 3000);
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token, page, query, offset, refresh]);
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
  if (!token)
    return (
      <main className="login">
        <div className="brand">◈ LocalCockpit</div>
        <h1>Votre machine, en clair.</h1>
        <p>Supervision locale · lecture seule · aucune télémétrie</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setToken(input);
            setInput("");
          }}
        >
          <label htmlFor="token">Jeton affiché par le lanceur local</label>
          <input
            id="token"
            type="password"
            autoComplete="off"
            required
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button>Ouvrir le cockpit →</button>
        </form>
        <small>Le jeton reste uniquement en mémoire dans cet onglet.</small>
      </main>
    );
  const stale = metrics
    ? Date.now() - Date.parse(metrics.collected_at) > 15000
    : false;
  return (
    <div className="layout">
      <aside>
        <div className="brand">◈ LocalCockpit</div>
        <span className="eyebrow">ESPACE PERSONNEL</span>
        <nav aria-label="Navigation principale">
          {[
            "Vue d’ensemble",
            "Système",
            "Processus",
            "Services",
            "IA locale",
            "Conteneurs",
          ].map((p, i) => (
            <button
              key={p}
              className={page === p ? "active" : ""}
              aria-current={page === p ? "page" : undefined}
              onClick={() => setPage(p)}
            >
              <span>{["▦", "◉", "≋", "⚙", "✧", "▣"][i]}</span>
              {p}
            </button>
          ))}
        </nav>
        <div className="aside-bottom">
          <p>● Mode lecture seule</p>
          <small>Aucune action système autorisée</small>
          <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            Thème {theme === "dark" ? "clair" : "sombre"}
          </button>
          <button
            onClick={() => {
              setToken("");
              setMetrics(null);
              setProcesses([]);
            }}
          >
            Déconnexion
          </button>
        </div>
      </aside>
      <main>
        <header>
          <span>POSTE LOCAL / {metrics?.hostname || "Connexion"}</span>
          <div>
            <span className={error || stale ? "badge warning" : "badge"}>
              {error || stale
                ? "● Données indisponibles ou anciennes"
                : "● Connecté en local"}
            </span>
            <button onClick={() => setRefresh((v) => v + 1)}>Actualiser</button>
          </div>
        </header>
        <div className="heading">
          <div>
            <span className="eyebrow">LOCALCOCKPIT / SUPERVISION</span>
            <h1>{page}</h1>
            <p>
              {page === "Vue d’ensemble"
                ? "L’essentiel de votre machine, en un coup d’œil."
                : "Données locales observées, sans modification du système."}
            </p>
          </div>
          <small>
            Dernière collecte système
            <br />
            {metrics
              ? new Date(metrics.collected_at).toLocaleTimeString()
              : "En attente"}
          </small>
        </div>
        {(error || stale) && (
          <div className="error" role="alert">
            {error ||
              "La collecte est interrompue. Les dernières valeurs ci-dessous sont anciennes."}
          </div>
        )}
        {["Vue d’ensemble", "Système"].includes(page) && (
          <>
            {!metrics ? (
              <p role="status">Collecte des métriques en cours…</p>
            ) : (
              <>
                <div className="cards">
                  <Card
                    label="PROCESSEUR"
                    value={pct(metrics.cpu_percent)}
                    detail={`${metrics.cpu_cores.length || "—"} cœurs logiques`}
                  />
                  <Card
                    label="MÉMOIRE"
                    value={pct(metrics.memory.percent)}
                    detail={`${bytes(metrics.memory.used)} / ${bytes(metrics.memory.total)}`}
                  />
                  <Card
                    label="STOCKAGE PRINCIPAL"
                    value={pct(
                      (
                        metrics.disks.find((d) => d.mount === "/") ||
                        metrics.disks[0]
                      )?.percent,
                    )}
                    detail="Système de fichiers /"
                  />
                  <Card
                    label="TEMPS DE FONCTIONNEMENT"
                    value={`${Math.floor(metrics.uptime_seconds / 3600)} h`}
                    detail={`Charge : ${metrics.load.map((v) => v.toFixed(2)).join(" · ")}`}
                  />
                </div>
                <div className="split">
                  <Graph history={history} />
                  <section className="panel">
                    <h2>Réseau</h2>
                    <p className="network">
                      ↓ {bytes(metrics.network.received_bps)}/s
                    </p>
                    <p className="network">
                      ↑ {bytes(metrics.network.sent_bps)}/s
                    </p>
                    <small>Débit agrégé des interfaces · octets/s</small>
                    <h2>Swap</h2>
                    <p>
                      {bytes(metrics.swap.used)} / {bytes(metrics.swap.total)}
                    </p>
                  </section>
                </div>
                <section className="panel">
                  <h2>Systèmes de fichiers</h2>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Point de montage</th>
                          <th>Utilisé</th>
                          <th>Capacité</th>
                          <th>Occupation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.disks.map((d) => (
                          <tr key={d.mount}>
                            <td>{d.mount}</td>
                            <td>{bytes(d.used)}</td>
                            <td>{bytes(d.total)}</td>
                            <td>{d.error || pct(d.percent)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
                {page === "Système" && (
                  <section className="panel">
                    <h2>Informations et capteurs</h2>
                    <p>{metrics.os}</p>
                    {metrics.temperatures.length ? (
                      metrics.temperatures.map((t, i) => (
                        <p key={i}>
                          {t.name} : {t.celsius.toFixed(1)} °C
                        </p>
                      ))
                    ) : (
                      <p>
                        Températures indisponibles : aucun capteur accessible.
                      </p>
                    )}
                    <p>GPU : collecte non implémentée.</p>
                  </section>
                )}
              </>
            )}
          </>
        )}
        {page === "Processus" && (
          <section className="panel">
            <h2>
              Processus{" "}
              <small>
                Triés par mémoire · CPU par cœur, peut dépasser 100 %
              </small>
            </h2>
            <input
              aria-label="Rechercher un processus"
              placeholder="Rechercher par nom…"
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
                    <th>Nom</th>
                    <th>Utilisateur</th>
                    <th>CPU</th>
                    <th>RAM</th>
                    <th>État</th>
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
                      <td>{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!processes.length && <p>Aucun résultat disponible.</p>}
            <div className="pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset((v) => Math.max(0, v - 50))}
              >
                Précédent
              </button>
              <span>{total} processus</span>
              <button
                disabled={offset + 50 >= total}
                onClick={() => setOffset((v) => v + 50)}
              >
                Suivant
              </button>
            </div>
          </section>
        )}
        {["IA locale", "Conteneurs"].includes(page) && (
          <>
            {moduleError && (
              <p className="error" role="alert">
                {moduleError} — les données précédentes sont anciennes.
              </p>
            )}
            {!module && !moduleError && (
              <p role="status">Vérification des intégrations…</p>
            )}
            {module && (
              <>
                <p className="module-time">
                  Vérification :{" "}
                  {new Date(module.collected_at).toLocaleTimeString()}
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
        <footer>
          Lecture seule · Données conservées localement · Aucun service cloud
        </footer>
      </main>
    </div>
  );
}
type AIStatus = Module & { ollama?: Module; openwebui?: Module };
function AIView({ data }: { data: AIStatus }) {
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
              <p>{m.message || `${m.latency_ms?.toFixed(0)} ms`}</p>
              {m.url && (
                <a href={m.url} target="_blank" rel="noreferrer">
                  Ouvrir {m.url} ↗
                </a>
              )}
              {m.models && (
                <>
                  <h3>Modèles installés</h3>
                  {!m.models.length && <p>Aucun modèle installé.</p>}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Nom</th>
                          <th>Taille</th>
                          <th>Famille</th>
                          <th>Quantification</th>
                        </tr>
                      </thead>
                      <tbody>
                        {m.models.map((model) => (
                          <tr key={model.name}>
                            <td>{model.name}</td>
                            <td>{bytes(model.size)}</td>
                            <td>{model.family || "Indisponible"}</td>
                            <td>{model.quantization || "Indisponible"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {m.loaded && (
                <p>
                  Modèles chargés :{" "}
                  {m.loaded.map((model) => model.name).join(", ") || "aucun"}
                </p>
              )}
            </section>
          ),
      )}
    </>
  );
}
