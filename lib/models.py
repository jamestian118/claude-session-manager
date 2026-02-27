"""数据模型定义"""

from dataclasses import dataclass, field
from enum import Enum


class ToolType(Enum):
    """CLI 工具类型"""

    # Note: labels are shown to the user (TUI + CLI output).
    CLAUDE = ("Claude Code", 1)  # color_index 1 = cyan
    CODEX = ("CodeX", 3)  # color_index 3 = yellow
    GEMINI = ("Gemini", 4)  # color_index 4 = magenta

    def __init__(self, label: str, color_index: int):
        self.label = label
        self.color_index = color_index

    @property
    def short(self) -> str:
        """列表前缀标识（内部用）：C / X / G"""
        return {"CLAUDE": "C", "CODEX": "X", "GEMINI": "G"}[self.name]


@dataclass
class SessionSummary:
    """会话摘要，来自 history 聚合"""

    session_id: str
    project: str
    first_display: str  # 首条用户消息
    last_display: str  # 最后一条用户消息
    timestamp_start: float  # 最早时间戳（毫秒）
    timestamp_end: float  # 最晚时间戳（毫秒）

    # User-defined session name (stored by CSM, tool-agnostic)
    custom_name: str = ""

    # Tool-agnostic workflow flags (stored by CSM)
    review_status: str = ""  # "" | "pending" | "reviewed" | "rechecked"
    review_updated_at: int = 0  # unix seconds

    message_count: int = 0
    tool_type: ToolType = ToolType.CLAUDE


@dataclass
class ChatMessage:
    """单条对话消息"""

    role: str  # user / assistant
    content: str  # 文本内容
    timestamp: str = ""
    uuid: str = ""


@dataclass
class SessionDetail:
    """会话详情"""

    session_id: str
    project: str
    messages: list = field(default_factory=list)  # List[ChatMessage]

    cwd: str = ""
    git_branch: str = ""
    tool_type: ToolType = ToolType.CLAUDE
    model_provider: str = ""

    # User-defined session name (stored by CSM)
    custom_name: str = ""

    # Tool-agnostic workflow flags (stored by CSM)
    review_status: str = ""  # "" | "pending" | "reviewed" | "rechecked"
    review_updated_at: int = 0

    # 结构化上下文提取
    files_changed: list = field(default_factory=list)  # 修改过的文件路径
    commands_run: list = field(default_factory=list)    # 执行过的命令
    errors: list = field(default_factory=list)          # 遇到的错误
