"use client";

import { useState } from "react";

import { AnswerCard } from "@/components/AnswerCard";
import { AppShell } from "@/components/AppShell";
import { ApiError, api } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

const EXAMPLES = [
  "How should I model major incidents in ITSM?",
  "When should I use CSM instead of ITSM?",
  "What's the right way to publish a scoped app to the Store?",
];

function AskView() {
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.chat(q, { sessionId });
      setAnswer(res);
      setSessionId(res.session_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <span className="eyebrow">Ask the platform</span>
        <h1>Grounded answers, with their sources in view.</h1>
        <p>
          Ask a ServiceNow question. NowLens retrieves from the indexed documentation, routes to a
          specialist, and shows whether the answer is grounded — alongside the passages it cited.
        </p>
      </div>

      <form
        className="ask-bar"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(message);
        }}
      >
        <div className="grow">
          <textarea
            className="field"
            placeholder="e.g. How do I route P1 incidents to an on-call engineer?"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                void ask(message);
              }
            }}
          />
        </div>
        <button className="btn" type="submit" disabled={busy || !message.trim()}>
          {busy ? <span className="spinner" /> : "Ask"}
        </button>
      </form>

      {!answer && !busy && (
        <div className="row" style={{ marginTop: 16 }}>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              className="chip"
              style={{ cursor: "pointer" }}
              onClick={() => {
                setMessage(ex);
                void ask(ex);
              }}
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="alert" style={{ marginTop: 20 }}>
          {error}
        </div>
      )}

      {answer && <AnswerCard answer={answer} />}
    </>
  );
}

export default function ChatPage() {
  return (
    <AppShell>
      <AskView />
    </AppShell>
  );
}
