class ParkingStack:
    def __init__(self, capacity: int):
        self.capacity = capacity  # 最大停車數量
        self.stack = []           # 用 list 當堆疊

    def is_full(self):
        return len(self.stack) >= self.capacity

    def is_empty(self):
        return len(self.stack) == 0

    def push(self, car):
        """車輛進場，放到堆疊頂端"""
        if self.is_full():
            return False
        self.stack.append(car)
        return True

    def pop(self):
        """車輛離場，從堆疊頂端開出去"""
        if self.is_empty():
            return None
        return self.stack.pop()

    def peek(self):
        """查看最裡面的那台車（不拿出來）"""
        if self.is_empty():
            return None
        return self.stack[-1]

    def find_car_index(self, plate: str):
        """
        尋找特定車牌在堆疊中的位置
        回傳 index（0 最底、len-1 最頂），找不到回傳 None
        """
        for i, car in enumerate(self.stack):
            if car.plate == plate:
                return i
        return None

    def get_all_cars(self):
        """回傳目前場內所有車輛（由最底到最頂）"""
        return list(self.stack)
