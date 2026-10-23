import { t, formatNumber } from "./i18n";
export const bytes = (n: number | null | undefined) =>
  n == null
    ? t("Indisponible")
    : n >= 1073741824
      ? `${formatNumber(n / 1073741824)} ${t("Gio")}`
      : n >= 1048576
        ? `${formatNumber(n / 1048576)} ${t("Mio")}`
        : `${formatNumber(n / 1024)} ${t("Kio")}`;
