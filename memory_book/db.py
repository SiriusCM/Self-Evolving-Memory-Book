"""数据库模型层 - SQLite schema + 基础CRUD操作"""

import sqlite3
from datetime import datetime
from typing import Optional


class Database:
    """SQLite数据库管理"""

    def __init__(self, db_path: str = "memory_book.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self):
        """初始化数据库表"""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_node (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER,
                name TEXT NOT NULL,
                summary TEXT DEFAULT '',
                token_count INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES memory_node(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (node_id) REFERENCES memory_node(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_node_parent
            ON memory_node(parent_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_item_node
            ON memory_item(node_id)
        """)

        # 确保ROOT节点存在
        cursor.execute("SELECT id FROM memory_node WHERE parent_id IS NULL AND level = 0")
        root = cursor.fetchone()
        if not root:
            cursor.execute("""
                INSERT INTO memory_node (name, summary, token_count, level)
                VALUES ('ROOT', '根节点', 0, 0)
            """)

        self.conn.commit()

    def get_root_id(self) -> int:
        """获取根节点ID"""
        cursor = self.conn.execute(
            "SELECT id FROM memory_node WHERE parent_id IS NULL AND level = 0"
        )
        row = cursor.fetchone()
        return row["id"]

    # ==================== Node 操作 ====================

    def create_node(
        self,
        name: str,
        parent_id: int,
        summary: str = "",
        token_count: int = 0,
    ) -> int:
        """创建新节点"""
        parent = self.get_node(parent_id)
        level = (parent["level"] or 0) + 1 if parent else 0

        cursor = self.conn.execute(
            """INSERT INTO memory_node (name, parent_id, summary, token_count, level)
               VALUES (?, ?, ?, ?, ?)""",
            (name, parent_id, summary, token_count, level),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_node(self, node_id: int) -> Optional[sqlite3.Row]:
        """获取节点"""
        cursor = self.conn.execute("SELECT * FROM memory_node WHERE id = ?", (node_id,))
        return cursor.fetchone()

    def update_node(
        self,
        node_id: int,
        name: Optional[str] = None,
        summary: Optional[str] = None,
        token_count: Optional[int] = None,
    ):
        """更新节点"""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        if token_count is not None:
            updates.append("token_count = ?")
            params.append(token_count)

        if not updates:
            return

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(node_id)

        self.conn.execute(
            f"UPDATE memory_node SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self.conn.commit()

    def delete_node(self, node_id: int):
        """删除节点（级联删除子节点和记忆项）"""
        self.conn.execute("DELETE FROM memory_node WHERE id = ?", (node_id,))
        self.conn.commit()

    def get_children(self, parent_id: int) -> list[sqlite3.Row]:
        """获取子节点列表"""
        cursor = self.conn.execute(
            "SELECT * FROM memory_node WHERE parent_id = ? ORDER BY name",
            (parent_id,),
        )
        return cursor.fetchall()

    def get_all_nodes(self) -> list[sqlite3.Row]:
        """获取所有节点"""
        cursor = self.conn.execute("SELECT * FROM memory_node ORDER BY level, name")
        return cursor.fetchall()

    def get_node_path(self, node_id: int) -> str:
        """获取节点路径（如：技术/Java/Spring）"""
        parts = []
        current_id = node_id
        while current_id is not None:
            node = self.get_node(current_id)
            if node is None or node["name"] == "ROOT":
                break
            parts.append(node["name"])
            current_id = node["parent_id"]
        parts.reverse()
        return "/".join(parts)

    def find_node_by_path(self, path: str) -> Optional[sqlite3.Row]:
        """根据路径查找节点（如：技术/Java/Spring）"""
        parts = path.strip("/").split("/")
        current_id = self.get_root_id()

        for part in parts:
            if not part:
                continue
            children = self.get_children(current_id)
            found = False
            for child in children:
                if child["name"] == part:
                    current_id = child["id"]
                    found = True
                    break
            if not found:
                return None

        return self.get_node(current_id)

    def move_node(self, node_id: int, new_parent_id: int):
        """移动节点到新父节点"""
        new_parent = self.get_node(new_parent_id)
        new_level = (new_parent["level"] or 0) + 1 if new_parent else 0
        old_node = self.get_node(node_id)

        self.conn.execute(
            "UPDATE memory_node SET parent_id = ?, level = ?, updated_at = ? WHERE id = ?",
            (new_parent_id, new_level, datetime.now().isoformat(), node_id),
        )

        # 递归更新子节点层级
        self._update_children_level(node_id, new_level)
        self.conn.commit()

    def _update_children_level(self, parent_id: int, parent_level: int):
        """递归更新子节点层级"""
        children = self.get_children(parent_id)
        for child in children:
            child_level = parent_level + 1
            self.conn.execute(
                "UPDATE memory_node SET level = ? WHERE id = ?",
                (child_level, child["id"]),
            )
            self._update_children_level(child["id"], child_level)

    def update_token_count(self, node_id: int):
        """更新节点的token统计"""
        cursor = self.conn.execute(
            "SELECT content FROM memory_item WHERE node_id = ?", (node_id,)
        )
        items = cursor.fetchall()
        total = sum(len(item["content"]) for item in items) // 4  # 粗略估算: 4字符≈1token
        self.update_node(node_id, token_count=total)

    def update_ancestor_token_counts(self, node_id: int):
        """更新祖先节点的token统计"""
        current_id = node_id
        while current_id is not None:
            self.update_token_count(current_id)
            node = self.get_node(current_id)
            if node is None or node["parent_id"] is None:
                break
            current_id = node["parent_id"]

    # ==================== Item 操作 ====================

    def create_item(self, node_id: int, content: str) -> int:
        """创建记忆项"""
        cursor = self.conn.execute(
            "INSERT INTO memory_item (node_id, content) VALUES (?, ?)",
            (node_id, content),
        )
        self.conn.commit()
        self.update_token_count(node_id)
        self.update_ancestor_token_counts(node_id)
        return cursor.lastrowid

    def get_items(self, node_id: int) -> list[sqlite3.Row]:
        """获取节点的所有记忆项"""
        cursor = self.conn.execute(
            "SELECT * FROM memory_item WHERE node_id = ? ORDER BY created_at",
            (node_id,),
        )
        return cursor.fetchall()

    def get_all_items(self, node_id: int) -> list[sqlite3.Row]:
        """获取节点及其所有子节点的记忆项"""
        items = list(self.get_items(node_id))
        children = self.get_children(node_id)
        for child in children:
            items.extend(self.get_all_items(child["id"]))
        return items

    def move_item(self, item_id: int, new_node_id: int):
        """移动记忆项到新节点"""
        old_item = self.conn.execute(
            "SELECT node_id FROM memory_item WHERE id = ?", (item_id,)
        ).fetchone()
        self.conn.execute(
            "UPDATE memory_item SET node_id = ? WHERE id = ?",
            (new_node_id, item_id),
        )
        self.conn.commit()
        if old_item:
            self.update_token_count(old_item["node_id"])
            self.update_ancestor_token_counts(old_item["node_id"])
        self.update_token_count(new_node_id)
        self.update_ancestor_token_counts(new_node_id)

    def delete_item(self, item_id: int):
        """删除记忆项"""
        item = self.conn.execute(
            "SELECT node_id FROM memory_item WHERE id = ?", (item_id,)
        ).fetchone()
        self.conn.execute("DELETE FROM memory_item WHERE id = ?", (item_id,))
        self.conn.commit()
        if item:
            self.update_token_count(item["node_id"])
            self.update_ancestor_token_counts(item["node_id"])

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None