"use client";

import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";

function SearchView() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.search(q));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <span className="eyebrow">Retrieve</span>
        <h1>Search the corpus directly.</h1>
        <p>
          Hybrid retrieval — dense vectors fused with lexical search, reranked — with no generation.
          See exactly which passages NowLens would ground an answer in, and how each was found.
        </p>
      </div>

      <form className="ask-bar" onSubmit={run}>
        <div className="grow">
          <input
            className="field"
            placeholder="Search documentation, e.g. assignment rules"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button className="btn" type="submit" disabled={busy || !query.trim()}>
          {busy ? <span className="spinner" /> : "Search"}
        </button>
      </form>

      {error && (
        <div className="alert" style={{ marginTop: 20 }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          <p className="muted mono" style={{ fontSize: 13 }}>
            {result.hits.length} {result.hits.length === 1 ? "result" : "results"}
          </p>
          {result.hits.map((hit) => (
            <article className="card hit" key={hit.chunk_id}>
              <div className="hit-head">
                <span className="hit-title">
                  {hit.source_url ? (
                    <a href={hit.source_url} target="_blank" rel="noopener noreferrer">
                      {hit.title}
                    </a>
                  ) : (
                    hit.title
                  )}
                </span>
                <span className="score">{hit.score.toFixed(3)}</span>
              </div>
              <p className="hit-snippet">{hit.snippet}</p>
              <div className="chips">
                <span className="chip">{hit.retriever}</span>
                {hit.domains.map((d) => (
                  <span key={d} className="chip">
                    {d}
                  </span>
                ))}
              </div>
            </article>
          ))}
          {result.hits.length === 0 && (
            <p className="muted">No matching passages. Try different terms, or ingest more docs.</p>
          )}
        </div>
      )}
    </>
  );
}

export default function SearchPage() {
  return (
    <AppShell>
      <SearchView />
    </AppShell>
  );
}
