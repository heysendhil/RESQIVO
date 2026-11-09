import type { AnswerResponse } from "@/lib/api";
import { citedSources } from "@/lib/evidence";

import { Badge } from "./results";

const INDEX_COMMANDS = `cd backend
set -a; source .env; set +a
# Save an approved source as knowledge/local/<SOURCE-ID>.pdf (or .txt), then:
../.venv/bin/python -m app.rag.cli build --corpus approved
../.venv/bin/python -m app.rag.cli sources`;

/** What the frontend can honestly say about the knowledge base. The API has no
 * endpoint that lists indexed documents, so only evidence actually returned in
 * this session is shown. */
export default function KnowledgeBase({ answers }: { answers: (AnswerResponse | null | undefined)[] }) {
  const sources = citedSources(answers);
  const reportedEmpty = answers.some((a) => a?.reason === "knowledge_base_empty");

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section
        aria-labelledby="kb-evidence-heading"
        className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="kb-evidence-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
            Evidence returned this session
          </h3>
          <Badge tone="neutral">Index contents not reported by the API</Badge>
        </div>
        {reportedEmpty && (
          <p role="note" className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-warn-ink">
            The backend reported that the knowledge base is empty. Build the index (see
            right), then ask again.
          </p>
        )}
        {sources.length === 0 ? (
          <p className="rounded-md border border-dashed border-line p-6 text-center text-sm text-muted">
            No evidence has been returned yet in this session. Ask RESQIVO a question,
            or generate a draft plan, to see the cited sources here.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="w-full min-w-[30rem] text-left text-xs">
              <thead className="text-muted">
                <tr className="border-b border-line">
                  <th scope="col" className="px-3 py-2 font-medium">Source</th>
                  <th scope="col" className="px-3 py-2 font-medium">Title · publisher</th>
                  <th scope="col" className="px-3 py-2 font-medium">Pages cited</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Citations</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.sourceId} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2 font-mono text-accent">{source.sourceId}</td>
                    <td className="px-3 py-2">
                      <span className="text-ink">{source.title}</span>
                      <span className="text-muted"> · {source.publisher}</span>
                      {source.synthetic && (
                        <span className="ml-2">
                          <Badge tone="draft">Synthetic source</Badge>
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono">
                      {source.pages.length ? source.pages.join(", ") : "Not supplied"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{source.citations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-muted">
          Page numbers appear only for passages indexed from a PDF. The API does not
          return source file names.
        </p>
      </section>

      <section
        aria-labelledby="kb-index-heading"
        className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4"
      >
        <h3 id="kb-index-heading" className="text-sm font-semibold uppercase tracking-wider text-ink">
          Adding documents
        </h3>
        <p className="text-sm text-muted">
          Documents are indexed by an administrator on the server, not from this
          dashboard. Only sources approved in{" "}
          <span className="font-mono text-ink">knowledge/seed/sources.json</span> with an
          open licence are indexed. Text-based PDFs are supported; scanned PDFs are
          reported because OCR is not available.
        </p>
        <pre className="overflow-x-auto rounded-md border border-line bg-canvas p-3 font-mono text-xs leading-relaxed text-ink">
          {INDEX_COMMANDS}
        </pre>
      </section>
    </div>
  );
}
