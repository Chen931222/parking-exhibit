# 檔名：main.py
from datetime import datetime

from parking_stack import ParkingStack
from waiting_queue import WaitingQueue
from car_record_tree import CarRecordTree


# 車輛資料結構
class Car:
    def __init__(self, plate, is_disabled=False, enter_time=None):
        self.plate = plate
        self.is_disabled = is_disabled
        self.enter_time = enter_time or datetime.now()

    def __repr__(self):
        t = self.enter_time.strftime("%H:%M:%S")
        return f"{self.plate} (進場 {t}, 身障={self.is_disabled})"


# 停車場主系統
class ParkingLot:
    def __init__(self, normal_cap, disabled_cap, waiting_cap=None):
        self.normal_area = ParkingStack(normal_cap)      # 一般車位
        self.disabled_area = ParkingStack(disabled_cap)  # 身障車位
        self.waiting_queue = WaitingQueue(waiting_cap)   # 外面排隊
        self.record_tree = CarRecordTree()               # BST 紀錄

    def car_enter(self, plate, is_disabled):
        car = Car(plate, is_disabled)

        # 現在的規則：
        # 身障車優先身障區，其次一般區，再不行才排隊
        if is_disabled:
            if not self.disabled_area.is_full():
                self.disabled_area.push(car)
                #  進場就記錄 in_time
                self.record_tree.add_enter_record(
                    car.plate,
                    car.enter_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                print(f" 身障車 {plate} 已停入『身障車位』")
                return

            elif not self.normal_area.is_full():
                self.normal_area.push(car)
                self.record_tree.add_enter_record(
                    car.plate,
                    car.enter_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                print(f"身障車位滿，{plate} 停入『一般區』")
                return

            else:
                self._enqueue_waiting(car)
                return

        else:
            if not self.normal_area.is_full():
                self.normal_area.push(car)
                self.record_tree.add_enter_record(
                    car.plate,
                    car.enter_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                print(f"一般車 {plate} 已停入『一般區』")
                return
            else:
                self._enqueue_waiting(car)
                return


    def _enqueue_waiting(self, car):
        if self.waiting_queue.enqueue(car):
            print(f" 停車場滿，車牌 {car.plate} 排入等待區")
        else:
            print(f" 等待區滿，無法接收車牌 {car.plate}")

   
    def car_leave(self, plate):
        # 找在哪一區
        area = None
        if self.disabled_area.find_car_index(plate) is not None:
            area = self.disabled_area
            area_name = "身障車位"
        elif self.normal_area.find_car_index(plate) is not None:
            area = self.normal_area
            area_name = "一般車位"
        else:
            print(f"場內找不到車牌 {plate}")
            return

        print(f"車輛 {plate} 在「{area_name}」，準備離場...")

        temp_stack = []

        # 將上方車輛逐台搬出
        while True:
            top = area.pop()
            if top.plate == plate:
                target_car = top
                break
            temp_stack.append(top)

        # 記錄離場
        out_time = datetime.now()
        
        self.record_tree.add_leave_record(
            target_car.plate,
            out_time.strftime("%Y-%m-%d %H:%M:%S")
        )

        print(f"車輛 {plate} 已離場完成")

        # 將其他車放回去
        while temp_stack:
            area.push(temp_stack.pop())

        # 排隊車進場
        if not self.waiting_queue.is_empty():
            next_car = self.waiting_queue.dequeue()
            next_car.enter_time = datetime.now()
            print(f"🚘 排隊車 {next_car.plate} 進入停車場")

            self.car_enter(next_car.plate, next_car.is_disabled)

   
    def show_area(self):
        print("\n=== 身障區 ===")
        cars = self.disabled_area.get_all_cars()
        if not cars:
            print("（空）")
        else:
            for c in cars:
                print(c)

        print("\n=== 一般區 ===")
        cars = self.normal_area.get_all_cars()
        if not cars:
            print("（空）")
        else:
            for c in cars:
                print(c)

    def show_waiting(self):
        print("\n=== 排隊區 ===")
        cars = self.waiting_queue.get_all_cars()
        if not cars:
            print("（無人排隊）")
        else:
            for c in cars:
                print(c)

    def search_record(self, plate):
        records = self.record_tree.find_records(plate)
        if records is None:
            print(f"沒有車牌 {plate} 的紀錄")
            return

        print(f"\n 車牌 {plate} 歷史紀錄：")
        for r in records:
            out_text = r["out"] if r["out"] is not None else "（尚未離場）"
            print(f"進：{r['in']}    離：{out_text}")


    def show_all_records(self):
        print("\n=== 所有車牌紀錄（排序後） ===")
        nodes = self.record_tree.get_all_nodes()
        if not nodes:
            print("（尚無紀錄）")
            return
        for node in nodes:
            print(f"\n車牌：{node.plate}")
            for r in node.records:
                out_text = r["out"] if r["out"] is not None else "（尚未離場）"
                print(f"  進：{r['in']}    離：{out_text}")

import re

def is_valid_plate(plate: str) -> bool:
    # 新正則表達式：允許 ABC-1234 或 AB-1234 或 1234-AB
    pattern = r"^[A-Z]{2,3}-\d{4}$|^\d{4}-[A-Z]{2,3}$"
    return bool(re.match(pattern, plate))

def menu():
    print("\n===== 停車場系統 =====")
    print("1. 車輛進場")
    print("2. 車輛離場")
    print("3. 顯示目前停車狀況")
    print("4. 顯示排隊車輛")
    print("5. 查詢車牌歷史紀錄（BST）")
    print("6. 顯示所有紀錄")
    print("0. 離開")
    print("=======================")


def main():
    lot = ParkingLot(normal_cap=5, disabled_cap=2, waiting_cap=5)

    while True:
        menu()
        op = input("請選擇： ").strip()

        if op == "1":
            plate = input("輸入車牌（只可含英文大寫、數字與-，格式為:ABC-1234、AB-1234、1234-AB））： ").strip().upper()
            if not is_valid_plate(plate):
                print("車牌格式不合法，請重新輸入")
                continue
            dis = input("是否身障車？(y/n)： ").strip().lower()
            is_dis = (dis == "y")
            lot.car_enter(plate, is_dis)
        elif op == "2":
            plate = input("輸入離場車牌： ").strip()
            lot.car_leave(plate)

        elif op == "3":
            lot.show_area()

        elif op == "4":
            lot.show_waiting()

        elif op == "5":
            plate = input("輸入車牌： ").strip()
            lot.search_record(plate)

        elif op == "6":
            lot.show_all_records()

        elif op == "0":
            print("系統已退出")
            break

        else:
            print("無效輸入")


if __name__ == "__main__":
    main()
