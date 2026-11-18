/* ======================= 카드뉴스 승인 · 인스타그램 업로드 =======================
 * 기존 Worker(tg-login) 맨 아래에 이 블록 전체를 붙여 넣고, 아래 세 군데를 고칩니다.
 *
 * (1) fetch 라우터 안, '/tg/webhook' 줄 바로 아래에 추가
 *       if (url.pathname.startsWith('/cardnews/') && req.method === 'POST') return await cardnewsApi(req, env, url);
 *
 * (2) tgWebhook 안, `const update = await req.json().catch(() => ({}));` 바로 다음 줄에 추가
 *       if (update.callback_query) return cardnewsCallback(env, update.callback_query);
 *
 * (4) scheduled 안, 기존 briefingCron 줄 바로 아래에 추가
 *       ctx.waitUntil(cardnewsCron(env).catch(e => console.error('cardnews cron', e)));
 *
 * (3) setup 안의 allowed_updates 를 ['message'] → ['message', 'callback_query'] 로 변경
 *     배포 후 https://<worker 주소>/setup?key=<WEBHOOK_SECRET> 을 한 번 열어 웹훅을 다시 등록
 *
 * [추가 환경 변수]
 *   CARDNEWS_KEY     (Secret)  GitHub Actions 와 공유하는 비밀값 (GitHub Secrets 의 CARDNEWS_KEY 와 같은 값)
 *   CARDNEWS_BASE    (Text)    이미지 보관 주소. 예: https://raw.githubusercontent.com/<계정>/<저장소>/media/
 *   IG_USER_ID       (Text)    인스타그램 프로페셔널 계정 ID (숫자)
 *   IG_ACCESS_TOKEN  (Secret)  인스타그램 사용자 액세스 토큰 (장기 토큰, 60일마다 갱신)
 *   IG_GRAPH_HOST    (Text, 선택) 기본 graph.instagram.com (Facebook 로그인 토큰이면 graph.facebook.com)
 *   GH_DISPATCH_TOKEN (Secret) GitHub 토큰(cardnews 저장소 Actions 읽기·쓰기). 넣으면 Worker 가 정시(한국 0·3·6·…·21시)에 실행을 호출
 *   THREADS_ACCESS_TOKEN (Secret, 선택) 스레드 사용자 액세스 토큰. 넣으면 인스타그램 게시 후 스레드에도 같은 사진·글을 올림
 *
 * [상태 저장] Firestore cardnews/{세트ID}: { status: pending|uploading|posted|rejected, chat, mid, v, at }
 */
function cnKeyboard(id, v, n) {
  const rows = [[{ text: '✅ 승인', callback_data: `cn:ok:${id}` }, { text: '❌ 반려', callback_data: `cn:no:${id}` }]];
  if (n > 1) rows.push([{ text: '◀ 이전 사진', callback_data: `cn:pv:${id}` }, { text: `다음 사진 ▶ (${v + 1}/${n})`, callback_data: `cn:nx:${id}` }]);
  return { inline_keyboard: rows };
}
function cnBase(env) { return String(env.CARDNEWS_BASE || '').replace(/\/?$/, '/'); }
function cnCaption(item, v) { return `${item.caption}\n\n📸 ${item.variants[v].credit}\n${item.cta}`; }
function cnText(item, v, head) { return `${head ? head + '\n' : ''}${item.label}\n\n${cnCaption(item, v)}`.slice(0, 1024); }
function cnJson(o, status) { return new Response(JSON.stringify(o), { status: status || 200, headers: { 'Content-Type': 'application/json' } }); }
async function cnItem(env, id) {
  if (!/^[0-9T-]+$/.test(id || '')) return null;
  try { const r = await fetch(`${cnBase(env)}${id}.json`); if (r.ok) { const it = await r.json(); if (it && it.variants && it.variants.length) return it; } } catch (e) {}
  return null;
}

/* 텔레그램에 사진을 주소가 아닌 파일로 직접 올린다 (텔레그램 서버가 이미지 주소를 못 읽는 경우 대비) */
async function cnTgPhoto(env, method, params, imageUrl) {
  const img = await fetch(imageUrl);
  if (!img.ok) return { ok: false, description: 'image ' + img.status };
  const blob = await img.blob();
  const form = new FormData();
  for (const [k, v] of Object.entries(params)) form.append(k, typeof v === 'object' ? JSON.stringify(v) : String(v));
  if (method === 'sendPhoto') form.append('photo', blob, 'card.jpg');
  else form.append('card', blob, 'card.jpg');
  const r = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, { method: 'POST', body: form });
  return r.json().catch(() => ({ ok: false, description: 'bad response ' + r.status }));
}

