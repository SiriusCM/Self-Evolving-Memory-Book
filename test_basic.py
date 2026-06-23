"""基础功能测试"""
import os
from memory_book.db import Database

# 清理旧的测试数据库
if os.path.exists("test_memory.db"):
    os.remove("test_memory.db")

db = Database("test_memory.db")
root_id = db.get_root_id()
print(f"根节点ID: {root_id}")

# 创建子节点
tech_id = db.create_node("技术", root_id)
java_id = db.create_node("Java", tech_id)
spring_id = db.create_node("Spring", java_id)
ai_id = db.create_node("AI", tech_id)
biz_id = db.create_node("创业", root_id)

print(f"技术节点ID: {tech_id}")
print(f"Java节点ID: {java_id}")
print(f"Spring节点ID: {spring_id}")

# 创建记忆项
db.create_item(java_id, "我喜欢Java")
db.create_item(spring_id, "最近在研究Spring AI")
db.create_item(ai_id, "自组织记忆树不需要向量数据库")

# 路径测试
path = db.get_node_path(spring_id)
print(f"路径: {path}")

# 路径查找
node = db.find_node_by_path("技术/Java/Spring")
print(f"路径查找: {node['name'] if node else None}")

# Token统计
spring_node = db.get_node(spring_id)
print(f"Spring节点tokens: {spring_node['token_count']}")

# 子节点测试
children = db.get_children(tech_id)
print(f"技术子节点: {[c['name'] for c in children]}")

# 树摘要测试
from memory_book.core import MemoryTree
memory = MemoryTree.__new__(MemoryTree)
memory.db = db
tree_text = memory.get_tree_summary()
print(f"\n记忆树:\n{tree_text}")

# 统计
stats = memory.get_stats()
print(f"\n统计: {stats}")

db.close()
os.remove("test_memory.db")
print("\n所有测试通过!")