import React, { useEffect, useState } from "react";
import { api } from "./api";
import { bytes } from "./format";
import { getLanguage, t, useLanguage } from "./i18n";

type Options = {
  roots: { id: string; label: string }[];
  configuration_error: boolean;
};
type Listing = {
  items: { name: string; kind: string; size: number | null }[];
  truncated: boolean;
};
export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function FilesView({ token }: { token: string }) {
  useLanguage();
  const [options, setOptions] = useState<Options | null>(null);
  const [root, setRoot] = useState("");
  const [path, setPath] = useState("");
  const [query, setQuery] = useState("");
  const [listing, setListing] = useState<Listing | null>(null);
  const [preview, setPreview] = useState<{
    name: string;
    text: string;
    truncated: boolean;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void api<Options>("files/options", token, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setOptions(data);
          setRoot(data.roots[0]?.id || "");
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [token]);
  useEffect(() => {
    setListing(null);
    setPreview(null);
    setSelected("");
    if (!root) return;
    const controller = new AbortController();
    setError("");
    void api<Listing>(
      `files?${new URLSearchParams({ root, path, q: query })}`,
      token,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setListing(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [token, root, path, query, refresh]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setPreview(null);
    setError("");
    const target = path ? `${path}/${selected}` : selected;
    void api<{ text: string; truncated: boolean }>(
      `files/preview?${new URLSearchParams({ root, path: target })}`,
      token,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setPreview({ name: selected, ...data });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [token, root, path, selected]);
  async function download(name: string) {
    setBusy(true);
    setError("");
    try {
      const target = path ? `${path}/${name}` : name;
      const response = await fetch(
        `/api/v1/files/download?${new URLSearchParams({ root, path: target })}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            "Accept-Language": getLanguage(),
          },
          signal: AbortSignal.timeout(8000),
        },
      );
      if (!response.ok) {
        if (response.status === 401)
          window.dispatchEvent(new Event("session-expired"));
        throw new Error(
          (await response.json()).error?.message ||
            t("Lecture refusée ou fichier indisponible"),
        );
      }
      saveBlob(await response.blob(), name);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t("Explorateur de fichiers")}</h2>
      <p>
        {t(
          "Lecture seule dans les racines autorisées. Aucun lien symbolique suivi. Aperçu texte expurgé ; téléchargement original limité à 1 Mio.",
        )}
      </p>
      {options?.configuration_error && (
        <p role="alert">
          {t("Configuration des racines refusée ; aucun dossier exposé.")}
        </p>
      )}
      {options && !options.roots.length && (
        <p>
          {t(
            "Aucune racine configurée. Définissez LOCALCOCKPIT_FILE_ROOTS au lancement.",
          )}
        </p>
      )}
      {!!options?.roots.length && (
        <>
          <div className="filters">
            <label>
              {t("Racine autorisée")}{" "}
              <select
                value={root}
                disabled={busy}
                onChange={(e) => {
                  setRoot(e.target.value);
                  setPath("");
                  setQuery("");
                }}
              >
                {options.roots.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              disabled={!path || busy}
              onClick={() => {
                setPath(path.split("/").slice(0, -1).join("/"));
                setQuery("");
              }}
            >
              {t("Dossier parent")}
            </button>
            <button disabled={busy} onClick={() => setRefresh((v) => v + 1)}>
              {t("Actualiser")}
            </button>
          </div>
          <p>
            {t("Dossier relatif")} : {path || "/"}
          </p>
          <label>
            {t("Filtrer le dossier courant")}{" "}
            <input
              value={query}
              maxLength={100}
              disabled={busy}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {!listing && !error && <p role="status">{t("Chargement…")}</p>}
          {listing?.truncated && (
            <p role="status">
              {t(
                "Lecture limitée aux 500 premières entrées ; le filtre porte uniquement sur ces entrées.",
              )}
            </p>
          )}
          {listing && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Nom")}</th>
                    <th>{t("Type")}</th>
                    <th>{t("Taille")}</th>
                    <th>{t("Actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {listing.items.map((row) => (
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
                      <td>
                        {row.kind === "directory" && (
                          <button
                            disabled={busy}
                            onClick={() => {
                              setPath(path ? `${path}/${row.name}` : row.name);
                              setQuery("");
                            }}
                          >
                            {t("Ouvrir")}
                          </button>
                        )}
                        {row.kind === "file" && (
                          <>
                            <button
                              disabled={busy}
                              onClick={() => setSelected(row.name)}
                            >
                              {t("Aperçu texte")}
                            </button>{" "}
                            <button
                              disabled={busy || (row.size ?? 0) > 1048576}
                              onClick={() => void download(row.name)}
                            >
                              {t("Télécharger l’original")}
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!listing.items.length && (
                <p>{t("Aucun résultat disponible.")}</p>
              )}
            </div>
          )}
        </>
      )}
      {preview && (
        <section aria-label={t("Aperçu texte")}>
          <h3>{preview.name}</h3>
          <pre>{preview.text}</pre>
          {preview.truncated && <p>{t("Aperçu tronqué à 16 Kio.")}</p>}
        </section>
      )}
      {error && (
        <p role="alert" className="error">
          {t(error)}
        </p>
      )}
    </section>
  );
}