async function cnInstagram(env, path, body) {
  const host = env.IG_GRAPH_HOST || 'graph.instagram.com';
  const init = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, access_token: env.IG_ACCESS_TOKEN }) }
    : { method: 'GET' };
  const url = `https://${host}/${path}` + (body ? '' : `${path.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(env.IG_ACCESS_TOKEN)}`);
  const res = await fetch(url, init);
  return res.json().catch(() => ({ error: { message: 'bad response ' + res.status } }));
}

async function cnPublish(env, imageUrl, caption) {
  if (!env.IG_USER_ID || !env.IG_ACCESS_TOKEN) throw new Error('IG_USER_ID / IG_ACCESS_TOKEN 이 설정되지 않았습니다.');
  const box = await cnInstagram(env, `${env.IG_USER_ID}/media`, { image_url: imageUrl, caption });
  if (!box.id) throw Object.assign(new Error(box.error && box.error.message || '컨테이너 생성 실패'), { code: box.error && box.error.code });
  let pub = null;
  for (let i = 0; i < 6; i++) {                       // 컨테이너 준비가 덜 됐으면 잠깐 기다렸다가 다시 시도
    pub = await cnInstagram(env, `${env.IG_USER_ID}/media_publish`, { creation_id: box.id });
    if (pub.id) break;
    await new Promise(r => setTimeout(r, 2500));
  }
  if (!pub || !pub.id) throw Object.assign(new Error(pub && pub.error && pub.error.message || '게시 실패'), { code: pub && pub.error && pub.error.code });
  const info = await cnInstagram(env, `${pub.id}?fields=permalink`);
  return { id: pub.id, permalink: info.permalink || '' };
}

/* 승인 처리 (버튼 승인과 자동 승인 공통). 반환: posted | busy | failed */
async function cnApprove(env, id, item, st, auto) {
  // 버튼을 먼저 '업로드 중'으로 바꿔 중복 업로드를 막는다 (이미 바뀌어 있으면 수정이 실패하므로 그대로 종료)
  const lock = await tg(env, 'editMessageReplyMarkup', { chat_id: st.chat, message_id: st.mid, reply_markup: { inline_keyboard: [[{ text: '⏳ 업로드 중…', callback_data: 'cn:wait' }]] } });
  if (!lock.ok) return 'busy';
  await fsWrite(env, [{ path: `cardnews/${id}`, data: { status: 'uploading' }, mask: true }]);
  const v = Math.min(Number(st.v || 0), item.variants.length - 1);
  try {
    const post = await cnPublish(env, cnBase(env) + item.variants[v].file, cnCaption(item, v));
    await fsWrite(env, [{ path: `cardnews/${id}`, data: { status: 'posted', permalink: post.permalink, auto: !!auto, postedAt: Date.now() }, mask: true }]);
    const th = await cnThreads(env, cnBase(env) + item.variants[v].file, item, v);
    const done = [[post.permalink && { text: '인스타그램 보기', url: post.permalink }, th && th.permalink && { text: '스레드 보기', url: th.permalink }].filter(Boolean)].filter(r => r.length);
    await tg(env, 'editMessageCaption', { chat_id: st.chat, message_id: st.mid, caption: cnText(item, v, auto ? '✅ 자동 승인 · 업로드 완료' : '✅ 업로드 완료'), reply_markup: { inline_keyboard: done } });
    await tg(env, 'sendMessage', { chat_id: st.chat, text: `✅ 인스타그램 업로드 완료${auto ? ' (자동 승인)' : ''}\n${(item.headline || []).join(' ')}${post.permalink ? '\n' + post.permalink : ''}${th ? (th.permalink ? '\n스레드: ' + th.permalink : (th.id ? '\n스레드 업로드 완료' : '\n⚠️ 스레드 업로드 실패: ' + th.error)) : ''}` });
    return 'posted';
  } catch (e) {
    await fsWrite(env, [{ path: `cardnews/${id}`, data: { status: auto ? 'failed' : 'pending' }, mask: true }]);
    await tg(env, 'editMessageReplyMarkup', { chat_id: st.chat, message_id: st.mid, reply_markup: cnKeyboard(id, v, item.variants.length) });
    const hint = e.code === 190 ? '\n인스타그램 토큰이 만료됐습니다. IG_ACCESS_TOKEN 을 갱신해 주세요.' : '';
    await tg(env, 'sendMessage', { chat_id: st.chat, text: `⚠️ 업로드 실패: ${e.message}${hint}\n승인 버튼을 다시 누르면 재시도합니다.` });
    return 'failed';
  }
}

