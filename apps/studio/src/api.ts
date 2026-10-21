// The whyline-api base (?api=host:port, default localhost:8000) and a cached read-only document fetch.
const params = new URLSearchParams(window.location.search);
export const API = params.get("api") ?? "localhost:8000";
export const RECORD = params.get("record") === "1";

export function http(path: string): string {
  return `http://${API}${path}`;
}

const docs = new Map<string, Promise<Record<string, unknown> | null>>();

/** GET /match/{id}/doc/{doc_id}; null when the id does not resolve. Cached per page. */
export function fetchDoc(matchId: string, docId: string): Promise<Record<string, unknown> | null> {
  const key = `${matchId}/${docId}`;
  let p = docs.get(key);
  if (!p) {
    p = fetch(http(`/match/${matchId}/doc/${docId}`))
      .then((r) => (r.ok ? (r.json() as Promise<Record<string, unknown>>) : null))
      .catch(() => null);
    docs.set(key, p);
    void p.then((doc) => doc === null && docs.delete(key)); // a missing doc may exist later
  }
  return p;
}

export async function post(path: string, body: unknown): Promise<Response> {
  return fetch(http(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function clockText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
