import React, { useEffect, useState } from "react";
import { api } from "./api";
import { bytes } from "./format";
import { t, useLanguage, getLocale, formatNumber } from "./i18n";
import { Graph } from "./components";
import type { History } from "./types";

type Section = { status: string; code?: string; data?: any; scope?: string };
type Inspection = {
  ups?: {
    status: string;
    items: { name: string; status: string; values: Record<string, string> }[];
  };
  collected_at: string;
  network: {
    interfaces: { name: string; up: boolean; addresses: string[] }[];
    listeners: {
      address: string;
      port: number;
      protocol: string;
      scope: string;
    }[];
    listeners_status: string;
    dns?: string[];
    routes?: { interface: string; destination: string; gateway: string }[];
  };
  disks: Section;
  gpu: Section;
  updates: Section;
  time: Section;
  installed_services: Section;
  power: { status: string; items: any[] };
  smart: { device: string; status: string; passed?: boolean }[];
};
export function AuditView({ token }: { token: string }) {
  useLanguage();
  const [data, setData] = useState<{
    items: { id: string; action: string; timestamp: string }[];
    total: number;
  }>({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void api<typeof data>(`audit?offset=${offset}`, token, controller.signal)
      .then((value) => {
        setData(value);
        setError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [token, offset]);
  return (
    <section className="panel">
      <h2>{t("Historique d’audit")}</h2>
      <p>
        {t("Les 1000 dernières opérations applicatives, sans corps ni jeton.")}
      </p>
      {error && <p role="alert">{t(error)}</p>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("Date")}</th>
              <th>{t("Action")}</th>
              <th>{t("Opération")}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.timestamp).toLocaleString(getLocale())}</td>
                <td>{row.action}</td>
                <td>{row.id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          {t("Précédent")}
        </button>
        <span>{data.total}</span>
        <button
          disabled={offset + 50 >= data.total}
          onClick={() => setOffset(offset + 50)}
        >
          {t("Suivant")}
        </button>
      </div>
    </section>
  );
}
function Tree({ items }: { items: any[] }) {
  return (
    <ul>
      {items.map((item, index) => (
        <li key={index}>
          {item.name} · {item.type} · {bytes(item.size)} · {item.fstype || "—"}{" "}
          · {item.mountpoint || "—"}
          {item.children && <Tree items={item.children} />}
        </li>
      ))}
    </ul>
  );
}
function State({ value }: { value: Section }) {
  return value.status !== "available" ? (
    <p>{t("Outil absent, accès refusé ou données indisponibles.")}</p>
  ) : null;
}
export function MonitoringView({ token }: { token: string }) {
  useLanguage();
  const [data, setData] = useState<Inspection | null>(null);
  const [history, setHistory] = useState<History>([]);
  const [hours, setHours] = useState(24);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await api<Inspection>(
          "system/inspection",
          token,
          controller.signal,
        );
        setData(value);
        setError("");
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 30000);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [token]);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ items: History }>(
      `system/trends?hours=${hours}`,
      token,
      controller.signal,
    )
      .then((value) => {
        setHistory(value.items);
        setHistoryError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setHistoryError(e.message);
      });
    return () => controller.abort();
  }, [token, hours, data?.collected_at]);
  return (
    <>
      <section className="panel">
        <h2>{t("Tendances persistantes")}</h2>
        <label>
          {t("Période")}{" "}
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
          >
            <option value={24}>24 h</option>
            <option value={168}>{t("7 jours")}</option>
          </select>
        </label>
        <p>
          {t(
            "Un échantillon par minute, conservé sept jours. Les périodes sans collecte restent absentes.",
          )}
        </p>
        {historyError && <p role="alert">{t(historyError)}</p>}
      </section>
      <Graph history={history} persistent />
      {error && <p role="alert">{t(error)}</p>}
      {data && (
        <>
          <p>
            {t("Vérification :")}{" "}
            {new Date(data.collected_at).toLocaleString(getLocale())}{" "}
            {Date.now() - Date.parse(data.collected_at) > 90000 &&
              t("Données anciennes")}
          </p>
          <section className="panel">
            <h2>{t("Réseau et exposition")}</h2>
            <p>
              {t(
                "Une écoute locale ne prouve pas une exposition Internet. Aucun scan actif n’est effectué.",
              )}
            </p>
            {data.network.interfaces.map((row) => (
              <p key={row.name}>
                {row.name} · {t(row.up ? "active" : "inactive")} ·{" "}
                {row.addresses.join(", ")}
              </p>
            ))}
            <h3>DNS</h3>
            <p>{data.network.dns?.join(", ") || t("Indisponible")}</p>
            <h3>{t("Routes IPv4")}</h3>
            {data.network.routes?.map((route, i) => (
              <p key={i}>
                {route.interface} · {route.destination} → {route.gateway}
              </p>
            ))}
            <h3>{t("Ports en écoute")}</h3>
            {data.network.listeners_status !== "available" && (
              <p>{t("Droits de lecture insuffisants")}</p>
            )}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Adresse")}</th>
                    <th>{t("Port")}</th>
                    <th>{t("Portée")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.network.listeners.map((row, i) => (
                    <tr key={i}>
                      <td>{row.address}</td>
                      <td>
                        {row.port}/{row.protocol}
                      </td>
                      <td>{t(row.scope)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <h2>{t("Disques, partitions et SMART")}</h2>
            <State value={data.disks} />
            {data.disks.data && (
              <Tree items={data.disks.data.blockdevices || []} />
            )}
            <p>
              {t(
                "SMART est consulté sans élévation de droits sur quatre disques au maximum.",
              )}
            </p>
            {data.smart.map((row) => (
              <p key={row.device}>
                {row.device} :{" "}
                {t(
                  row.status !== "available"
                    ? "Indisponible"
                    : row.passed
                      ? "État SMART correct"
                      : "Alerte SMART",
                )}
              </p>
            ))}
          </section>
          <section className="panel">
            <h2>GPU</h2>
            <State value={data.gpu} />
            <p>
              {t("Sondes NVIDIA uniquement ; aucun pilote n’est installé.")}
            </p>
            {data.gpu.data?.map((row: any, i: number) => (
              <p key={i}>
                {row.name} · {formatNumber(row.utilization)} % ·{" "}
                {formatNumber(row.memory_used_mib)} /{" "}
                {formatNumber(row.memory_total_mib)} MiB
              </p>
            ))}
          </section>
          <section className="panel">
            <h2>{t("Mises à jour disponibles")}</h2>
            <p>
              {t(
                "Lecture du cache APT existant, sans actualisation ni installation.",
              )}
            </p>
            <State value={data.updates} />
            {data.updates.data?.map((row: any, i: number) => (
              <p key={i}>
                {row.package} · {row.version}
              </p>
            ))}
            {data.updates.status === "available" &&
              !data.updates.data?.length && (
                <p>{t("Aucune mise à jour annoncée par le cache local.")}</p>
              )}
          </section>
          <section className="panel">
            <h2>{t("Services installés")}</h2>
            <State value={data.installed_services} />
            <details>
              <summary>{t("Afficher les unités installées")}</summary>
              {data.installed_services.data?.map((row: any, i: number) => (
                <p key={i}>
                  {row.unit} · {row.state}
                </p>
              ))}
            </details>
          </section>
          <div className="split">
            <section className="panel">
              <h2>{t("Synchronisation de l’heure")}</h2>
              <State value={data.time} />
              {data.time.data && (
                <pre>{JSON.stringify(data.time.data, null, 2)}</pre>
              )}
            </section>
            <section className="panel">
              <h2>{t("Alimentation")}</h2>
              <p>
                {t(
                  "Périphériques du noyau et onduleurs NUT locaux, sans configuration ni commande de contrôle.",
                )}
              </p>
              {data.ups?.items.map((ups, i) => (
                <p key={i}>
                  {ups.name} · {t(ups.status)} ·{" "}
                  {Object.entries(ups.values)
                    .map(([key, value]) => `${key}: ${value}`)
                    .join(" · ")}
                </p>
              ))}
              {data.power.status !== "available" ? (
                <p>{t("Indisponible")}</p>
              ) : (
                data.power.items.map((row: any, i: number) => (
                  <p key={i}>
                    {row.name} · {row.type} · {row.status} ·{" "}
                    {row.capacity ?? "—"}%
                  </p>
                ))
              )}
            </section>
          </div>
        </>
      )}
    </>
  );
}
