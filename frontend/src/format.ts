export const bytes = (n: number | null | undefined) =>
  n == null
    ? "Indisponible"
    : n >= 1073741824
      ? `${(n / 1073741824).toFixed(1)} Gio`
      : n >= 1048576
        ? `${(n / 1048576).toFixed(1)} Mio`
        : `${(n / 1024).toFixed(1)} Kio`;
