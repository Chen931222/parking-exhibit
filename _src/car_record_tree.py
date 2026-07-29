class CarRecordNode:
    def __init__(self, plate):
        self.plate = plate
        # 每筆紀錄格式：{"in": str, "out": str or None}
        self.records = []  # 用來儲存進場與離場紀錄
        self.left = None    # 左子節點
        self.right = None   # 右子節點


class CarRecordTree:
    def __init__(self):
        self.root = None  # 初始化為空樹

    def _insert_node(self, node, plate):
        # 插入車輛節點到二元搜尋樹
        if node is None:
            return CarRecordNode(plate)
        if plate < node.plate:
            node.left = self._insert_node(node.left, plate)
        elif plate > node.plate:
            node.right = self._insert_node(node.right, plate)
        return node

    def _search(self, node, plate):
        # 在二元搜尋樹中查找車牌對應的節點
        if node is None:
            return None
        if plate == node.plate:
            return node
        if plate < node.plate:
            return self._search(node.left, plate)
        else:
            return self._search(node.right, plate)

    # 進場紀錄
    def add_enter_record(self, plate, in_time):
        # 確保該車輛節點存在於二元搜尋樹中
        self.root = self._insert_node(self.root, plate)
        node = self._search(self.root, plate)
        if node is None:
            return
        # 檢查車輛是否已經有未結束的進場紀錄
        for record in node.records:
            if record["out"] is None:
                # 如果已經有進場但尚未離場的紀錄，則忽略這次進場
                print(f"車輛 {plate} 已經進場，無法重複進場。")
                return
        
        # 如果沒有未結束的紀錄，新增進場紀錄
        node.records.append({"in": in_time, "out": None})

    # 離場紀錄
    def add_leave_record(self, plate, out_time):
        node = self._search(self.root, plate)
        if node is None:
            # 沒有這台車的任何紀錄，就創一筆「未知進場時間」
            self.root = self._insert_node(self.root, plate)
            node = self._search(self.root, plate)
        # 從最後一筆往前找 out = None 的紀錄
        target_record = None
        for r in reversed(node.records):
            
            if r["out"] is None:
                target_record = r
                break
        if target_record is not None:
            target_record["out"] = out_time
        else:
            # 理論上不太會發生：沒有未完成紀錄，但卻離場
            node.records.append({"in": "未知", "out": out_time})

    # 查詢紀錄
    def find_records(self, plate):
        node = self._search(self.root, plate)
        if node is None:
            return None
        return node.records

    # 以中序走訪回傳所有車牌節點（照車牌排序）
    def _inorder(self, node, result):
        if node is None:
            return
        self._inorder(node.left, result)
        result.append(node)
        self._inorder(node.right, result)

    def get_all_nodes(self):
        """
        回傳所有車輛節點（排序後）
        """
        result = []
        self._inorder(self.root, result)
        return result
