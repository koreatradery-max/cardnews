#!/usr/bin/env python3
"""카드뉴스 자동화 실행기.
  python run.py generate          이슈 수집 → 문구 작성 → 썸네일 제작 (out/ 에 저장)
  python run.py notify            out/pending.json 의 세트를 텔레그램으로 승인 요청 → 10분 무응답 시 자동 승인
  python run.py prune DIR HOURS   DIR 안의 오래된 세트 파일 삭제 (이미지 보관 브랜치 정리용)
  python run.py admin DIR MODE    DIR(이미지 보관 브랜치) 의 세트 점검. MODE: status | resend | bulk | threads
                                   resend = 텔레그램에 못 간 세트 재전송, bulk = 재전송 후 아직 안 올라간 세트 일괄 업로드
"""
import json, os, re, sys, time, traceback
from datetime import datetime, timedelta
from cardnews import config, collect, write, images, render, telegram

log = lambda *a: print(*a, flush=True)


def load_history():
    try:
        items = json.load(open(config.HISTORY, encoding="utf-8")).get("items", [])
    except Exception:
        items = []
    cut = (datetime.now(config.KST) - timedelta(days=config.HISTORY_DAYS)).isoformat()
    return [x for x in items if x.get("at", "") >= cut]


def save_history(items):
    os.makedirs(os.path.dirname(config.HISTORY), exist_ok=True)
    json.dump({"items": items}, open(config.HISTORY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def bigrams(s):
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def is_duplicate(issue, history):
    """LLM 이 놓친 중복을 한 번 더 거른다: 주제 문장이 비슷하거나 검색어가 사실상 같으면 중복."""
    a, qa = bigrams(issue["topic"]), set(issue["query"].split())
    for h in history:
        b, qb = bigrams(h.get("topic", "")), set(h.get("query", "").split())
        if a and b and len(a & b) / len(a | b) >= 0.5:
            return True
        if qa and qb and (qa <= qb or qb <= qa) and len(qa & qb) >= 2:
            return True
    return False


def generate():
    now = datetime.now(config.KST)
    os.makedirs(config.OUT_DIR, exist_ok=True)
    history = load_history()
    log("1) 이슈 후보 수집")
    cands, trends = collect.collect_candidates(log)
    if len(cands) < 10:
        raise RuntimeError(f"뉴스 후보가 너무 적습니다 ({len(cands)}건). 수집 채널을 확인하세요.")
    log(f"   후보 {len(cands)}건")
    log("2) 이슈 선별")
    picks = write.select_issues(cands, trends, [h["topic"] for h in history], config.SETS_PER_RUN + 5)
    made = []
    for issue in picks:
        if len(made) >= config.SETS_PER_RUN:
            break
        if is_duplicate(issue, history):
            log(f"   건너뜀(중복): {issue['topic']}")
            continue
        try:
            item = build_set(issue, f"{now:%y%m%dT%H%M}-{len(made) + 1}", cands)
        except Exception as e:
            log(f"   실패: {issue['topic']} ({e})")
            continue
        if item:
            made.append(item)
            history.append({"at": now.isoformat(), "topic": issue["topic"], "query": issue["query"], "id": item["id"]})
    for i, item in enumerate(made):
        v = item["verify"]
        item["label"] = (f"[{i + 1}/{len(made)}] {item['category']}\n검증: 언론사 {len(v['publishers'])}곳 보도 확인 · AI 검수 통과"
                         + (f" (수정 {len(v['fixed'])}건)" if v["fixed"] else "")
                         + (f"\n⏱ {config.auto_minutes(now.hour):g}분 안에 응답이 없으면 자동 승인됩니다" if config.auto_minutes(now.hour) else ""))
        json.dump(item, open(os.path.join(config.OUT_DIR, item["id"] + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    json.dump({"at": now.isoformat(), "ids": [m["id"] for m in made], "auto_min": config.auto_minutes(now.hour)},
              open(os.path.join(config.OUT_DIR, "pending.json"), "w", encoding="utf-8"))
    save_history(history)
    log(f"완료: {len(made)}세트")
    return made


def build_set(issue, set_id, pool=()):
    log(f"3) 작성: {issue['topic']}")
    words = issue["query"].split()
    arts = collect.related(words, issue["articles"], pool)
    have = {a["link"] for a in arts}
    arts += [n for n in collect.naver_news(issue["query"]) if n["link"] not in have][:4]   # 네이버 키가 있을 때만 보강
    metas = []
    for a in arts[:5]:
        metas.append({**a, **collect.fetch_article(a["link"])})
    if not any(len(m["text"]) > 150 for m in metas):
        log("   기사 본문을 읽지 못해 건너뜀")
        return None
    # 검증 ①: 교차 확인 — 서로 다른 언론사 2곳 이상이 보도한 이슈만 쓴다
    cross = collect.cross_sources(words, log)
    publishers = sorted({(m.get("site") or m["source"]) for m in metas} | {src for _, src in cross})
    if len(publishers) < 2:
        log(f"   검증 탈락(교차 확인): 보도한 언론사가 {len(publishers)}곳뿐")
        return None
    material = write.material_text(arts, [m["text"] for m in metas[:3]], [f"{t} ({src})" for t, src in cross])
    draft = write.write_set(issue, material)
    if not draft:
        log("   자료 부족으로 건너뜀")
        return None
    # 검증 ②: AI 검수 2회 + 숫자 자동 대조
    text, fixed = write.double_check(draft, material, log)
    if not text:
        return None
    imgs = images.candidates(metas, collect.naver_images(issue["query"]), config.VARIANTS, log)
    variants = []
    if not imgs:
        log("   쓸 수 있는 사진이 없어 기본 배경 사용")
        f = f"{set_id}_0.jpg"
        render.render(render.fallback_bg((255, 214, 10)), text["headline"], os.path.join(config.OUT_DIR, f))
        variants.append({"file": f, "credit": config.BRAND})
    for v, (img, credit) in enumerate(imgs):
        f = f"{set_id}_{v}.jpg"
        render.render(img, text["headline"], os.path.join(config.OUT_DIR, f), images.accent_color(img))
        variants.append({"file": f, "credit": credit})
    return {"id": set_id, "category": issue["category"], "topic": issue["topic"], "headline": text["headline"],
            "caption": text["caption"], "cta": config.CTA, "variants": variants,
            "sources": [a["link"] for a in arts[:3]],
            "verify": {"publishers": publishers, "fixed": fixed}}


def notify():
    """승인 요청을 보내고, 정해진 시간 동안 응답이 없는 세트는 자동 승인한다."""
    p = os.path.join(config.OUT_DIR, "pending.json")
    pending = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    ids = pending.get("ids", [])
    auto_min = float(pending.get("auto_min", 0))
    if not ids:
        telegram.send_text("카드뉴스: 이번 회차에는 올릴 만한 새 이슈를 만들지 못했습니다.")
        return
    sent = []
    for sid in ids:
        r = {}
        for attempt in range(10):                      # 방금 올린 이미지가 공개 주소에 반영될 때까지 몇 분 걸릴 수 있다
            r = telegram.submit(sid)
            if r.get("ok"):
                break
            time.sleep(20)
        log("전송", sid, r.get("ok"), r.get("error", ""))
        if r.get("ok"):
            sent.append(sid)
    if not sent:
        raise RuntimeError("텔레그램 승인 요청을 하나도 보내지 못했습니다.")
    if auto_min <= 0:
        return
    log(f"{auto_min:g}분 대기 후 응답 없는 세트 자동 승인")
    time.sleep(auto_min * 60)
    for sid in sent:
        r = telegram.auto_approve(sid)
        log("자동 승인 확인", sid, r.get("result") or r.get("error"))


def prune(folder, hours):
    cut = datetime.now(config.KST).replace(tzinfo=None) - timedelta(hours=float(hours))
    n = 0
    for name in os.listdir(folder):
        m = re.match(r"(\d{6}T\d{4})-\d+", name)
        if m and datetime.strptime(m.group(1), "%y%m%dT%H%M") < cut:
            os.remove(os.path.join(folder, name))
            n += 1
    log(f"정리: {n}개 삭제")


def admin(folder, mode):
    if mode == "threads":
        r = telegram.worker("/cardnews/threads", {})
        log("스레드 연결:", r)
        telegram.send_text(f"스레드 연결 점검: {'정상 @' + r.get('username', '') if r.get('ok') else '실패 ' + str(r.get('error'))}")
        if not r.get("ok"):
            raise RuntimeError(r.get("error"))
        return
    ids = sorted({m.group(1) for n in os.listdir(folder) if (m := re.match(r"(\d{6}T\d{4}-\d+)\.json$", n))})
    log(f"세트 {len(ids)}개")
    status = lambda: {x["id"]: x for x in telegram.worker("/cardnews/status", {"ids": ids}).get("items", [])}
    st = status()
    for i in ids:
        x = st.get(i, {})
        log(f"  {i}: {x.get('status')}" + (f"  오류: {x['lastError']}" if x.get("lastError") else ""))
    if mode == "status":
        return
    for i in [i for i in ids if st.get(i, {}).get("status") == "not_sent"]:
        r = telegram.submit(i)
        log("재전송", i, r.get("ok"), r.get("result") or r.get("error", ""))
    if mode != "bulk":
        return
    st = status()
    todo = [i for i in ids if st.get(i, {}).get("status") in ("pending", "failed")]
    log(f"일괄 업로드 대상 {len(todo)}개")
    done, bad = [], []
    for k in range(0, len(todo), 3):
        r = telegram.worker("/cardnews/bulk", {"ids": todo[k:k + 3]}, timeout=300)
        for x in r.get("items", []) or [{"id": i, "result": r.get("error")} for i in todo[k:k + 3]]:
            log("업로드", x["id"], x.get("result"))
    st = status()
    for i in todo:
        (done if st.get(i, {}).get("status") == "posted" else bad).append(i)
    msg = f"카드뉴스 일괄 업로드: 성공 {len(done)}건 / 실패 {len(bad)}건"
    for i in bad:
        msg += f"\n- {i}: {st.get(i, {}).get('lastError') or st.get(i, {}).get('status')}"
    log(msg)
    telegram.send_text(msg[:3500])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "generate":
            generate()
        elif cmd == "notify":
            notify()
        elif cmd == "admin":
            admin(sys.argv[2], sys.argv[3])
        elif cmd == "prune":
            prune(sys.argv[2], sys.argv[3])
        else:
            print(__doc__)
    except Exception as e:
        traceback.print_exc()
        if cmd in ("generate", "notify"):
            try:
                telegram.send_text(f"카드뉴스 실행 오류 ({cmd}): {e}"[:900])
            except Exception:
                pass
        sys.exit(1)
