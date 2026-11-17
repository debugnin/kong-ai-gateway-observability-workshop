// Minimal stateless MCP server (Streamable HTTP, JSON responses) for the observability workshop.
// TOOLSET picks the tools. Some tools are slow or flaky on purpose so latency and error panels get data:
//   *_flaky tools fail ~30% of the time (JSON-RPC error + HTTP 500), slow_* tools take 1-3 s.
const http = require('http');
const PORT = +process.env.PORT || 4020;
const NAME = process.env.TOOLSET || 'code';
const obj = (properties = {}, required = []) => ({ type: 'object', properties, required });
const S = { type: 'string' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TOOLSETS = {
  code: {
    search_repo: ['Search repository code for a string', obj({ query: S }, ['query']), async (a) => `3 matches for "${a.query}" in payments-service`],
    list_open_prs: ['List open pull requests', obj(), async () => 'PR #412 "Add retry to ledger client"; PR #415 "Bump deps"'],
    run_ci_flaky: ['Trigger CI (fails often)', obj(), async () => { if (Math.random() < 0.3) throw new Error('CI backend unavailable'); return 'CI run #9031 started'; }],
  },
  finance: {
    get_invoice_summary: ['Summarise invoices for a month', obj({ month: S }, ['month']), async (a) => `Invoices ${a.month}: 128 issued, $412,300 total, 4 overdue`],
    slow_budget_report: ['Build the budget report (slow)', obj(), async () => { await sleep(1000 + Math.random() * 2000); return 'Engineering $20,000; Finance $10,000'; }],
  },
};
const tools = TOOLSETS[NAME];
const send = (res, code, id, payload) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify({ jsonrpc: '2.0', id, ...payload })); };

http.createServer((req, res) => {
  if (req.url === '/healthz') { res.writeHead(200); return res.end('ok'); }
  if (req.method !== 'POST' || req.url.split('?')[0] !== '/mcp') { res.writeHead(405); return res.end(); }
  let raw = ''; req.on('data', (d) => (raw += d));
  req.on('end', async () => {
    let m; try { m = JSON.parse(raw); } catch { return send(res, 200, null, { error: { code: -32700, message: 'parse error' } }); }
    if (m.id === undefined) { res.writeHead(202); return res.end(); } // notification
    if (m.method === 'initialize') return send(res, 200, m.id, { result: { protocolVersion: m.params?.protocolVersion || '2025-03-26', capabilities: { tools: {} }, serverInfo: { name: `${NAME}-mcp`, version: '1.0.0' } } });
    if (m.method === 'ping') return send(res, 200, m.id, { result: {} });
    if (m.method === 'tools/list') return send(res, 200, m.id, { result: { tools: Object.entries(tools).map(([name, [description, inputSchema]]) => ({ name, description, inputSchema })) } });
    if (m.method === 'tools/call') {
      const t = tools[m.params?.name];
      if (!t) return send(res, 200, m.id, { error: { code: -32602, message: 'unknown tool' } });
      try { return send(res, 200, m.id, { result: { content: [{ type: 'text', text: await t[2](m.params.arguments || {}) }] } }); }
      catch (e) { return send(res, 500, m.id, { error: { code: -32000, message: e.message } }); }
    }
    send(res, 200, m.id, { error: { code: -32601, message: 'method not found' } });
  });
}).listen(PORT, () => console.log(`${NAME}-mcp on :${PORT}`));
