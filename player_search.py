import os
import re
import asyncio
import random
import time
from difflib import SequenceMatcher
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
import subprocess
import sys
import platform

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('player_search')

# 用户代理列表，用于反爬虫
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
]

class PlayerSearcher:
    """CS:GO 选手数据查询类"""
    
    def __init__(self):
        """初始化查询器"""
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
            
        # 存储用户搜索结果
        self.search_results = {}
        self.search_timestamps = {}
        self.result_timeout = 30  # 结果有效期（秒）
        
        # 加载选手数据
        self.players_file = os.path.join(os.path.dirname(__file__), "players.txt")
        self.ensure_players_file_exists()
    
    def ensure_players_file_exists(self):
        """确保players.txt文件存在"""
        if not os.path.exists(self.players_file):
            logger.warning(f"players.txt文件不存在，创建示例文件")
            with open(self.players_file, "w", encoding="utf-8") as f:
                f.write("# 示例格式 (ID|选手名)\n")
                f.write("21879|a1pha\n")
                f.write("24394|aapestt\n")
                f.write("13317|aaron\n")
                f.write("8918|s1mple\n")
                f.write("7998|device\n")
            logger.info("已创建示例players.txt文件")
    
    async def load_player_data(self) -> Dict[str, str]:
        """从players.txt加载选手数据"""
        players = {}
        try:
            with open(self.players_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):  # 跳过注释行
                        # 使用竖线分隔ID和选手名
                        if "|" in line:
                            parts = line.split("|", 1)  # 最多分割一次，以防选手名中含有竖线
                            if len(parts) == 2:
                                player_id = parts[0].strip()
                                player_name = parts[1].strip()
                                players[player_id] = player_name
            logger.info(f"成功加载 {len(players)} 名选手数据")
        except Exception as e:
            logger.error(f"加载选手数据失败: {str(e)}")
        return players
    
    def fuzzy_match(self, query: str, choices: Dict[str, str]) -> List[Tuple[str, str, float]]:
        """模糊匹配选手名称"""
        results = []
        query = query.lower()
        
        for player_id, player_name in choices.items():
            name_lower = player_name.lower()
            if query in name_lower:
                # 如果是子字符串，给予较高的匹配分数
                score = 0.9
            else:
                # 否则计算字符串相似度
                score = SequenceMatcher(None, query, name_lower).ratio()
            
            if score > 0.3:  # 设置一个相似度阈值
                results.append((player_id, player_name, score))
        
        # 按相似度降序排序
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:10]  # 最多返回10个结果
    
    async def search_player_cmd(self, message: str, user_id: str) -> Dict[str, Any]:
        """处理选手搜索命令"""
        # 修改正则表达式，同时兼容带斜杠和不带斜杠的命令
        match = re.match(r"^/?搜索选手\s+(.*)", message)
        if not match:
            return {"message": "命令格式错误，正确格式为：/搜索选手 [选手名]"}
        
        player_name = match.group(1).strip()
        if not player_name:
            return {"message": "请输入选手名称"}
        
        # 加载选手数据
        players = await self.load_player_data()
        if not players:
            return {"message": "无法加载选手数据，请检查players.txt文件是否存在且格式正确"}
        
        # 模糊匹配
        matches = self.fuzzy_match(player_name, players)
        if not matches:
            return {"message": f"未找到与 '{player_name}' 相关的选手"}
        
        # 保存搜索结果和时间戳
        self.search_results[user_id] = matches
        self.search_timestamps[user_id] = time.time()
        
        # 格式化搜索结果
        result_message = "🔍 搜索结果：\n" + "═" * 30 + "\n\n"
        for i, (player_id, name, _) in enumerate(matches[:5], 1):
            result_message += f"#{i} {name} (ID: {player_id})\n"
        
        result_message += f"\n📌 在{self.result_timeout}秒内发送 '选手[数字]' 来查看对应选手的数据，例如：选手1"
        
        return {"message": result_message, "type": "search_result"}
    
    async def view_player_cmd(self, message: str, user_id: str) -> Dict[str, Any]:
        """处理查看选手请求"""
        logger.info(f"处理查看选手请求: message={message}, user_id={user_id}")
        
        # 从 "选手1" 格式中提取数字
        match = re.match(r"选手(\d+)", message)
        if not match:
            logger.warning(f"命令格式错误: {message}")
            return {"message": "命令格式错误，正确格式为：选手[数字]"}
        
        # 检查是否有最近的搜索结果
        if user_id not in self.search_results or user_id not in self.search_timestamps:
            logger.warning(f"用户 {user_id} 未找到搜索结果或时间戳")
            return {"message": "请先使用 /搜索选手 命令查询选手"}
        
        # 检查结果是否过期
        current_time = time.time()
        last_search_time = self.search_timestamps[user_id]
        elapsed_time = current_time - last_search_time
        logger.debug(f"用户 {user_id} 搜索结果时间: {last_search_time}, 当前时间: {current_time}, 经过时间: {elapsed_time}秒")
        
        if elapsed_time > self.result_timeout:
            logger.info(f"用户 {user_id} 的搜索结果已过期 ({elapsed_time}秒 > {self.result_timeout}秒), 清理数据")
            del self.search_results[user_id]
            del self.search_timestamps[user_id]
            return {"message": f"搜索结果已过期，请重新搜索"}
        
        try:
            index = int(match.group(1))
            logger.debug(f"解析的索引号: {index}")
            
            if index < 1 or index > len(self.search_results[user_id]):
                logger.warning(f"索引超出范围: {index}, 可用范围: 1-{len(self.search_results[user_id])}")
                return {"message": f"请输入1到{len(self.search_results[user_id])}之间的数字"}
            
            player_id, player_name, _ = self.search_results[user_id][index - 1]
            logger.info(f"用户 {user_id} 选择了索引 {index}: player_id={player_id}, player_name={player_name}")
            
            return {
                "message": f"📊 正在获取 {player_name} 的数据，请稍候...",
                "type": "processing",
                "player_id": player_id,
                "player_name": player_name
            }
            
        except ValueError:
            logger.error(f"解析索引时出错: {match.group(1)}")
            return {"message": "请输入有效的数字"}
        except Exception as e:
            logger.error(f"view_player_cmd 处理过程中出错: {str(e)}", exc_info=True)
            return {"message": f"处理请求时出错: {str(e)}"}
    
    async def get_player_stats(self, player_id: str, player_name: str) -> Optional[str]:
        """获取选手统计数据并截图"""
        logger.info(f"开始获取选手 {player_name}(ID:{player_id}) 的统计数据")
        
        try:
            # 导入playwright，确保已安装
            from playwright.async_api import async_playwright
            
            # 生成截图文件路径
            screenshot_path = os.path.join(self.screenshot_dir, f"player_stats_{player_id}_{int(time.time())}.png")
            logger.debug(f"截图保存路径: {screenshot_path}")
            
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
                    logger.info(f"第 {attempt + 1}/{max_retries} 次尝试获取选手数据")
                    
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
                            viewport={'width': 1920, 'height': 1080},
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
                        url = f"https://event.5eplay.com/csgo/player/csgo_pl_{player_id}"
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
                                
                                # 查找并点击"数据"标签
                                logger.debug("尝试查找并点击'数据'标签...")
                                data_tab = await page.query_selector('ul.sub-tab-wrap.flex-horizontal li:text("数据")')
                                if data_tab:
                                    logger.debug("找到'数据'标签，准备点击")
                                    # 模拟点击
                                    await data_tab.hover()
                                    await asyncio.sleep(random.uniform(0.3, 0.8))
                                    await data_tab.click()
                                    logger.debug("已点击'数据'标签")
                                    
                                    # 等待数据加载
                                    logger.debug("等待数据内容加载...")
                                    await page.wait_for_selector('.player-detail-index', state="visible", timeout=15000)
                                    await asyncio.sleep(random.uniform(1.0, 2.0))
                                    
                                    # 隐藏页面顶部元素
                                    logger.debug("隐藏顶部元素(header-box和sub-header)...")
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
                                        
                                        // 调整页面布局，确保没有留白
                                        const contentElement = document.querySelector('.player-detail-index');
                                        if (contentElement) {
                                            contentElement.style.marginTop = '0';
                                            contentElement.style.paddingTop = '10px';
                                        }
                                    """)
                                    logger.debug("页面顶部和底部元素已隐藏")
                                    
                                    # 强制等待一下，确保样式应用
                                    await asyncio.sleep(0.5)
                                    
                                    # 检查数据是否实际加载
                                    logger.debug("检查数据是否已加载...")
                                    stats_element = await page.query_selector('.player-detail-index')
                                    if stats_element:
                                        logger.info("数据已加载，开始截图")
                                        
                                        # 获取元素尺寸
                                        bbox = await stats_element.bounding_box()
                                        if bbox:
                                            logger.debug(f"数据元素尺寸: x={bbox['x']}, y={bbox['y']}, w={bbox['width']}, h={bbox['height']}")
                                        
                                        # 截图
                                        await stats_element.screenshot(path=screenshot_path)
                                        logger.info(f"已保存 {player_name} 的数据截图到 {screenshot_path}")
                                        
                                        # 验证截图文件是否生成
                                        if os.path.exists(screenshot_path):
                                            file_size = os.path.getsize(screenshot_path)
                                            logger.debug(f"截图文件大小: {file_size} 字节")
                                            if file_size > 0:
                                                logger.info("截图成功完成")
                                                return screenshot_path
                                            else:
                                                logger.warning(f"截图文件大小为零: {screenshot_path}")
                                        else:
                                            logger.warning(f"截图文件未生成: {screenshot_path}")
                                    else:
                                        logger.error("未找到数据元素 .player-detail-index")
                                else:
                                    logger.error("未找到'数据'标签")
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
            
            logger.error("获取选手数据失败，已达到最大尝试次数")
            return None
            
        except ImportError:
            logger.error("未安装playwright，请使用pip install playwright安装")
            return None
        except Exception as e:
            logger.error(f"获取选手数据时出错: {str(e)}", exc_info=True)
            return None
    
    async def help_cmd(self) -> Dict[str, str]:
        """显示帮助信息"""
        help_text = "🎮 CS:GO 选手数据查询系统 🎮\n" + "═" * 30 + "\n\n"
        help_text += "可用命令：\n"
        help_text += "  /搜索选手 [选手名] - 搜索符合名称的选手\n"
        help_text += "  选手[数字] - 查看搜索结果中对应编号的选手数据\n"
        help_text += "\n📌 数据来源于5eplay.com"
        
        return {"message": help_text, "type": "help"}
    
    async def process_message(self, message: str, user_id: str = "default_user") -> Dict[str, Any]:
        """处理用户消息，返回处理结果"""
        message = message.strip()
        
        # 处理帮助命令
        if message == "/help" or message == "/帮助" or message == "help" or message == "帮助":
            return await self.help_cmd()
        
        # 处理搜索选手命令 - 修改为同时支持带斜杠和不带斜杠
        if re.match(r"^/?搜索选手", message):
            return await self.search_player_cmd(message, user_id)
        
        # 处理查看选手命令
        if re.match(r"^/?选手\d+$", message):
            view_result = await self.view_player_cmd(message, user_id)
            
            # 如果是需要获取选手数据的请求
            if view_result.get("type") == "processing":
                player_id = view_result.get("player_id")
                player_name = view_result.get("player_name")
                
                # 获取选手统计数据
                logger.info(f"开始获取选手 {player_name}(ID:{player_id}) 的统计数据")
                
                try:
                    screenshot_path = await self.get_player_stats(player_id, player_name)
                    
                    if screenshot_path:
                        logger.info(f"成功获取选手 {player_name} 的数据，截图保存在 {screenshot_path}")
                        return {
                            "message": f"已获取 {player_name} 的数据",
                            "type": "player_stats",
                            "image_path": screenshot_path
                        }
                    else:
                        logger.error(f"未能获取选手 {player_name} 的数据")
                        return {"message": f"获取 {player_name} 的数据失败，请稍后重试"}
                except Exception as e:
                    logger.error(f"获取选手数据时发生异常: {str(e)}", exc_info=True)
                    return {"message": f"获取选手数据时出错: {str(e)}"}
            
            return view_result
        
        # 其他命令
        return {"message": "未知命令，请使用 /help 查看帮助"}

# 创建全局实例，以便可以被导入
player_searcher = PlayerSearcher()

# 导出API函数，与main.py类似
async def search_player(message: str, user_id: str = "default_user") -> Dict[str, Any]:
    """搜索选手API"""
    return await player_searcher.search_player_cmd(message, user_id)

async def view_player(message: str, user_id: str = "default_user") -> Dict[str, Any]:
    """查看选手API"""
    return await player_searcher.view_player_cmd(message, user_id)

async def process_message(message: str, user_id: str = "default_user") -> Dict[str, Any]:
    """处理消息API"""
    return await player_searcher.process_message(message, user_id)

# 在导入时检查playwright是否已安装
try:
    import playwright
    logger.info(f"Playwright版本: {getattr(playwright, '__version__', 'unknown')}")
except ImportError:
    logger.error("未找到playwright库，某些功能可能无法正常使用")
except Exception as e:
    logger.error(f"检查playwright时出错: {str(e)}")

# 检查screenshots目录是否存在，如果不存在则创建
if not os.path.exists(os.path.join(os.path.dirname(__file__), "screenshots")):
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), "screenshots"), exist_ok=True)
        logger.info("已创建screenshots目录")
    except Exception as e:
        logger.error(f"创建screenshots目录时出错: {str(e)}")
