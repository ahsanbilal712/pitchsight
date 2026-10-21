// Where the overlay's data comes from: the whyline-api (?api=host:port, default localhost:8000) or, with
// ?fixture=1, files served next to the page. fetchDoc reads one blackboard document by id either way.
import { FIXTURE } from "./record";

export const API = new URLSearchParams(window.location.search).get("api") ?? "localhost:8000";

const cache = new Map<string, Promise<Record<string, unknown> | null>>();

export function fetchDoc(matchId: string, docId: string): Promise<Record<string, unknown> | null> {
  const url = FIXTURE ? `fixtures/docs/${docId}.json` : `http://${API}/match/${matchId}/doc/${docId}`;
  let p = cache.get(url);
  if (!p) {
    p = fetch(url)
      .then((r) => (r.ok ? (r.json() as Promise<Record<string, unknown>>) : null))
      .catch(() => null);
    cache.set(url, p);
  }
  return p;
}
