"""Provider 抽象基类"""

from abc import ABC, abstractmethod
from pathlib import Path
from ..models import ToolType, SessionSummary, SessionDetail


class BaseProvider(ABC):
    """所有 CLI 工具 provider 的基类"""

    @property
    @abstractmethod
    def tool_type(self) -> ToolType:
        ...

    @property
    @abstractmethod
    def base_dir(self) -> Path:
        ...

    def is_available(self) -> bool:
        """检查该工具的数据目录是否存在"""
        return self.base_dir.exists()

    @abstractmethod
    def load_sessions(self) -> list[SessionSummary]:
        """加载会话摘要列表"""
        ...

    @abstractmethod
    def load_session_detail(self, session_id: str, project: str = "") -> SessionDetail | None:
        """加载会话完整对话"""
        ...

    @abstractmethod
    def delete_session(self, session_id: str) -> dict[str, bool]:
        """删除会话，返回各步骤结果"""
        ...

    @abstractmethod
    def get_resume_command(self, session_id: str) -> list[str]:
        """获取恢复会话的命令"""
        ...

    # ── 标题/名称（可选能力，不同工具实现不同） ──

    def get_session_title(self, session_id: str) -> str | None:
        """Return the current tool-native session title/name if supported."""
        return None

    def set_session_title(self, session_id: str, title: str) -> tuple[bool, str]:
        """Set the tool-native session title/name if supported."""
        return False, "Not supported"

    def clear_session_title(self, session_id: str) -> tuple[bool, str]:
        """Clear the tool-native session title/name (restore default) if supported."""
        return False, "Not supported"

    def load_stats(self) -> dict | None:
        """加载统计数据（默认不支持）"""
        return None
