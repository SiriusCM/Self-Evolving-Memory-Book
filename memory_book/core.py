"""MemoryTree核心类 - 自组织Agent记忆框架"""

import logging
from typing import Optional

from memory_book.db import Database
from memory_book.llm import LLMClient

logger = logging.getLogger(__name__)

# 裂变阈值：节点token数超过此值触发裂变
SPLIT_TOKEN_THRESHOLD = 100000


class MemoryBook:
    """
    自组织Agent记忆树

    三个核心接口：
    - save(text): 保存记忆，AI自动分类
    - query(question): 查询记忆，AI路由检索
    - organize(): 自动裂变/合并/摘要
    """

    def __init__(
        self,
        db_path: str = "memory_book.db",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        split_threshold: int = SPLIT_TOKEN_THRESHOLD,
    ):
        self.db = Database(db_path)
        self.llm = LLMClient(api_key=api_key, base_url=base_url, model=model)
        self.split_threshold = split_threshold

    # ==================== 树结构管理 ====================

    def get_tree_summary(self, max_depth: int = 3) -> str:
        """生成目录树摘要（默认前三层）"""
        root_id = self.db.get_root_id()
        lines: list[str] = []
        self._build_tree_text(root_id, lines, prefix="", depth=0, max_depth=max_depth)
        return "\n".join(lines) if lines else "(空树)"

    def _build_tree_text(
        self,
        node_id: int,
        lines: list[str],
        prefix: str,
        depth: int,
        max_depth: int,
    ):
        """递归构建树形文本"""
        node = self.db.get_node(node_id)
        if not node:
            return

        if node["name"] == "ROOT":
            # ROOT节点不展示名称，只展示子节点
            children = self.db.get_children(node_id)
            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                connector = "└── " if is_last else "├── "
                child_prefix = "    " if is_last else "│   "
                token_info = f" ({child['token_count']}tokens)" if child["token_count"] > 0 else ""
                summary_info = f" - {child['summary'][:50]}" if child["summary"] else ""
                lines.append(f"{connector}{child['name']}{token_info}{summary_info}")
                if depth + 1 < max_depth:
                    self._build_tree_text(
                        child["id"], lines, prefix + child_prefix, depth + 1, max_depth
                    )
                elif self.db.get_children(child["id"]):
                    lines.append(f"{prefix + child_prefix}└── ...")
        else:
            children = self.db.get_children(node_id)
            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                connector = "└── " if is_last else "├── "
                child_prefix = prefix + ("    " if is_last else "│   ")
                token_info = f" ({child['token_count']}tokens)" if child["token_count"] > 0 else ""
                summary_info = f" - {child['summary'][:50]}" if child["summary"] else ""
                lines.append(f"{prefix}{connector}{child['name']}{token_info}{summary_info}")
                if depth + 1 < max_depth:
                    self._build_tree_text(
                        child["id"], lines, child_prefix, depth + 1, max_depth
                    )
                elif self.db.get_children(child["id"]):
                    lines.append(f"{child_prefix}└── ...")

    def _ensure_node_path(self, path: str) -> int:
        """确保路径上的节点都存在，返回最终节点ID"""
        parts = [p for p in path.strip("/").split("/") if p]
        current_id = self.db.get_root_id()

        for part in parts:
            children = self.db.get_children(current_id)
            found = False
            for child in children:
                if child["name"] == part:
                    current_id = child["id"]
                    found = True
                    break
            if not found:
                current_id = self.db.create_node(name=part, parent_id=current_id)
                logger.info(f"创建新节点: {part} (parent_id={current_id})")

        return current_id

    # ==================== save ====================

    def save(self, text: str) -> dict:
        """
        保存记忆

        流程：
        1. 读取目录树摘要
        2. LLM判断归属节点
        3. 写入SQLite
        4. 更新节点token统计
        """
        if not text.strip():
            return {"status": "error", "message": "记忆内容不能为空"}

        # 1. 读取目录摘要
        tree_summary = self.get_tree_summary()

        # 2. LLM判断归属
        try:
            result = self.llm.classify_memory(text, tree_summary)
        except Exception as e:
            logger.warning(f"LLM分类失败，保存到根节点: {e}")
            result = {
                "node_path": "",
                "reason": f"LLM分类失败: {e}",
                "should_create": False,
            }

        node_path = result.get("node_path", "")
        should_create = result.get("should_create", False)

        # 3. 确定目标节点
        if node_path:
            if should_create:
                # 创建新节点路径
                node_id = self._ensure_node_path(node_path)
            else:
                # 查找已有节点
                node = self.db.find_node_by_path(node_path)
                if node:
                    node_id = node["id"]
                else:
                    # 路径不存在，自动创建
                    logger.info(f"节点路径不存在，自动创建: {node_path}")
                    node_id = self._ensure_node_path(node_path)
        else:
            node_id = self.db.get_root_id()

        # 4. 写入记忆项
        item_id = self.db.create_item(node_id=node_id, content=text)

        node = self.db.get_node(node_id)
        full_path = self.db.get_node_path(node_id) if node else "ROOT"

        logger.info(f"记忆已保存: node={full_path}, item_id={item_id}")

        # 5. 更新节点摘要（如果节点没有摘要）
        if node and not node["summary"]:
            self._update_node_summary(node_id)

        return {
            "status": "ok",
            "item_id": item_id,
            "node_path": full_path,
            "reason": result.get("reason", ""),
        }

    # ==================== query ====================

    def query(self, question: str) -> dict:
        """
        查询记忆

        流程：
        1. 读取目录树摘要
        2. LLM选择相关节点
        3. 加载节点内容
        4. 返回上下文
        """
        if not question.strip():
            return {"answer": "", "memory_nodes": []}

        # 1. 读取目录摘要
        tree_summary = self.get_tree_summary()

        # 2. LLM路由选择节点
        try:
            route_result = self.llm.query_route(question, tree_summary)
        except Exception as e:
            logger.error(f"LLM路由失败: {e}")
            return {"answer": f"查询路由失败: {e}", "memory_nodes": []}

        node_paths = route_result.get("nodes", [])
        reason = route_result.get("reason", "")

        # 3. 加载节点内容
        memory_nodes = []
        all_contents = []

        for path in node_paths:
            node = self.db.find_node_by_path(path)
            if not node:
                logger.warning(f"节点不存在: {path}")
                continue

            # 获取该节点及其子节点的所有记忆项
            items = self.db.get_all_items(node["id"])
            contents = [item["content"] for item in items]

            if contents:
                node_info = {
                    "path": path,
                    "summary": node["summary"],
                    "item_count": len(items),
                    "contents": contents,
                }
                memory_nodes.append(node_info)
                all_contents.extend(contents)

        # 4. 生成回答
        if not all_contents:
            answer = "未找到相关记忆。"
        else:
            answer = self._generate_answer(question, all_contents)

        return {
            "answer": answer,
            "memory_nodes": memory_nodes,
            "route_reason": reason,
        }

    def _generate_answer(self, question: str, contents: list[str]) -> str:
        """基于记忆内容生成回答"""
        contents_text = "\n---\n".join(f"- {c}" for c in contents[:50])  # 限制条目数
        system_prompt = """你是一个记忆检索助手。请根据用户的记忆内容回答问题。

要求：
1. 基于记忆内容回答，不要编造
2. 如果记忆中没有相关信息，明确说明
3. 简洁直接"""

        user_message = f"""用户问题：{question}

相关记忆：
{contents_text}

请回答。"""

        try:
            return self.llm.chat(system_prompt, user_message)
        except Exception as e:
            logger.error(f"生成回答失败: {e}")
            return f"相关记忆：\n" + "\n".join(f"- {c}" for c in contents[:10])

    # ==================== organize ====================

    def organize(self) -> dict:
        """
        自动整理记忆树

        功能：
        1. 检查节点是否需要裂变（token过大或主题发散）
        2. 检查节点是否需要合并（高度相似）
        3. 更新过期摘要
        """
        results = {
            "split": [],
            "merged": [],
            "summary_updated": [],
            "errors": [],
        }

        all_nodes = self.db.get_all_nodes()

        # 1. 检查裂变
        for node in all_nodes:
            if node["name"] == "ROOT":
                continue
            try:
                self._check_split(node, results)
            except Exception as e:
                logger.error(f"裂变检查失败 node={node['name']}: {e}")
                results["errors"].append(f"裂变检查失败: {node['name']} - {e}")

        # 2. 检查合并（同级节点两两比较）
        self._check_merges(all_nodes, results)

        # 3. 更新摘要
        for node in all_nodes:
            if node["name"] == "ROOT":
                continue
            try:
                self._check_summary(node, results)
            except Exception as e:
                logger.error(f"摘要更新失败 node={node['name']}: {e}")
                results["errors"].append(f"摘要更新失败: {node['name']} - {e}")

        return results

    def _check_split(self, node, results: dict):
        """检查节点是否需要裂变"""
        # 条件1: token超过阈值
        if node["token_count"] < self.split_threshold:
            return

        # 条件2: 必须有记忆项
        items = self.db.get_items(node["id"])
        if len(items) < 3:
            return

        # 已经有子节点的不再裂变（避免递归裂变）
        children = self.db.get_children(node["id"])
        if children:
            return

        logger.info(f"检查裂变: {node['name']} (tokens={node['token_count']})")

        # 读取全部内容
        contents = "\n---\n".join(item["content"] for item in items)
        split_result = self.llm.analyze_split(contents, node["name"])

        if not split_result.get("should_split", False):
            return

        sub_nodes = split_result.get("sub_nodes", [])
        if not sub_nodes:
            return

        # 执行裂变
        self._do_split(node, items, sub_nodes)
        results["split"].append({
            "node": node["name"],
            "sub_nodes": [s["name"] for s in sub_nodes],
            "reason": split_result.get("reason", ""),
        })

    def _do_split(self, node, items: list, sub_nodes: list[dict]):
        """执行裂变操作"""
        # 1. 创建子节点
        created_nodes = {}
        for sub in sub_nodes:
            sub_id = self.db.create_node(
                name=sub["name"],
                parent_id=node["id"],
                summary=sub.get("summary", ""),
            )
            created_nodes[sub["name"]] = {
                "id": sub_id,
                "summary": sub.get("summary", ""),
            }

        # 2. 将记忆项迁移到子节点
        for item in items:
            try:
                classify = self.llm.classify_item_to_subnode(
                    item["content"], sub_nodes
                )
                target_name = classify.get("target_node", "")
                if target_name in created_nodes:
                    self.db.move_item(item["id"], created_nodes[target_name]["id"])
                else:
                    # 找最接近的
                    for name in created_nodes:
                        if target_name.lower() in name.lower() or name.lower() in target_name.lower():
                            self.db.move_item(item["id"], created_nodes[name]["id"])
                            break
            except Exception as e:
                logger.warning(f"记忆项分类失败 item_id={item['id']}: {e}")
                # 保留在原节点
                continue

        # 3. 重写父节点摘要
        self._update_node_summary(node["id"])

    def _check_merges(self, all_nodes, results: dict):
        """检查同级节点是否需要合并"""
        # 按parent_id分组
        from collections import defaultdict
        siblings = defaultdict(list)
        for node in all_nodes:
            if node["name"] == "ROOT" or node["parent_id"] is None:
                continue
            siblings[node["parent_id"]].append(node)

        for parent_id, nodes in siblings.items():
            if len(nodes) < 2:
                continue

            # 两两比较
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    node_a = nodes[i]
                    node_b = nodes[j]

                    # 只比较有摘要的节点
                    if not node_a["summary"] or not node_b["summary"]:
                        continue

                    try:
                        merge_result = self.llm.check_merge_similarity(
                            f"名称: {node_a['name']}\n摘要: {node_a['summary']}",
                            f"名称: {node_b['name']}\n摘要: {node_b['summary']}",
                        )

                        if merge_result.get("should_merge", False) and merge_result.get("similarity", 0) > 90:
                            self._do_merge(node_a, node_b, merge_result)
                            results["merged"].append({
                                "node_a": node_a["name"],
                                "node_b": node_b["name"],
                                "merged_name": merge_result.get("merged_name", ""),
                                "similarity": merge_result.get("similarity", 0),
                            })
                    except Exception as e:
                        logger.warning(f"合并检查失败: {e}")

    def _do_merge(self, node_a, node_b, merge_result: dict):
        """执行合并操作"""
        merged_name = merge_result.get("merged_name", node_a["name"])
        merged_summary = merge_result.get("merged_summary", "")

        # 将node_b的子节点移到node_a下
        children_b = self.db.get_children(node_b["id"])
        for child in children_b:
            self.db.move_node(child["id"], node_a["id"])

        # 将node_b的记忆项移到node_a
        items_b = self.db.get_items(node_b["id"])
        for item in items_b:
            self.db.move_item(item["id"], node_a["id"])

        # 更新node_a的名称和摘要
        self.db.update_node(node_a["id"], name=merged_name, summary=merged_summary)

        # 删除node_b
        self.db.delete_node(node_b["id"])

        # 更新token统计
        self.db.update_token_count(node_a["id"])

    def _check_summary(self, node, results: dict):
        """检查并更新节点摘要"""
        items = self.db.get_items(node["id"])
        if not items:
            return

        # 如果节点没有摘要，或者内容较多但摘要为空，则生成
        if not node["summary"]:
            self._update_node_summary(node["id"])
            results["summary_updated"].append(node["name"])

    def _update_node_summary(self, node_id: int):
        """更新节点摘要"""
        items = self.db.get_items(node_id)
        if not items:
            return

        node = self.db.get_node(node_id)
        if not node:
            return

        contents = "\n---\n".join(item["content"] for item in items[:100])
        try:
            summary = self.llm.generate_summary(contents, node["name"])
            self.db.update_node(node_id, summary=summary)
            logger.info(f"摘要已更新: {node['name']}")
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")

    # ==================== 工具方法 ====================

    def print_tree(self, max_depth: int = 3):
        """打印记忆树"""
        print(self.get_tree_summary(max_depth))

    def get_stats(self) -> dict:
        """获取统计信息"""
        all_nodes = self.db.get_all_nodes()
        total_items = 0
        total_tokens = 0
        for node in all_nodes:
            items = self.db.get_items(node["id"])
            total_items += len(items)
            total_tokens += node["token_count"]

        return {
            "total_nodes": len(all_nodes) - 1,  # 排除ROOT
            "total_items": total_items,
            "total_tokens": total_tokens,
        }

    def close(self):
        """关闭数据库连接"""
        self.db.close()