const defaultBase = "http://localhost:8000";

export function apiUrl(path: string): string {
  const base = (process.env.NEXT_PUBLIC_API_URL || defaultBase).replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

function headers(init?: HeadersInit): HeadersInit {
  const h = new Headers(init);
  h.set("Content-Type", "application/json");
  const key = process.env.NEXT_PUBLIC_API_KEY;
  if (key) h.set("X-API-Key", key);
  return h;
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(apiUrl(path), {
    headers: headers(),
    cache: "no-store",
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(apiUrl(path), {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json() as Promise<T>;
}
