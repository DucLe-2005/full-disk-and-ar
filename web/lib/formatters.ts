function parseDate(value: string) {
  const normalizedValue = value.replace(" ", "T");
  const hasTimeZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalizedValue);
  const date = new Date(hasTimeZone ? normalizedValue : `${normalizedValue}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function formatDateTime(value: string) {
  const date = parseDate(value);
  if (!date) return value;
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(
    date.getUTCHours()
  )}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`;
}

export function formatTime(value: string) {
  const date = parseDate(value);
  if (!date) return value;
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`;
}

export function formatRequestedAtForMessage(value?: string | null) {
  return value ? formatDateTime(`${value.replace(" ", "T")}Z`) : "current hour";
}

export function percent(value: number) {
  return `${Math.round(value * 1000) / 10}%`;
}

export function predictionTone(predictedClass: string) {
  return predictedClass.toLowerCase().includes("non") ? "calm" : "alert";
}
