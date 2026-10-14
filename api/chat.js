// Vercel 서버리스 함수: 화면의 질문을 OpenRouter(네모트론)로 전달하고 답을 스트리밍으로 돌려준다.
// 키는 Vercel 환경변수에만 둔다 — 저장소·화면 파일에는 넣지 않는다.
//   OPENROUTER_API_KEY  (필수) OpenRouter 키
//   APP_PASSCODE        (권장) 화면 접속 암호. 비우면 누구나 호출 가능
//   NEMOTRON_MODEL      (선택) 기본 nvidia/nemotron-3.5-lightning:free
//   CHAT_BASE_URL       (선택) OpenAI 호환 주소. 기본 https://openrouter.ai/api/v1
const BASE = (process.env.CHAT_BASE_URL || "https://openrouter.ai/api/v1").replace(/\/$/, "");
const MODEL = process.env.NEMOTRON_MODEL || "nvidia/nemotron-3.5-lightning:free";
const MAX_CHARS = 80000;   // 문맥 포함 입력 글자 수 상한 (무료 사용량 보호)
const MAX_MSGS = 40;

function bad(res, status, error) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify({ error }));
}

function upstreamError(status, text) {
  if (status === 401) return "API 키가 올바르지 않습니다. Vercel 환경변수 OPENROUTER_API_KEY를 확인하세요.";
  if (status === 402) return "OpenRouter 크레딧이 부족합니다. 무료 모델(:free)인지 확인하세요.";
  if (status === 429) return "무료 사용 한도에 걸렸습니다. 잠시 뒤 다시 시도하세요.";
  if (status === 404) return `모델을 찾지 못했습니다(${MODEL}). NEMOTRON_MODEL 값을 확인하세요.`;
  return `모델 호출 실패(${status}): ${String(text).slice(0, 300)}`;
}

async function readBody(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") return JSON.parse(req.body || "{}");
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

module.exports = async function handler(req, res) {
  const key = process.env.OPENROUTER_API_KEY || process.env.CHAT_API_KEY;
  const pass = process.env.APP_PASSCODE || "";
  if (req.method === "GET") {
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    return res.end(JSON.stringify({ ok: !!key, model: MODEL, passcode: !!pass }));
  }
  if (req.method !== "POST") return bad(res, 405, "POST만 받습니다.");
  if (!key) return bad(res, 500, "서버에 OPENROUTER_API_KEY가 설정되지 않았습니다.");
  if (pass && req.headers["x-app-passcode"] !== pass) return bad(res, 401, "접속 암호가 맞지 않습니다.");

  let body;
  try { body = await readBody(req); } catch (e) { return bad(res, 400, "요청 형식(JSON)이 올바르지 않습니다."); }
  const msgs = Array.isArray(body.messages) ? body.messages : null;
  if (!msgs || !msgs.length || msgs.length > MAX_MSGS) return bad(res, 400, "messages가 비었거나 너무 깁니다.");
  let total = 0;
  for (const m of msgs) {
    if (!["system", "user", "assistant"].includes(m && m.role) || typeof m.content !== "string") return bad(res, 400, "메시지 형식이 올바르지 않습니다.");
    total += m.content.length;
  }
  if (total > MAX_CHARS) return bad(res, 413, `입력이 너무 깁니다(${total}자 > ${MAX_CHARS}자). 보낼 데이터 범위를 줄이세요.`);

  let up;
  try {
    up = await fetch(`${BASE}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
        "HTTP-Referer": `https://${req.headers.host || "localhost"}`,
        "X-Title": "RE Exposure Hub",
      },
      body: JSON.stringify({ model: MODEL, messages: msgs, stream: true, temperature: 0.2, max_tokens: 2000 }),
    });
  } catch (e) {
    return bad(res, 502, "모델 서버에 연결하지 못했습니다: " + e.message);
  }
  if (!up.ok) return bad(res, up.status, upstreamError(up.status, await up.text()));

  res.statusCode = 200;
  res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
  res.setHeader("Cache-Control", "no-cache, no-transform");
  res.setHeader("X-Model", MODEL);
  const reader = up.body.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(Buffer.from(value));
    }
  } finally {
    res.end();
  }
};
