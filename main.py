"""MemoryTree - 自组织Agent记忆框架 演示"""

import logging

from memory_book import MemoryBook

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    # 初始化记忆书
    # 支持环境变量: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
    memory = MemoryBook(
        db_path="memory_tree.db",
        api_key="pk-c6e31ff0-772e-4fe7-b8d6-b48fe1363dfa",
        base_url="http://ai-api.jdcloud.com/v1",
        model="JoyAI-Code",
    )

    print("=" * 60)
    print("MemoryTree - 自组织Agent记忆框架")
    print("=" * 60)

    # ========== 1. 保存记忆 ==========
    print("\n>>> 保存记忆...")

    memories = [
        "我喜欢Java",
        "最近在研究Spring AI",
        "计划开发Agent框架",
        "自组织记忆树不需要向量数据库",
        "Agent需要记忆系统来保持上下文",
        "MCP协议可以让Agent调用外部工具",
        "Workflow是Agent编排的重要模式",
        "我在考虑创业方向，可能做AI相关的SaaS",
        "游戏也是一个可能的创业方向",
        "Spring Boot 3.x已经全面支持GraalVM原生镜像",
    ]

    for m in memories:
        result = memory.save(m)
        print(f"  保存: '{m}' -> {result['node_path']} ({result.get('reason', '')})")

    # ========== 2. 查看记忆树 ==========
    print("\n>>> 当前记忆树:")
    memory.print_tree()

    # ========== 3. 查询记忆 ==========
    print("\n>>> 查询记忆...")

    questions = [
        "我之前聊过创业吗",
        "我了解哪些Agent相关技术",
        "我之前聊过Memory框架吗",
    ]

    for q in questions:
        print(f"\n  问题: {q}")
        result = memory.query(q)
        print(f"  回答: {result['answer']}")
        if result.get("memory_nodes"):
            for node in result["memory_nodes"]:
                print(f"  相关节点: {node['path']} ({node['item_count']}条记忆)")

    # ========== 4. 统计信息 ==========
    print("\n>>> 统计信息:")
    stats = memory.get_stats()
    print(f"  节点数: {stats['total_nodes']}")
    print(f"  记忆条数: {stats['total_items']}")
    print(f"  总Token数: {stats['total_tokens']}")

    # ========== 5. 自动整理 ==========
    print("\n>>> 自动整理...")
    organize_result = memory.organize()
    print(f"  裂变: {len(organize_result['split'])}个")
    for s in organize_result["split"]:
        print(f"    {s['node']} -> {s['sub_nodes']}")
    print(f"  合并: {len(organize_result['merged'])}个")
    for m in organize_result["merged"]:
        print(f"    {m['node_a']} + {m['node_b']} -> {m['merged_name']}")
    print(f"  摘要更新: {len(organize_result['summary_updated'])}个")
    if organize_result["errors"]:
        print(f"  错误: {organize_result['errors']}")

    # ========== 6. 整理后的记忆树 ==========
    print("\n>>> 整理后的记忆树:")
    memory.print_tree()

    memory.close()
    print("\n完成!")


if __name__ == "__main__":
    main()