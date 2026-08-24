// Answer a question about what the firms have published, with citations.
//
// No vector database. The whole corpus -- 213 articles of title plus a short summary -- is
// roughly 15k tokens, which fits in context with room to spare. Retrieval would add an
// embedding step, a store to keep in sync, and a failure mode that does not currently
// exist: the retriever misses the relevant article and the model answers confidently from
// the wrong ones. Passing everything is simpler and strictly more accurate at this size.
// Revisit somewhere north of 5,000 articles.

const MAX_QUESTION = 300;

const SYSTEM = `You answer questions about what accounting and advisory firms have recently
published, using only the numbered articles supplied.

Your reader is a finance professional. They want an answer, not a reading list.

Rules:
- Use ONLY the supplied articles. If they do not answer the question, say so plainly and
  say what the firms ARE discussing nearby. Never answer from your own knowledge.
- Cite by article index. Every factual claim carries at least one citation.
- When firms differ, say so and name them. When they agree, say that too — agreement between
  independent firms is the most useful thing this corpus contains.
- Lead with the answer. No preamble, no restating the question.
- At most 120 words.
- "confidence" is low when fewer than two articles bear on the question.

Return JSON only: {"answer": str, "citations": [int], "firms": [str],
"confidence": "high"|"medium"|"low", "followups": [str]}`;

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Use POST.' });

  const question = String(req.body?.question || '').trim();
  if (question.length < 5) {
    return res.status(400).json({ error: 'Ask a question about what the firms are publishing.' });
  }

  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    return res.status(503).json({
      error: 'Answering is not configured on this deployment.',
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

  const pool = rows.filter((r) => r && r.title);
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
          { role: 'user', content: `Question: ${question.slice(0, MAX_QUESTION)}\n\nArticles:\n${listing}` },
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
    // Never fall back to an empty answer: "nothing found" and "the model failed" look
    // identical to a reader and only one of them is true.
    return res.status(502).json({ error: `Could not answer that: ${String(e).slice(0, 140)}` });
  }

  // Citation indexes come from the model, so they are untrusted.
  const cited = (Array.isArray(verdict.citations) ? verdict.citations : [])
    .filter((i) => Number.isInteger(i) && i >= 0 && i < pool.length)
    .slice(0, 8)
    .map((i) => ({
      title: pool[i].title,
      firm: pool[i]._firm,
      url: pool[i].article_url,
      date: pool[i].published_date,
    }));

  return res.status(200).json({
    question,
    answer: verdict.answer.slice(0, 1200),
    confidence: ['high', 'medium', 'low'].includes(verdict.confidence) ? verdict.confidence : 'medium',
    citations: cited,
    followups: (Array.isArray(verdict.followups) ? verdict.followups : [])
      .filter((f) => typeof f === 'string').slice(0, 3).map((f) => f.slice(0, 120)),
    searched: pool.length,
  });
}
