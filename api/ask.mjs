// One natural-language entry point to the corpus.
//
// This started as two endpoints -- "ask a question" and "filter to my company" -- which was
// a distinction the machine cared about and the reader did not. Both are the same act: put
// words in, get the relevant subset of what the firms published back. So there is one input,
// and the model decides which of the two the text is before answering.
//
// No vector database. The whole corpus -- title plus a short summary for ~213 articles -- is
// roughly 15k tokens and fits in context. Retrieval would add an embedding step, a store to
// keep in sync, and a failure mode that does not exist today: the retriever misses the right
// article and the model answers confidently from the wrong ones. Revisit past ~5,000 articles.

const MAX_INPUT = 600;
const MAX_POOL = 140;

const SYSTEM = `You serve one natural-language input against a corpus of articles published by
accounting and advisory firms. Your reader is a finance professional.

FIRST decide what the input is:

- "question" — they are asking about something the firms have written about.
- "profile" — they are describing a company or situation, and want to know what applies to it.

If it is a QUESTION, answer it:
- Use ONLY the supplied articles. If they do not answer it, say so plainly and say what the
  firms ARE discussing nearby. Never answer from your own knowledge.
- When firms differ, say so and name them. When they agree, say that — agreement between
  independent firms is the most useful thing this corpus contains.
- Lead with the answer. No preamble. At most 120 words.
- Put supporting article indexes in "citations".

If it is a PROFILE, select what applies:
- Relevance means the article would change what this company does, or what it needs to know.
  Not "mentions their industry" — actually applies to them.
- Be strict. Three genuinely relevant articles beat fifteen loosely related ones. If nothing
  applies, return an empty list and say so in "answer".
- Put chosen article indexes in "citations", most relevant first, and give each a "why" in
  "reasons" (same order, at most 18 words each, specific to this company).

Always:
- Never invent an article. Only use indexes you were given.
- "confidence" is low when fewer than two articles bear on the input.

Return JSON only: {"mode": "question"|"profile", "answer": str, "citations": [int],
"reasons": [str], "confidence": "high"|"medium"|"low", "followups": [str]}`;

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Use POST.' });

  // `question` and `profile` are accepted so the older endpoints' callers keep working.
  const input = String(req.body?.input ?? req.body?.question ?? req.body?.profile ?? '').trim();
  if (input.length < 5) {
    return res.status(400).json({
      error: 'Ask a question, or describe the business you want this filtered to.',
    });
  }

  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    return res.status(503).json({
      error: 'This is not configured on this deployment.',
      hint: 'Set OPENAI_API_KEY in the project environment to enable it.',
    });
  }

  const origin = `https://${req.headers['x-forwarded-host'] || req.headers.host}`;
  let rows;
  try {
    const resp = await fetch(`${origin}/data/latest.json`, { signal: AbortSignal.timeout(15000) });
    if (!resp.ok) throw new Error(`latest.json returned ${resp.status}`);
    rows = await resp.json();
  } catch (e) {
    return res.status(502).json({ error: `Could not read the dataset: ${String(e).slice(0, 120)}` });
  }
  if (!Array.isArray(rows) || !rows.length) {
    return res.status(503).json({ error: 'No articles have been published yet.' });
  }

  // Newest first and capped: a shorter list produces stricter judgements, and the newest
  // articles are the ones a reader is asking about.
  const pool = rows
    .filter((r) => r && r.title)
    .sort((a, b) => Date.parse(b.published_date || 0) - Date.parse(a.published_date || 0))
    .slice(0, MAX_POOL);

  const listing = pool
    .map((r, i) => `${i}. [${r._firm || '?'}] ${r.title}: ${(r.summary || '').slice(0, 190)}`)
    .join('\n');

  let verdict;
  try {
    const ai = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
        temperature: 0,
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: SYSTEM },
          { role: 'user', content: `Input: ${input.slice(0, MAX_INPUT)}\n\nArticles:\n${listing}` },
        ],
      }),
      signal: AbortSignal.timeout(90000),
    });
    const body = await ai.json();
    if (body.error) throw new Error(body.error.message || 'model error');
    const content = body.choices?.[0]?.message?.content;
    if (typeof content !== 'string') throw new Error('model returned no content');
    verdict = JSON.parse(content);
    if (!verdict || typeof verdict.answer !== 'string') throw new Error('model returned no answer');
  } catch (e) {
    // Never degrade to an empty result: "nothing found" and "the model failed" look
    // identical to a reader, and only one of them is true.
    return res.status(502).json({ error: `Could not answer that: ${String(e).slice(0, 140)}` });
  }

  // Indexes come from the model, so they are untrusted.
  const reasons = Array.isArray(verdict.reasons) ? verdict.reasons : [];
  const citations = (Array.isArray(verdict.citations) ? verdict.citations : [])
    .filter((i) => Number.isInteger(i) && i >= 0 && i < pool.length)
    .slice(0, 10)
    .map((i, n) => ({
      title: pool[i].title,
      summary: pool[i].summary,
      firm: pool[i]._firm,
      url: pool[i].article_url,
      date: pool[i].published_date,
      why: String(reasons[n] || '').slice(0, 160),
    }));

  return res.status(200).json({
    input,
    mode: verdict.mode === 'profile' ? 'profile' : 'question',
    answer: verdict.answer.slice(0, 1200),
    confidence: ['high', 'medium', 'low'].includes(verdict.confidence) ? verdict.confidence : 'medium',
    citations,
    followups: (Array.isArray(verdict.followups) ? verdict.followups : [])
      .filter((f) => typeof f === 'string').slice(0, 3).map((f) => f.slice(0, 120)),
    searched: pool.length,
  });
}
