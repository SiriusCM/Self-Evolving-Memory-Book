"""MemoryTree MCP Server - 存取记忆 (Streamable HTTP 模式)"""

import json
import os
import sys

# 确保能导入项目根目录的 memory_book 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.fastmcp import FastMCP

from memory_book.core import MemoryBook

# 创建MCP Server
app = FastMCP("memory-book", host="0.0.0.0", port=8080)

# 全局记忆树实例，由环境变量注入LLM参数
_memory: MemoryBook | None = None


def get_memory() -> MemoryBook:
    """获取MemoryTree实例"""
    global _memory
    if _memory is None:
        _memory = MemoryBook(
            db_path=os.getenv("MEMORY_DB_PATH", "memory_book.db"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
    return _memory


@app.tool()
def save_memory(text: str) -> str:
    """保存一段记忆到记忆书，AI自动分类归属节点"""
    if not text.strip():
        return "记忆内容不能为空"
    result = get_memory().save(text)
    return json.dumps(result, ensure_ascii=False)


@app.tool()
def query_memory(question: str) -> str:
    """从记忆树查询记忆，AI自动路由检索相关节点并返回上下文"""
    if not question.strip():
        return "查询问题不能为空"
    result = get_memory().query(question)
    simplified = {
        "answer": result.get("answer", ""),
        "nodes": [
            {"path": n["path"], "item_count": n["item_count"]}
            for n in result.get("memory_nodes", [])
        ],
    }
    return json.dumps(simplified, ensure_ascii=False)


if __name__ == "__main__":
    app.run(transport="streamable-http")