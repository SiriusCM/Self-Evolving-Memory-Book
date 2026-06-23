"""LLM客户端层 - 基于requests的API调用"""

import json
import logging
import os
import re
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 120


class LLMClient:
    """基于requests的OpenAI Compatible API客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.timeout = timeout or int(os.getenv("AI_REQUEST_TIMEOUT", str(DEFAULT_TIMEOUT)))

        base = self.base_url.rstrip("/")
        self.api_url = f"{base}/chat/completions"

    def chat(self, system_prompt: str, user_message: str) -> str:
        """基础聊天接口"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
            "stream": False,
        }

        response = requests.post(
            url=self.api_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            content = content.replace("```json", "").replace("```", "").strip()
            return content

        raise ValueError("AI无返回内容")

    def chat_json(self, system_prompt: str, user_message: str) -> Any:
        """聊天并解析JSON响应"""
        system_prompt += "\n\n你必须以纯JSON格式回复，不要包含任何其他文字或markdown标记。"
        raw = self.chat(system_prompt, user_message)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        json_match = re.search(r"\[[\s\S]*\]", raw)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(f"LLM返回的不是有效JSON: {raw[:200]}")

    def classify_memory(self, memory_text: str, tree_summary: str) -> dict:
        """让LLM判断记忆应归属哪个节点"""
        system_prompt = """你是一个记忆分类助手。你需要判断一段新记忆应该归属到记忆树的哪个节点。

规则：
1. 仔细阅读目录树摘要，选择最匹配的节点路径
2. 如果没有合适的节点，可以建议创建新节点（给出完整路径）
3. 优先选择已有节点，只有确实无法归类时才创建新节点
4. 返回JSON格式

返回格式示例：
{
  "node_path": "技术/Java/Spring",
  "reason": "该记忆涉及Spring框架相关内容",
  "should_create": false
}

如果要创建新节点：
{
  "node_path": "技术/Java/Spring AI",
  "reason": "Spring AI是Spring生态中的新方向，需要独立节点",
  "should_create": true
}"""

        user_message = f"""记忆内容：{memory_text}

当前目录树：
{tree_summary}

请判断该记忆应该归属哪个节点。"""

        return self.chat_json(system_prompt, user_message)

    def query_route(self, question: str, tree_summary: str) -> dict:
        """让LLM选择查询相关的节点"""
        system_prompt = """你是一个记忆检索助手。你需要根据用户的问题，从记忆树目录中选择最相关的节点。

规则：
1. 可以选择多个节点
2. 优先选择最精确的节点
3. 如果没有直接匹配，选择可能相关的父节点
4. 返回JSON格式

返回格式：
{
  "nodes": ["技术/AI/Memory", "技术/AI/Agent"],
  "reason": "问题涉及Memory框架和Agent开发"
}"""

        user_message = f"""用户问题：{question}

当前目录树：
{tree_summary}

请选择最相关的节点。"""

        return self.chat_json(system_prompt, user_message)

    def generate_summary(self, contents: str, node_name: str) -> str:
        """让LLM生成节点摘要"""
        system_prompt = f"""你是一个摘要生成助手。请为节点"{node_name}"生成一段简洁的摘要。

要求：
1. 概括节点下所有记忆的核心主题
2. 简洁但信息完整
3. 200字以内
4. 只返回摘要文本，不要JSON格式"""

        user_message = f"""节点名称：{node_name}

节点下的记忆内容：
{contents}

请生成摘要。"""

        return self.chat(system_prompt, user_message)

    def analyze_split(self, contents: str, node_name: str) -> dict:
        """让LLM分析节点是否需要裂变"""
        system_prompt = """你是一个记忆树管理助手。你需要分析一个节点的记忆内容，判断是否需要裂变（拆分）为多个子节点。

规则：
1. 如果内容主题明显分散，建议拆分为多个子节点
2. 如果内容主题聚焦，不需要拆分
3. 每个子节点名称要简洁明确
4. 返回JSON格式

返回格式：
{
  "should_split": true,
  "sub_nodes": [
    {"name": "Agent", "summary": "Agent框架、工作流相关内容"},
    {"name": "MCP", "summary": "MCP协议、工具调用相关内容"},
    {"name": "Memory", "summary": "记忆系统、存储检索相关内容"}
  ],
  "reason": "内容覆盖了Agent、MCP、Memory三个不同方向"
}

如果不需拆分：
{
  "should_split": false,
  "sub_nodes": [],
  "reason": "内容主题聚焦，无需拆分"
}"""

        user_message = f"""节点名称：{node_name}

节点下的记忆内容：
{contents}

请分析是否需要裂变。"""

        return self.chat_json(system_prompt, user_message)

    def classify_item_to_subnode(self, content: str, subnode_summaries: list[dict]) -> dict:
        """让LLM将记忆项分类到裂变后的子节点"""
        subnode_desc = "\n".join(
            f"- {s['name']}: {s['summary']}" for s in subnode_summaries
        )
        system_prompt = f"""你是一个记忆分类助手。请将一段记忆归类到以下子节点之一。

可选子节点：
{subnode_desc}

返回JSON格式：
{
  "target_node": "子节点名称",
  "reason": "归类原因"
}"""

        user_message = f"""记忆内容：{content}

请归类到合适的子节点。"""

        return self.chat_json(system_prompt, user_message)

    def check_merge_similarity(self, node_a_summary: str, node_b_summary: str) -> dict:
        """让LLM判断两个节点是否应该合并"""
        system_prompt = """你是一个记忆树管理助手。请判断两个节点是否应该合并。

规则：
1. 只有当两个节点主题高度相似（>90%相似）时才建议合并
2. 合并后的节点名称要能涵盖两者的主题
3. 返回JSON格式

返回格式：
{
  "should_merge": true,
  "merged_name": "Spring",
  "merged_summary": "涵盖Spring和Spring Boot相关内容",
  "similarity": 95
}

或：
{
  "should_merge": false,
  "reason": "两个节点主题不同",
  "similarity": 30
}"""

        user_message = f"""节点A摘要：{node_a_summary}

节点B摘要：{node_b_summary}

请判断是否应该合并。"""

        return self.chat_json(system_prompt, user_message)