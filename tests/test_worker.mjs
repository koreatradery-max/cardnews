// Worker 카드뉴스 블록 검증 (텔레그램·인스타그램·Firestore 는 가짜): node tests/test_worker.mjs
import fs from 'fs';
import assert from 'assert';
const src = fs.readFileSync(new URL('../worker/cardnews-worker.js', import.meta.url), 'utf8');
const ID = '261117T1507-1';
const item = { id: ID, label: '[1/3] 연예', caption: '제목\n\n본문입니다.', cta: '팔로우', headline: ['줄1', '줄2'],
  variants: [{ file: ID + '_0.jpg', credit: 'A일보' }, { file: ID + '_1.jpg', credit: 'B뉴스' }] };
let ghCalls = [], ghStatus = 204;
let tgCalls = [], igCalls = [], thCalls = [], thMode = 'ok', igMode = 'ok', markup = null, db = {};
globalThis.setTimeout = (f) => f();
const tg = async (env, method, p) => {
  tgCalls.push([method, p]);
  if (method === 'sendPhoto') { markup = JSON.stringify(p.reply_markup); return { ok: true, result: { message_id: 7 } }; }
  if (method === 'editMessageReplyMarkup' || method === 'editMessageMedia' || method === 'editMessageCaption') {
    const m = JSON.stringify(p.reply_markup);
    if (method === 'editMessageReplyMarkup' && m === markup) return { ok: false, description: 'message is not modified' };
    markup = m;
  }
  return { ok: true };
};
const fsGet = async (env, path) => db[path] ? { ...db[path] } : null;
const fsWrite = async (env, writes) => { for (const w of writes) db[w.path] = w.mask ? { ...(db[w.path] || {}), ...w.data } : { ...w.data }; };
globalThis.fetch = async (url, init) => {
  url = String(url);
  if (url.includes('api.telegram.org')) {
    const p = Object.fromEntries([...init.body.entries()].filter(([k]) => k !== 'photo' && k !== 'card').map(([k, v]) => [k, (k === 'reply_markup' || k === 'media') ? JSON.parse(v) : v]));
    const method = url.split('/').pop();
    p._file = init.body.get('photo') ? 'photo' : (init.body.get('card') ? 'card' : null);
    return { json: async () => tg(env, method, p) };
  }
  if (url.includes('api.github.com')) { ghCalls.push([url, init]); return { status: ghStatus, text: async () => 'bad creds' }; }
  if (url.endsWith('.jpg')) return { ok: true, blob: async () => new Blob(['jpg']) };
  if (url.endsWith('.json')) return { ok: url.includes(ID), json: async () => item };
  if (url.includes('graph.threads.net')) {
    const params = init && init.body ? Object.fromEntries(init.body) : null;
    thCalls.push([url.split('?')[0], params]);
    if (thMode === 'fail' && url.endsWith('/threads')) return { json: async () => ({ error: { message: 'th down' } }) };
    if (url.endsWith('/threads')) return { json: async () => ({ id: 'TBOX' }) };
    if (url.endsWith('/threads_publish')) return { json: async () => ({ id: 'TPOST' }) };
    return { json: async () => ({ permalink: 'https://www.threads.net/@x/post/abc' }) };
  }
  const body = init && init.body ? JSON.parse(init.body) : null;
  igCalls.push([url, body]);
  if (url.endsWith('/media')) return { json: async () => igMode === 'expired' ? { error: { message: 'token expired', code: 190 } } : { id: 'BOX1' } };
  if (url.endsWith('/media_publish')) return { json: async () => ({ id: 'POST1' }) };
  return { json: async () => ({ permalink: 'https://www.instagram.com/p/xyz/' }) };
};
class Res { constructor(b, o) { this.body = b; this.status = (o && o.status) || 200; } }
const mod = new Function('tg', 'adminIds', 'fsGet', 'fsWrite', 'Response', src + '\nreturn { cardnewsCallback, cardnewsApi, cnText, cardnewsCron };');
const { cardnewsCallback, cardnewsApi, cnText, cardnewsCron } = mod(tg, () => ['111'], fsGet, fsWrite, Res);
const env = { BOT_TOKEN: 'B', IG_USER_ID: '999', IG_ACCESS_TOKEN: 'TOK', CARDNEWS_BASE: 'https://raw.example/media', CARDNEWS_KEY: 'K' };
const api = async (path, body, key = 'K') => { const r = await cardnewsApi({ headers: { get: () => key }, json: async () => body }, env, { pathname: path }); return { status: r.status, ...JSON.parse(r.body) }; };
const cq = (data, from = 111) => ({ id: 'c1', data, from: { id: from }, message: { chat: { id: 111 }, message_id: 7 } });
const reset = () => { tgCalls = []; igCalls = []; };
const fresh = async () => { db = {}; markup = null; igMode = 'ok'; reset(); await api('/cardnews/submit', { id: ID }); reset(); };

