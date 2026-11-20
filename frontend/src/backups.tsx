import React, { useEffect, useState } from "react";
import { api, post } from "./api";
import { saveBlob } from "./files";
import { t, useLanguage } from "./i18n";
import type { Preferences } from "./preferences";
type Plan = {
  plan_id: string;
  expires_seconds: number;
  changes: { field: string; before: unknown; after: unknown }[];
};
export function BackupsView({
  token,
  csrf,
  onRestored,
}: {
  token: string;
  csrf: string;
  onRestored: (preferences: Preferences) => void;
}) {
  useLanguage();
  const [content, setContent] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [exportConfirmed, setExportConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [snapshots, setSnapshots] = useState<string[]>([]);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ items: string[] }>("backups", token, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setSnapshots(data.items);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [token, refresh]);
  useEffect(() => {
    if (!plan) return;
    const timer = setTimeout(() => {
      setPlan(null);
      setConfirmed(false);
      setNotice(t("Aperçu de restauration expiré ou modifié"));
    }, plan.expires_seconds * 1000);
    return () => clearTimeout(timer);
  }, [plan]);
  function change(value: string) {
    setContent(value);
    setPlan(null);
    setConfirmed(false);
    setNotice("");
  }
  async function run(job: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await job();
    } catch (e) {
      setPlan(null);
      setConfirmed(false);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t("Sauvegardes et restauration")}</h2>
      <p>
        {t(
          "Sauvegardez uniquement les préférences et règles d’alerte Cockpitor. Les fichiers, bases, conversations, secrets et configurations système sont exclus.",
        )}
      </p>
      <p>
        {t(
          "Les noms et cibles des règles figurent dans le fichier. Le checksum détecte une corruption, pas une origine fiable. Importez uniquement une copie de confiance.",
        )}
      </p>
      <label className="confirmation">
        <input
          type="checkbox"
          checked={exportConfirmed}
          disabled={busy}
          onChange={(e) => setExportConfirmed(e.target.checked)}
        />
        {t("Je confirme l’export des préférences locales")}
      </label>
      <button
        disabled={busy || !exportConfirmed}
        onClick={() =>
          void run(async () => {
            const backup = await post("backups/export", token, csrf, {
              confirmed: true,
            });
            saveBlob(
              new Blob([JSON.stringify(backup, null, 2)], {
                type: "application/json",
              }),
              "cockpitor-preferences.json",
            );
            setExportConfirmed(false);
            setNotice(t("Sauvegarde exportée et auditée."));
          })
        }
      >
        {t("Exporter les préférences")}
      </button>
      <h3>{t("Restaurer une copie")}</h3>
      <label>
        {t("Fichier de sauvegarde JSON")}{" "}
        <input
          type="file"
          accept="application/json,.json"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            change("");
            if (!file) return;
            void run(async () => {
              if (file.size > 32768)
                throw new Error(t("Sauvegarde invalide ou incompatible"));
              change(await file.text());
            });
          }}
        />
      </label>
      <label>
        {t("Contenu de la sauvegarde")}
        <textarea
          value={content}
          disabled={busy}
          maxLength={32768}
          onChange={(e) => change(e.target.value)}
        />
      </label>
      <button
        disabled={busy || !content.trim()}
        onClick={() =>
          void run(async () => {
            setPlan(
              await post<Plan>("backups/prepare", token, csrf, {
                backup: content,
              }),
            );
            setConfirmed(false);
          })
        }
      >
        {t("Examiner les différences")}
      </button>
      {plan && (
        <section aria-label={t("Différences de restauration")}>
          <h3>{t("Différences de restauration")}</h3>
          <p>
            {t(
              "Cet aperçu expire après deux minutes. Une copie de récupération est enregistrée avant toute restauration.",
            )}
          </p>
          {!plan.changes.length && <p>{t("Aucune différence.")}</p>}
          {plan.changes.map((row) => (
            <details key={row.field} open>
              <summary>
                {t(
                  (
                    {
                      language: "Langue",
                      theme: "Thème",
                      refresh_seconds: "Rafraîchissement",
                      retention_days: "Rétention",
                      rules: "Règles d’alerte",
                    } as Record<string, string>
                  )[row.field] || row.field,
                )}
              </summary>
              <p>{t("Avant")}</p>
              <pre>{JSON.stringify(row.before, null, 2)}</pre>
              <p>{t("Après")}</p>
              <pre>{JSON.stringify(row.after, null, 2)}</pre>
            </details>
          ))}
          <label className="confirmation">
            <input
              type="checkbox"
              disabled={busy}
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            {t("Je confirme le remplacement des préférences examinées")}
          </label>
          <button
            disabled={busy || !confirmed || !plan.changes.length}
            onClick={() =>
              void run(async () => {
                const result = await post<{ settings: Preferences }>(
                  "backups/restore",
                  token,
                  csrf,
                  { plan_id: plan.plan_id, confirmed: true },
                );
                setPlan(null);
                setConfirmed(false);
                change("");
                onRestored(result.settings);
                setNotice(
                  t(
                    "Préférences restaurées ; copie de récupération conservée.",
                  ),
                );
                setRefresh((v) => v + 1);
              })
            }
          >
            {t("Restaurer les préférences")}
          </button>
        </section>
      )}
      <h3>{t("Copies de récupération")}</h3>
      <p>
        {t(
          "Au maximum 20 copies, sans suppression automatique. Téléchargez une copie pour l’examiner ou la restaurer.",
        )}
      </p>
      {!snapshots.length && <p>{t("Aucune copie de récupération.")}</p>}
      {snapshots.map((id) => (
        <p key={id}>
          <code>{id.slice(0, 8)}</code>{" "}
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const data = await api(`backups/snapshot?id=${id}`, token);
                saveBlob(
                  new Blob([JSON.stringify(data, null, 2)], {
                    type: "application/json",
                  }),
                  "cockpitor-recovery.json",
                );
              })
            }
          >
            {t("Télécharger la copie")}
          </button>
        </p>
      ))}
      {busy && <p role="status">{t("Traitement en cours…")}</p>}
      {notice && <p role="status">{t(notice)}</p>}
      {error && (
        <p className="error" role="alert">
          {t(error)}
        </p>
      )}
    </section>
  );
}
