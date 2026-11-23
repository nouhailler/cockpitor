import React, { useEffect, useRef, useState } from "react";
import { api, post } from "./api";
import { t, useLanguage, getLocale } from "./i18n";
import { bytes } from "./format";
type Host = {
  id: string;
  label: string;
  group: string;
  address: string;
  port: number;
  username: string;
  host_key_fingerprint: string;
  configuration_id: string;
  allow_sftp: boolean;
  remote_root: string | null;
  last_check: {
    checked_at: string;
    status: string;
    host_key_verified: boolean;
  } | null;
};
type Inventory = { items: Host[]; configuration_error: boolean };
type Result = {
  checked_at: string;
  authenticated: boolean;
  host_key_verified: boolean;
  items?: { name: string; kind: string; size: number | null }[];
  truncated?: boolean;
};
export function RemoteView({ token, csrf }: { token: string; csrf: string }) {
  useLanguage();
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [group, setGroup] = useState("");
  const [selected, setSelected] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    void api<Inventory>("remote/hosts", token, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted) setInventory(data);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [token, refresh]);
  const hosts =
    inventory?.items.filter((host) => !group || host.group === group) || [];
  const host = hosts.find((row) => row.id === selected);
  function reset() {
    setConfirmed(false);
    setResult(null);
    setError("");
  }
  async function connect(kind: "check" | "list") {
    if (!host || !confirmed || busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    controller.current = new AbortController();
    try {
      const data = await post<Result>(
        `remote/${kind}`,
        token,
        csrf,
        {
          host_id: host.id,
          configuration_id: host.configuration_id,
          confirmed: true,
        },
        controller.current.signal,
      );
      if (mounted.current) setResult(data);
    } catch (e) {
      if (mounted.current)
        setError(
          (e as Error).name === "AbortError"
            ? t("Connexion distante annulée")
            : (e as Error).message,
        );
    } finally {
      if (mounted.current) {
        setBusy(false);
        setConfirmed(false);
        setRefresh((value) => value + 1);
      }
    }
  }
  return (
    <section className="panel">
      <h2>{t("Hôtes distants SSH/SFTP")}</h2>
      <p>
        {t(
          "Aucune connexion automatique. Chaque lecture exige une confirmation et une clé d’hôte épinglée. Aucun terminal, commande distante, transfert ou écriture.",
        )}
      </p>
      {inventory?.configuration_error && (
        <p role="alert">
          {t("Configuration des hôtes refusée ; aucune connexion disponible.")}
        </p>
      )}
      {inventory && !inventory.items.length && (
        <p>
          {t(
            "Aucun hôte configuré. Définissez LOCALCOCKPIT_REMOTE_HOSTS au lancement avec une clé d’hôte vérifiée hors bande.",
          )}
        </p>
      )}
      {!!inventory?.items.length && (
        <>
          <div className="filters">
            <label>
              {t("Groupe d’hôtes")}{" "}
              <select
                value={group}
                disabled={busy}
                onChange={(e) => {
                  setGroup(e.target.value);
                  setSelected("");
                  reset();
                }}
              >
                <option value="">{t("Tous les groupes")}</option>
                {[...new Set(inventory.items.map((row) => row.group))]
                  .filter(Boolean)
                  .map((value) => (
                    <option key={value}>{value}</option>
                  ))}
              </select>
            </label>
            <label>
              {t("Hôte distant")}{" "}
              <select
                value={selected}
                disabled={busy}
                onChange={(e) => {
                  setSelected(e.target.value);
                  reset();
                }}
              >
                <option value="">{t("Choisir un hôte")}</option>
                {hosts.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.label} · {row.address}:{row.port}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {host && (
            <>
              <dl>
                <dt>{t("Destination SSH")}</dt>
                <dd>
                  {host.username}@{host.address}:{host.port}
                </dd>
                <dt>{t("Empreinte de clé d’hôte attendue")}</dt>
                <dd className="fingerprint">{host.host_key_fingerprint}</dd>
                <dt>{t("Racine SFTP configurée")}</dt>
                <dd>
                  {host.allow_sftp
                    ? host.remote_root
                    : t("Lecture SFTP non autorisée pour cet hôte")}
                </dd>
                <dt>{t("Dernière tentative enregistrée")}</dt>
                <dd>
                  {host.last_check
                    ? `${new Date(host.last_check.checked_at).toLocaleString(getLocale())} · ${t(({ available: "Connexion vérifiée", host_key_rejected: "Clé d’hôte refusée", authentication_failed: "Authentification distante refusée", unavailable: "Indisponible" } as Record<string, string>)[host.last_check.status] || "Indisponible")}`
                    : t("Aucune tentative")}
                </dd>
              </dl>
              <p>
                {t(
                  "Vérifiez la destination et l’empreinte par un canal de confiance. Une lecture SFTP reste limitée par les droits du compte distant ; un chroot doit être imposé sur le serveur pour un confinement fort.",
                )}
              </p>
              <label className="confirmation">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={busy}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                {t(
                  "Je confirme cette connexion vers l’hôte et la clé affichés",
                )}
              </label>
              <div className="filters">
                <button
                  disabled={busy || !confirmed}
                  onClick={() => void connect("check")}
                >
                  {t("Vérifier la connexion SSH")}
                </button>
                <button
                  disabled={busy || !confirmed || !host.allow_sftp}
                  onClick={() => void connect("list")}
                >
                  {t("Lister la racine SFTP")}
                </button>
                {busy && (
                  <button
                    onClick={() => {
                      controller.current?.abort();
                      void post("remote/cancel", token, csrf).catch(() => {});
                    }}
                  >
                    {t("Annuler")}
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
      {busy && <p role="status">{t("Connexion SSH/SFTP en cours…")}</p>}
      {error && (
        <p role="alert" className="error">
          {t(error)}
        </p>
      )}
      {result && (
        <section aria-label={t("Résultat de connexion")}>
          <p role="status">
            {result.host_key_verified && result.authenticated
              ? t(
                  "Connexion vérifiée à cet instant ; session SSH fermée après lecture.",
                )
              : t("Connexion non vérifiée")}
          </p>
          <p>{new Date(result.checked_at).toLocaleString(getLocale())}</p>
          {result.truncated && (
            <p>
              {t("Liste SFTP limitée aux 200 premières entrées examinées.")}
            </p>
          )}
          {result.items && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Nom")}</th>
                    <th>{t("Type")}</th>
                    <th>{t("Taille")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((row) => (
                    <tr key={row.name}>
                      <td>{row.name}</td>
                      <td>
                        {t(
                          row.kind === "directory"
                            ? "Dossier"
                            : row.kind === "file"
                              ? "Fichier"
                              : "Lecture bloquée",
                        )}
                      </td>
                      <td>{row.size === null ? "—" : bytes(row.size)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!result.items.length && <p>{t("Aucun résultat disponible.")}</p>}
            </div>
          )}
        </section>
      )}
    </section>
  );
}