/* GitHub Actions → Worker.  POST /cardnews/submit {id} · /cardnews/auto {id} · /cardnews/notice {text} */
async function cardnewsApi(req, env, url) {
  if (!env.CARDNEWS_KEY || req.headers.get('X-Cardnews-Key') !== env.CARDNEWS_KEY) return cnJson({ ok: false, error: 'forbidden' }, 403);
  const body = await req.json().catch(() => ({}));
  const admin = adminIds(env)[0];
  if (!admin) return cnJson({ ok: false, error: 'ADMIN_TG_IDS 없음' }, 500);
  if (url.pathname === '/cardnews/notice') {
    const r = await tg(env, 'sendMessage', { chat_id: admin, text: String(body.text || '').slice(0, 3500) });
    return cnJson({ ok: !!r.ok });
  }
  const id = String(body.id || '');
  const item = await cnItem(env, id);
  if (!item) return cnJson({ ok: false, error: 'set_not_found' }, 404);
  if (url.pathname === '/cardnews/submit') {
    const old = await fsGet(env, `cardnews/${id}`);
    if (old) return cnJson({ ok: true, result: 'already_sent' });
    const r = await cnTgPhoto(env, 'sendPhoto', { chat_id: admin, caption: cnText(item, 0), reply_markup: cnKeyboard(id, 0, item.variants.length) }, cnBase(env) + item.variants[0].file);
    if (!r.ok) return cnJson({ ok: false, error: r.description || 'sendPhoto 실패' }, 502);
    await fsWrite(env, [{ path: `cardnews/${id}`, data: { status: 'pending', chat: String(admin), mid: r.result.message_id, v: 0, at: Date.now() } }]);
    return cnJson({ ok: true, result: 'sent' });
  }
  if (url.pathname === '/cardnews/auto') {
    const st = await fsGet(env, `cardnews/${id}`);
    if (!st) return cnJson({ ok: false, error: 'not_sent' }, 404);
    if (st.status !== 'pending') return cnJson({ ok: true, result: 'skip_' + st.status });
    return cnJson({ ok: true, result: await cnApprove(env, id, item, st, true) });
  }
  return cnJson({ ok: false, error: 'not_found' }, 404);
}

/* 텔레그램 버튼 처리 */
async function cardnewsCallback(env, cq) {
  const ok = new Response('ok');
  const answer = (text, alert) => tg(env, 'answerCallbackQuery', { callback_query_id: cq.id, text, show_alert: !!alert });
  const [ns, act, id] = String(cq.data || '').split(':');
  if (ns !== 'cn' || !cq.message) { await answer(''); return ok; }
  if (!adminIds(env).includes(String(cq.from.id))) { await answer('권한이 없습니다.', true); return ok; }
  if (act === 'wait') { await answer('업로드 중입니다. 잠시만 기다려 주세요.'); return ok; }
  const item = await cnItem(env, id);
  const st = item && await fsGet(env, `cardnews/${id}`);
  if (!item || !st) { await answer('세트 정보를 찾지 못했습니다. (보관 기간 3일이 지났을 수 있어요)', true); return ok; }
  if (st.status !== 'pending' && st.status !== 'failed') { await answer('이미 처리된 건입니다.'); return ok; }
  const n = item.variants.length, v = Math.min(Number(st.v || 0), n - 1);
  const where = { chat: cq.message.chat.id, mid: cq.message.message_id, v };

  if (act === 'nx' || act === 'pv') {
    const nv = (v + (act === 'pv' ? n - 1 : 1)) % n;
    const r = await cnTgPhoto(env, 'editMessageMedia', { chat_id: where.chat, message_id: where.mid,
      media: { type: 'photo', media: 'attach://card', caption: cnText(item, nv) }, reply_markup: cnKeyboard(id, nv, n) }, cnBase(env) + item.variants[nv].file);
    if (r.ok) await fsWrite(env, [{ path: `cardnews/${id}`, data: { v: nv }, mask: true }]);
    await answer(r.ok ? `사진 ${nv + 1}/${n}` : '사진을 바꾸지 못했습니다.');
    return ok;
  }
  if (act === 'no') {
    await fsWrite(env, [{ path: `cardnews/${id}`, data: { status: 'rejected' }, mask: true }]);
    await tg(env, 'editMessageCaption', { chat_id: where.chat, message_id: where.mid, caption: cnText(item, v, '❌ 반려됨 (폐기)'), reply_markup: { inline_keyboard: [] } });
    await answer('폐기했습니다.');
    return ok;
  }
  if (act === 'ok') {
    await answer('인스타그램에 업로드합니다.');
    const r = await cnApprove(env, id, item, where, false);
    if (r === 'busy') await answer('이미 처리 중입니다.');
    return ok;
  }
  await answer('');
  return ok;
}

