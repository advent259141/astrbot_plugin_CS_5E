import os
import logging
import asyncio
from typing import Dict, Any

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, Image
from astrbot.api.all import *

# 导入现有的 player_search 和 team_search 模块
try:
    from .player_search import PlayerSearcher
    from .team_search import TeamSearcher
    from .recent_match import RecentMatchFetcher
    from .match_result import MatchResultFetcher
except ImportError:
    from player_search import PlayerSearcher
    from team_search import TeamSearcher
    from recent_match import RecentMatchFetcher
    from match_result import MatchResultFetcher

@register(
    name="astrbot_plugin_5e",  # 插件名称必须与文件名一致
    author="astrbot",
    version="1.0.0",
    desc="5E平台CS:GO选手和战队数据查询插件"
)
class FiveEPlayerQuery(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        
        # 配置日志记录器
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        # 添加处理器到日志记录器
        self.logger.addHandler(console_handler)
        
        # 创建PlayerSearcher和TeamSearcher实例
        self.player_searcher = PlayerSearcher()
        self.team_searcher = TeamSearcher()
        self.match_fetcher = RecentMatchFetcher()
        self.result_fetcher = MatchResultFetcher()
        
        # 添加截图保存路径
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
            
        self.logger.info("5E数据查询插件初始化完成")

    @filter.command("5e_help")
    async def show_help(self, event: AstrMessageEvent):
        """显示5E查询插件的帮助信息"""
        help_result = await self.player_searcher.help_cmd()
        team_help_result = await self.team_searcher.help_cmd()
        
        # 合并两个帮助信息，并添加最近比赛命令说明
        combined_help = help_result["message"] + "\n\n" + "═" * 30 + "\n\n" + team_help_result["message"]
        combined_help += "\n\n" + "═" * 30 + "\n\n🏆 CS:GO 比赛查询系统 🏆\n\n"
        combined_help += "可用命令：\n  最近比赛 - 查询最近的比赛信息\n  比赛结果 - 查询最近的比赛结果"
        
        yield event.plain_result(combined_help)

    @filter.command("搜索选手")
    async def search_player_cmd(self, event: AstrMessageEvent):
        """搜索选手命令"""
        message = event.message_obj.message_str
        user_id = str(event.get_session_id())
        
        # 处理命令
        result = await self.player_searcher.search_player_cmd(message, user_id)
        yield event.plain_result(result["message"])
        
    @filter.regex(r"^/?搜索战队\s+.*")
    async def search_team_cmd(self, event: AstrMessageEvent):
        """搜索战队命令"""
        message = event.message_obj.message_str
        user_id = str(event.get_session_id())
        
        self.logger.info(f"收到战队搜索请求: {message}, 用户ID: {user_id}")
        
        # 处理命令
        result = await self.team_searcher.search_team_cmd(message, user_id)
        yield event.plain_result(result["message"])

    @filter.regex(r"^选手\s*[1-5]$")
    async def handle_view_player(self, event: AstrMessageEvent):
        """处理查看选手命令"""
        user_id = str(event.get_session_id())
        message = event.message_obj.message_str
        
        self.logger.info(f"收到选手查询命令: {message}, 用户ID: {user_id}")
        
        try:
            # 处理选手查询
            self.logger.debug(f"调用 player_searcher.view_player_cmd({message}, {user_id})")
            result = await self.player_searcher.view_player_cmd(message, user_id)
            
            self.logger.debug(f"查询结果类型: {result.get('type', 'unknown')}")
            
            # 如果是处理中状态，需要获取数据
            if result.get("type") == "processing":
                self.logger.info(f"准备获取选手 {result.get('player_name')} (ID: {result.get('player_id')}) 的数据")
                yield event.plain_result(result["message"])
                
                player_id = result.get("player_id")
                player_name = result.get("player_name")
                
                # 获取选手数据
                self.logger.debug(f"开始获取选手数据: player_id={player_id}, player_name={player_name}")
                screenshot_path = await self.player_searcher.get_player_stats(player_id, player_name)
                
                if screenshot_path and os.path.exists(screenshot_path):
                    self.logger.info(f"成功获取选手截图: {screenshot_path}")
                    # 发送图片
                    message_chain = [
                        Plain(text=f"📊 {player_name} 的数据：\n"),
                        Image(file=screenshot_path)
                    ]
                    yield event.chain_result(message_chain)
                else:
                    self.logger.error(f"获取选手数据失败或截图文件不存在: {screenshot_path}")
                    yield event.plain_result(f"获取 {player_name} 的数据失败，请稍后重试")
            else:
                # 其他结果直接回复
                self.logger.info(f"直接返回结果: {result['message'][:50]}...")
                yield event.plain_result(result["message"])
        except Exception as e:
            self.logger.error(f"处理选手查询命令时出错: {str(e)}", exc_info=True)
            yield event.plain_result(f"处理请求时出错: {str(e)}")
            
    @filter.regex(r"^战队\s*[1-9]\d*$")
    async def handle_view_team(self, event: AstrMessageEvent):
        """处理查看战队命令"""
        user_id = str(event.get_session_id())
        message = event.message_obj.message_str
        
        self.logger.info(f"收到战队查询命令: {message}, 用户ID: {user_id}")
        
        try:
            # 处理战队查询
            self.logger.debug(f"调用 team_searcher.view_team_cmd({message}, {user_id})")
            result = await self.team_searcher.view_team_cmd(message, user_id)
            
            self.logger.debug(f"查询结果类型: {result.get('type', 'unknown')}")
            
            # 如果是处理中状态，需要获取数据
            if result.get("type") == "processing":
                self.logger.info(f"准备获取战队 {result.get('team_name')} (ID: {result.get('team_id')}) 的数据")
                yield event.plain_result(result["message"])
                
                team_id = result.get("team_id")
                team_name = result.get("team_name")
                
                # 获取战队数据
                self.logger.debug(f"开始获取战队数据: team_id={team_id}, team_name={team_name}")
                screenshot_path = await self.team_searcher.get_team_stats(team_id, team_name)
                
                if screenshot_path and os.path.exists(screenshot_path):
                    self.logger.info(f"成功获取战队截图: {screenshot_path}")
                    # 发送图片
                    message_chain = [
                        Plain(text=f"📊 {team_name} 的数据：\n"),
                        Image(file=screenshot_path)
                    ]
                    yield event.chain_result(message_chain)
                else:
                    self.logger.error(f"获取战队数据失败或截图文件不存在: {screenshot_path}")
                    yield event.plain_result(f"获取 {team_name} 的数据失败，请稍后重试")
            else:
                # 其他结果直接回复
                self.logger.info(f"直接返回结果: {result['message'][:50]}...")
                yield event.plain_result(result["message"])
        except Exception as e:
            self.logger.error(f"处理战队查询命令时出错: {str(e)}", exc_info=True)
            yield event.plain_result(f"处理请求时出错: {str(e)}")

    @filter.regex(r"^/?最近比赛$")
    async def handle_recent_matches(self, event: AstrMessageEvent):
        """处理最近比赛查询命令"""
        self.logger.info(f"收到最近比赛查询命令")
        
        try:
            yield event.plain_result("📊 正在获取最近比赛数据，请稍候...")
            
            # 获取最近比赛数据
            screenshot_path = await self.match_fetcher.get_recent_matches()
            
            if screenshot_path and os.path.exists(screenshot_path):
                self.logger.info(f"成功获取最近比赛截图: {screenshot_path}")
                # 发送图片
                message_chain = [
                    Plain(text="📊 最近的CS:GO比赛：\n"),
                    Image(file=screenshot_path)
                ]
                yield event.chain_result(message_chain)
            else:
                self.logger.error(f"获取最近比赛数据失败或截图文件不存在")
                yield event.plain_result("获取最近比赛数据失败，请稍后重试")
        except Exception as e:
            self.logger.error(f"处理最近比赛查询命令时出错: {str(e)}", exc_info=True)
            yield event.plain_result(f"处理请求时出错: {str(e)}")

    @filter.regex(r"^/?比赛结果$")
    async def handle_match_results(self, event: AstrMessageEvent):
        """处理比赛结果查询命令"""
        self.logger.info(f"收到比赛结果查询命令")
        
        # 修改获取用户ID的方式，使用get_sender_id()方法
        user_id = str(event.get_sender_id())
        self.logger.debug(f"使用get_sender_id()获取用户ID: {user_id}")
        
        try:
            yield event.plain_result("📊 正在获取最近的比赛结果，请稍候...")
            
            # 传递user_id给process_command
            result = await self.result_fetcher.process_command("比赛结果", user_id)
            
            if result["success"]:
                self.logger.info(f"成功获取比赛结果，用户ID: {user_id}")
                yield event.plain_result(result["message"])
            else:
                self.logger.error(f"获取比赛结果失败: {result['message']}")
                yield event.plain_result(f"获取比赛结果失败: {result['message']}")
        except Exception as e:
            self.logger.error(f"处理比赛结果查询命令时出错: {str(e)}", exc_info=True)
            yield event.plain_result(f"处理请求时出错: {str(e)}")

    @filter.regex(r"^比赛\d+$")
    async def handle_match_detail(self, event: AstrMessageEvent):
        """处理比赛详情命令"""
        # 修改获取用户ID的方式，使用get_sender_id()方法
        message = event.message_obj.message_str.strip()
        user_id = str(event.get_sender_id())
        
        self.logger.info(f"收到比赛详情命令: {message}, 用户ID: {user_id}")
        
        try:
            # 查看会话状态
            active_sessions = self.result_fetcher.active_browsers.keys()
            user_session = self.result_fetcher.search_results.get(user_id, "无")
            
            self.logger.debug(f"用户 {user_id} 的会话ID: {user_session}")
            self.logger.debug(f"当前活跃会话IDs: {list(active_sessions)}")
            self.logger.debug(f"用户的会话是否活跃: {user_session in active_sessions}")
            
            if user_id in self.result_fetcher.search_results:
                session_id = self.result_fetcher.search_results[user_id]
                if session_id in self.result_fetcher.active_browsers:
                    browser_data = self.result_fetcher.active_browsers[session_id]
                    try:
                        is_connected = browser_data['browser'].is_connected()
                        is_page_closed = browser_data['page'].is_closed()
                        self.logger.debug(f"浏览器连接状态: {is_connected}, 页面是否关闭: {is_page_closed}")
                    except Exception as e:
                        self.logger.warning(f"检查浏览器状态时出错: {str(e)}")
            
            yield event.plain_result("🔍 正在获取比赛详细信息，请稍候...")
            
            # 获取比赛详情
            result = await self.result_fetcher.process_command(message, user_id)
            
            if result["success"]:
                self.logger.info(f"成功获取比赛详情")
                
                if "image_path" in result and os.path.exists(result["image_path"]):
                    # 发送带图片的消息
                    match_info = result.get("match_info", {})
                    team1 = match_info.get("team1", "")
                    team2 = match_info.get("team2", "")
                    score1 = match_info.get("score1", "")
                    score2 = match_info.get("score2", "")
                    
                    message_text = f"📊 比赛详情: {team1} {score1} vs {score2} {team2}\n"
                    
                    message_chain = [
                        Plain(text=message_text),
                        Image(file=result["image_path"])
                    ]
                    yield event.chain_result(message_chain)
                else:
                    yield event.plain_result(result["message"])
            else:
                self.logger.error(f"获取比赛详情失败: {result['message']}")
                yield event.plain_result(result["message"])
        except Exception as e:
            self.logger.error(f"处理比赛详情命令时出错: {str(e)}", exc_info=True)
            yield event.plain_result(f"处理请求时出错: {str(e)}")

    async def on_message(self, event: AstrMessageEvent):
        """处理消息事件"""
        # 统一获取用户ID的方式
        message = event.message_obj.message_str.strip()
        user_id = str(event.get_sender_id())  # 使用get_sender_id()方法
        
        # 如果是帮助命令
        if message.lower() in ("5e帮助", "team_help", "战队帮助"):
            if message.lower() == "5e帮助":
                help_result = await self.player_searcher.help_cmd()
                yield event.plain_result(help_result["message"])
            elif message.lower() in ("team_help", "战队帮助"):
                help_result = await self.team_searcher.help_cmd()
                yield event.plain_result(help_result["message"])
        
        # 增加对最近比赛命令的处理
        if message in ("最近比赛", "/最近比赛"):
            screenshot_path = await self.match_fetcher.get_recent_matches()
            
            if screenshot_path and os.path.exists(screenshot_path):
                message_chain = [
                    Plain(text="📊 最近的CS:GO比赛：\n"),
                    Image(file=screenshot_path)
                ]
                yield event.chain_result(message_chain)
            else:
                yield event.plain_result("获取最近比赛数据失败，请稍后重试")
        
        # 增加对比赛结果命令的处理
        if message in ("比赛结果", "/比赛结果"):
            self.logger.debug(f"on_message中处理比赛结果命令，用户ID: {user_id}")
            result = await self.result_fetcher.process_command(message, user_id)
            if result["success"]:
                yield event.plain_result(result["message"])
            else:
                yield event.plain_result(f"获取比赛结果失败: {result['message']}")
        
        # 增加对比赛详情命令的处理
        match_command = re.match(r"^比赛(\d+)$", message)
        if match_command:
            self.logger.debug(f"on_message中处理比赛详情命令，用户ID: {user_id}")
            result = await self.result_fetcher.process_command(message, user_id)
            if result["success"] and "image_path" in result and os.path.exists(result["image_path"]):
                # 发送比赛详情图片
                match_info = result.get("match_info", {})
                team1 = match_info.get("team1", "")
                team2 = match_info.get("team2", "")
                
                message_chain = [
                    Plain(text=f"📊 比赛详情: {team1} vs {team2}\n"),
                    Image(file=result["image_path"])
                ]
                yield event.chain_result(message_chain)
            else:
                yield event.plain_result(result["message"])
