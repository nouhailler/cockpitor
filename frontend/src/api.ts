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
