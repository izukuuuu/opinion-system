"""NetInsight login, counting and collection helpers adapted from the Sona workflow."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests

COUNT_API_URL = "https://pro.netinsight.com.cn/netInsight/general/advancedSearch/infoCount"
INFO_LIST_API_URL = "https://pro.netinsight.com.cn/netInsight/general/advancedSearch/infoList"
LOGIN_URL = "https://pro.netinsight.com.cn/login"

BASE_COUNT_PARAMS: Dict[str, str] = {
    "keyWordIndex": "ALL",
    "weiboWordIndex": "1",
    "luntanWordIndex": "1",
    "trollLabelFilter": "ALL",
    "trollSubFilter": "IP地域异常;登录设备异常;发文行为异常;发文内容异常",
    "sort": "relevance",
    "monitorSite": "",
    "excludeWeb": "",
    "industrySector": "",
    "eventType": "",
    "excludeWordsIndex": "0;1;2;3",
    "ipLocation": "",
    "signLocation": "",
    "sensitivityTendency": "民生问题;环保问题;教育问题;医疗问题;自然灾害;腐败问题;事故灾难;热点事件;社会不公;社会安全;司法问题;民族分裂;暴恐问题;军警问题;信访维权;意识形态;宗教问题;其他",
    "mediaIndustry": "娱乐;公益;广告;游戏;气象;民族与宗教;通信;能源;航空;政务;财经;医疗健康;科技;军事;教育;农林牧渔业;电商;体育;汽车;房产;旅游;文化;食品;其它",
    "contentIndustry": "娱乐;公益;广告;游戏;气象;民族与宗教;通信;能源;航空;政务;财经;医疗健康;科技;军事;教育;农林牧渔业;电商;体育;汽车;房产;旅游;文化;食品;其它",
    "contentArea": "",
    "mediaArea": "北京;天津;河北;山西;内蒙古;辽宁;吉林;黑龙江;上海;江苏;浙江;安徽;福建;江西;山东;河南;湖北;湖南;广东;广西;海南;重庆;四川;贵州;云南;西藏;陕西;甘肃;青海;宁夏;新疆;台湾;香港;澳门;其它",
    "weiboFilter": "黄v;橙v;金v;蓝v;无认证",
    "weMediaFilter": "小红书;微头条;一点号;头条号;企鹅号;百家号;网易号;搜狐号;新浪号;大鱼号;人民号;快传号;澎湃号;大风号",
    "videoFilter": "抖音;快手;哔哩哔哩;今日头条;西瓜视频;度小视;好看视频;微视;美拍;梨视频;电视视频;其他;百度视频",
    "forumFilter": "百度贴吧;知乎;豆瓣;其他",
    "simflag": "urlRemove",
    "mediaLevel": "ALL",
    "emotion": "ALL",
    "sendWay": "ALL",
    "infoType": "1",
    "reloadFilterId": "0",
    "reloadId": "0",
    "warnFangshi": "ALL",
    "hasAlertTypes": "ALL",
    "allList": "true",
    "ruleId": "",
    "searchType": "fulltext",
    "moreStatus": "false",
    "source": "ALL",
    "pageNo": "0",
    "pageSize": "50",
    "signal": "[object AbortSignal]",
}

BASE_INFO_PARAMS: Dict[str, str] = {
    "keyWordIndex": "ALL",
    "weiboWordIndex": "2",
    "luntanWordIndex": "2",
    "trollLabelFilter": "ALL",
    "trollSubFilter": "IP地域异常;登录设备异常;发文行为异常;发文内容异常",
    "sort": "relevance",
    "monitorSite": "",
    "excludeWeb": "",
    "industrySector": "",
    "eventType": "",
    "excludeWordsIndex": "0;1;2;3",
    "ipLocation": "",
    "signLocation": "",
    "sensitivityTendency": "民生问题;环保问题;教育问题;医疗问题;自然灾害;腐败问题;事故灾难;热点事件;社会不公;社会安全;司法问题;民族分裂;暴恐问题;军警问题;信访维权;意识形态;宗教问题;其他",
    "mediaIndustry": "娱乐;公益;广告;游戏;气象;民族与宗教;通信;能源;航空;政务;财经;医疗健康;科技;军事;教育;农林牧渔业;电商;体育;汽车;房产;旅游;文化;食品;其它",
    "contentIndustry": "娱乐;公益;广告;游戏;气象;民族与宗教;通信;能源;航空;政务;财经;医疗健康;科技;军事;教育;农林牧渔业;电商;体育;汽车;房产;旅游;文化;食品;其它",
    "contentArea": "",
    "mediaArea": "北京;天津;河北;山西;内蒙古;辽宁;吉林;黑龙江;上海;江苏;浙江;安徽;福建;江西;山东;河南;湖北;湖南;广东;广西;海南;重庆;四川;贵州;云南;西藏;陕西;甘肃;青海;宁夏;新疆;台湾;香港;澳门;其它",
    "weiboFilter": "黄v;橙v;金v;蓝v;无认证",
    "weMediaFilter": "小红书",
    "videoFilter": "抖音;快手;哔哩哔哩;今日头条;西瓜视频",
    "forumFilter": "百度贴吧;知乎;豆瓣",
    "simflag": "urlRemove",
    "mediaLevel": "ALL",
    "emotion": "ALL",
    "sendWay": "ALL",
    "infoType": "2",
    "reloadFilterId": "0",
    "reloadId": "0",
    "warnFangshi": "ALL",
    "hasAlertTypes": "ALL",
    "allList": "true",
    "ruleId": "",
    "searchType": "precise",
    "moreStatus": "false",
    "source": "ALL",
    "fuzzyValueScope": "fullText",
    "fuzzyValue": "",
    "signal": "[object AbortSignal]",
}


@dataclass
class RequestContext:
    headers: Dict[str, str]
    cookies: Dict[str, str]


@dataclass
class SearchConfig:
    keyword: str
    time_range: str
    platform: str
    page_size: int = 50
    sort: str = "comments_desc"
    info_type: str = "2"
    page_id: str = ""


class NetInsightError(RuntimeError):
    """Raised when the NetInsight flow cannot continue safely."""


def login_and_capture(
    username: str,
    password: str,
    *,
    headless: bool = False,
    no_proxy: bool = False,
    login_timeout_ms: int = 90000,
    browser_channel: str = "",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> RequestContext:
    return asyncio.run(
        _login_and_capture_async(
            username=username,
            password=password,
            headless=headless,
            no_proxy=no_proxy,
            login_timeout_ms=login_timeout_ms,
            browser_channel=browser_channel,
            progress_callback=progress_callback,
        )
    )


async def _login_and_capture_async(
    *,
    username: str,
    password: str,
    headless: bool,
    no_proxy: bool,
    login_timeout_ms: int,
    browser_channel: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> RequestContext:
    def _step(msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    deadline = time.monotonic() + max(login_timeout_ms, 10000) / 1000.0
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover
        raise NetInsightError(
            "缺少 playwright 依赖，无法执行 NetInsight 登录。"
            "请安装 playwright，并准备 Chromium/Edge 浏览器。"
        ) from exc

    async with async_playwright() as playwright:
        launch_options: Dict[str, Any] = {"headless": headless}
        if no_proxy:
            launch_options["args"] = ["--no-proxy-server"]
        else:
            proxy_url = (
                os.getenv("HTTP_PROXY")
                or os.getenv("HTTPS_PROXY")
                or os.getenv("ALL_PROXY")
            )
            if proxy_url:
                launch_options["proxy"] = {"server": proxy_url}

        _step("正在启动浏览器…")
        browser = await _launch_browser(playwright, launch_options, browser_channel)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            _step("正在打开登录页面…")
            await page.goto(LOGIN_URL, wait_until="commit", timeout=_remaining_timeout_ms(deadline))
            await page.wait_for_timeout(1500)

            _step("正在等待登录表单…")
            login_form = await _wait_for_login_form(page, deadline)

            _step("正在填写账号密码…")
            account_input = login_form.locator(
                'input[placeholder="账号"], input[placeholder*="账号"], input[type="text"]'
            ).first
            await account_input.wait_for(state="visible", timeout=_remaining_timeout_ms(deadline))
            await account_input.fill(username)

            password_input = login_form.locator(
                'input[placeholder="密码"], input[placeholder*="密码"], input[type="password"]'
            ).first
            await password_input.wait_for(state="visible", timeout=_remaining_timeout_ms(deadline))
            await password_input.fill(password)

            _step("正在点击登录按钮…")
            login_button = login_form.locator('button.el-button--primary:has-text("登 录")').first
            if await login_button.count() == 0:
                login_button = login_form.locator('button.el-button--primary:has-text("登录")').first
            if await login_button.count() == 0:
                login_button = login_form.locator("button.el-button--primary").first
            await login_button.click()

            _step("正在等待登录跳转…")
            await page.wait_for_timeout(2500)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(18000, _remaining_timeout_ms(deadline)))
            except Exception:
                pass
            await page.wait_for_timeout(3500)

            _step("正在获取会话凭证…")
            cookies_list = await context.cookies()
            cookies = {cookie["name"]: cookie["value"] for cookie in cookies_list}
            session_id = cookies.get("TRSJSESSIONID")
            session_web = cookies.get("TRSJSESSIONIDWEB")
            if not session_id or not session_web:
                raise NetInsightError("登录后未获取到 NetInsight 必要的会话 Cookie。")

            return RequestContext(
                headers=_build_headers(session_web),
                cookies={
                    "TRSJSESSIONID": session_id,
                    "TRSJSESSIONIDWEB": session_web,
                },
            )
        finally:
            await browser.close()


async def _launch_browser(playwright: Any, launch_options: Dict[str, Any], browser_channel: str):
    candidates: List[Dict[str, Any]] = []
    if browser_channel:
        candidates.append({**launch_options, "channel": browser_channel})
    if os.name == "nt":
        candidates.append({**launch_options, "channel": "msedge"})
        candidates.append({**launch_options, "channel": "chrome"})
    candidates.append(dict(launch_options))

    last_error: Optional[Exception] = None
    for options in candidates:
        try:
            return await playwright.chromium.launch(**options)
        except Exception as exc:
            last_error = exc
            continue
    raise NetInsightError(
        "无法启动浏览器完成 NetInsight 登录。"
        "请确认已安装 Playwright 浏览器，或本机存在可用的 Edge/Chrome。"
    ) from last_error


async def _wait_for_login_form(page: Any, deadline: float):
    try:
        account_tab = page.locator('#tab-account, .el-tabs__item:has-text("账号登录")').first
        if await account_tab.count() > 0:
            await account_tab.click(timeout=3000)
    except Exception:
        pass

    await page.wait_for_function(
        """
        () => {
          const scope =
            document.querySelector('form.login-form') ||
            document.querySelector('#pane-account') ||
            document.body
          if (!scope) return false
          const account =
            scope.querySelector('input[placeholder="账号"]') ||
            scope.querySelector('input[placeholder*="账号"]') ||
            scope.querySelector('input[type="text"]')
          const password =
            scope.querySelector('input[placeholder="密码"]') ||
            scope.querySelector('input[placeholder*="密码"]') ||
            scope.querySelector('input[type="password"]')
          return Boolean(account && password)
        }
        """,
        timeout=_remaining_timeout_ms(deadline),
    )
    return page.locator("form.login-form, #pane-account").first


def _remaining_timeout_ms(deadline: float) -> int:
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise NetInsightError("NetInsight 登录超时，请检查网络或稍后重试。")
    return remaining


def query_platform_counts(
    *,
    keywords: Iterable[str],
    time_range: str,
    platform: str,
    threshold: int,
    context: RequestContext,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    keyword_counts: Dict[str, int] = {}
    warnings: List[str] = []
    words = [str(item).strip() for item in keywords if str(item).strip()]
    if not words:
        return {
            "platform": platform,
            "search_matrix": {},
            "raw_counts": {},
            "total_available": 0,
            "planned_total": 0,
            "warnings": ["关键词为空"],
        }

    for index, keyword in enumerate(words, start=1):
        try:
            count = _query_keyword_count(
                keyword=keyword,
                time_range=time_range,
                platform=platform,
                context=context,
            )
        except Exception as exc:
            count = 0
            warnings.append(f"关键词“{keyword}”计数失败: {str(exc)}")
        keyword_counts[keyword] = count
        if progress_callback:
            progress_callback(
                {
                    "platform": platform,
                    "keyword": keyword,
                    "count": count,
                    "index": index,
                    "total": len(words),
                }
            )

    search_matrix = _calculate_proportional_counts(keyword_counts, threshold)
    return {
        "platform": platform,
        "search_matrix": search_matrix,
        "raw_counts": keyword_counts,
        "total_available": sum(keyword_counts.values()),
        "planned_total": sum(search_matrix.values()),
        "warnings": warnings,
    }


def collect_platform_records(
    *,
    search_matrix: Dict[str, int],
    time_range: str,
    platform: str,
    context: RequestContext,
    page_size: int = 50,
    sort: str = "comments_desc",
    info_type: str = "2",
    task_id: str = "",
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    all_records: List[Dict[str, Any]] = []
    search_summary: Dict[str, Any] = {}
    keywords = [(str(keyword).strip(), int(count)) for keyword, count in (search_matrix or {}).items()]

    for keyword_index, (keyword, target_count) in enumerate(keywords, start=1):
        if not keyword or target_count <= 0:
            continue

        max_pages = max(1, (target_count + page_size - 1) // page_size)
        page_id = ""
        collected_for_keyword: List[Dict[str, Any]] = []
        no_data = False

        for page_no in range(max_pages):
            config = SearchConfig(
                keyword=keyword,
                time_range=time_range,
                platform=platform,
                page_size=page_size,
                sort=sort,
                info_type=info_type,
                page_id=page_id,
            )
            page_items, next_page_id, is_no_data = _fetch_page(config, context)
            if is_no_data:
                no_data = True
                break
            if not page_items:
                break

            for raw_item in page_items:
                collected_for_keyword.append(
                    normalize_record(raw_item, keyword=keyword, platform=platform, task_id=task_id)
                )
                if len(collected_for_keyword) >= target_count:
                    break

            page_id = next_page_id or page_id

            if progress_callback:
                progress_callback(
                    {
                        "platform": platform,
                        "keyword": keyword,
                        "keyword_index": keyword_index,
                        "keyword_total": len(keywords),
                        "page": page_no + 1,
                        "pages": max_pages,
                        "keyword_target": target_count,
                        "keyword_collected": len(collected_for_keyword),
                        "fetched_total": len(all_records) + len(collected_for_keyword),
                    }
                )

            if len(collected_for_keyword) >= target_count:
                break
            if len(page_items) < page_size:
                break
            time.sleep(0.8)

        search_summary[keyword] = {
            "target": target_count,
            "actual": len(collected_for_keyword),
            "status": "no_data" if no_data and not collected_for_keyword else "success" if collected_for_keyword else "failed",
        }
        all_records.extend(collected_for_keyword)

    return {
        "platform": platform,
        "records": all_records,
        "search_summary": search_summary,
    }


def deduplicate_records(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    removed = 0
    for record in records:
        content_key = str(record.get("内容") or "").strip()
        title_key = str(record.get("标题") or "").strip()
        url_key = str(record.get("URL") or "").strip()
        dedupe_key = content_key or f"{title_key}::{url_key}"
        if dedupe_key and dedupe_key in seen:
            removed += 1
            continue
        if dedupe_key:
            seen.add(dedupe_key)
        deduped.append(record)
    return deduped, removed


def normalize_record(raw_item: Dict[str, Any], *, keyword: str, platform: str, task_id: str) -> Dict[str, Any]:
    title = raw_item.get("title") or raw_item.get("copyTitle", "")
    content = raw_item.get("content") or raw_item.get("copyAbstracts", "") or raw_item.get("abstracts", "")
    return {
        "任务ID": task_id,
        "原始ID": raw_item.get("id", ""),
        "检索词": keyword,
        "平台": raw_item.get("channel") or raw_item.get("groupName") or platform,
        "标题": _strip_html(title),
        "内容": _strip_html(content),
        "作者": raw_item.get("author") or raw_item.get("screenName", ""),
        "发布时间": raw_item.get("timeBak") or raw_item.get("time", ""),
        "发布时间戳": raw_item.get("time", ""),
        "URL": raw_item.get("urlName", ""),
        "情感": raw_item.get("emotion") or raw_item.get("appraiseNew", ""),
        "评论数": _safe_int(raw_item.get("commentNum"), 0),
        "转发数": _safe_int(raw_item.get("shareNum"), 0),
        "点赞数": _safe_int(raw_item.get("prNum"), 0),
        "来源": raw_item.get("siteName") or raw_item.get("siteNameBak", ""),
        "IP属地": raw_item.get("ipLocation", ""),
        "命中关键词": _keyword_hits(raw_item, keyword),
        "行业类型": raw_item.get("industryType", ""),
    }


def _query_keyword_count(
    *,
    keyword: str,
    time_range: str,
    platform: str,
    context: RequestContext,
    max_retries: int = 3,
) -> int:
    payload = dict(BASE_COUNT_PARAMS)
    payload.update(
        {
            "keyWord": json.dumps(
                {
                    "wordSpace": None,
                    "wordOrder": False,
                    "keyWords": keyword,
                },
                ensure_ascii=False,
            ),
            "timeRange": time_range,
            "groupName": "ALL",
        }
    )

    session = _build_session(context)
    for attempt in range(1, max_retries + 1):
        try:
            response = session.post(COUNT_API_URL, data=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            code = int(result.get("code") or 0)
            if code == 515:
                raise NetInsightError("NetInsight 登录态已失效，请重新登录。")
            if code != 200:
                raise NetInsightError(
                    f"NetInsight 计数接口返回异常: code={result.get('code')} message={result.get('message') or ''}"
                )
            data = result.get("data", [])
            if not isinstance(data, list):
                raise NetInsightError("NetInsight 计数接口返回格式不正确。")
            total_all = 0
            matched = 0
            for item in data:
                if not isinstance(item, dict):
                    continue
                value = _safe_int(item.get("value"), 0)
                total_all += value
                if not platform or platform == "全部":
                    matched = total_all
                elif str(item.get("name") or "").strip() == platform:
                    matched = value
                    break
            return total_all if platform == "全部" else matched
        except requests.RequestException:
            if attempt >= max_retries:
                raise
            time.sleep(1.5)
    return 0


def _fetch_page(
    config: SearchConfig,
    context: RequestContext,
    *,
    max_retries: int = 3,
) -> Tuple[List[Dict[str, Any]], str, bool]:
    payload = _build_info_payload(config)
    session = _build_session(context)

    for attempt in range(1, max_retries + 1):
        try:
            response = session.post(INFO_LIST_API_URL, data=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            code = int(result.get("code") or 0)
            if code == 204:
                return [], "", True
            if code != 200:
                message = result.get("message") or "未知错误"
                if code == 515:
                    raise NetInsightError("NetInsight 登录态已失效，请重新登录。")
                raise NetInsightError(f"NetInsight 列表接口返回异常: code={code} message={message}")

            data = result.get("data") or {}
            content = data.get("content") or {}
            page_items = content.get("pageItems") or []
            page_id = str(data.get("pageId") or config.page_id or "")
            return [item for item in page_items if isinstance(item, dict)], page_id, False
        except requests.RequestException:
            if attempt >= max_retries:
                raise
            time.sleep(1.5)
    return [], "", False


def _build_info_payload(config: SearchConfig) -> Dict[str, str]:
    payload = dict(BASE_INFO_PARAMS)
    payload.update(
        {
            "keyWord": json.dumps(
                {
                    "wordSpace": None,
                    "wordOrder": False,
                    "keyWords": config.keyword,
                },
                ensure_ascii=False,
            ),
            "timeRange": config.time_range,
            "groupName": config.platform,
            "source": config.platform,
            "pageNo": "0" if not config.page_id else "1",
            "pageSize": str(config.page_size),
            "sort": _resolve_sort(config.sort),
            "infoType": str(config.info_type or "2"),
        }
    )
    if config.page_id:
        payload["pageId"] = config.page_id
    return payload


def _build_headers(authorization: str) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": authorization,
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://pro.netinsight.com.cn",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "signal": "[object AbortSignal]",
    }


def _build_session(context: RequestContext) -> requests.Session:
    session = requests.Session()
    session.headers.update(context.headers)
    session.cookies.update(context.cookies)
    if os.getenv("NETINSIGHT_NO_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}:
        session.trust_env = False
    return session


def _calculate_proportional_counts(keyword_counts: Dict[str, int], threshold: int) -> Dict[str, int]:
    total_count = sum(keyword_counts.values())
    if total_count <= 0:
        return {keyword: 0 for keyword in keyword_counts}
    if total_count <= threshold:
        return dict(keyword_counts)

    allocated: Dict[str, int] = {}
    fractions: List[Tuple[str, float]] = []
    allocated_total = 0
    for keyword, count in keyword_counts.items():
        ratio = (count / total_count) * threshold
        base = max(1, int(ratio))
        allocated[keyword] = base
        allocated_total += base
        fractions.append((keyword, ratio - int(ratio)))

    remaining = max(threshold - allocated_total, 0)
    fractions.sort(key=lambda item: item[1], reverse=True)
    for keyword, _ in fractions:
        if remaining <= 0:
            break
        allocated[keyword] += 1
        remaining -= 1
    return allocated


def allocate_platform_limits(platform_totals: Dict[str, int], threshold: int) -> Dict[str, int]:
    positive = {
        str(platform).strip(): _safe_int(total, 0)
        for platform, total in (platform_totals or {}).items()
        if str(platform).strip() and _safe_int(total, 0) > 0
    }
    if not positive:
        return {str(platform).strip(): 0 for platform in (platform_totals or {}) if str(platform).strip()}
    return _calculate_proportional_counts(positive, threshold)


def _resolve_sort(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"hot", "热门"}:
        return "hot"
    if text in {"comments_desc", "comment_desc", "-commtcount", "评论数"}:
        return "-commtCount"
    return "relevance"


def _strip_html(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def _keyword_hits(item: Dict[str, Any], fallback_keyword: str) -> str:
    hits = item.get("keyWordes")
    if isinstance(hits, list):
        cleaned = [str(value).strip() for value in hits if str(value).strip()]
        if cleaned:
            return ";".join(cleaned)
    hit_word = str(item.get("hitWord") or "").strip()
    return hit_word or fallback_keyword


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "NetInsightError",
    "RequestContext",
    "collect_platform_records",
    "deduplicate_records",
    "login_and_capture",
    "normalize_record",
    "allocate_platform_limits",
    "query_platform_counts",
]
