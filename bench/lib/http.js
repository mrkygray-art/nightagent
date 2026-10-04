// One HTTP request with the bench's retry rule (spec section 5):
// retry 429, 5xx, and network errors/timeouts up to `max_retries` times with backoff,
// honoring Retry-After; never retry other 4xx. Failures are returned, never thrown,
// so they are recorded as failures instead of being dropped.
//
// Latency is the wall-clock time of the attempt that produced the final response.
// Error messages never include request headers (where the API key lives).

const defaultSleep = (ms) => new Promise((r) => setTimeout(r, ms));

function retryAfterMs(res, cap) {
  const v = res.headers?.get?.('retry-after');
  if (!v) return null;
  const secs = Number(v);
  const ms = Number.isFinite(secs) ? secs * 1000 : Date.parse(v) - Date.now();
  return Number.isFinite(ms) && ms > 0 ? Math.min(ms, cap) : null;
}

async function readBody(res) {
  const text = await res.text();
  try { return JSON.parse(text); } catch { return text; }
}

// makeRequest() must return fresh fetch arguments each time ({ url, init }), since a body
// stream can't be re-sent.
// binary: true returns a successful body as an ArrayBuffer (audio) instead of text/JSON.
async function requestWithRetry(makeRequest, retry, { fetch = globalThis.fetch, sleep = defaultSleep, binary = false } = {}) {
  const maxRetries = retry.max_retries ?? 2;
  let attempts = 0;
  let last = null;
  while (attempts <= maxRetries) {
    attempts++;
    const { url, init } = makeRequest();
    const started = performance.now();
    let res;
    try {
      res = await fetch(url, { ...init, signal: AbortSignal.timeout(retry.timeout_ms ?? 60000) });
    } catch (e) {
      last = { ok: false, status: null, body: null, latencyMs: null, attempts, error: `network error: ${e.name === 'TimeoutError' ? 'timed out' : e.message}` };
      if (attempts <= maxRetries) await sleep(retry.backoff_ms?.[attempts - 1] ?? 1000);
      continue;
    }
    const body = binary && res.ok ? await res.arrayBuffer() : await readBody(res);
    const latencyMs = Math.round(performance.now() - started);
    if (res.ok) return { ok: true, status: res.status, body, latencyMs, attempts, error: null };
    const detail = typeof body === 'string' ? body : JSON.stringify(body);
    last = { ok: false, status: res.status, body, latencyMs, attempts, error: `HTTP ${res.status}: ${detail.slice(0, 300)}` };
    const retryable = res.status === 429 || res.status >= 500;
    if (!retryable || attempts > maxRetries) break;
    await sleep(retryAfterMs(res, retry.max_retry_after_ms ?? 30000) ?? retry.backoff_ms?.[attempts - 1] ?? 1000);
  }
  return last;
}

module.exports = { requestWithRetry };
