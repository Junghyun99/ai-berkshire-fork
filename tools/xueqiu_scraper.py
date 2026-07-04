#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snowball 범용 크롤러: 지정된 사용자의 전체 타임라인을 탐색하고 키워드를 기준으로 사용자의 원래 댓글을 필터링합니다.。

특성：
  - Playwright 로그인 상태 재사용: 처음 headful 수동 로그인，state 로컬에 지속
  - 듀얼 채널 fetch：우선순위 페이지 내 JS fetch，실패 시 폴백 context.request（APIRequestContext）
  - 중단점에서 계속 상승: 매회 10 페이지 저장 진행률; 중단 후 다시 실행하고 자동으로 마지막 위치부터 계속
  - 전류 제한：2-4s 랜덤 지터 + 모든 50 페이지 긴 휴식 30s + 마디 없는 5 시간 초과 후 자동으로 종료하고 진행 상태를 유지합니다.
  - 순수 포워딩 필터링: 수집된 사용자가 작성한 내용만 포함（text 비어있지 않아, 아니"앞으로 웨이보"）

자격 증명은 환경 변수를 통해 전달됩니다.，**코드 저장소에 들어가지 마세요**：
  export XQ_PHONE=13xxxxxxxxx
  export XQ_PASSWORD=xxx
설정할 필요가 없으며 처음 실행하면 팝업이 나타납니다. headful 브라우저를 사용하면 수동으로 로그인할 수 있습니다(QR 코드 스캔)./짧은 메시지/비밀번호는 선택사항입니다.）。

사용 예：
  # Pinduoduo에 대한 Duan Yongping
  python3 xueqiu_scraper.py \\
      --user-id 1247347556 \\
      --keywords 핀둬둬,PDD,Temu,황 정 \\
      --output ../reports/핀둬둬/Duan Yongping Xueqiu가 연설을 했습니다.-PDD관련된.md

  # 다른 사용자 + 기타 키워드
  python3 xueqiu_scraper.py --user-id 6784593966 --keywords 마오타이 --output /tmp/out.md

