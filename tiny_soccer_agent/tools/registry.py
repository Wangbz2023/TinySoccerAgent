"""ToolRegistry：注册和分发 SoccerAgent 风格工具。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from ..memory import SQLiteMemory
from .base import (
    TOOL_CLOSE_QA,
    TOOL_COMMENTARY,
    TOOL_GAME_INFO,
    TOOL_GAME_SEARCH,
    TOOL_LLM,
    TOOL_MATCH_HISTORY,
    TOOL_TEXTUAL_RAG,
    ToolCall,
    ToolResult,
)
from .closeqa import closeqa
from .commentary_generation import commentary_generation
from .game_info_retrieval import game_info_retrieval
from .game_search import game_search
from .llm import llm_final_synthesis
from .match_history_retrieval import match_history_retrieval
from .textual_retrieval_augment import textual_retrieval_augment


ToolFunction = Callable[[str, List[str], Dict[str, Any], SQLiteMemory], ToolResult]


class ToolRegistry:
    """最小工具注册表：工具名必须保持 toolbox.csv / SoccerAgent 风格。"""

    def __init__(self, memory: SQLiteMemory):
        self.memory = memory
        self._tools: Dict[str, ToolFunction] = {}

    def register(self, name: str, func: ToolFunction) -> None:
        self._tools[name] = func

    def execute(self, call: ToolCall, context: Dict[str, Any]) -> ToolResult:
        if call.tool not in self._tools:
            return ToolResult(tool=call.tool, answer=f"Tool '{call.tool}' is not registered.", status="error")
        return self._tools[call.tool](call.query, call.material, context, self.memory)


def build_default_registry(memory: SQLiteMemory) -> ToolRegistry:
    registry = ToolRegistry(memory)
    registry.register(TOOL_GAME_SEARCH, game_search)
    registry.register(TOOL_GAME_INFO, game_info_retrieval)
    registry.register(TOOL_MATCH_HISTORY, match_history_retrieval)
    registry.register(TOOL_TEXTUAL_RAG, textual_retrieval_augment)
    registry.register(TOOL_COMMENTARY, commentary_generation)
    registry.register(TOOL_LLM, llm_final_synthesis)
    registry.register(TOOL_CLOSE_QA, closeqa)
    return registry
