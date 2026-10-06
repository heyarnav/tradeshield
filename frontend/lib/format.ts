export const money = (value: unknown, digits = 2): string =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value ?? 0));

export const signedMoney = (value: unknown): string => {
  const amount = Number(value ?? 0);
  const sign = amount > 0 ? "+" : amount < 0 ? "?" : "";
  return `${sign}${money(Math.abs(amount))}`;
};

export const qty = (value: unknown): string =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(Number(value ?? 0));

export const pct = (value: unknown, digits = 2): string =>
  `${Number(value ?? 0).toFixed(digits)}%`;

export const dateTime = (value: unknown): string => {
  if (!value) return "--";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
};

export const dateOnly = (value: unknown): string => {
  if (!value) return "--";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
};

export const relative = (value: unknown): string => {
  if (!value) return "--";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  const absolute = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (absolute < 60) return formatter.format(-seconds, "second");
  if (absolute < 3600) return formatter.format(-Math.round(seconds / 60), "minute");
  if (absolute < 86400) return formatter.format(-Math.round(seconds / 3600), "hour");
  if (absolute < 604800) return formatter.format(-Math.round(seconds / 86400), "day");
  if (absolute < 2629800) return formatter.format(-Math.round(seconds / 604800), "week");
  return formatter.format(-Math.round(seconds / 2629800), "month");
};
