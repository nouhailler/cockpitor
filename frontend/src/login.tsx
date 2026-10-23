import React, { useState } from "react";
import { t, LanguagePicker, useLanguage } from "./i18n";
import { login } from "./api";

export function LoginView({
  onLogin,
  notice,
}: {
  onLogin: (token: string, csrf: string) => void;
  notice: string;
}) {
  useLanguage();
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <div className="brand">◈ LocalCockpit</div>
      <LanguagePicker />
      <h1>{t("Votre machine, en clair.")}</h1>
      <p>{t("Supervision locale · lecture seule · aucune télémétrie")}</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const data = await login(input);
            if (!data.token || !data.csrf_token)
              throw new Error(t("Demande de connexion invalide"));
            onLogin(data.token, data.csrf_token);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setInput("");
            setBusy(false);
          }
        }}
      >
        <label htmlFor="token">{t("Jeton affiché par le lanceur local")}</label>
        <input
          id="token"
          type="password"
          autoComplete="off"
          required
          maxLength={256}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button disabled={busy}>{t("Ouvrir le cockpit →")}</button>
      </form>
      {(error || notice) && (
        <p className="error" role="alert">
          {t(error || notice)}
        </p>
      )}
      <small>
        {t(
          "Session en mémoire : 15 minutes sans activité, 8 heures maximum. Le jeton de lancement ne sert qu’à la connexion.",
        )}
      </small>
    </main>
  );
}
