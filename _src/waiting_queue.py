from collections import deque

class WaitingQueue:
    def __init__(self, capacity=None):
        self.capacity = capacity
        self.queue = deque()

    def is_empty(self):
        return len(self.queue) == 0

    def is_full(self):
        if self.capacity is None:
            return False
        return len(self.queue) >= self.capacity

    def enqueue(self, car):
        if self.is_full():
            return False
        self.queue.append(car)
        return True

    def dequeue(self):
        if self.is_empty():
            return None
        return self.queue.popleft()

    def get_all_cars(self):
        return list(self.queue)
