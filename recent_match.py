import os
import asyncio
import random
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image
import io

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('recent_match')

# 用户代理列表，用于反爬虫
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
]

class RecentMatchFetcher:
    """CS:GO 最近比赛查询类"""
    
    def __init__(self):
        """初始化查询器"""
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
    
    async def get_recent_matches(self) -> Optional[str]:
        """获取最近比赛数据并截图"""
        logger.info("开始获取最近比赛数据")
        
        try:
            # 导入playwright，确保已安装
            from playwright.async_api import async_playwright
            
            # 生成截图文件路径
            screenshot_path = os.path.join(self.screenshot_dir, f"recent_matches_{int(time.time())}.png")
            logger.debug(f"最终截图保存路径: {screenshot_path}")
            
            # 临时截图存储
            temp_screenshots = []
            
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
            
            # 执行截图
            for attempt in range(max_retries):
                try:
                    logger.info(f"第 {attempt + 1}/{max_retries} 次尝试获取比赛数据")
                    
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
                                
                                # 隐藏页面顶部元素
                                logger.debug("隐藏顶部元素...")
                                await page.evaluate("""
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
                                logger.debug("页面顶部和底部元素已隐藏")
                                
                                # 强制等待一下，确保样式应用
                                await asyncio.sleep(0.5)
                                
                                # 查找所有的比赛元素
                                logger.debug("查找比赛元素...")
                                
                                # 首先查找第一个日期标题
                                first_title = await page.query_selector('.match-time-title')
                                if first_title:
                                    logger.debug("找到第一个日期标题")
                                    # 截图第一个日期标题
                                    first_title_path = os.path.join(self.screenshot_dir, f"title_0_{int(time.time())}.png")
                                    await first_title.screenshot(path=first_title_path)
                                    temp_screenshots.append(first_title_path)
                                else:
                                    logger.warning("未找到日期标题")
                                    
                                # 查找所有的比赛行
                                match_items = await page.query_selector_all('.match-item-row.cp')
                                if match_items and len(match_items) > 0:
                                    logger.info(f"找到 {len(match_items)} 个比赛条目")
                                    
                                    # 限制最多显示10场比赛
                                    match_count = min(len(match_items), 10)
                                    logger.debug(f"将显示前 {match_count} 场比赛")
                                    
                                    for i in range(match_count):
                                        # 获取当前比赛元素
                                        match_item = match_items[i]
                                        
                                        # 先检查此比赛前是否有日期标题
                                        # 获取前一个元素，检查是否是日期标题
                                        if i > 0:  # 第一个比赛前的日期标题已经单独处理了
                                            # 使用JavaScript检查前一个元素是否是日期标题
                                            is_title_before = await page.evaluate("""
                                                (element) => {
                                                    const prevElement = element.previousElementSibling;
                                                    return prevElement && prevElement.classList.contains('match-time-title');
                                                }
                                            """, match_item)
                                            
                                            if is_title_before:
                                                logger.debug(f"比赛 {i+1} 前有日期标题")
                                                # 获取并截图日期标题
                                                date_title = await page.evaluate("""
                                                    (element) => {
                                                        return element.previousElementSibling;
                                                    }
                                                """, match_item)
                                                
                                                if date_title:
                                                    title_path = os.path.join(self.screenshot_dir, f"title_{i+1}_{int(time.time())}.png")
                                                    # 错误处理: 移除下面的evaluate调用，因为参数太多
                                                    # await page.evaluate("""
                                                    #     (element, path) => {
                                                    #         const rect = element.getBoundingClientRect();
                                                    #         // 这里我们可以做一些额外的处理，比如滚动到元素位置
                                                    #     }
                                                    # """, date_title, title_path)
                                                    
                                                    # 截图日期标题
                                                    date_title_element = await page.query_selector(f".match-time-title:nth-of-type({i+1})")
                                                    if date_title_element:
                                                        await date_title_element.screenshot(path=title_path)
                                                        temp_screenshots.append(title_path)
                                        
                                        # 截图比赛条目
                                        match_path = os.path.join(self.screenshot_dir, f"match_{i}_{int(time.time())}.png")
                                        await match_item.screenshot(path=match_path)
                                        temp_screenshots.append(match_path)
                                        
                                    # 处理完所有元素后，合并图片
                                    logger.info("开始合并截图...")
                                    if temp_screenshots:
                                        # 打开所有图片
                                        images = [Image.open(img_path) for img_path in temp_screenshots]
                                        
                                        # 计算合并后图片的总高度和最大宽度
                                        total_height = sum(img.height for img in images)
                                        max_width = max(img.width for img in images)
                                        
                                        # 创建新图片
                                        merged_image = Image.new('RGB', (max_width, total_height), color=(255, 255, 255))
                                        
                                        # 合并图片
                                        y_offset = 0
                                        for img in images:
                                            merged_image.paste(img, (0, y_offset))
                                            y_offset += img.height
                                            img.close()  # 关闭图片以释放资源
                                        
                                        # 保存合并后的图片
                                        merged_image.save(screenshot_path)
                                        merged_image.close()
                                        
                                        # 删除临时截图
                                        for img_path in temp_screenshots:
                                            try:
                                                os.remove(img_path)
                                            except Exception as e:
                                                logger.error(f"删除临时截图出错: {str(e)}")
                                        
                                        logger.info(f"成功合并截图到 {screenshot_path}")
                                        return screenshot_path
                                    else:
                                        logger.warning("没有可合并的截图")
                                else:
                                    logger.warning("未找到任何比赛条目")
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
            
            logger.error("获取比赛数据失败，已达到最大尝试次数")
            return None
            
        except ImportError:
            logger.error("未安装playwright或PIL，请使用pip install playwright pillow安装")
            return None
        except Exception as e:
            logger.error(f"获取比赛数据时出错: {str(e)}", exc_info=True)
            # 清理可能遗留的临时截图
            for img_path in temp_screenshots:
                try:
                    if os.path.exists(img_path):
                        os.remove(img_path)
                except:
                    pass
            return None
    
    async def process_command(self, command: str) -> Dict[str, Any]:
        """处理最近比赛命令"""
        if command.strip() in ["最近比赛", "/最近比赛"]:
            try:
                # 获取最近比赛数据
                logger.info("开始获取最近比赛数据")
                screenshot_path = await self.get_recent_matches()
                
                if (screenshot_path and os.path.exists(screenshot_path)):
                    logger.info(f"成功获取最近比赛数据，截图保存在 {screenshot_path}")
                    return {
                        "message": "已获取最近比赛数据",
                        "type": "recent_matches",
                        "image_path": screenshot_path
                    }
                else:
                    logger.error("未能获取最近比赛数据")
                    return {"message": "获取最近比赛数据失败，请稍后重试"}
            except Exception as e:
                logger.error(f"处理最近比赛命令时出错: {str(e)}", exc_info=True)
                return {"message": f"处理命令时出错: {str(e)}"}
        else:
            return {"message": "未知命令，请使用 '最近比赛' 命令查询最新比赛信息"}

# 创建全局实例，以便可以被导入
recent_match_fetcher = RecentMatchFetcher()

# 导出API函数
async def get_recent_matches() -> Optional[str]:
    """获取最近比赛数据API"""
    return await recent_match_fetcher.get_recent_matches()

async def process_command(command: str) -> Dict[str, Any]:
    """处理命令API"""
    return await recent_match_fetcher.process_command(command)

# 在导入时检查playwright和PIL是否已安装
try:
    import playwright
    logger.info(f"Playwright版本: {getattr(playwright, '__version__', 'unknown')}")
    from PIL import Image
    logger.info(f"PIL已安装")
except ImportError as e:
    logger.error(f"未找到必要的库: {str(e)}，请使用pip install playwright pillow安装")
except Exception as e:
    logger.error(f"初始化时出错: {str(e)}")

# 检查screenshots目录是否存在，如果不存在则创建
if not os.path.exists(os.path.join(os.path.dirname(__file__), "screenshots")):
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), "screenshots"), exist_ok=True)
        logger.info("已创建screenshots目录")
    except Exception as e:
        logger.error(f"创建screenshots目录时出错: {str(e)}")
