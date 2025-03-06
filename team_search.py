import os
import re
import asyncio
import random
import time
from difflib import SequenceMatcher
import logging
from typing import Dict, List, Tuple, Optional, Union, Any

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('team_search')

# 用户代理列表，用于反爬虫
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
]

class TeamSearcher:
    """CS:GO 战队数据查询类"""
    
    def __init__(self):
        """初始化查询器"""
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
            
        # 存储用户搜索结果
        self.search_results = {}
        self.search_timestamps = {}
        self.result_timeout = 30  # 结果有效期（秒）
        
        # 加载战队数据
        self.teams_file = os.path.join(os.path.dirname(__file__), "teams.txt")
        self.ensure_teams_file_exists()
    
    def ensure_teams_file_exists(self):
        """确保teams.txt文件存在"""
        if not os.path.exists(self.teams_file):
            logger.warning(f"teams.txt文件不存在，创建示例文件")
            with open(self.teams_file, "w", encoding="utf-8") as f:
                f.write("# 示例格式 (战队ID|战队名称|战队URL)\n")
                f.write("9710|LSU|https://hltv.org/stats/teams/9710/lsu\n")
                f.write("13146|Supernova Comets|https://hltv.org/stats/teams/13146/supernova-comets\n")
                f.write("6889|E-Corp|https://hltv.org/stats/teams/6889/e-corp\n")
                f.write("8804|etopkald|https://hltv.org/stats/teams/8804/etopkald\n")
                f.write("11291|Meta4Pro|https://hltv.org/stats/teams/11291/meta4pro\n")
            logger.info("已创建示例teams.txt文件")
    
    async def load_team_data(self) -> Dict[str, Tuple[str, str]]:
        """从teams.txt加载战队数据"""
        teams = {}
        try:
            with open(self.teams_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):  # 跳过注释行
                        # 使用竖线分隔战队ID、名称和URL
                        parts = line.split("|", 2)
                        if len(parts) >= 2:
                            team_id = parts[0].strip()
                            team_name = parts[1].strip()
                            team_url = parts[2].strip() if len(parts) > 2 else f"https://event.5eplay.com/csgo/team/csgo_tm_{team_id}"
                            teams[team_name] = (team_id, team_url)
            logger.info(f"成功加载 {len(teams)} 个战队数据")
        except Exception as e:
            logger.error(f"加载战队数据失败: {str(e)}")
        return teams
    
    def fuzzy_match(self, query: str, team_data: Dict[str, Tuple[str, str]]) -> List[Tuple[str, str, str, float]]:
        """模糊匹配战队名称"""
        results = []
        query = query.lower()
        
        # 处理查询中的空格
        query_no_space = query.replace(" ", "")
        
        for team_name, (team_id, team_url) in team_data.items():
            team_name_lower = team_name.lower()
            team_name_no_space = team_name_lower.replace(" ", "")
            
            # 计算相似度（考虑带空格和不带空格的情况）
            if query in team_name_lower:
                # 如果是子字符串，给予较高的匹配分数
                score = 0.9
            elif query_no_space in team_name_no_space:
                # 不带空格的子字符串匹配
                score = 0.85
            else:
                # 否则计算字符串相似度
                score_with_space = SequenceMatcher(None, query, team_name_lower).ratio()
                score_no_space = SequenceMatcher(None, query_no_space, team_name_no_space).ratio()
                score = max(score_with_space, score_no_space)
            
            if score > 0.3:  # 设置一个相似度阈值
                results.append((team_name, team_id, team_url, score))
        
        # 按相似度降序排序
        results.sort(key=lambda x: x[3], reverse=True)
        return results[:10]  # 最多返回10个结果
    
    async def search_team_cmd(self, message: str, user_id: str) -> Dict[str, Any]:
        """处理战队搜索命令"""
        # 修改正则表达式，同时兼容带斜杠和不带斜杠的命令
        match = re.match(r"^/?搜索战队\s+(.*)", message)
        if not match:
            return {"message": "命令格式错误，正确格式为：/搜索战队 [战队名]"}
        
        team_name = match.group(1).strip()
        if not team_name:
            return {"message": "请输入战队名称"}
        
        # 加载战队数据
        teams = await self.load_team_data()
        if not teams:
            return {"message": "无法加载战队数据，请检查teams.txt文件是否存在且格式正确"}
        
        # 模糊匹配
        matches = self.fuzzy_match(team_name, teams)
        if not matches:
            return {"message": f"未找到与 '{team_name}' 相关的战队"}
        
        # 保存搜索结果和时间戳
        self.search_results[user_id] = matches
        self.search_timestamps[user_id] = time.time()
        
        # 格式化搜索结果
        result_message = "🔍 搜索结果：\n" + "═" * 30 + "\n\n"
        for i, (name, team_id, _, _) in enumerate(matches[:5], 1):
            result_message += f"#{i} {name} (ID: {team_id})\n"
        
        result_message += f"\n📌 在{self.result_timeout}秒内发送 '战队[数字]' 来查看对应战队的数据，例如：战队1"
        
        return {"message": result_message, "type": "search_result"}
    
    async def view_team_cmd(self, message: str, user_id: str) -> Dict[str, Any]:
        """处理查看战队请求"""
        logger.info(f"处理查看战队请求: message={message}, user_id={user_id}")
        
        # 从 "战队1" 格式中提取数字
        match = re.match(r"战队(\d+)", message)
        if not match:
            logger.warning(f"命令格式错误: {message}")
            return {"message": "命令格式错误，正确格式为：战队[数字]"}
        
        # 检查是否有最近的搜索结果
        if user_id not in self.search_results or user_id not in self.search_timestamps:
            logger.warning(f"用户 {user_id} 未找到搜索结果或时间戳")
            return {"message": "请先使用 /搜索战队 命令查询战队"}
        
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
            
            team_name, team_id, team_url, _ = self.search_results[user_id][index - 1]
            logger.info(f"用户 {user_id} 选择了索引 {index}: team_id={team_id}, team_name={team_name}, team_url={team_url}")
            
            return {
                "message": f"📊 正在获取 {team_name} 的数据，请稍候...",
                "type": "processing",
                "team_id": team_id,
                "team_name": team_name,
                "team_url": team_url
            }
            
        except ValueError:
            logger.error(f"解析索引时出错: {match.group(1)}")
            return {"message": "请输入有效的数字"}
        except Exception as e:
            logger.error(f"view_team_cmd 处理过程中出错: {str(e)}", exc_info=True)
            return {"message": f"处理请求时出错: {str(e)}"}
    
    async def get_team_stats(self, team_id: str, team_name: str) -> Optional[str]:
        """获取战队统计数据并截图"""
        logger.info(f"开始获取战队 {team_name}(ID:{team_id}) 的统计数据")
        
        try:
            # 导入playwright，确保已安装
            from playwright.async_api import async_playwright
            
            # 生成截图文件路径
            screenshot_path = os.path.join(self.screenshot_dir, f"team_stats_{team_id}_{int(time.time())}.png")
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
                    logger.info(f"第 {attempt + 1}/{max_retries} 次尝试获取战队数据")
                    
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
                        url = f"https://event.5eplay.com/csgo/team/csgo_tm_{team_id}"
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
                                    const contentElement = document.querySelector('.team-detail-container');
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
                                stats_element = await page.query_selector('.team-detail-container.flex-vertical')
                                if stats_element:
                                    logger.info("数据已加载，开始截图")
                                    
                                    # 获取元素尺寸
                                    bbox = await stats_element.bounding_box()
                                    if bbox:
                                        logger.debug(f"数据元素尺寸: x={bbox['x']}, y={bbox['y']}, w={bbox['width']}, h={bbox['height']}")
                                    
                                    # 截图
                                    await stats_element.screenshot(path=screenshot_path)
                                    logger.info(f"已保存 {team_name} 的数据截图到 {screenshot_path}")
                                    
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
                                    logger.error("未找到数据元素 .team-detail-container.flex-vertical")
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
            
            logger.error("获取战队数据失败，已达到最大尝试次数")
            return None
            
        except ImportError:
            logger.error("未安装playwright，请使用pip install playwright安装")
            return None
        except Exception as e:
            logger.error(f"获取战队数据时出错: {str(e)}", exc_info=True)
            return None
    
    async def help_cmd(self) -> Dict[str, str]:
        """显示帮助信息"""
        help_text = "🏆 CS:GO 战队数据查询系统 🏆\n" + "═" * 30 + "\n\n"
        help_text += "可用命令：\n"
        help_text += "  /搜索战队 [战队名] - 搜索符合名称的战队\n"
        help_text += "  战队[数字] - 查看搜索结果中对应编号的战队数据\n"
        help_text += "\n📌 数据来源于5eplay.com"
        
        return {"message": help_text, "type": "help"}
    
    async def process_message(self, message: str, user_id: str = "default_user") -> Dict[str, Any]:
        """处理用户消息，返回处理结果"""
        message = message.strip()
        
        # 处理帮助命令
        if message == "/team_help" or message == "/战队帮助" or message == "team_help" or message == "战队帮助":
            return await self.help_cmd()
        
        # 处理搜索战队命令 - 修改为同时支持带斜杠和不带斜杠
        if re.match(r"^/?搜索战队", message):
            return await self.search_team_cmd(message, user_id)
        
        # 处理查看战队命令
        if re.match(r"^/?战队\d+$", message):
            view_result = await self.view_team_cmd(message, user_id)
            
            # 如果是需要获取战队数据的请求
            if view_result.get("type") == "processing":
                team_id = view_result.get("team_id")
                team_name = view_result.get("team_name")
                
                # 获取战队统计数据
                logger.info(f"开始获取战队 {team_name}(ID:{team_id}) 的统计数据")
                
                try:
                    screenshot_path = await self.get_team_stats(team_id, team_name)
                    
                    if screenshot_path:
                        logger.info(f"成功获取战队 {team_name} 的数据，截图保存在 {screenshot_path}")
                        return {
                            "message": f"已获取 {team_name} 的数据",
                            "type": "team_stats",
                            "image_path": screenshot_path
                        }
                    else:
                        logger.error(f"未能获取战队 {team_name} 的数据")
                        return {"message": f"获取 {team_name} 的数据失败，请稍后重试"}
                except Exception as e:
                    logger.error(f"获取战队数据时发生异常: {str(e)}", exc_info=True)
                    return {"message": f"获取战队数据时出错: {str(e)}"}
            
            return view_result
        
        # 其他命令
        return {"message": "未知命令，请使用 /team_help 查看帮助"}

# 创建全局实例，以便可以被导入
team_searcher = TeamSearcher()

# 导出API函数
async def search_team(message: str, user_id: str = "default_user") -> Dict[str, Any]:
    """搜索战队API"""
    return await team_searcher.search_team_cmd(message, user_id)

async def view_team(message: str, user_id: str = "default_user") -> Dict[str, Any]:
    """查看战队API"""
    return await team_searcher.view_team_cmd(message, user_id)

async def process_message(message: str, user_id: str = "default_user") -> Dict[str, Any]:
    """处理消息API"""
    return await team_searcher.process_message(message, user_id)

# 在导入时检查playwright是否已安装
try:
    import playwright
    logger.info(f"Playwright版本: {getattr(playwright, '__version__', 'unknown')}")
except ImportError:
    logger.error("未找到playwright库，战队数据查询功能可能无法正常使用")
except Exception as e:
    logger.error(f"检查playwright时出错: {str(e)}")

# 检查screenshots目录是否存在，如果不存在则创建
if not os.path.exists(os.path.join(os.path.dirname(__file__), "screenshots")):
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), "screenshots"), exist_ok=True)
        logger.info("已创建screenshots目录")
    except Exception as e:
        logger.error(f"创建screenshots目录时出错: {str(e)}")
