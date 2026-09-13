/*
 Cloudflare Worker: token-free upload/delete for the PDF vault.
 The worker holds the GitHub token; the page authenticates with the site password.
 Secrets (wrangler secret put): GITHUB_TOKEN, VAULT_PASSWORD
 Vars: OWNER=DoronKabiri, REPO=obgyn, DIR=docs, ALLOW_ORIGIN=https://doronkabiri.com
*/
export default {
  async fetch(req, env) {
    const cors = {
      'Access-Control-Allow-Origin': env.ALLOW_ORIGIN || '*',
      'Access-Control-Allow-Methods': 'POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    const auth = req.headers.get('Authorization') || '';
    if (auth !== 'Bearer ' + env.VAULT_PASSWORD) return json({ error: 'unauthorized' }, 401, cors);
    if (req.method !== 'POST' && req.method !== 'DELETE') return json({ error: 'method' }, 405, cors);
    let body;
    try { body = await req.json(); } catch { return json({ error: 'bad json' }, 400, cors); }
    const name = String(body.name || '');
    if (!/^[\w.\- ()֐-׿]+\.pdf\.enc$/.test(name)) return json({ error: 'bad name' }, 400, cors);
    const api = `https://api.github.com/repos/${env.OWNER}/${env.REPO}/contents/${env.DIR}/${encodeURIComponent(name)}`;
    const gh = { 'Authorization': 'Bearer ' + env.GITHUB_TOKEN, 'Accept': 'application/vnd.github+json', 'User-Agent': 'obgyn-vault-worker', 'Content-Type': 'application/json' };
    // existing sha (for overwrite / delete)
    let sha;
    const chk = await fetch(api + '?ref=main', { headers: gh });
    if (chk.ok) sha = (await chk.json()).sha;
    if (req.method === 'DELETE') {
      if (!sha) return json({ error: 'not found' }, 404, cors);
      const r = await fetch(api, { method: 'DELETE', headers: gh, body: JSON.stringify({ message: 'Delete ' + name, sha, branch: 'main' }) });
      return json({ ok: r.ok, status: r.status }, r.ok ? 200 : 502, cors);
    }
    if (typeof body.content !== 'string' || body.content.length > 34 * 1024 * 1024) return json({ error: 'bad content' }, 400, cors);
    if (sha && !body.overwrite) return json({ error: 'exists' }, 409, cors);
    const put = { message: 'Add ' + name, content: body.content, branch: 'main' };
    if (sha) put.sha = sha;
    const r = await fetch(api, { method: 'PUT', headers: gh, body: JSON.stringify(put) });
    return json({ ok: r.ok, status: r.status }, r.ok ? 200 : 502, cors);
  },
};
function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
}
