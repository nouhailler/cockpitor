export async function api<T>(
  path: string,
  token: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(8000)])
      : AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error?.message || `Erreur HTTP ${response.status}`);
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
      "Content-Type": "application/json",
      "X-LocalCockpit-CSRF": csrf,
    },
    body: JSON.stringify(settings),
    signal: AbortSignal.timeout(8000),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error?.message || `Erreur HTTP ${response.status}`);
  return data as T;
}
