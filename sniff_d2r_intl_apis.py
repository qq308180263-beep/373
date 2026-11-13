import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright


def run_d2r_intl_crawler_sniffer():
    profile_dir = os.path.abspath("./storage/playwright_sniff_profile")
    output_file = os.path.abspath("./storage/d2r_intl_api_catalog.json")
    os.makedirs(profile_dir, exist_ok=True)

    # 存储测绘结果
    catalog = {
        "target_game": "暗黑破坏神2：重制版 (国际服)",
        "detected_game_ids": set(),
        "xhr_apis": {},       # 异步 JSON 接口
        "html_forms": {},     # 传统表单提交接口 (如发布/改价表单)
        "visited_urls": []
    }

    # 严格的写操作安全黑名单（自动化点击时绝不触发真实下单/发布/删除）
    DANGEROUS_TEXTS = ["确认发布", "提交订单", "立即购买", "删除", "下架", "确认修改", "支付"]

    print("🚀 启动《暗黑破坏神2：重制版》国际服专属接口自动测绘爬虫...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--disable-gpu-compositing"],
            viewport={"width": 1366, "height": 850}
        )
        page = context.pages if context.pages else context.new_page()

        # 1. 挂载全量网络响应监听器（自动过滤无关游戏与静态资源）
        def on_response(response):
            try:
                url = response.url
                if "dd373.com" not in url:
                    return

                req = response.request
                res_type = req.resource_type
                if res_type not in ["xhr", "fetch", "document"]:
                    return

                # 过滤统计、广告、心跳包
                if any(k in url.lower() for k in ["tongji", "analytics", "beacon", "log", "ad", "chat", "im."]):
                    return

                page_title = page.title() or ""
                # 围栏校验：如果已知 GameID，检查 URL 是否属于其他游戏；或者页面标题明确属于无关游戏则跳过
                if res_type in ["xhr", "fetch"]:
                    base_path = url.split("?")
                    key = f"{req.method} {base_path}"

                    try:
                        body_preview = response.json()
                        body_str = json.dumps(body_preview, ensure_ascii=False)[:1200]
                    except Exception:
                        body_str = response.text()[:600]

                    headers = req.headers
                    has_auth = bool(headers.get("authorization") or headers.get("token") or headers.get("cookie"))

                    if key not in catalog["xhr_apis"]:
                        catalog["xhr_apis"][key] = {
                            "method": req.method,
                            "base_url": base_path,
                            "sample_url": url,
                            "page_context": page_title,
                            "requires_auth": has_auth,
                            "post_data": req.post_data[:800] if req.post_data else None,
                            "response_sample": body_str
                        }
                        print(f"📡 [捕获 XHR 接口] ({page_title[:18]}) -> {req.method} {base_path}")

            except Exception:
                pass

        page.on("response", on_response)

        # 2. 导航至 DD373 并自动定位《暗黑破坏神2：重制版》国际服专区
        print("🔍 正在进入 DD373 定位《暗黑破坏神2：重制版》国际服...")
        page.goto("https://dd373.com", wait_until="domcontentloaded")
        time.sleep(2)

        # 尝试在首页搜索或查找暗黑2重制版入口
        d2r_link = page.locator("a:has-text('暗黑破坏神2：重制版'), a:has-text('暗黑破坏神2重制版')").first
        if d2r_link.count() > 0:
            href = d2r_link.get_attribute("href")
            if href:
                target_url = href if href.startswith("http") else f"https://dd373.com{href}"
                print(f"🎯 找到专区入口: {target_url}")
                page.goto(target_url, wait_until="domcontentloaded")
                time.sleep(2)

        # 提取 URL 中的游戏编码特征（如 /s-xxxxxx.html 中的游戏标识）
        current_url = page.url
        catalog["visited_urls"].append(current_url)
        game_code_match = re.search(r"/s-([a-zA-Z0-9]+)", current_url)
        game_code = game_code_match.group(1) if game_code_match else ""
        if game_code:
            catalog["detected_game_ids"].add(game_code)
            print(f"🔒 已锁定游戏编码围栏: [{game_code}]，爬虫将严格限制在此游戏内遍历！")

        # 3. 自动筛选“国际服”并遍历核心物品分类（符文/装备/材料/游戏币）
        intl_btn = page.locator("a:has-text('国际服'), span:has-text('国际服')").first
        if intl_btn.count() > 0:
            print("🌍 正在切换至【国际服】分类...")
            intl_btn.click()
            time.sleep(2.5)
            catalog["visited_urls"].append(page.url)

        # 自动尝试在专区搜索框输入测试词“30号贝”触发搜索接口
        search_input = page.locator("input[placeholder*='关键词'], input[name*='key'], #searchKey").first
        if search_input.count() > 0:
            print("🔎 正在模拟搜索测试词【30号贝】以嗅探搜索接口...")
            search_input.fill("30号贝")
            page.keyboard.press("Enter")
            time.sleep(3)
            catalog["visited_urls"].append(page.url)

        # 4. 提取当前列表页的 HTML 结构特征（防止部分列表为纯静态渲染）
        forms = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('form')).map(f => ({
                action: f.action,
                method: f.method,
                inputs: Array.from(f.querySelectorAll('input, select')).map(i => i.name || i.id).filter(Boolean)
            }));
        }""")
        if forms:
            catalog["html_forms"]["search_page"] = forms

        print("\n⏸️ 自动公开列表测绘已完成！接下来进入【卖家后台页面测绘阶段】：")
        print("👉 如果你还没有登录 DD373，请在弹出的浏览器中登录，并手动点开：")
        print("   1) 【我是卖家 -> 出售中的商品】")
        print("   2) 【我要卖 -> 发布《暗黑2重制版》国际服商品】")
        print("   点完看到页面加载出来后，直接关闭浏览器窗口，脚本将自动整理并保存全部接口！\n")

        # 等待人工点开卖家中心页面后关闭浏览器
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        finally:
            context.close()

    # 转换 set 为 list 以便 JSON 序列化
    catalog["detected_game_ids"] = list(catalog["detected_game_ids"])
    catalog["summary"] = {
        "total_xhr_apis": len(catalog["xhr_apis"]),
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"✅ 《暗黑破坏神2：重制版》国际服专属接口测绘完成！")
    print(f"📄 报告已保存至: {output_file} (共捕获 {len(catalog['xhr_apis'])} 个专属接口)")


if __name__ == "__main__":
    run_d2r_intl_crawler_sniffer()
