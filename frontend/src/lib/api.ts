const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function scoreTone(score: number) {
  if (score >= 90) return { ring: "text-emerald-500", chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900" };
  if (score >= 80) return { ring: "text-emerald-500", chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900" };
  if (score >= 70) return { ring: "text-amber-500", chip: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900" };
  if (score >= 60) return { ring: "text-orange-500", chip: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-300 dark:border-orange-900" };
  return { ring: "text-ink-400", chip: "bg-ink-100 text-ink-600 border-ink-200 dark:bg-ink-900 dark:text-ink-300 dark:border-ink-800" };
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "sin fecha";
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return "hace minutos";
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "ayer";
  if (days < 30) return `hace ${days} días`;
  const months = Math.floor(days / 30);
  return `hace ${months} ${months === 1 ? "mes" : "meses"}`;
}

export const MODALITY: Record<string, string> = {
  remote: "Remoto",
  hybrid: "Híbrido",
  onsite: "Presencial",
  unknown: "Sin especificar",
};
