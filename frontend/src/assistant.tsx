import React, { useEffect, useRef, useState } from "react";
import { api, post } from "./api";
import { t, useLanguage, getLocale, formatNumber } from "./i18n";
type SystemContext = {
  source?: string;
  collected_at?: string;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  swap_percent?: number | null;
};
const diagnosticQuestions = [
  "Quels contrôles en lecture seule proposer pour une machine lente ?",
  "Comment distinguer une pression mémoire d’une utilisation CPU élevée ?",
  "Explique les observations jointes, leurs limites et les vérifications utiles.",
];
function ContextSummary({ context }: { context: SystemContext }) {
  return (
    <section aria-label={t("Observations système")}>
      <p>
        {t("Source des observations")} : {context.source || t("Indisponible")}
      </p>
      <p>
        {t("Date des observations")} :{" "}
        {context.collected_at &&
        Number.isFinite(Date.parse(context.collected_at))
          ? new Date(context.collected_at).toLocaleString(getLocale())
          : t("Indisponible")}
      </p>
      <dl>
        {(
          [
            ["Utilisation CPU", context.cpu_percent],
            ["Utilisation RAM", context.memory_percent],
            ["Utilisation swap", context.swap_percent],
          ] as const
        ).map(([label, value]) => (
          <React.Fragment key={label}>
            <dt>{t(label)}</dt>
            <dd>
              {typeof value === "number" && Number.isFinite(value)
                ? `${formatNumber(value)} %`
                : t("Indisponible")}
            </dd>
          </React.Fragment>
        ))}
      </dl>
      <details>
        <summary>{t("Données techniques des observations")}</summary>
        <pre>{JSON.stringify(context, null, 2)}</pre>
      </details>
    </section>
  );
}
type ChatMessage = { role: string; content: string; context?: SystemContext };
export function AssistantView({
  token,
  csrf,
}: {
  token: string;
  csrf: string;
}) {
  useLanguage();
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [retain, setRetain] = useState(false);
  const [threads, setThreads] = useState<{ id: string; created_at: string }[]>(
    [],
  );
  const [thread, setThread] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [preview, setPreview] = useState<{
    context_id: string;
    context: SystemContext;
  } | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [include, setInclude] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    void api<{ ollama: { models?: { name: string; local?: boolean }[] } }>(
      "ai/status",
      token,
      abort.signal,
    )
      .then((value) => {
        const names =
          value.ollama.models
            ?.filter((m) => m.local !== false)
            .map((m) => m.name) || [];
        setModels(names);
        setModel(names[0] || "");
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    void api<{ items: typeof threads }>("ai/threads", token, abort.signal)
      .then((value) => setThreads(value.items))
      .catch(() => {});
    return () => {
      mounted.current = false;
      abort.abort();
      controller.current?.abort();
    };
  }, [token]);
  async function open(id: string) {
    setThread(id);
    setPreview(null);
    setInclude(false);
    setError("");
    if (!id) {
      setMessages([]);
      return;
    }
    try {
      const data = await api<{ items: ChatMessage[] }>(
        `ai/thread?id=${encodeURIComponent(id)}`,
        token,
      );
      setMessages(data.items);
      setRetain(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function send() {
    setBusy(true);
    setError("");
    controller.current = new AbortController();
    try {
      const data = await post<{
        answer: string;
        thread_id: string | null;
        context?: SystemContext;
      }>(
        "ai/chat",
        token,
        csrf,
        {
          model,
          prompt,
          history: messages.slice(-8).map((message) => ({
            role: message.role,
            content: message.content.slice(0, 4000),
          })),
          retain,
          thread_id: thread || null,
          context_id: include ? preview?.context_id : null,
        },
        controller.current.signal,
      );
      if (!mounted.current) return;
      setMessages((old) => [
        ...old,
        { role: "user", content: prompt },
        { role: "assistant", content: data.answer, context: data.context },
      ]);
      setPrompt("");
      setThread(data.thread_id || "");
      setPreview(null);
      setInclude(false);
      if (retain) {
        const saved = await api<{ items: typeof threads }>("ai/threads", token);
        if (mounted.current) setThreads(saved.items);
      }
    } catch (e) {
      if (mounted.current)
        setError(
          (e as Error).name === "AbortError"
            ? t("Génération annulée")
            : (e as Error).message,
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t("Assistant IA local")}</h2>
      <p>
        {t(
          "Ollama uniquement. Les réponses proposent des diagnostics ; aucune commande n’est exécutée. Vérifiez les conseils avant de les appliquer.",
        )}
      </p>
      <div className="filters">
        <label>
          {t("Modèle")}{" "}
          <select
            disabled={busy}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {!models.length && (
              <option value="">{t("Aucun modèle installé.")}</option>
            )}
            {models.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          {t("Conversation")}{" "}
          <select
            disabled={busy}
            value={thread}
            onChange={(e) => void open(e.target.value)}
          >
            <option value="">{t("Nouvelle conversation")}</option>
            {threads.map((row) => (
              <option value={row.id} key={row.id}>
                {new Date(row.created_at).toLocaleString(getLocale())} ·{" "}
                {row.id.slice(0, 6)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p>
        {t(
          "Enregistrement facultatif : 20 conversations, 40 messages par conversation. Le masquage des secrets est partiel ; ne saisissez aucun identifiant sensible.",
        )}
      </p>
      <label className="confirmation">
        <input
          type="checkbox"
          checked={retain}
          disabled={busy}
          onChange={(e) => setRetain(e.target.checked)}
        />
        {t("Conserver cette conversation localement")}
      </label>
      <button
        disabled={busy || previewBusy}
        onClick={async () => {
          setPreviewBusy(true);
          setPreview(null);
          setInclude(false);
          try {
            const result = await post<{
              context_id: string;
              context: SystemContext;
            }>("ai/context", token, csrf);
            if (mounted.current) {
              setPreview(result);
              setError("");
            }
          } catch (e) {
            if (mounted.current) setError((e as Error).message);
          } finally {
            if (mounted.current) setPreviewBusy(false);
          }
        }}
      >
        {t("Préparer un aperçu du contexte système")}
      </button>
      {preview && (
        <>
          <ContextSummary context={preview.context} />
          <p>
            {t(
              "Aperçu figé, valable au plus cinq minutes après la collecte. Actualisez-le avant un nouveau diagnostic.",
            )}
          </p>
          <label className="confirmation">
            <input
              type="checkbox"
              checked={include}
              disabled={busy}
              onChange={(e) => setInclude(e.target.checked)}
            />
            {t("Joindre uniquement ces observations au prochain message")}
          </label>
        </>
      )}
      <div className="chat-messages" aria-live="polite">
        {messages.map((message, i) => (
          <article className="rule-editor" key={i}>
            <strong>{t(message.role === "user" ? "Vous" : "Assistant")}</strong>
            <pre>{message.content}</pre>
            {message.context != null && (
              <details>
                <summary>{t("Observations jointes")}</summary>
                <ContextSummary context={message.context} />
              </details>
            )}
          </article>
        ))}
      </div>
      <fieldset disabled={busy}>
        <legend>{t("Questions de diagnostic")}</legend>
        <p>
          {t(
            "Ces suggestions remplissent la question sans envoyer de données.",
          )}
        </p>
        <div className="filters">
          {diagnosticQuestions.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => setPrompt(t(question))}
            >
              {t(question)}
            </button>
          ))}
        </div>
      </fieldset>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label htmlFor="ai-prompt">{t("Votre question")}</label>
        <textarea
          id="ai-prompt"
          required
          maxLength={4000}
          value={prompt}
          disabled={busy}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <div className="filters">
          <button
            disabled={
              busy ||
              previewBusy ||
              !model ||
              !prompt.trim() ||
              (include && !preview)
            }
          >
            {busy ? t("Génération…") : t("Envoyer à Ollama local")}
          </button>
          {busy && (
            <button
              type="button"
              onClick={() => {
                controller.current?.abort();
                void post("ai/cancel", token, csrf).catch(() => {});
              }}
            >
              {t("Annuler")}
            </button>
          )}
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {t(error)}
        </p>
      )}
    </section>
  );
}
