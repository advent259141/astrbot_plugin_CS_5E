import os
import asyncio
import random
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
import re

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('match_result')

# 用户代理列表，用于反爬虫
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
]

class MatchResultFetcher:
    """CS:GO 比赛结果查询类"""
    
    def __init__(self):
        """初始化查询器"""
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
            
        # 存储用户搜索结果和时间戳
        self.search_results = {}
        self.search_timestamps = {}
        self.result_timeout = 30  # 结果有效期（秒）
        
        # 存储比赛页面的browser和page，以便进行后续操作
        self.active_browsers = {}

    async def get_match_results(self) -> Dict[str, Any]:
        """获取比赛结果数据"""
        logger.info("开始获取比赛结果数据")
        
        try:
            # 导入playwright，确保已安装
            from playwright.async_api import async_playwright
            
            # 比赛结果数据
            match_results = []
            match_elements = []  # 存储匹配到的元素，用于后续点击
            
            # 配置浏览器启动参数
            browser_args = [
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
            logger.debug(f"浏览器启动参数: {browser_args}")
            
            # 重试机制
            max_retries = 3
            retry_delay = 2
            
            # 执行查询
            for attempt in range(max_retries):
                try:
                    logger.info(f"第 {attempt + 1}/{max_retries} 次尝试获取比赛结果数据")
                    
                    async with async_playwright() as p:
                        # 随机选择一个用户代理
                        user_agent = random.choice(USER_AGENTS)
                        logger.debug(f"使用的User-Agent: {user_agent}")
                        
                        logger.debug("启动浏览器...")
                        browser = await p.chromium.launch(
                            headless=True,
                            args=browser_args
                        )
                        
                        logger.debug("创建浏览器上下文...")
                        context = await browser.new_context(
                            viewport={'width': 1280, 'height': 900},
                            user_agent=user_agent,
                            ignore_https_errors=True,
                            accept_downloads=True,
                            java_script_enabled=True,
                            bypass_csp=True,
                            extra_http_headers={
                                'Accept': '*/*',
                                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                                'Accept-Encoding': 'gzip, deflate, br',
                                'Connection': 'keep-alive',
                            }
                        )
                        
                        logger.debug("创建新页面...")
                        page = await context.new_page()
                        
                        # 添加反爬虫脚本
                        logger.debug("添加反爬虫脚本...")
                        await page.add_init_script("""
                            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                            window.localStorage.setItem('CookieConsent', JSON.stringify({
                                accepted: true,
                                necessary: true,
                                preferences: true,
                                statistics: true,
                                marketing: true
                            }));
                        """)
                        
                        # 设置超时
                        page.set_default_timeout(60000)
                        
                        # 访问页面
                        url = "https://event.5eplay.com/csgo/matches"
                        logger.info(f"第 {attempt + 1} 次尝试访问URL: {url}")
                        
                        # 延迟
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                        logger.debug(f"延迟后开始导航...")
                        
                        response = await page.goto(url, wait_until="domcontentloaded")
                        
                        # 检查响应
                        if response:
                            logger.info(f"页面响应状态码: {response.status}")
                            
                            if response.status == 200:
                                # 等待页面加载
                                logger.debug("等待页面加载完成...")
                                await page.wait_for_load_state("networkidle")
                                await asyncio.sleep(random.uniform(1.0, 2.0))
                                
                                # 查找赛果按钮
                                logger.debug("查找赛果按钮...")
                                result_btn = await page.query_selector('span.trigger-item:text("赛果")')
                                if result_btn:
                                    logger.debug("找到赛果按钮，点击...")
                                    # 点击赛果按钮
                                    await result_btn.click()
                                    
                                    # 等待页面加载
                                    logger.debug("等待赛果页面加载...")
                                    await asyncio.sleep(2.0)  # 给页面足够的时间加载
                                    await page.wait_for_load_state("networkidle")
                                    
                                    # 查找比赛结果项
                                    logger.debug("查找比赛结果元素...")
                                    match_items = await page.query_selector_all('div.match-item-row.cp')
                                    
                                    if match_items and len(match_items) > 0:
                                        logger.info(f"找到 {len(match_items)} 个比赛结果")
                                        
                                        # 限制最多显示5场比赛结果
                                        match_count = min(len(match_items), 5)
                                        logger.debug(f"将提取前 {match_count} 场比赛结果")
                                        
                                        for i in range(match_count):
                                            match_item = match_items[i]
                                            
                                            # 修复evaluate调用，将参数合并到JavaScript函数中
                                            js_function = """(element) => {
                                                const index = %d;
                                                return {
                                                    index: index,
                                                    selector: `div.match-item-row.cp:nth-of-type(${index + 1})`
                                                };
                                            }""" % (i + 1)
                                            match_element_info = await page.evaluate(js_function, match_item)
                                            match_elements.append(match_element_info)
                                            
                                            # 查找内部的比赛信息元素
                                            left_item = await match_item.query_selector('div.match-item.match-item-left.flex-horizontal.flex-align-center')
                                            
                                            try:
                                                # 获取比赛时间
                                                time_element = await left_item.query_selector('div.match-time-star div')
                                                match_time = await time_element.inner_text() if time_element else "未知时间"
                                                logger.debug(f"比赛时间: {match_time}")
                                                
                                                # 获取队伍名称
                                                team_elements = await left_item.query_selector_all('div.match-team.flex-vertical.flex-align-center div.cp p.ellip')
                                                team_names = []
                                                for team_element in team_elements:
                                                    team_name = await team_element.inner_text()
                                                    team_names.append(team_name)
                                                
                                                if len(team_names) >= 2:
                                                    team1_name = team_names[0]
                                                    team2_name = team_names[1]
                                                    logger.debug(f"队伍名称: {team1_name} vs {team2_name}")
                                                else:
                                                    team1_name = "未知队伍1"
                                                    team2_name = "未知队伍2"
                                                    logger.warning(f"未能获取完整队伍名称")
                                                
                                                # 获取比分
                                                score_elements = await left_item.query_selector_all('div.all-score-box div.all-score div')
                                                scores = []
                                                for score_element in score_elements:
                                                    score_text = await score_element.inner_text()
                                                    scores.append(score_text)
                                                
                                                if len(scores) >= 2:
                                                    team1_score = scores[0]
                                                    team2_score = scores[1]
                                                    logger.debug(f"比分: {team1_score}-{team2_score}")
                                                else:
                                                    team1_score = "?"
                                                    team2_score = "?"
                                                    logger.warning(f"未能获取完整比分")
                                                
                                                # 添加到结果列表，包含索引信息
                                                match_results.append({
                                                    'index': i + 1,
                                                    'time': match_time,
                                                    'team1': team1_name,
                                                    'team2': team2_name,
                                                    'score1': team1_score,
                                                    'score2': team2_score,
                                                    'selector': match_element_info['selector']
                                                })
                                                
                                            except Exception as e:
                                                logger.error(f"解析比赛 {i+1} 数据时出错: {str(e)}")
                                        
                                        # 比赛数据获取成功 - 不要关闭浏览器，存起来以便后续使用
                                        if match_results:
                                            logger.info(f"成功获取 {len(match_results)} 场比赛结果，保持浏览器会话")
                                            
                                            # 生成唯一的会话ID
                                            session_id = f"session_{time.time()}"
                                            
                                            # 存储浏览器和页面以备后续使用
                                            self.active_browsers[session_id] = {
                                                'browser': browser,
                                                'context': context,
                                                'page': page,
                                                'results': match_results,
                                                'elements': match_elements,
                                                'timestamp': time.time()
                                            }
                                            
                                            # 计划30秒后关闭浏览器
                                            asyncio.create_task(self.close_browser_after_timeout(session_id, 30))
                                            
                                            return {
                                                "success": True,
                                                "message": "获取比赛结果成功",
                                                "results": match_results,
                                                "session_id": session_id
                                            }
                                    else:
                                        logger.warning("未找到比赛结果元素")
                                else:
                                    logger.warning("未找到赛果按钮")
                            else:
                                logger.warning(f"页面返回非200状态码: {response.status}")
                        else:
                            logger.warning("没有收到页面响应")
                        
                        # 关闭浏览器
                        logger.debug("关闭浏览器...")
                        await browser.close()
                        
                        # 如果失败且不是最后一次尝试，则等待后重试
                        if attempt < max_retries - 1:
                            retry_time = retry_delay * (attempt + 1)
                            logger.warning(f"第 {attempt + 1} 次尝试失败，等待 {retry_time} 秒后重试")
                            await asyncio.sleep(retry_time)
                    
                except Exception as e:
                    logger.error(f"第 {attempt + 1} 次尝试出错: {str(e)}", exc_info=True)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
            
            # 如果所有尝试都失败
            logger.error("获取比赛结果数据失败，已达到最大尝试次数")
            return {
                "success": False,
                "message": "获取比赛结果数据失败，请稍后重试",
                "results": []
            }
            
        except ImportError:
            logger.error("未安装playwright，请使用pip install playwright安装")
            return {
                "success": False,
                "message": "未安装必要的库，请联系管理员",
                "results": []
            }
        except Exception as e:
            logger.error(f"获取比赛结果时出错: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取比赛结果时出错: {str(e)}",
                "results": []
            }
    
    async def close_browser_after_timeout(self, session_id: str, timeout: int):
        """在指定超时后关闭浏览器"""
        try:
            await asyncio.sleep(timeout)
            if session_id in self.active_browsers:
                logger.info(f"会话 {session_id} 超时，关闭浏览器")
                try:
                    await self.active_browsers[session_id]['browser'].close()
                except Exception as e:
                    logger.error(f"关闭浏览器时出错: {str(e)}")
                finally:
                    # 清理会话数据
                    del self.active_browsers[session_id]
                    
                    # 清理所有引用此会话的用户记录
                    users_to_clear = []
                    for user, sess_id in self.search_results.items():
                        if sess_id == session_id:
                            users_to_clear.append(user)
                    
                    # 从字典中删除引用
                    for user in users_to_clear:
                        if user in self.search_results:
                            logger.info(f"清理用户 {user} 的过期会话引用")
                            del self.search_results[user]
                        if user in self.search_timestamps:
                            del self.search_timestamps[user]
        except Exception as e:
            logger.error(f"关闭浏览器任务出错: {str(e)}")

    async def view_match_details(self, session_id: str, match_index: int) -> Dict[str, Any]:
        """查看指定比赛的详细信息"""
        logger.info(f"查看会话 {session_id} 的比赛 #{match_index} 详细信息")
        
        if session_id not in self.active_browsers:
            return {
                "success": False,
                "message": "会话已过期，请重新获取比赛结果",
                "type": "match_detail_expired"
            }
        
        session_data = self.active_browsers[session_id]
        results = session_data['results']
        
        # 检查索引是否有效
        if match_index < 1 or match_index > len(results):
            return {
                "success": False,
                "message": f"索引超出范围，请输入1到{len(results)}之间的数字",
                "type": "match_detail_invalid_index"
            }
        
        try:
            # 找到对应的比赛数据
            match_data = None
            for match in results:
                if match['index'] == match_index:
                    match_data = match
                    break
            
            if not match_data:
                return {
                    "success": False,
                    "message": f"未找到索引为 {match_index} 的比赛数据",
                    "type": "match_detail_not_found"
                }
            
            # 重新打开新的浏览器会话，而不是尝试重用可能不稳定的会话
            logger.info("为获取比赛详情创建全新的浏览器会话")
            
            # 提取我们需要的数据
            team1_name = match_data['team1']
            team2_name = match_data['team2']
            score1 = match_data['score1']
            score2 = match_data['score2']
            match_time = match_data['time']
            
            # 创建新的浏览器实例
            from playwright.async_api import async_playwright
            
            # 配置浏览器启动参数
            browser_args = [
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
            
            screenshot_path = os.path.join(self.screenshot_dir, f"match_detail_{match_index}_{int(time.time())}.png")
            
            async with async_playwright() as p:
                # 随机选择一个用户代理
                user_agent = random.choice(USER_AGENTS)
                
                logger.debug("启动新的浏览器...")
                browser = await p.chromium.launch(
                    headless=True,
                    args=browser_args
                )
                
                logger.debug("创建浏览器上下文...")
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 900},
                    user_agent=user_agent,
                    ignore_https_errors=True,
                    accept_downloads=True,
                    java_script_enabled=True,
                    bypass_csp=True
                )
                
                logger.debug("创建新页面...")
                page = await context.new_page()
                
                # 添加反爬虫脚本
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.localStorage.setItem('CookieConsent', JSON.stringify({
                        accepted: true, necessary: true, preferences: true, statistics: true, marketing: true
                    }));
                """)
                
                # 设置超时
                page.set_default_timeout(60000)
                
                # 直接访问比赛结果页面
                url = "https://event.5eplay.com/csgo/matches"
                logger.info(f"访问URL: {url}")
                
                # 延迟
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
                response = await page.goto(url, wait_until="domcontentloaded")
                
                if not response or response.status != 200:
                    logger.error(f"页面响应错误，状态码: {response.status if response else 'none'}")
                    await browser.close()
                    return {
                        "success": False,
                        "message": "无法访问比赛页面，请稍后再试",
                        "type": "match_detail_page_error"
                    }
                
                # 等待页面加载
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1.5)
                
                # 查找赛果按钮
                logger.debug("查找赛果按钮...")
                result_btn = await page.query_selector('span.trigger-item:text("赛果")')
                if not result_btn:
                    logger.error("未找到赛果按钮")
                    await browser.close()
                    return {
                        "success": False,
                        "message": "无法找到赛果按钮，请稍后再试",
                        "type": "match_detail_button_not_found"
                    }
                
                # 点击赛果按钮
                await result_btn.click()
                logger.debug("已点击赛果按钮")
                
                # 等待加载
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(1.5)
                
                # 找到相似的比赛 - 通过队伍名称匹配
                found_match = False
                match_items = await page.query_selector_all('div.match-item-row.cp')
                
                logger.info(f"找到 {len(match_items)} 个比赛条目，尝试匹配 {team1_name} vs {team2_name}")
                
                # 遍历匹配比赛
                for match_item in match_items:
                    try:
                        # 查找内部的比赛信息元素
                        left_item = await match_item.query_selector('div.match-item.match-item-left.flex-horizontal.flex-align-center')
                        if not left_item:
                            continue
                            
                        # 获取队伍名称
                        team_elements = await left_item.query_selector_all('div.match-team.flex-vertical.flex-align-center div.cp p.ellip')
                        
                        # 如果找不到两个队伍，则跳过
                        if len(team_elements) < 2:
                            continue
                            
                        item_team1 = await team_elements[0].inner_text()
                        item_team2 = await team_elements[1].inner_text()
                        
                        logger.debug(f"比较: {item_team1} vs {item_team2} 与 {team1_name} vs {team2_name}")
                        
                        # 检查是否匹配
                        if (item_team1 == team1_name and item_team2 == team2_name) or \
                           (item_team1 == team2_name and item_team2 == team1_name):
                            logger.info(f"找到匹配比赛: {item_team1} vs {item_team2}")
                            
                            # 点击这个比赛
                            found_match = True
                            await match_item.click()
                            logger.debug("已点击匹配的比赛")
                            
                            # 等待页面导航完成
                            await page.wait_for_load_state("networkidle")
                            await asyncio.sleep(2)
                            break
                            
                    except Exception as e:
                        logger.warning(f"处理比赛条目时出错: {str(e)}")
                        continue
                
                if not found_match:
                    logger.warning(f"未找到匹配的比赛: {team1_name} vs {team2_name}")
                    await browser.close()
                    return {
                        "success": False,
                        "message": f"未在当前页面找到 {team1_name} vs {team2_name} 的比赛",
                        "type": "match_detail_not_found"
                    }
                
                # 隐藏页面右侧边栏、顶部和页脚元素
                logger.debug("隐藏页面不需要的元素")
                await page.evaluate("""
                    // 隐藏右侧边栏
                    const rightAsideBox = document.querySelector('div.right-aside-box');
                    if (rightAsideBox) rightAsideBox.style.display = 'none';
                    
                    // 隐藏页面顶部元素
                    const headerElements = document.querySelectorAll('.header-box, .sub-header');
                    for (let el of headerElements) {
                        if (el) el.style.display = 'none';
                    }
                    
                    // 隐藏其他可能影响显示的元素
                    const otherElements = document.querySelectorAll('.fixed-header, .nav');
                    for (let el of otherElements) {
                        if (el) el.style.display = 'none';
                    }
                    
                    // 隐藏底部页脚元素
                    const footerElements = document.querySelectorAll('footer.mini-footer');
                    for (let el of footerElements) {
                        if (el) el.style.display = 'none';
                    }
                """)
                
                # 等待样式应用
                await asyncio.sleep(1)
                
                # 查找并截图主要内容区域
                logger.debug("查找主要内容区域")
                
                # 尝试找出所有可能包含比赛详情的元素并记录
                logger.info("尝试查找所有可能的比赛详情元素")
                
                # 检查主要内容元素
                content_element = await page.query_selector('div.free-main-loading.free-main-loading-box')
                if content_element:
                    logger.info("✓ 找到主要内容元素: div.free-main-loading.free-main-loading-box")
                    bbox = await content_element.bounding_box()
                    if bbox:
                        logger.info(f"  - 元素大小: 宽度={bbox['width']}px, 高度={bbox['height']}px")
                        logger.info(f"  - 元素位置: x={bbox['x']}, y={bbox['y']}")
                else:
                    logger.warning("✗ 未找到主要内容元素: div.free-main-loading.free-main-loading-box")
                
                # 检查其他可能的元素
                match_info_element = await page.query_selector('div.match-info')
                if match_info_element:
                    logger.info("✓ 找到比赛信息元素: div.match-info")
                    match_info_html = await page.evaluate("element => element.outerHTML", match_info_element)
                    logger.debug(f"比赛信息元素HTML结构 (截取前100字符): {match_info_html[:100]}...")
                else:
                    logger.warning("✗ 未找到比赛信息元素: div.match-info")
                    
                # 检查比赛详情元素
                match_detail = await page.query_selector('div.match-detail')
                if match_detail:
                    logger.info("✓ 找到比赛详情元素: div.match-detail")
                    match_detail_html = await page.evaluate("element => element.outerHTML", match_detail)
                    logger.debug(f"比赛详情元素HTML结构 (截取前100字符): {match_detail_html[:100]}...")
                else:
                    logger.warning("✗ 未找到比赛详情元素: div.match-detail")
                
                # 检查主体内容区域
                main_content = await page.query_selector('main.main-content')
                if main_content:
                    logger.info("✓ 找到主体内容区域: main.main-content")
                else:
                    logger.warning("✗ 未找到主体内容区域: main.main-content")
                
                # 尝试截图页面上所有可见元素
                visible_elements = await page.evaluate("""() => {
                    const elements = [];
                    const visibleElements = document.querySelectorAll('div[class*="main"], div[class*="content"], div[class*="match"]');
                    for (const el of visibleElements) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 50 && rect.height > 50) {
                            elements.push({
                                selector: el.tagName + (el.id ? '#' + el.id : '') + 
                                          (el.className ? '.' + el.className.replace(/ /g, '.') : ''),
                                width: rect.width,
                                height: rect.height,
                                visible: rect.top < window.innerHeight && rect.bottom > 0 && 
                                         rect.left < window.innerWidth && rect.right > 0
                            });
                        }
                    }
                    return elements;
                }""")
                
                logger.info(f"页面上找到 {len(visible_elements)} 个潜在可见元素")
                for i, el in enumerate(visible_elements[:5]):  # 限制只显示前5个，避免日志过长
                    logger.info(f"  #{i+1}: {el['selector']} (宽度: {el['width']}px, 高度: {el['height']}px, 可见: {el['visible']})")
                
                if not content_element:
                    # 如果没有找到指定元素，尝试截取整个页面内容区域
                    logger.warning("未找到指定内容元素，尝试截取main元素")
                    content_element = await page.query_selector('main') or await page.query_selector('body')
                    if content_element:
                        element_type = "main" if await page.evaluate("element => element.tagName", content_element) == "MAIN" else "body"
                        logger.info(f"✓ 将使用 {element_type} 元素作为备选截图目标")
                    else:
                        logger.error("✗ 没有找到任何可用的内容元素！")
                
                # 截图
                if content_element:
                    # 在截图之前先等待一秒，确保页面完全渲染
                    await asyncio.sleep(1)
                    
                    # 截图前记录页面宽高
                    viewport_size = await page.evaluate("""() => {
                        return {
                            width: window.innerWidth,
                            height: window.innerHeight,
                            docWidth: document.documentElement.scrollWidth,
                            docHeight: document.documentElement.scrollHeight
                        };
                    }""")
                    logger.info(f"页面尺寸: 视口={viewport_size['width']}x{viewport_size['height']}, 文档={viewport_size['docWidth']}x{viewport_size['docHeight']}")
                    
                    # 截图
                    await content_element.screenshot(path=screenshot_path)
                    
                    # 验证截图
                    if os.path.exists(screenshot_path):
                        file_size = os.path.getsize(screenshot_path)
                        logger.info(f"✓ 成功截图比赛详情到 {screenshot_path} (文件大小: {file_size} 字节)")
                        
                        # 判断截图是否有效（大于1KB）
                        if file_size > 1024:
                            logger.info("✓ 截图文件大小合理，应该包含有效内容")
                        else:
                            logger.warning(f"! 截图文件过小 ({file_size} 字节)，可能是空白页面或截图失败")
                    else:
                        logger.error(f"✗ 截图文件不存在: {screenshot_path}")
                    
                    # 关闭浏览器
                    await browser.close()
                    
                    # 验证截图是否成功
                    if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                        return {
                            "success": True,
                            "message": f"已获取比赛 {team1_name} vs {team2_name} 的详细信息",
                            "type": "match_detail",
                            "image_path": screenshot_path,
                            "match_info": {
                                "team1": team1_name,
                                "team2": team2_name,
                                "score1": score1,
                                "score2": score2,
                                "time": match_time
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "message": "截图失败或文件大小为零",
                            "type": "match_detail_screenshot_failed"
                        }
                else:
                    await browser.close()
                    return {
                        "success": False,
                        "message": "未找到可截图的内容元素",
                        "type": "match_detail_content_not_found"
                    }
                    
        except Exception as e:
            logger.error(f"查看比赛详情时出错: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"处理请求时出错: {str(e)}",
                "type": "match_detail_error"
            }

    def format_results(self, results: List[Dict[str, str]]) -> str:
        """格式化比赛结果为易读的文本"""
        if not results:
            return "没有找到最近的比赛结果"
        
        formatted = "📊 最近的CS:GO比赛结果:\n" + "═" * 35 + "\n\n"
        
        for i, match in enumerate(results, 1):
            index = match.get('index', i)  # 使用保存的索引或默认为循环索引
            formatted += f"#{index} ⏰ {match['time']}\n"
            formatted += f"🏆 {match['team1']} {match['score1']} : {match['score2']} {match['team2']}\n"
            if i < len(results):
                formatted += "\n" + "─" * 30 + "\n\n"
        
        # 添加使用说明
        formatted += "\n📌 在30秒内发送 '比赛[数字]' 查看对应比赛的详细信息，例如：比赛1"
        
        return formatted
    
    async def process_command(self, command: str, user_id: str = "default_user") -> Dict[str, Any]:
        """处理比赛结果命令"""
        command = command.strip()
        
        # 增加调试日志以追踪用户ID
        logger.info(f"处理命令 '{command}' 来自用户ID: {user_id}")
        
        # 处理"比赛结果"命令
        if command in ["比赛结果", "/比赛结果"]:
            try:
                # 记录当前所有会话状态
                logger.debug(f"当前活跃浏览器会话: {list(self.active_browsers.keys())}")
                logger.debug(f"当前用户会话映射: {self.search_results}")
                
                # 获取比赛结果数据
                logger.info("开始获取比赛结果数据")
                
                # 如果用户已经有一个活跃会话，先检查其有效性
                if user_id in self.search_results:
                    session_id = self.search_results[user_id]
                    if session_id in self.active_browsers:
                        try:
                            browser = self.active_browsers[session_id]['browser']
                            page = self.active_browsers[session_id]['page']
                            
                            # 检查浏览器连接和页面是否打开
                            if browser.is_connected() and not page.is_closed():
                                # 延长这个会话的生命周期
                                logger.info(f"用户 {user_id} 已有活跃会话 {session_id}，延长其有效期")
                                self.search_timestamps[user_id] = time.time()
                                
                                # 重新格式化已有的结果
                                existing_results = self.active_browsers[session_id]['results']
                                formatted_results = self.format_results(existing_results)
                                
                                return {
                                    "success": True,
                                    "message": formatted_results,
                                    "type": "match_results",
                                    "session_id": session_id
                                }
                        except Exception as e:
                            logger.warning(f"检查现有会话时出错: {str(e)}")
                            # 继续创建新会话
                
                # 获取新的比赛结果
                results = await self.get_match_results()
                
                if results["success"]:
                    # 保存会话ID和用户关联
                    session_id = results["session_id"]
                    self.search_results[user_id] = session_id
                    self.search_timestamps[user_id] = time.time()
                    
                    # 记录会话存储情况以便调试
                    logger.info(f"已保存用户 {user_id} 的会话ID: {session_id}, 当前用户会话数: {len(self.search_results)}")
                    
                    # 格式化结果
                    formatted_results = self.format_results(results["results"])
                    logger.info("成功格式化比赛结果")
                    
                    return {
                        "success": True,
                        "message": formatted_results,
                        "type": "match_results",
                        "session_id": session_id
                    }
                else:
                    logger.error("未能获取比赛结果")
                    return {
                        "success": False,
                        "message": results["message"],
                        "type": "match_results"
                    }
            except Exception as e:
                logger.error(f"处理比赛结果命令时出错: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"处理命令时出错: {str(e)}",
                    "type": "match_results"
                }
        
        # 处理"比赛[数字]"命令
        match_command = re.match(r"^比赛(\d+)$", command)
        if match_command:
            try:
                match_index = int(match_command.group(1))
                
                # 记录查询的会话情况
                logger.info(f"用户 {user_id} 请求查看比赛 #{match_index}")
                logger.info(f"当前存储的会话用户IDs: {list(self.search_results.keys())}")
                logger.info(f"当前用户会话ID映射: {self.search_results}")
                
                # 检查用户是否有活跃的会话
                if user_id not in self.search_results or user_id not in self.search_timestamps:
                    logger.warning(f"用户 {user_id} 没有活跃会话")
                    
                    # 尝试查看是否有可用的浏览器会话，如果有则为此用户创建
                    if self.active_browsers:
                        # 找到最新的会话
                        newest_session_id = sorted(
                            self.active_browsers.keys(),
                            key=lambda sid: self.active_browsers[sid]['timestamp'],
                            reverse=True
                        )[0]
                        
                        logger.info(f"为用户 {user_id} 分配现有会话: {newest_session_id}")
                        self.search_results[user_id] = newest_session_id
                        self.search_timestamps[user_id] = time.time()
                        
                        # 继续处理请求...
                    else:
                        return {
                            "success": False,
                            "message": "请先使用'比赛结果'命令查询最近的比赛",
                            "type": "match_detail_no_session"
                        }
                
                # 检查会话是否过期
                elapsed = time.time() - self.search_timestamps[user_id]
                if elapsed > self.result_timeout:
                    # 清理过期数据
                    if user_id in self.search_results:
                        del self.search_results[user_id]
                    if user_id in self.search_timestamps:
                        del self.search_timestamps[user_id]
                    
                    return {
                        "success": False,
                        "message": "会话已过期，请重新使用'比赛结果'命令",
                        "type": "match_detail_expired"
                    }
                
                # 获取会话ID
                session_id = self.search_results[user_id]
                
                # 查看详细比赛信息
                return await self.view_match_details(session_id, match_index)
                
            except ValueError:
                return {
                    "success": False,
                    "message": "请输入有效的比赛编号",
                    "type": "match_detail_invalid_input"
                }
            except Exception as e:
                logger.error(f"处理比赛详情命令时出错: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"处理请求时出错: {str(e)}",
                    "type": "match_detail_error"
                }
        
        # 其他命令
        return {
            "success": False,
            "message": "未知命令，请使用 '比赛结果' 命令查询最近的比赛结果，或使用 '比赛[数字]' 查看详细信息",
            "type": "unknown"
        }

# 创建全局实例，以便可以被导入
match_result_fetcher = MatchResultFetcher()

# 导出API函数
async def get_match_results() -> Dict[str, Any]:
    """获取比赛结果API"""
    return await match_result_fetcher.get_match_results()

async def process_command(command: str, user_id: str = "default_user") -> Dict[str, Any]:
    """处理命令API"""
    return await match_result_fetcher.process_command(command, user_id)

# 在导入时检查playwright是否已安装
try:
    import playwright
    logger.info(f"Playwright版本: {getattr(playwright, '__version__', 'unknown')}")
except ImportError as e:
    logger.error(f"未找到必要的库: {str(e)}，请使用pip install playwright安装")
except Exception as e:
    logger.error(f"初始化时出错: {str(e)}")

# 检查screenshots目录是否存在，如果不存在则创建
if not os.path.exists(os.path.join(os.path.dirname(__file__), "screenshots")):
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), "screenshots"), exist_ok=True)
        logger.info("已创建screenshots目录")
    except Exception as e:
        logger.error(f"创建screenshots目录时出错: {str(e)}")