// 비밀값이 틀리면 거부
assert.equal((await api('/cardnews/submit', { id: ID }, 'wrong')).status, 403);
// 승인 요청 전송: 사진 주소·본문·버튼, 상태 저장, 두 번 보내지 않음
let r = await api('/cardnews/submit', { id: ID });
assert.equal(r.result, 'sent');
const sp = tgCalls[0][1];
assert.equal(sp.chat_id, '111'); assert.equal(sp._file, 'photo');
assert.equal(sp.caption, '[1/3] 연예\n\n제목\n\n본문입니다.\n\n📸 A일보\n팔로우');
assert.ok(sp.reply_markup.inline_keyboard[0][0].callback_data.length <= 64);
assert.equal(db['cardnews/' + ID].status, 'pending');
assert.equal((await api('/cardnews/submit', { id: ID })).result, 'already_sent');
assert.equal((await api('/cardnews/submit', { id: '200101T0000-1' })).status, 404);

// 권한 없는 사용자의 버튼
reset(); await cardnewsCallback(env, cq('cn:ok:' + ID, 222));
assert.equal(igCalls.length, 0); assert.equal(tgCalls[0][1].text, '권한이 없습니다.');

// 다른 사진 → 2번째로 교체(출처도 바뀜) → 10분 뒤 자동 승인은 지금 보이는 2번째 사진으로 업로드
await fresh(); await cardnewsCallback(env, cq('cn:nx:' + ID));
const em = tgCalls.find(c => c[0] === 'editMessageMedia')[1];
assert.equal(em.media.media, 'attach://card'); assert.equal(em._file, 'card'); assert.ok(em.media.caption.includes('📸 B뉴스'));
assert.equal(db['cardnews/' + ID].v, 1);
// 이전 사진 → 1번째로 되돌아가고, 다시 다음 사진 → 2번째
reset(); await cardnewsCallback(env, cq('cn:pv:' + ID));
assert.equal(db['cardnews/' + ID].v, 0);
reset(); await cardnewsCallback(env, cq('cn:pv:' + ID)); assert.equal(db['cardnews/' + ID].v, 1);   // 첫 장에서 이전 → 마지막 장
const kb = tgCalls.find(c => c[0] === 'editMessageMedia')[1].reply_markup.inline_keyboard[1];
assert.equal(kb[0].callback_data, 'cn:pv:' + ID); assert.ok(kb[1].text.includes('(2/2)'));
reset(); r = await api('/cardnews/auto', { id: ID });
assert.equal(r.result, 'posted');
assert.equal(igCalls[0][0], 'https://graph.instagram.com/999/media');
assert.deepEqual(igCalls[0][1], { image_url: 'https://raw.example/media/' + ID + '_1.jpg', caption: '제목\n\n본문입니다.\n\n📸 B뉴스\n팔로우', access_token: 'TOK' });
assert.equal(igCalls[1][1].creation_id, 'BOX1');
assert.ok(tgCalls.at(-1)[1].text.includes('자동 승인') && tgCalls.at(-1)[1].text.includes('instagram.com/p/xyz'));
assert.equal(db['cardnews/' + ID].status, 'posted'); assert.equal(db['cardnews/' + ID].auto, true);
// 이미 올라간 건: 자동 승인·버튼 모두 다시 올리지 않음
reset(); assert.equal((await api('/cardnews/auto', { id: ID })).result, 'skip_posted');
await cardnewsCallback(env, cq('cn:ok:' + ID)); assert.equal(igCalls.length, 0);

// 버튼 승인 → 이후 자동 승인은 건너뜀
await fresh(); await cardnewsCallback(env, cq('cn:ok:' + ID));
assert.equal(igCalls[0][1].image_url, 'https://raw.example/media/' + ID + '_0.jpg');
assert.ok(tgCalls.at(-1)[1].text.startsWith('✅ 인스타그램 업로드 완료\n'));
reset(); assert.equal((await api('/cardnews/auto', { id: ID })).result, 'skip_posted'); assert.equal(igCalls.length, 0);

// 반려 → 자동 승인 안 됨
await fresh(); await cardnewsCallback(env, cq('cn:no:' + ID));
assert.ok(tgCalls.find(c => c[0] === 'editMessageCaption')[1].caption.startsWith('❌ 반려됨'));
reset(); assert.equal((await api('/cardnews/auto', { id: ID })).result, 'skip_rejected'); assert.equal(igCalls.length, 0);

