// Mock LLM provider for the observability workshop. No real model: replies are canned, token counts are
// estimated from text length, latency is random (log-normal-ish), and a few percent of calls fail.
//   POST /v1/chat/completions   OpenAI format (Bearer auth), stream or not
//   POST /v1/messages           Anthropic format (x-api-key auth), stream or not
// Prompt markers: FAIL_UPSTREAM -> 529, RATE_LIMIT -> 429, SLOW -> +3s.
const http = require('http');
const PORT = +process.env.PORT || 4010;
const KEY = process.env.MOCK_LLM_KEY || 'mock-llm-key-change-me';
const ERR_RATE = +(process.env.ERROR_RATE ?? 0.04);
const txt = (c) => typeof c === 'string' ? c : (c || []).map((b) => b.text || '').join(' ');
const tok = (s) => Math.max(1, Math.ceil(s.length / 4));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const json = (res, code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)); };
const jitter = (base) => Math.round(base * (0.6 + Math.random() * 1.2) * (Math.random() < 0.05 ? 3 : 1));

http.createServer((req, res) => {
  const path = req.url.split('?')[0];
  if (path === '/healthz') return json(res, 200, { ok: true });
  const openai = path === '/v1/chat/completions';
  const anth = path === '/v1/messages';
  if (req.method !== 'POST' || !(openai || anth)) return json(res, 404, { error: 'POST /v1/chat/completions or /v1/messages' });
  const auth = openai ? req.headers.authorization === `Bearer ${KEY}` : req.headers['x-api-key'] === KEY;
  if (!auth) return json(res, 401, { error: { type: 'authentication_error', message: 'invalid key' } });
  let raw = '';
  req.on('data', (d) => (raw += d));
  req.on('end', async () => {
    let b; try { b = JSON.parse(raw); } catch { return json(res, 400, { error: 'bad JSON' }); }
    const prompt = (b.messages || []).map((m) => txt(m.content)).join('\n') + txt(b.system);
    const last = txt((b.messages || []).slice(-1)[0]?.content);
    if (prompt.includes('RATE_LIMIT')) return json(res, 429, { error: { type: 'rate_limit_error', message: 'simulated 429' } });
    if (prompt.includes('FAIL_UPSTREAM') || Math.random() < ERR_RATE) return json(res, 529, { error: { type: 'overloaded_error', message: 'simulated upstream failure' } });
    const words = 8 + Math.floor(Math.random() * 60);
    const reply = `Simulated reply to "${last.slice(0, 40)}": ` + 'lorem ipsum dolor sit amet '.repeat(Math.ceil(words / 5)).trim().split(' ').slice(0, words).join(' ');
    const usage = { in: tok(prompt) + 8, out: tok(reply) };
    const ttft = jitter(250) + (prompt.includes('SLOW') ? 3000 : 0);
    const perTok = jitter(12);
    const id = 'mock_' + Math.random().toString(36).slice(2, 12);
    if (!b.stream) {
      await sleep(ttft + perTok * usage.out);
      if (openai) return json(res, 200, { id, object: 'chat.completion', created: Math.floor(Date.now() / 1000), model: b.model,
        choices: [{ index: 0, message: { role: 'assistant', content: reply }, finish_reason: 'stop' }],
        usage: { prompt_tokens: usage.in, completion_tokens: usage.out, total_tokens: usage.in + usage.out } });
      return json(res, 200, { id, type: 'message', role: 'assistant', model: b.model, content: [{ type: 'text', text: reply }],
        stop_reason: 'end_turn', stop_sequence: null, usage: { input_tokens: usage.in, output_tokens: usage.out } });
    }
    await sleep(ttft);
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
    const chunks = reply.match(/\S+\s*/g) || [reply];
    if (openai) {
      const ch = (delta, fin) => `data: ${JSON.stringify({ id, object: 'chat.completion.chunk', model: b.model, choices: [{ index: 0, delta, finish_reason: fin }] })}\n\n`;
      res.write(ch({ role: 'assistant', content: '' }, null));
      for (const c of chunks) { res.write(ch({ content: c }, null)); await sleep(perTok); }
      res.write(ch({}, 'stop'));
      res.write(`data: ${JSON.stringify({ id, object: 'chat.completion.chunk', model: b.model, choices: [], usage: { prompt_tokens: usage.in, completion_tokens: usage.out, total_tokens: usage.in + usage.out } })}\n\n`);
      res.end('data: [DONE]\n\n');
    } else {
      const ev = (e, d) => res.write(`event: ${e}\ndata: ${JSON.stringify(d)}\n\n`);
      ev('message_start', { type: 'message_start', message: { id, type: 'message', role: 'assistant', model: b.model, content: [], stop_reason: null, usage: { input_tokens: usage.in, output_tokens: 1 } } });
      ev('content_block_start', { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } });
      for (const c of chunks) { ev('content_block_delta', { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: c } }); await sleep(perTok); }
      ev('content_block_stop', { type: 'content_block_stop', index: 0 });
      ev('message_delta', { type: 'message_delta', delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: usage.out } });
      ev('message_stop', { type: 'message_stop' });
      res.end();
    }
  });
}).listen(PORT, () => console.log(`llm-mock on :${PORT} (OpenAI + Anthropic formats)`));