로그인 상태 캐시 기본값 /tmp/xueqiu_state.json，사용 가능 --state-path 씌우다。
"""

import argparse
import asyncio
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright


def is_match(text, keywords):
    t = (text or '').lower()
    return any(k.lower() in t for k in keywords)


def parse_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(ts)


def clean(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', '', s)
    for ent, rep in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&nbsp;', ' ')]:
        s = s.replace(ent, rep)
    return re.sub(r'&#\d+;', '', s).strip()


async def browser_fetch_json(page, url, timeout_s=15):
    """우선순위 페이지 JS fetch；실패 시 폴백 context.request。"""
    js = f"""
        async () => {{
            const ctl = new AbortController();
            const to = setTimeout(() => ctl.abort(), {int(timeout_s*1000)});
            try {{
                const r = await fetch({json.dumps(url)}, {{
                    headers: {{'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}},
                    credentials: 'include', signal: ctl.signal
                }});
                const text = await r.text();
                clearTimeout(to);
                try {{ return JSON.parse(text); }}
                catch(e) {{ return {{_raw: text.substring(0, 300)}}; }}
            }} catch(e) {{
                clearTimeout(to);
                return {{_error: e.toString()}};
            }}
        }}
    """
    try:
        result = await asyncio.wait_for(page.evaluate(js), timeout=timeout_s + 5)
        if result and not result.get('_error') and not result.get('_raw'):
            return result
    except Exception:
        pass
    try:
        resp = await page.context.request.get(url, headers={
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://xueqiu.com/',
        }, timeout=timeout_s * 1000)
        if resp.ok:
            return await resp.json()
    except Exception:
        return None
    return None


async def verify_login(page, user_id):
    test = await browser_fetch_json(
        page,
        f'https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&page=2&count=1'
    )
    return bool(test and test.get('statuses') is not None)


async def interactive_login(pw, state_path, user_id):
    phone = os.environ.get('XQ_PHONE', '')
    print("\n[로그인이 필요합니다] 열릴 것이다 headful 브라우저에서 Snowball 로그인을 완료하십시오.")
    if phone:
        print(f"        환경 변수 XQ_PHONE = {phone}   （비밀번호의 경우 XQ_PASSWORD）")
    else:
        print("        설정되지 않음 XQ_PHONE/XQ_PASSWORD，QR 코드를 수동으로 스캔하거나 브라우저에 로그인 정보를 입력하세요.")
    browser = await pw.chromium.launch(
        headless=False,
        args=['--disable-blink-features=AutomationControlled'],
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='zh-CN',
        viewport={'width': 1280, 'height': 800},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    page = await context.new_page()
    await page.goto('https://xueqiu.com/', wait_until='domcontentloaded')
    print(">>> 브라우저에서 로그인을 완료하십시오. 스크립트는 5s 폴링, 감지가 성공하고 자동으로 계속됩니다(가장 긴 10 분）")
    ok = False
    for i in range(120):
        await asyncio.sleep(5)
        try:
            if await verify_login(page, user_id):
                ok = True
                print(f"  ✓ 로그인 성공(No. {i+1} 투표소）")
                break
        except Exception as e:
            print(f"  폴링 예외(소홀히 하다): {e}")
        if (i + 1) % 6 == 0:
            print(f"  ...아직 로그인 대기 중(기다림 {(i+1)*5}s）")
    if not ok:
        print("10 몇 분 내에 로그인이 감지되지 않아 로그아웃됩니다.")
        await browser.close()
        return None
    await context.storage_state(path=state_path)
    print(f"로그인 상태가 저장되었습니다 → {state_path}")
    return browser, context, page


async def load_with_state(pw, state_path, user_id):
    if not os.path.exists(state_path):
        return None
    browser = await pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
    )
    context = await browser.new_context(
        storage_state=state_path,
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='zh-CN',
        viewport={'width': 1280, 'height': 800},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    page = await context.new_page()
    loaded = False
    for attempt in range(3):
        try:
            await page.goto('https://xueqiu.com/', wait_until='domcontentloaded', timeout=15000)
            loaded = True
            break
        except Exception as e:
            print(f"  홈페이지를 로드하지 못했습니다.(아니요.{attempt+1}이류): {e}")
            await asyncio.sleep(5)
    if not loaded:
        try:
            await page.goto('about:blank')
        except Exception:
            pass
    await asyncio.sleep(2)
    if await verify_login(page, user_id):
        print("✓ 저장된 로그인 상태를 재사용하였습니다.")
        return browser, context, page
    print("저장됨 state 만료됨")
    await browser.close()
    return None


async def fetch_all_timeline(page, user_id, keywords, progress_path, dump_all_path=''):
    collected = {}
    # all_posts：오프라인 다중 주제 분석을 위해 이 사용자의 모든 원본 진술(키워드로 필터링되지 않음)을 저장합니다.
    all_posts = {}
    if dump_all_path and os.path.exists(dump_all_path):
        try:
            for e in json.load(open(dump_all_path)):
                all_posts[e['id']] = e
            print(f"  ↪ 전체 캐시 로드：{len(all_posts)} 조각")
        except Exception as e:
            print(f"  전체 캐시 읽기 실패: {e}")
    print("\n=== 전체 타임라인을 횡단하세요 ===")
    data = await browser_fetch_json(
        page,
        f'https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&page=1&count=20'
    )
    if not data or data.get('error_code'):
        print(f"  아니요.1페이지 실패: {data}")
        return collected
    max_page = data.get('maxPage', 600)
    total = data.get('total', '?')
    print(f"  사용자ID: {user_id} | 총 게시물 수: {total} | 총 페이지: {max_page}")

    total_posts = 0
    found = 0

    def process(d):
        nonlocal total_posts, found
        for post in d.get('statuses', []):
            total_posts += 1
            text = clean(post.get('text', '') or post.get('description', ''))
            title = clean(post.get('title', ''))
            rt = post.get('retweeted_status') or {}
            rt_text = clean(rt.get('text', ''))
            own_text = (text or '').strip()
            if own_text in ('', '앞으로 웨이보', '앞으로 웨이보', 'Repost'):
                continue
            pid = str(post.get('id', ''))
            date = parse_ts(post.get('created_at', 0))
            entry = {'id': pid, 'date': date, 'title': title, 'text': own_text,
                     'url': f'https://xueqiu.com/{user_id}/{pid}'}
            if rt:
                rt_user = (rt.get('user') or {}).get('screen_name', '')
                entry['retweet_of'] = f'@{rt_user}: {rt_text}'
            # 전체 캐시(필터링 없음)）
            if dump_all_path and pid not in all_posts:
                all_posts[pid] = entry
            # 키워드별로 컬렉션 필터링
            if keywords and is_match(title + ' ' + own_text, keywords):
                if pid not in collected:
                    collected[pid] = entry
                    found += 1
                    preview = own_text[:80] if own_text else (rt_text[:80] if rt_text else title[:80])
                    print(f"  ✓ [{date}] {preview}...")

    process(data)
    start_page = 2
    if os.path.exists(progress_path):
        try:
            with open(progress_path) as f:
                prev = json.load(f)
            start_page = max(2, prev.get('next_page', 2))
            for e in prev.get('collected', []):
                collected[e['id']] = e
                found += 1
            print(f"  ↪ 계속 오르기: 1장부터 {start_page} 페이지가 시작되었습니다. 이미 {found} 조각")
        except Exception as e:
            print(f"  진행 파일을 읽지 못했습니다.: {e}")

    def save_progress(next_page):
        with open(progress_path, 'w', encoding='utf-8') as f:
            json.dump({'next_page': next_page, 'collected': list(collected.values())},
                      f, ensure_ascii=False)
        if dump_all_path:
            with open(dump_all_path, 'w', encoding='utf-8') as f:
                json.dump(list(all_posts.values()), f, ensure_ascii=False)

    consec_fail = 0
    for p in range(start_page, max_page + 1):
        try:
            data = await browser_fetch_json(
                page,
                f'https://xueqiu.com/v4/statuses/user_timeline.json?user_id={user_id}&page={p}&count=20',
                timeout_s=15,
            )
        except Exception as e:
            print(f"  아니요.{p}페이지 예외: {e}")
            data = None
        if not data:
            consec_fail += 1
            print(f"  아니요.{p}페이지가 응답하지 않음/시간 초과(연속 {consec_fail} 이류）")
            if consec_fail >= 5:
                print("  연속 실패 5 여러 번 진행 상황을 저장하고 종료합니다(자동 이력서 크롤링을 다시 실행）")
                save_progress(p)
                break
            await asyncio.sleep(5 * consec_fail)
            continue
        consec_fail = 0
        if data.get('error_code'):
            print(f"  아니요.{p}페이지 오류: {data.get('error_code')} {data.get('error_description')}")
            save_progress(p)
            break
        statuses = data.get('statuses', [])
        if not statuses:
            print(f"  아니요.{p}페이지가 비어 있음, 끝")
            break
        prev_found = found
        process(data)
        if p % 10 == 0 or found > prev_found:
            print(f"  아니요.{p}/{max_page}페이지 | 스캔됨 {total_posts} 조각 | 때리다 {found}")
        if p % 10 == 0:
            save_progress(p + 1)
        if p % 50 == 0:
            print(f"  ⏸ 아니요.{p}페이지 이후 중단 30s")
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(random.uniform(2.0, 4.0))
    else:
        if os.path.exists(progress_path):
            os.remove(progress_path)

    # 마지막 디스크 배치가 완전히 캐시됩니다.
    if dump_all_path:
        with open(dump_all_path, 'w', encoding='utf-8') as f:
            json.dump(list(all_posts.values()), f, ensure_ascii=False)
        print(f"  전체 캐시 → {dump_all_path}（{len(all_posts)} 조각）")
    print(f"\n완료: 스캔 {total_posts} 바, 치다 {found} 조각")
    return collected


def format_md(collected, user_id, keywords):
    posts = sorted(collected.values(), key=lambda x: x.get('date', ''))
    lines = [
        f"# Snowball의 연설 편집: 사용자 {user_id}",
        "",
        f"> **정보 출처**：스노볼 https://xueqiu.com/u/{user_id}",
        f"> **정리 시간**：{datetime.now().strftime('%Y-%m-%d')}",
        f"> **포함된 항목 수**：{len(posts)} 조각",
        f"> **키워드 필터**：{', '.join(keywords)}",
        f"> **수집방법**：Playwright 로그인 상태 + user_timeline.json 전체 순회(내 원래 명령문만)）",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(posts, 1):
        lines.append(f"## {i}. {p.get('date','?')}")
        lines.append("")
        if p.get('title'):
            lines += [f"**【{p['title']}】**", ""]
        if p.get('retweet_of'):
            lines += [f"> 원본 텍스트를 전달하세요.：{p['retweet_of']}", ""]
        if p.get('text'):
            lines.append(p['text'])
            lines.append("")
        lines += [f"원천：{p.get('url','')}", "", "---", ""]
    return '\n'.join(lines)


def parse_args():
    ap = argparse.ArgumentParser(description="Snowball 사용자 타임라인 크롤러(키워드로 내 원래 댓글 필터링)）")
    ap.add_argument('--user-id', type=int, help='눈덩이 사용자ID（홈페이지URL숫자 필드）')
    ap.add_argument('--keywords', type=str, default='',
                    help='쉼표로 구분된 키워드 목록입니다. 예: 핀둬둬,PDD,황 정,Temu')
    ap.add_argument('--output', type=str, default='', help='markdown 출력 경로')
    ap.add_argument('--raw-json', type=str, default='', help='（선택) 항목 원본 조회 JSON 출력 경로')
    ap.add_argument('--state-path', type=str, default='/tmp/xueqiu_state.json',
                    help='로그인 캐시 파일(기본값 /tmp/xueqiu_state.json）')
    ap.add_argument('--dump-all', type=str, default='',
                    help='전체 캐시 경로: 크롤링 시 후속 오프라인 다중 주제 분석을 위해 사용자의 모든 원본 댓글이 여기에 기록됩니다.')
    ap.add_argument('--from-cache', type=str, default='',
                    help='크롤링을 건너뛰고 모든 기존 데이터를 캐시합니다. JSON 필터 생성 markdown（필요 --keywords 그리고 --output）')
    return ap.parse_args()


def filter_from_cache(cache_path, keywords, user_id):
    posts = json.load(open(cache_path))
    out = []
    for p in posts:
        if is_match((p.get('title','') + ' ' + p.get('text','')), keywords):
            out.append(p)
    return {p['id']: p for p in out}


async def main():
    args = parse_args()
    keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]

    # 오프라인 필터링 모드
    if args.from_cache:
        if not (keywords and args.output):
            print("--from-cache 동시에 지정해야 합니다. --keywords 그리고 --output")
            return
        user_id = args.user_id or 0
        collected = filter_from_cache(args.from_cache, keywords, user_id)
        print(f"캐시에서 {args.from_cache} 체로 걸러내다 {len(collected)} 기사(키워드: {keywords}）")
        if not collected:
            return
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(format_md(collected, user_id, keywords))
        print(f"Markdown → {args.output}")
        return

    if not args.user_id:
        print("필요 --user-id")
        return

    progress_path = args.state_path + f'.progress.{args.user_id}'
    raw_json = args.raw_json or f'/tmp/xueqiu_{args.user_id}_raw.json'

    print("=" * 60)
    print(f"눈덩이 크롤러 | user_id={args.user_id} | keywords={keywords} | dump_all={args.dump_all}")
    print("=" * 60)

    async with async_playwright() as pw:
        session = await load_with_state(pw, args.state_path, args.user_id)
        if not session:
            session = await interactive_login(pw, args.state_path, args.user_id)
        if not session:
            print("로그인할 수 없습니다. 로그아웃하세요.")
            return
        browser, _, page = session
        collected = await fetch_all_timeline(page, args.user_id, keywords, progress_path, args.dump_all)
        await browser.close()

    print(f"\n=== 결정적인: {len(collected)} 운명 ===")
    if not collected:
        return
    with open(raw_json, 'w', encoding='utf-8') as f:
        json.dump(list(collected.values()), f, ensure_ascii=False, indent=2)
    print(f"원래의JSON → {raw_json}")
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(format_md(collected, args.user_id, keywords))
        print(f"Markdown  → {args.output}")


if __name__ == '__main__':
    asyncio.run(main())
