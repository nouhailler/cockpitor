import React, { useEffect, useRef, useState } from "react";
import { api, post } from "./api";
import { t, useLanguage, getLocale } from "./i18n";

type Plan = {
  id: string;
  action: string;
  target: string;
  engine: string | null;
  status: string;
  fingerprint: string;
  snapshot: unknown;
  expires_seconds: number;
  approval_expires_seconds: number;
  mode: string;
  system_execution_enabled: boolean;
};
type Operation = {
  id: string;
  action: string;
  status: string;
  updated_at: string;
};
const labels: Record<string, string> = {
  "service.start": "Démarrage de service",
  "service.stop": "Arrêt de service",
  "service.restart": "Redémarrage de service",
  "container.start": "Démarrage de conteneur",
  "container.restart": "Redémarrage de conteneur",
};
export function ActionsView({ token, csrf }: { token: string; csrf: string }) {
  useLanguage();
  const [action, setAction] = useState("service.restart");
  const [target, setTarget] = useState("");
  const [engine, setEngine] = useState("docker");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [approval, setApproval] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [operations, setOperations] = useState<Operation[]>([]);
  const [version, setVersion] = useState(0);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const active = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      active.current?.abort();
      setApproval("");
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ items: Operation[]; total: number }>(
      `operations?offset=${offset}`,
      token,
      controller.signal,
    )
      .then((value) => {
        setOperations(value.items);
        setTotal(value.total);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [token, version, offset]);
  async function execute(kind: "prepare" | "approve" | "simulate") {
    setBusy(true);
    setError("");
    setNotice("");
    active.current = new AbortController();
    try {
      if (kind === "prepare") {
        setPlan(null);
        setApproval("");
        setConfirmed(false);
        const value = await post<Plan>(
          "action-plans/prepare",
          token,
          csrf,
          {
            action,
            target,
            engine: action.startsWith("container.") ? engine : null,
          },
          active.current.signal,
        );
        if (mounted.current) setPlan(value);
      } else if (kind === "approve" && plan) {
        const value = await post<{ plan: Plan; approval_token: string }>(
          "action-plans/approve",
          token,
          csrf,
          { plan_id: plan.id, fingerprint: plan.fingerprint, confirmed },
          active.current.signal,
        );
        if (mounted.current) {
          setPlan(value.plan);
          setApproval(value.approval_token);
          setConfirmed(false);
        }
      } else if (kind === "simulate" && plan) {
        const credential = approval;
        setApproval("");
        const value = await post<{
          plan: Plan;
          commands_executed: boolean;
          system_changed: boolean;
        }>(
          "action-plans/simulate",
          token,
          csrf,
          { plan_id: plan.id, approval_token: credential },
          active.current.signal,
        );
        if (mounted.current) {
          setPlan(value.plan);
          setNotice(
            t(
              "Simulation terminée : aucune commande de modification exécutée, aucun changement système.",
            ),
          );
        }
      }
    } catch (e) {
      if (mounted.current) {
        setError(
          (e as Error).name === "AbortError"
            ? t("Simulation annulée")
            : (e as Error).message,
        );
        if (kind !== "prepare") {
          setApproval("");
          setPlan(null);
        }
      }
    } finally {
      if (mounted.current) {
        setBusy(false);
        setVersion((v) => v + 1);
      }
    }
  }
  async function cancel() {
    if (!plan) return;
    active.current?.abort();
    setApproval("");
    setConfirmed(false);
    try {
      const value = await post<Plan>("action-plans/cancel", token, csrf, {
        plan_id: plan.id,
      });
      if (mounted.current) {
        setPlan(value);
        setNotice(t("Plan annulé."));
        setVersion((v) => v + 1);
      }
    } catch (e) {
      if (mounted.current) setError((e as Error).message);
    }
  }
  const terminal =
    plan && !["prepared", "approved", "simulating"].includes(plan.status);
  return (
    <>
      <section className="panel">
        <h2>{t("Actions contrôlées — simulation uniquement")}</h2>
        <p>
          {t(
            "Ce parcours vérifie les protections sans démarrer, arrêter ou redémarrer de ressource. L’exécution système est désactivée et aucun agent privilégié n’est installé.",
          )}
        </p>
        <p>
          {t(
            "Cible exacte issue d’un inventaire récent, vérifiée à chaque étape. Les services critiques sont exclus. Le plan expire après 120 secondes ; son approbation après 60 secondes au maximum.",
          )}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void execute("prepare");
          }}
        >
          <div className="filters">
            <label>
              {t("Action à examiner")}
              <select
                disabled={busy || (!!plan && !terminal)}
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                {Object.entries(labels).map(([value, label]) => (
                  <option value={value} key={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            {action.startsWith("container.") && (
              <label>
                {t("Moteur")}
                <select
                  disabled={busy || (!!plan && !terminal)}
                  value={engine}
                  onChange={(e) => setEngine(e.target.value)}
                >
                  <option value="docker">Docker</option>
                  <option value="podman">Podman</option>
                </select>
              </label>
            )}
            <label>
              {t("Cible exacte")}
              <input
                required
                maxLength={200}
                autoComplete="off"
                disabled={busy || (!!plan && !terminal)}
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </label>
          </div>
          <button disabled={busy || (!!plan && !terminal)}>
            {t("Préparer le plan de simulation")}
          </button>
        </form>
        {plan && (
          <article className="rule-editor">
            <h3>
              {t(labels[plan.action] || plan.action)} · {plan.target}
            </h3>
            <p>
              {t("État")} : {t(plan.status)} · {t("Identifiant")} : {plan.id}
            </p>
            <p>
              {t(
                "Les durées affichées sont celles de la dernière réponse ; le serveur vérifie l’expiration à chaque étape.",
              )}
            </p>
            <p>
              {t("Validité restante du plan : {0} s", {
                0: plan.expires_seconds,
              })}
            </p>
            <details>
              <summary>{t("Instantané de référence et empreinte")}</summary>
              <pre>{JSON.stringify(plan.snapshot, null, 2)}</pre>
              <code>{plan.fingerprint}</code>
            </details>
            {plan.status === "prepared" && (
              <>
                <label className="confirmation">
                  <input
                    type="checkbox"
                    disabled={busy}
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  {t(
                    "J’approuve uniquement la simulation de ce plan pour cette cible exacte.",
                  )}
                </label>
                <button
                  disabled={busy || !confirmed}
                  onClick={() => void execute("approve")}
                >
                  {t("Approuver ce plan de simulation")}
                </button>
              </>
            )}
            {plan.status === "approved" && (
              <>
                <p>
                  {t("Approbation à usage unique : {0} s maximum", {
                    0: plan.approval_expires_seconds,
                  })}
                </p>
                <button
                  disabled={busy || !approval}
                  onClick={() => void execute("simulate")}
                >
                  {t("Lancer la simulation approuvée")}
                </button>
              </>
            )}
            {!terminal && (
              <button onClick={() => void cancel()}>
                {t("Annuler le plan")}
              </button>
            )}
            {terminal && (
              <button
                onClick={() => {
                  setPlan(null);
                  setApproval("");
                  setConfirmed(false);
                }}
              >
                {t("Nouveau plan")}
              </button>
            )}
          </article>
        )}
        {busy && <p role="status">{t("Vérifications en cours…")}</p>}
        {error && (
          <p className="error" role="alert">
            {t(error)}
          </p>
        )}
        {notice && <p role="status">{t(notice)}</p>}
      </section>
      <section className="panel">
        <h2>{t("Historique des simulations")}</h2>
        <p>
          {t(
            "Historique partagé du compte local, sans cible ni jeton. Les approbations ne survivent pas au redémarrage.",
          )}
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t("Date")}</th>
                <th>{t("Action")}</th>
                <th>{t("État")}</th>
                <th>{t("Opération")}</th>
              </tr>
            </thead>
            <tbody>
              {operations.map((row) => (
                <tr key={row.id}>
                  <td>
                    {new Date(row.updated_at).toLocaleString(getLocale())}
                  </td>
                  <td>{t(labels[row.action] || row.action)}</td>
                  <td>{t(row.status)}</td>
                  <td>{row.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset((v) => Math.max(0, v - 50))}
          >
            {t("Précédent")}
          </button>
          <span>{total}</span>
          <button
            disabled={offset + 50 >= total}
            onClick={() => setOffset((v) => v + 50)}
          >
            {t("Suivant")}
          </button>
        </div>
      </section>
    </>
  );
}
