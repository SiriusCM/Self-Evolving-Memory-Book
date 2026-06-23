"""MemoryTree MCP Server - 存取记忆"""

import json
import os
import sys

# 确保能导入项目根目录的 memory_book 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server import Server
from mcp.server.stdio import stdio_server

from memory_book.core import MemoryTree

# 创建MCP Server
app = Server("memory-tree")

# 全局记忆树实例，由环境变量注入LLM参数
_memory: MemoryTree | None = None


def get_memory() -> MemoryTree:
    """获取MemoryTree实例"""
    global _memory
    if _memory is None:
        _memory = MemoryTree(
            db_path=os.getenv("MEMORY_DB_PATH", "memory_book.db"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
    return _memory


@app.list_tools()
async def list_tools():
    """列出可用工具"""
    return [
        {
            "name": "save_memory",
            "description": "保存一段记忆到记忆树，AI自动分类归属节点",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要保存的记忆内容",
                    },
                },
                "required": ["text"],
            },
        },
        {
            "name": "query_memory",
            "description": "从记忆树查询记忆，AI自动路由检索相关节点并返回上下文",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要查询的问题",
                    },
                },
                "required": ["question"],
            },
        },
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    """调用工具"""
    memory = get_memory()

    if name == "save_memory":
        text = arguments.get("text", "")
        if not text.strip():
            return [{"type": "text", "text": "记忆内容不能为空"}]
        result = memory.save(text)
        return [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False),
            }
        ]

    elif name == "query_memory":
        question = arguments.get("question", "")
        if not question.strip():
            return [{"type": "text", "text": "查询问题不能为空"}]
        result = memory.query(question)
        # 简化返回：只保留answer和节点路径
        simplified = {
            "answer": result.get("answer", ""),
            "nodes": [
                {"path": n["path"], "item_count": n["item_count"]}
                for n in result.get("memory_nodes", [])
            ],
        }
        return [
            {
                "type": "text",
                "text": json.dumps(simplified, ensure_ascii=False),
            }
        ]

    else:
        return [{"type": "text", "text": f"未知工具: {name}"}]


async def main():
    """启动MCP Server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())