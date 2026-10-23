import { getLanguage, t } from "./i18n";
export async function api<T>(
  path: string,
  token: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Accept-Language": getLanguage(),
    },
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(8000)])
      : AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token)
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(
      t(data.error?.message || "") || `Erreur HTTP ${response.status}`,
    );
  }
  return data as T;
}

export async function saveSettings<T>(
  settings: unknown,
  token: string,
  csrf: string,
): Promise<T> {
  const response = await fetch("/api/v1/settings", {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Accept-Language": getLanguage(),
      "Content-Type": "application/json",
      "X-LocalCockpit-CSRF": csrf,
    },
    body: JSON.stringify(settings),
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token)
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(
      t(data.error?.message || "") || `Erreur HTTP ${response.status}`,
    );
  }
  return data as T;
}

export async function post<T>(
  path: string,
  token: string,
  csrf: string,
  body: unknown = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Accept-Language": getLanguage(),
      "Content-Type": "application/json",
      "X-LocalCockpit-CSRF": csrf,
    },
    body: JSON.stringify(body),
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(80000)])
      : AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token)
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(
      t(data.error?.message || "Erreur HTTP {0}", { 0: response.status }),
    );
  }
  return data as T;
}

export async function login(bootstrap: string) {
  const options = await api<{ csrf_token: string }>("auth/options", "");
  return post<{ token: string; csrf_token: string }>(
    "auth/sessions",
    "",
    options.csrf_token,
    { token: bootstrap },
  );
}
