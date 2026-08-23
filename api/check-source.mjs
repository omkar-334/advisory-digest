// Eligibility check for a proposed source, mirroring scripts/onboard.py's gate.
//
// Creating a collector takes several minutes, so it cannot be a web request. Deciding
// whether a source is ELIGIBLE takes a couple of seconds, so that is what this does:
// the browser gets a verdict and the command to run, and no credits are spent on a
// target that was never going to qualify.
//
// The three refusals are enforced here as well as in the Python gate. Duplicated on
// purpose: this endpoint is public, and a rule that only exists in the CLI is not a rule.

const GOV_SUFFIXES = ['.gov', '.gov.in', '.gov.uk', '.gov.au', '.mil', '.nic.in', '.gouv.fr'];
// Below this much visible text there is nothing for the classifier to judge, so it guesses.
// scripts/onboard.py refuses on the same threshold.
const MIN_PAGE_TEXT = 200;
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/120.0 Safari/537.36';

function visibleText(html, limit = 6000) {
  return html
    .replace(/<(script|style|noscript|svg|head)[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    // Numeric entities as well as named ones: a listing full of &#8217; would otherwise
    // reach the classifier as noise.
    .replace(/&(#\d+|#x[0-9a-f]+|[a-z]+);/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit);
}

function hostOf(url) {
  try { return new URL(url).hostname.toLowerCase(); } catch { return ''; }
}

function gate(url, v) {
  const host = hostOf(url);
  const blocked = [];
  if (v.is_government || GOV_SUFFIXES.some((s) => host.endsWith(s))) {
    blocked.push({
      rule: 'Government sites',
      why: 'Barred by hackathon rule 7, and Scraper Studio rejects these domains outright.',
    });
  }
  if (v.requires_login) {
    blocked.push({
      rule: 'Login-walled content',
      why: 'Barred by rule 6. Nothing here attempts to authenticate or reuse a session.',
    });
  }
  if (v.has_paywall) {
    blocked.push({ rule: 'Paywalled content', why: 'Barred by rule 6.' });
  }
  if (v.personal_data_risk === 'high') {
    blocked.push({
      rule: 'Pages about private individuals',
      why: 'Out of scope regardless of the rules.',
    });
  }
  if (!v.is_listing_page) {
    blocked.push({
      rule: 'Not an article listing',
      why: `Looks like ${v.content_type || 'something else'}. A single article or a homepage is not a source.`,
    });
  }
  return blocked;
}

const SYSTEM = `You screen candidate web sources for a scraping pipeline that collects
professional and industry articles. You are shown the visible text of one page.

Judge only what the page evidences. Be strict: a wrong "eligible" wastes money generating a
scraper that cannot work.

Definitions:
- listing page: shows MANY distinct articles/posts, each with its own headline and link.
  A single article, a homepage, a product page or a contact page is NOT a listing page.
- login wall: the content requires signing in or creating an account.
- paywall: the content requires payment or subscription.
- personal data: pages whose primary content is about identifiable private individuals.
  Author bylines alone do not count, since those are excluded at extraction time.

Return JSON only: {"is_listing_page": bool, "publisher": str, "content_type": str,
"requires_login": bool, "has_paywall": bool, "is_government": bool,
"personal_data_risk": "none"|"low"|"high", "article_count_estimate": int,
"suggested_description": str, "confidence": number, "reason": str}`;

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Use POST.' });
  }

  const { url } = req.body || {};
  if (!url || !/^https?:\/\//i.test(url)) {
    return res.status(400).json({ error: 'Enter a full URL, starting with https://' });
  }

  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    return res.status(503).json({
      error: 'Source checking is not configured on this deployment.',
      hint: 'Set OPENAI_API_KEY in the project environment to enable it.',
    });
  }

  // A block is information, not a verdict: several legitimate sources refuse plain
  // requests and work correctly through Bright Data's unblocking layer.
  let status = 0;
  let html = '';
  let note = '';
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': UA },
      signal: AbortSignal.timeout(20000),
    });
    status = resp.status;
    html = await resp.text();
    if ([401, 403, 429].includes(status)) {
      note = `This site returns HTTP ${status} to a plain request. That is not disqualifying: ` +
             `Bright Data's unblocking layer usually handles it.`;
    } else if (status >= 400) {
      note = `This site returns HTTP ${status} to a plain request.`;
    }
  } catch (e) {
    return res.status(502).json({ error: `Could not reach that URL: ${String(e).slice(0, 140)}` });
  }

  const text = visibleText(html);
  if (text.length < MIN_PAGE_TEXT) {
    return res.status(422).json({ error: 'That page returned almost no readable text to assess.' });
  }

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
          {
            role: 'user',
            content: `URL: ${url}\nHTTP status to a plain request: ${status}\n\n` +
              `Visible page text (truncated):\n${text}\n\n` +
              `For suggested_description, write one instruction (max 400 chars) telling an AI ` +
              `scraper builder exactly what to extract from each article card on this page. ` +
              `Always require title, summary, published_date as ISO 8601, an absolute ` +
              `article_url, and tags. Always forbid author names and personal data.`,
          },
        ],
      }),
      signal: AbortSignal.timeout(60000),
    });
    const body = await ai.json();
    if (body?.error) throw new Error(body.error.message || 'classifier error');
    const content = body?.choices?.[0]?.message?.content;
    if (typeof content !== 'string') throw new Error('classifier returned no reply');
    verdict = JSON.parse(content);
    // JSON mode guarantees valid JSON, not an object: a bare array or number here would
    // read every gate field as undefined and wave the source through.
    if (!verdict || typeof verdict !== 'object' || Array.isArray(verdict)) {
      throw new Error('classifier reply was not an object');
    }
  } catch (e) {
    return res.status(502).json({ error: `Could not assess that page: ${String(e).slice(0, 140)}` });
  }

  const blocked = gate(url, verdict);
  const eligible = blocked.length === 0;
  const description = String(verdict.suggested_description || '').slice(0, 500);

  return res.status(200).json({
    url,
    http_status: status,
    note,
    eligible,
    blocked,
    publisher: verdict.publisher || null,
    content_type: verdict.content_type || null,
    article_count_estimate: verdict.article_count_estimate ?? null,
    confidence: verdict.confidence ?? null,
    reason: verdict.reason || '',
    description,
    command: eligible ? `./scripts/onboard.py ${url}` : null,
  });
}
