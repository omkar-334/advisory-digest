// Queue a proposed source to actually be added to the fleet.
//
// Building a collector takes four to twenty minutes, which no serverless function can wait
// for. So the browser does not build it: it dispatches a GitHub Actions run that does, on a
// runner that has the Bright Data CLI, the credentials and the time. The page gets a link to
// watch, and the workflow commits the new collector to the registry when it finishes.
//
// The eligibility gate is re-run here rather than trusted from the client. The check-source
// response is not a capability token: anyone can POST to this endpoint directly.

const GOV_SUFFIXES = ['.gov', '.gov.in', '.gov.uk', '.gov.au', '.mil', '.nic.in', '.gouv.fr'];
const REPO = process.env.GITHUB_REPO || 'omkar-334/advisory-digest';

function hostOf(url) {
  try { return new URL(url).hostname.toLowerCase(); } catch { return ''; }
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Use POST.' });

  const { url, description } = req.body || {};
  if (!url || !/^https?:\/\//i.test(url)) {
    return res.status(400).json({ error: 'Enter a full URL, starting with https://' });
  }
  if (!description || description.length < 20) {
    return res.status(400).json({ error: 'Run the eligibility check first.' });
  }

  // Cheap, non-negotiable check that does not depend on the client or on a model.
  const host = hostOf(url);
  if (GOV_SUFFIXES.some((s) => host.endsWith(s))) {
    return res.status(403).json({
      error: 'Government sites cannot be added.',
      rule: 'Barred by the hackathon rules, and Scraper Studio rejects these domains.',
    });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return res.status(503).json({
      error: 'Queuing is not configured on this deployment.',
      hint: 'Set GITHUB_TOKEN (a fine-grained token with Contents: read/write and Actions: '
          + 'read/write on this repository) in the Vercel project environment.',
      fallback: `./scripts/onboard.py ${url}`,
    });
  }

  const dispatch = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      event_type: 'add-source',
      // GitHub caps client_payload at 10 properties and 64KB; this is well inside both.
      client_payload: { url, description: String(description).slice(0, 500) },
    }),
    signal: AbortSignal.timeout(20000),
  });

  if (!dispatch.ok) {
    const detail = await dispatch.text();
    return res.status(502).json({
      error: 'Could not queue the build.',
      detail: detail.slice(0, 200),
      fallback: `./scripts/onboard.py ${url}`,
    });
  }

  return res.status(202).json({
    queued: true,
    url,
    firm: host.replace(/^www\./, ''),
    watch: `https://github.com/${REPO}/actions/workflows/add-source.yml`,
    message: 'Queued. The collector is being built now; it takes a few minutes. '
           + 'When it finishes it is validated against the contract and joins the fleet.',
  });
}
