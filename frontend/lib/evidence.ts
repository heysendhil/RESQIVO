// Evidence cited by API answers. Everything here comes from citation metadata
// returned by the backend; nothing is inferred from answer text.

import type { AnswerResponse, Citation } from "@/lib/api";

const PAGE_FRAGMENT = /#page=(\d{1,5})$/;

/** The PDF page a citation points to. The backend appends "#page=N" to the
 * official URL of passages indexed from a PDF; other passages have no page. */
export function citationPage(citation: Pick<Citation, "url">): number | null {
  const match = PAGE_FRAGMENT.exec(citation.url);
  return match ? Number(match[1]) : null;
}

export interface CitedSource {
  sourceId: string;
  title: string;
  publisher: string;
  synthetic: boolean;
  /** Distinct PDF pages cited, ascending; empty when no page was supplied. */
  pages: number[];
  citations: number;
}

/** Distinct sources cited across answers, in order of first appearance. Only
 * answered responses carry citations. */
export function citedSources(answers: (AnswerResponse | null | undefined)[]): CitedSource[] {
  const sources = new Map<string, CitedSource>();
  for (const answer of answers) {
    if (!answer || answer.status !== "answered") continue;
    for (const citation of answer.citations) {
      const entry = sources.get(citation.source_id) ?? {
        sourceId: citation.source_id,
        title: citation.title,
        publisher: citation.publisher,
        synthetic: citation.synthetic,
        pages: [],
        citations: 0,
      };
      entry.citations += 1;
      const page = citationPage(citation);
      if (page !== null && !entry.pages.includes(page)) {
        entry.pages = [...entry.pages, page].sort((a, b) => a - b);
      }
      sources.set(citation.source_id, entry);
    }
  }
  return [...sources.values()];
}
