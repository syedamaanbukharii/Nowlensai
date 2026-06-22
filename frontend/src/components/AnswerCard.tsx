import type { ChatResponse } from "@/lib/types";

function intentLabel(intent: string): string {
  return intent
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function AnswerCard({ answer }: { answer: ChatResponse }) {
  const grounded = answer.grounded;
  const verdict = answer.qa?.verdict;

  return (
    <article className="card answer" data-grounded={grounded}>
      <div className="answer-meta">
        {answer.intent && <span className="tag tag-intent">{intentLabel(answer.intent)}</span>}
        <span className={`tag ${grounded ? "tag-grounded" : "tag-ungrounded"}`}>
          {grounded ? "Grounded" : "Not grounded"}
        </span>
        {verdict && <span className="tag">QA: {verdict}</span>}
        {answer.domains.map((d) => (
          <span key={d} className="tag">
            {d}
          </span>
        ))}
      </div>

      <div className="answer-body">{answer.answer}</div>

      {answer.citations.length > 0 && (
        <div className="sources">
          <h3>Sources</h3>
          {answer.citations.map((c) => (
            <div className="source" key={`${c.index}-${c.chunk_id}`}>
              <span className="idx">{c.index}</span>
              <div>
                <div className="title">
                  {c.source_url ? (
                    <a href={c.source_url} target="_blank" rel="noopener noreferrer">
                      {c.title || c.source_url}
                    </a>
                  ) : (
                    c.title || "Untitled source"
                  )}
                </div>
                {c.snippet && <div className="snippet">{c.snippet}</div>}
                {c.source_url && <div className="url">{c.source_url}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