/* 스레드 동시 게시 (THREADS_ACCESS_TOKEN 이 있을 때만). 반환: null | { id, permalink } | { error } — 실패해도 인스타그램 게시에는 영향 없음 */
async function cnThreads(env, imageUrl, item, v) {
  if (!env.THREADS_ACCESS_TOKEN) return null;
  const call = async (path, params, method) => {
    const body = new URLSearchParams({ ...params, access_token: env.THREADS_ACCESS_TOKEN });
    const res = method === 'GET'
      ? await fetch(`https://graph.threads.net/v1.0/${path}?${body}`)
      : await fetch(`https://graph.threads.net/v1.0/${path}`, { method: 'POST', body });
    return res.json().catch(() => ({ error: { message: 'bad response ' + res.status } }));
  };
  try {
    // 스레드 글자 수 제한(500자)에 맞춰 뒤 문단부터 줄인다
    const tail = `\n\n📸 ${item.variants[v].credit}`;
    let paras = String(item.caption || '').split('\n\n');
    while (paras.length > 1 && (paras.join('\n\n') + tail).length > 470) paras.pop();
    let text = paras.join('\n\n');
    if ((text + tail).length > 470) text = text.slice(0, 470 - tail.length - 1) + '…';
    const user = env.THREADS_USER_ID || 'me';
    const box = await call(`${user}/threads`, { media_type: 'IMAGE', image_url: imageUrl, text: text + tail });
    if (!box.id) return { error: box.error && box.error.message || '컨테이너 생성 실패' };
    let pub = null;
    for (let i = 0; i < 6; i++) {
      await new Promise(r => setTimeout(r, 2500));           // 컨테이너 처리 시간을 기다린 뒤 게시
      pub = await call(`${user}/threads_publish`, { creation_id: box.id });
      if (pub.id) break;
    }
    if (!pub || !pub.id) return { error: pub && pub.error && pub.error.message || '게시 실패' };
    const info = await call(`${pub.id}`, { fields: 'permalink' }, 'GET');
    return { id: pub.id, permalink: info.permalink || '' };
  } catch (e) {
    return { error: e.message };
  }
}

/* 정시 실행: Worker 의 1분 크론에서 호출. 한국 시간 0·3·6·9·12·15·18·21시 정각에 GitHub Actions 를 실행시킨다 */
async function cardnewsCron(env, now) {
  if (!env.GH_DISPATCH_TOKEN) return 'no_token';
  const d = now || new Date();
  if (d.getUTCMinutes() !== 0 || d.getUTCHours() % 3 !== 0) return 'skip';
  const repo = env.CARDNEWS_REPO || 'koreatradery-max/cardnews';
  const r = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/cardnews.yml/dispatches`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'cardnews-worker', 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: 'main' }),
  });
  if (r.status === 204) return 'dispatched';
  const detail = (await r.text().catch(() => '')).slice(0, 200);
  const admin = adminIds(env)[0];
  if (admin) await tg(env, 'sendMessage', { chat_id: admin, text: `⚠️ 카드뉴스 정시 실행 호출 실패 (${r.status})\n${detail}${r.status === 401 ? '\nGH_DISPATCH_TOKEN 이 만료됐거나 잘못됐습니다.' : ''}` });
  return 'failed_' + r.status;
}
