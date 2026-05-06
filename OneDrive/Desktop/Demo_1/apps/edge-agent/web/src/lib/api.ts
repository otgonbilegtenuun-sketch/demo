import type { Role } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8080";

type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function roleHome(role?: Role): string {
  if (role === "parent") return "/parent";
  if (role === "admin") return "/dashboard";
  return "/teacher";
}

export function authHeaders(token?: string | null): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function api<T>(
  method: HttpMethod,
  path: string,
  token?: string | null,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token)
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store"
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const payload = (await res.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Keep the HTTP status text.
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function mediaUrl(path: string, token?: string | null): string {
  const sep = path.includes("?") ? "&" : "?";
  const auth = token ? `${sep}token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}${path}${auth}`;
}

export function wsUrl(token?: string | null): string {
  const base = new URL(API_BASE);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = "/ws/events";
  base.search = token ? `token=${encodeURIComponent(token)}` : "";
  return base.toString();
}

export function formatTime(value?: string | null): string {
  if (!value) return "-";
  const iso = value.includes("T") ? value : value.replace(" ", "T");
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`;
  const date = new Date(zoned);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
