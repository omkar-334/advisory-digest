// Filter the collected articles down to the ones that apply to one company.
//
// 219 articles is a reading list nobody finishes. Five that apply to you is a product. The
// filtering is a judgement about a business, not a keyword match, so it is a model call --
// but it runs over text already collected, so it costs no scraping.
//
// The profile is not stored. It is used for one request and discarded.

const MAX_ARTICLES = 120;
const MAX_PROFILE = 600;

const SYSTEM = `You decide which advisory articles are relevant to one specific company.

You are given a short profile of a business and a numbered list of articles collected from
accounting and advisory firm newsrooms.

Rules:
- Relevance means the article would plausibly change what this company does, or what it
  needs to know. Not "mentions their industry" -- actually applies to them.
- Be strict. Returning three genuinely relevant articles is far more useful than fifteen
  loosely related ones. If nothing applies, return an empty list and say so in "note".
- "why" must be specific to THIS company, in at most 18 words. Never restate the title.
- Rank most relevant first.
- Never invent an article. Only use the indexes you were given.

Return JSON only: {"matches": [{"index": int, "why": str}], "note": str}`;

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Use POST.' });

  const { profile } = req.body || {};
  if (!profile || String(profile).trim().length < 15) {
    return res.status(400).json({
      error: 'Describe the company in a sentence or two — industry, size, and anything '
           + 'that affects its reporting.',
    });
  }

  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    return res.status(503).json({
      error: 'Relevance filtering is not configured on this deployment.',
      hint: 'Set OPENAI_API_KEY in the project environment to enable it.',
    });
  }

  // Read the published dataset from this same deployment rather than keeping a copy.
  const origin = `https://${req.headers['x-forwarded-host'] || req.headers.host}`;
  let rows;
  try {
    const resp = await fetch(`${origin}/data/latest.json`, {
      signal: AbortSignal.timeout(15000),
    });
    if (!resp.ok) throw new Error(`latest.json returned ${resp.status}`);
    rows = await resp.json();
  } catch (e) {
    return res.status(502).json({ error: `Could not read the dataset: ${String(e).slice(0, 120)}` });
  }
  if (!Array.isArray(rows) || !rows.length) {
    return res.status(503).json({ error: 'No articles have been published yet.' });
  }

  // Newest first, capped: the model does not need the whole archive to answer this, and a
  // shorter list produces stricter judgements.
  const pool = rows
    .filter((r) => r && r.title)
    .sort((a, b) => Date.parse(b.published_date || 0) - Date.parse(a.published_date || 0))
    .slice(0, MAX_ARTICLES);

  const listing = pool
    .map((r, i) => `${i}. [${r._firm || '?'}] ${r.title}: ${(r.summary || '').slice(0, 200)}`)
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
          { role: 'user',
            content: `Company profile:\n${String(profile).slice(0, MAX_PROFILE)}\n\n`
                   + `Articles:\n${listing}` },
        ],
      }),
      signal: AbortSignal.timeout(90000),
    });
    const body = await ai.json();
    if (body.error) throw new Error(body.error.message || 'model error');
    verdict = JSON.parse(body.choices?.[0]?.message?.content ?? '{}');
  } catch (e) {
    return res.status(502).json({ error: `Could not assess relevance: ${String(e).slice(0, 120)}` });
  }

  // The model supplies the indexes, so they are untrusted: drop anything out of range.
  const matches = (Array.isArray(verdict.matches) ? verdict.matches : [])
    .filter((m) => Number.isInteger(m?.index) && m.index >= 0 && m.index < pool.length)
    .slice(0, 12)
    .map((m) => ({
      why: String(m.why || '').slice(0, 160),
      title: pool[m.index].title,
      summary: pool[m.index].summary,
      firm: pool[m.index]._firm,
      url: pool[m.index].article_url,
      date: pool[m.index].published_date,
    }));

  return res.status(200).json({
    considered: pool.length,
    matches,
    note: String(verdict.note || '').slice(0, 300),
  });
}