// 토큰 만료: 안내 + 버튼 복구, 다시 승인 가능
await fresh(); igMode = 'expired'; await cardnewsCallback(env, cq('cn:ok:' + ID));
assert.ok(tgCalls.at(-1)[1].text.includes('토큰이 만료')); assert.equal(db['cardnews/' + ID].status, 'pending');
igMode = 'ok'; reset(); await cardnewsCallback(env, cq('cn:ok:' + ID)); assert.equal(db['cardnews/' + ID].status, 'posted');
// 자동 승인 중 실패하면 failed 로 남고 버튼으로 재시도 가능
await fresh(); igMode = 'expired'; assert.equal((await api('/cardnews/auto', { id: ID })).result, 'failed');
igMode = 'ok'; reset(); await cardnewsCallback(env, cq('cn:ok:' + ID)); assert.equal(db['cardnews/' + ID].status, 'posted');

// 스레드 토큰이 없으면 스레드는 호출하지 않음
assert.equal(thCalls.length, 0);
// 스레드 토큰이 있으면 인스타그램 게시 후 스레드에도 게시, 버튼·알림에 링크 포함
env.THREADS_ACCESS_TOKEN = 'TH';
await fresh(); await cardnewsCallback(env, cq('cn:ok:' + ID));
assert.equal(thCalls[0][0], 'https://graph.threads.net/v1.0/me/threads');
assert.deepEqual(thCalls[0][1], { media_type: 'IMAGE', image_url: 'https://raw.example/media/' + ID + '_0.jpg', text: '제목\n\n본문입니다.\n\n📸 A일보', access_token: 'TH' });
assert.equal(thCalls[1][1].creation_id, 'TBOX');
assert.ok(tgCalls.at(-1)[1].text.includes('스레드: https://www.threads.net/@x/post/abc'));
const row = tgCalls.find(c => c[0] === 'editMessageCaption')[1].reply_markup.inline_keyboard[0];
assert.deepEqual(row.map(b => b.text), ['인스타그램 보기', '스레드 보기']);
// 스레드만 실패해도 인스타그램은 게시 완료로 처리
thCalls = []; thMode = 'fail'; await fresh(); await cardnewsCallback(env, cq('cn:ok:' + ID));
assert.equal(db['cardnews/' + ID].status, 'posted'); assert.ok(tgCalls.at(-1)[1].text.includes('스레드 업로드 실패: th down'));
// 긴 본문은 500자 제한에 맞게 줄임
thCalls = []; thMode = 'ok'; item.caption = ['제목', '가'.repeat(200), '나'.repeat(200), '다'.repeat(200)].join('\n\n');
await fresh(); await cardnewsCallback(env, cq('cn:ok:' + ID));
assert.ok(thCalls[0][1].text.length <= 470 && thCalls[0][1].text.endsWith('📸 A일보') && !thCalls[0][1].text.includes('다다'));
item.caption = '제목\n\n본문입니다.'; delete env.THREADS_ACCESS_TOKEN;

// 오류 알림
reset(); await api('/cardnews/notice', { text: '오류' }); assert.equal(tgCalls[0][1].text, '오류');
assert.equal(cnText(item, 0), '[1/3] 연예\n\n제목\n\n본문입니다.\n\n📸 A일보\n팔로우');
// 정시 실행 호출
assert.equal(await cardnewsCron(env, new Date('2026-11-18T03:00:30Z')), 'no_token');
env.GH_DISPATCH_TOKEN = 'G';
assert.equal(await cardnewsCron(env, new Date('2026-11-18T03:01:00Z')), 'skip');      // 정각 아님
assert.equal(await cardnewsCron(env, new Date('2026-11-18T04:00:00Z')), 'dispatched');  // 기본 1시간마다
env.CARDNEWS_EVERY_HOURS = '3';
assert.equal(await cardnewsCron(env, new Date('2026-11-18T04:00:00Z')), 'skip');        // 3시간 설정이면 한국 13시는 건너뜀
assert.equal(await cardnewsCron(env, new Date('2026-11-18T06:00:00Z')), 'dispatched');  // 한국 15시
delete env.CARDNEWS_EVERY_HOURS; ghCalls = [];
assert.equal(await cardnewsCron(env, new Date('2026-11-18T15:00:10Z')), 'dispatched'); // 한국 0시
assert.equal(ghCalls[0][0], 'https://api.github.com/repos/koreatradery-max/cardnews/actions/workflows/cardnews.yml/dispatches');
assert.equal(ghCalls[0][1].headers.Authorization, 'Bearer G'); assert.deepEqual(JSON.parse(ghCalls[0][1].body), { ref: 'main' });
ghStatus = 401; reset();
assert.equal(await cardnewsCron(env, new Date('2026-11-18T06:00:00Z')), 'failed_401');
assert.ok(tgCalls.at(-1)[1].text.includes('정시 실행 호출 실패 (401)'));
console.log('WORKER OK');
