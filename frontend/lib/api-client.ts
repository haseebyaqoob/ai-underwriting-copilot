
const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/* ------------------------------ case transform ------------------------------ */

function snakeToCamelKey(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
}

function camelToSnakeKey(key: string): string {
  return key.replace(/[A-Z]/g, (c) => "_" + c.toLowerCase());
}

function deepTransformKeys(value: unknown, mapKey: (k: string) => string): unknown {
  if (Array.isArray(value)) return value.map((v) => deepTransformKeys(v, mapKey));
  if (value !== null && typeof value === "object" && !(value instanceof Date)) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[mapKey(k)] = deepTransformKeys(v, mapKey);
    }
    return out;
  }
  return value;
}

export const toCamel = (v: unknown) => deepTransformKeys(v, snakeToCamelKey);
export const toSnake = (v: unknown) => deepTransformKeys(v, camelToSnakeKey);

/* --------------------------------- refresh --------------------------------- */

async function tryRefresh(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}${API_PREFIX}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        setAccessToken(null);
        return false;
      }
      const body = await res.json();
      setAccessToken(body.access_token);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Attempts a silent session restore on app boot (page reload loses the
 * in-memory token, but the httpOnly refresh cookie may still be valid). */
export async function bootstrapSession(): Promise<boolean> {
  return tryRefresh();
}

/* ---------------------------------- core fetch ------------------------------ */

interface RequestOpts {
  method?: string;
  body?: unknown;
  isForm?: boolean;
  /** Skip the Authorization header entirely (auth endpoints before login). */
  anonymous?: boolean;
}

async function rawRequest(path: string, opts: RequestOpts): Promise<Response> {
  const headers: Record<string, string> = {};
  if (!opts.isForm && opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (!opts.anonymous && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  return fetch(`${API_BASE}${API_PREFIX}${path}`, {
    method: opts.method ?? "GET",
    credentials: "include",
    headers,
    body: opts.isForm ? (opts.body as FormData) : opts.body !== undefined ? JSON.stringify(toSnake(opts.body)) : undefined,
  });
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      // FastAPI/Pydantic 422 validation error shape. `loc` is
      // ["body", "years_operating"] etc -- dropping it (as the previous
      // version of this function did) leaves a message like "Input
      // should be greater than or equal to 0" with zero indication of
      // WHICH field, which is unusable when a form has 15+ fields.
      // Skip the leading "body"/"query" location segment; keep the rest
      // (handles nested paths too, e.g. ["body", "items", 0, "amount"]).
      return data.detail
        .map((d: any) => {
          const loc = Array.isArray(d.loc) ? d.loc.slice(1).join(".") : null;
          return loc ? `${loc}: ${d.msg}` : d.msg;
        })
        .join("; ");
    }
    return res.statusText;
  } catch {
    return res.statusText || `Request failed (${res.status})`;
  }
}

export async function apiRequest<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  let res = await rawRequest(path, opts);

  if (res.status === 401 && !opts.anonymous) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await rawRequest(path, opts);
    }
  }

  if (!res.ok) {
    throw new ApiError(await parseErrorMessage(res), res.status);
  }
  if (res.status === 204) return undefined as T;

  const data = await res.json();
  return toCamel(data) as T;
}

export const api = {
  get: <T>(path: string) => apiRequest<T>(path),
  post: <T>(path: string, body?: unknown, opts?: Partial<RequestOpts>) =>
    apiRequest<T>(path, { method: "POST", body, ...opts }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  postForm: <T>(path: string, form: FormData) => apiRequest<T>(path, { method: "POST", body: form, isForm: true }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
  /** For endpoints that return raw file bytes (e.g. the Evidence Checklist's
   * document preview) rather than JSON -- `apiRequest` assumes a JSON body,
   * so this is a small parallel path that still carries the in-memory
   * Authorization header (a plain `<img src>`/`<a href>` can't, since the
   * token is deliberately never in a cookie -- see this file's header
   * comment) and still gets the one-shot 401-refresh-and-retry. */
  getBlob: async (path: string): Promise<Blob> => {
    let res = await rawRequest(path, {});
    if (res.status === 401) {
      const refreshed = await tryRefresh();
      if (refreshed) res = await rawRequest(path, {});
    }
    if (!res.ok) throw new ApiError(await parseErrorMessage(res), res.status);
    return res.blob();
  },
};

export { API_BASE, API_PREFIX };
