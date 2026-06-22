"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DocumentOut, JobOut } from "@/lib/types";

function AdminView() {
  const { user } = useAuth();
  const canOperate = user ? ["operator", "admin"].includes(user.role) : false;

  const [urls, setUrls] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [docs, setDocs] = useState<DocumentOut[]>([]);

  const load = useCallback(async () => {
    if (!canOperate) return;
    try {
      const [j, d] = await Promise.all([api.jobs(), api.documents()]);
      setJobs(j);
      setDocs(d);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load admin data.");
    }
  }, [canOperate]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const list = urls
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
    if (list.length === 0 || submitting) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await api.ingest(list, false);
      setNotice(`Queued ${list.length} URL${list.length === 1 ? "" : "s"} for ingestion.`);
      setUrls("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ingestion request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!canOperate) {
    return (
      <>
        <div className="page-head">
          <span className="eyebrow">Admin</span>
          <h1>Operator access required.</h1>
          <p>
            Ingestion and document management need the operator or admin role. Ask an administrator
            to promote your account.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <span className="eyebrow">Admin</span>
        <h1>Feed the knowledge base.</h1>
        <p>
          Submit documentation URLs to ingest. Each runs through crawl → extract → clean → chunk →
          embed → index, and appears below as a job you can track.
        </p>
      </div>

      <form className="card" style={{ padding: 20 }} onSubmit={submit}>
        <label className="lbl" htmlFor="urls">
          URLs to ingest (one per line)
        </label>
        <textarea
          id="urls"
          className="field"
          placeholder={"https://www.servicenow.com/docs/\nhttps://developer.servicenow.com/..."}
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
        />
        <div className="row" style={{ marginTop: 14, justifyContent: "space-between" }}>
          <span className="muted" style={{ fontSize: 13 }}>
            Work runs in the background; refresh to see status update.
          </span>
          <div className="row">
            <button type="button" className="btn-ghost" onClick={() => void load()}>
              Refresh
            </button>
            <button className="btn" type="submit" disabled={submitting || !urls.trim()}>
              {submitting ? <span className="spinner" /> : "Ingest"}
            </button>
          </div>
        </div>
        {notice && (
          <div style={{ marginTop: 12, color: "var(--grounded)", fontSize: 14 }}>{notice}</div>
        )}
        {error && (
          <div className="alert" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}
      </form>

      <section className="stack" style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 18 }}>Ingestion jobs</h2>
        <div className="card" style={{ padding: 4, overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>URL</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td className="url">{job.url}</td>
                  <td>
                    <span className="status" data-s={job.status}>
                      {job.status}
                    </span>
                  </td>
                  <td className="mono">{job.chunks_indexed}</td>
                  <td className="mono">{new Date(job.updated_at).toLocaleString()}</td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">
                    No jobs yet. Submit a URL above to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="stack" style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 18 }}>Indexed documents</h2>
        <div className="card" style={{ padding: 4, overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>URL</th>
                <th>Chunks</th>
                <th>Domains</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.title || "—"}</td>
                  <td className="url">{doc.url}</td>
                  <td className="mono">{doc.chunk_count}</td>
                  <td className="mono">{doc.domains.join(", ") || "—"}</td>
                </tr>
              ))}
              {docs.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">
                    Nothing indexed yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export default function AdminPage() {
  return (
    <AppShell>
      <AdminView />
    </AppShell>
  );
}
