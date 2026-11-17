// Traffic generator: weighted mix of teams, models, streaming and failures. Ctrl-C / `docker compose stop loadgen` to end.
const URL_ = process.env.GATEWAY_URL || 'http://localhost:18000';
const RPS = +process.env.RPS || 3;
const teams = [
  { name: 'team-a', key: process.env.KEY_TEAM_A, w: 5 },
  { name: 'team-b', key: process.env.KEY_TEAM_B, w: 3 },
  { name: 'team-c', key: process.env.KEY_TEAM_C, w: 1 },
];
// path = the model route on the gateway; fast = cheaper model gets more traffic
const models = [
  { path: '/llm/fast/v1/chat/completions', model: 'mock-fast', w: 6 },
  { path: '/llm/smart/v1/chat/completions', model: 'mock-smart', w: 3 },
  { path: '/llm/claude/v1/chat/completions', model: 'mock-claude', w: 3 },
];
const prompts = ['Summarise this incident report', 'Write a SQL query for monthly revenue', 'Explain OAuth client credentials',
  'Draft release notes for v2.3', 'Translate this paragraph to Thai', 'Review this pull request for risks'];
const pick = (arr) => { let r = Math.random() * arr.reduce((s, x) => s + x.w, 0); for (const x of arr) if ((r -= x.w) < 0) return x; return arr[0]; };
const mcps = [
  { path: '/mcp/code', calls: [['search_repo', { query: 'retry' }], ['list_open_prs', {}], ['run_ci_flaky', {}]], w: 3 },
  { path: '/mcp/finance', calls: [['get_invoice_summary', { month: '2026-10' }], ['slow_budget_report', {}]], w: 2 },
];
const stats = {};
async function rpc(path, key, method, params, id) {
  const r = await fetch(URL_ + path, { method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', apikey: key },
    body: JSON.stringify({ jsonrpc: '2.0', id, method, params }) });
  await r.text(); const k = 'mcp' + r.status; stats[k] = (stats[k] || 0) + 1;
}
async function oneMcp() {
  const t = pick(teams), m = pick(mcps), [tool, args] = m.calls[Math.floor(Math.random() * m.calls.length)];
  try {
    await rpc(m.path, t.key, 'initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: t.name, version: '1' } }, 1);
    await rpc(m.path, t.key, 'tools/list', {}, 2);
    await rpc(m.path, t.key, 'tools/call', { name: tool, arguments: args }, 3);
  } catch (e) { stats.mcperr = (stats.mcperr || 0) + 1; }
}
async function one() {
  const t = pick(teams), m = pick(models);
  let p = prompts[Math.floor(Math.random() * prompts.length)];
  const roll = Math.random();
  if (roll < 0.02) p += ' RATE_LIMIT'; else if (roll < 0.04) p += ' SLOW';
  const stream = Math.random() < 0.4;
  try {
    const r = await fetch(URL_ + m.path, { method: 'POST',
      headers: { 'content-type': 'application/json', apikey: Math.random() < 0.03 ? 'wrong-key' : (t.key || 'missing') },  // ~3% bad keys -> 401 access logs
      body: JSON.stringify({ model: m.model, stream, ...(stream ? { stream_options: { include_usage: true } } : {}), messages: [{ role: 'user', content: p }] }) });
    await r.text();
    stats[r.status] = (stats[r.status] || 0) + 1;
  } catch (e) { stats.err = (stats.err || 0) + 1; }
}
setInterval(() => { for (let i = 0; i < RPS; i++) one(); oneMcp(); }, 1000);
setInterval(() => console.log(new Date().toISOString(), JSON.stringify(stats)), 15000);
console.log(`loadgen -> ${URL_} at ~${RPS} rps`);
