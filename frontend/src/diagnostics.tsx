import { t, useLanguage, getLocale, formatNumber, getLanguage } from "./i18n";
import React, { useEffect, useState } from "react";
import { api } from "./api";

export function DiagnosticView({ token }: { token: string }) {
  useLanguage();
  const [csrf, setCsrf] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [state, setState] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ csrf_token: string }>(
      "diagnostics/options",
      token,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setCsrf(data.csrf_token);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError((e as Error).message);
      });
    return () => controller.abort();
  }, [token]);
  async function download() {
    if (!confirmed || !csrf) return;
    setBusy(true);
    setError("");
    setState("");
    let url: string | null = null;
    try {
      const response = await fetch("/api/v1/diagnostics", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Accept-Language": getLanguage(),
          "Content-Type": "application/json",
          "X-LocalCockpit-CSRF": csrf,
        },
        body: JSON.stringify({ confirmed: true }),
        signal: AbortSignal.timeout(8000),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(
          data.error?.message || `Erreur HTTP ${response.status}`,
        );
      }
      const blob = await response.blob();
      url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "cockpitor-diagnostic.json";
      document.body.append(link);
      link.click();
      link.remove();
      setState(
        response.headers.get("X-Diagnostic-Audit") === "recorded"
          ? t("Diagnostic téléchargé et export audité.")
          : t(
              "Diagnostic téléchargé ; audit indisponible car le stockage ne répond pas.",
            ),
      );
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (url) URL.revokeObjectURL(url);
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t("Diagnostic local expurgé")}</h2>
      <p>
        {t(
          "Le fichier JSON contient des métriques agrégées, les états et nombres de modules, des réglages non sensibles et les compteurs d’alertes. Il est généré à partir des derniers instantanés disponibles, sans commande supplémentaire.",
        )}{" "}
      </p>
      <h3>{t("Données exclues")}</h3>
      <p>
        {t(
          "Aucun nom de machine, utilisateur, processus, service, modèle ou conteneur ; aucun identifiant de conteneur, chemin, adresse réseau, URL d’intégration, journal, environnement, commande ou jeton.",
        )}{" "}
      </p>
      <p>
        {t(
          "Les systèmes de fichiers sont anonymisés. Aucun fichier n’est conservé sur le serveur et rien n’est envoyé à un service externe. Vérifiez le téléchargement avant de le partager.",
        )}{" "}
      </p>
      <label className="confirmation">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />{" "}
        {t(
          "Je confirme la génération et le téléchargement du diagnostic local.",
        )}{" "}
      </label>
      <p>
        <button
          disabled={!confirmed || !csrf || busy}
          onClick={() => void download()}
        >
          {busy ? t("Génération…") : t("Télécharger le diagnostic JSON")}
        </button>
      </p>
      {error && (
        <p className="error" role="alert">
          {t(error)}
        </p>
      )}
      {state && <p role="status">{t(state)}</p>}
    </section>
  );
}
