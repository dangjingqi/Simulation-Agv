# save as Test/fake_agv.py
import paho.mqtt.client as mqtt
import time
import json
import threading
import math

# ========== 配置 ==========
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# 充电桩位置列表（与前端保持一致）
CHARGERS = [
    {"id": "charger_1", "x": -40, "y": -50},
    {"id": "charger_2", "x": 40, "y": 50},
    {"id": "charger_3", "x": -20, "y": -20}
]

# ========== 多车配置 ==========
AGV_LIST = [
    {"id": "001", "x": 0, "y": 0, "battery": 85, "status": "idle", "speed": 0, "target_x": None, "target_y": None},
    {"id": "002", "x": -20, "y": 30, "battery": 92, "status": "idle", "speed": 0, "target_x": None, "target_y": None},
    {"id": "003", "x": 40, "y": -15, "battery": 78, "status": "idle", "speed": 0, "target_x": None, "target_y": None},
]

agv_clients = {}
agv_status = {agv["id"]: agv for agv in AGV_LIST}

# ========== 辅助函数 ==========
def publish_status(agv_id, client):
    """上报 AGV 状态"""
    status = agv_status[agv_id]
    status["timestamp"] = time.time()
    payload = json.dumps({
        "agv_id": agv_id,
        "battery": round(status["battery"], 1),
        "x": round(status["x"], 1),
        "y": round(status["y"], 1),
        "speed": status["speed"],
        "status": status["status"],
        "timestamp": status["timestamp"]
    })
    client.publish(f"agv/{agv_id}/status", payload)
    print(f"[{agv_id}] 📤 上报: 电量={status['battery']:.1f}%, 位置=({status['x']:.1f},{status['y']:.1f}), 状态={status['status']}")

def find_nearest_charger(x, y):
    """找到最近的充电桩"""
    nearest = None
    min_dist = float('inf')
    for charger in CHARGERS:
        dx = charger["x"] - x
        dy = charger["y"] - y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < min_dist:
            min_dist = dist
            nearest = charger
    return nearest, min_dist

def update_movement(agv_id):
    """更新 AGV 移动逻辑（点到点）"""
    status = agv_status[agv_id]
    if status["status"] != "moving":
        return
    
    target_x = status.get("target_x")
    target_y = status.get("target_y")
    
    if target_x is None or target_y is None:
        # 没有目标点，停止
        status["status"] = "idle"
        status["speed"] = 0
        return
    
    # 计算距离和方向
    dx = target_x - status["x"]
    dy = target_y - status["y"]
    distance = math.sqrt(dx*dx + dy*dy)
    
    if distance < 0.5:
        # 到达目标点
        status["x"] = target_x
        status["y"] = target_y
        status["status"] = "idle"
        status["speed"] = 0
        status["target_x"] = None
        status["target_y"] = None
        print(f"[{agv_id}] ✅ 已到达目标点 ({target_x:.1f}, {target_y:.1f})")
        
        # 检查是否到达充电桩（自动开始充电）
        nearest_charger, dist_to_charger = find_nearest_charger(status["x"], status["y"])
        if dist_to_charger < 1.0:
            print(f"[{agv_id}] 🔋 已到达充电桩，开始充电")
            status["status"] = "charging"
            status["speed"] = 0
        return
    
    # 向目标点移动（速度 2 米/秒）
    speed = 2.0
    step = min(speed, distance)
    status["x"] += (dx / distance) * step
    status["y"] += (dy / distance) * step
    status["speed"] = speed

def update_battery(agv_id):
    """更新电量逻辑"""
    status = agv_status[agv_id]
    
    if status["status"] == "moving":
        # 移动时耗电
        status["battery"] -= 0.15
    elif status["status"] == "charging":
        # 充电时增加
        old_battery = status["battery"]
        status["battery"] += 1.2
        
        if int(old_battery) != int(status["battery"]):
            print(f"[{agv_id}] 🔋 充电中: {status['battery']:.1f}%")
        
        # 充满后自动切换为空闲
        if status["battery"] >= 95:
            status["status"] = "idle"
            status["speed"] = 0
            status["battery"] = 100
            print(f"[{agv_id}] ✅ 充电完成，电量100%")
    
    # 限制电量范围
    status["battery"] = max(0, min(100, status["battery"]))
    
    # 低电量告警
    if status["battery"] < 20 and status["status"] != "charging":
        print(f"[{agv_id}] ⚠️ 低电量告警: {status['battery']:.1f}%")

# ========== MQTT 回调 ==========
def create_on_message(agv_id):
    """为每个 AGV 创建独立的 on_message 回调"""
    def on_message(client, userdata, msg):
        payload = msg.payload.decode()
        print(f"[{agv_id}] 📥 收到指令: {payload}")
        
        try:
            data = json.loads(payload)
            command = data.get("command")
            params = data.get("params", {})
            status = agv_status[agv_id]
            
            if command == "move":
                # 点对点移动（需要配合地图点击）
                target_x = params.get("x", status.get("target_x", status["x"]))
                target_y = params.get("y", status.get("target_y", status["y"]))
                status["target_x"] = target_x
                status["target_y"] = target_y
                status["status"] = "moving"
                status["speed"] = 2.0
                print(f"[{agv_id}] 🎯 目标点: ({target_x:.1f}, {target_y:.1f})")
                
            elif command == "move_to":
                target_x = params.get("x", status.get("target_x", status["x"]))
                target_y = params.get("y", status.get("target_y", status["y"]))
                status["target_x"] = target_x
                status["target_y"] = target_y
                status["status"] = "moving"
                status["speed"] = 2.0
                print(f"[{agv_id}] 🎯 目标点: ({target_x:.1f}, {target_y:.1f})")
                
            elif command == "stop":
                status["status"] = "idle"
                status["speed"] = 0
                status["target_x"] = None
                status["target_y"] = None
                print(f"[{agv_id}] 🛑 停止")
                
            elif command == "charge":
                # 充电指令：自动前往最近充电桩
                x = status["x"]
                y = status["y"]
                nearest_charger, distance = find_nearest_charger(x, y)
                if nearest_charger:
                    print(f"[{agv_id}] 🔋 前往最近充电桩 {nearest_charger['id']}，距离 {distance:.1f} 米")
                    status["target_x"] = nearest_charger["x"]
                    status["target_y"] = nearest_charger["y"]
                    status["status"] = "moving"
                    status["speed"] = 2.0
                else:
                    print(f"[{agv_id}] ❌ 未找到可用充电桩")
                
            elif command == "status":
                print(f"[{agv_id}] 📋 主动上报状态")
                
            publish_status(agv_id, client)
            
        except Exception as e:
            print(f"[{agv_id}] ❌ 解析指令出错: {e}")
    
    return on_message

def start_agv(agv_info):
    """启动单个 AGV 的 MQTT 客户端和状态更新线程"""
    agv_id = agv_info["id"]
    
    # 创建 MQTT 客户端
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = create_on_message(agv_id)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe(f"agv/{agv_id}/command")
    client.loop_start()
    
    agv_clients[agv_id] = client
    print(f"[{agv_id}] ✅ MQTT 客户端已启动")
    
    # 状态更新线程
    def update_loop():
        while True:
            update_movement(agv_id)
            update_battery(agv_id)
            publish_status(agv_id, client)
            time.sleep(1)
    
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()
    print(f"[{agv_id}] ✅ 状态更新线程已启动")

# ========== 主程序 ==========
def main():
    print("=" * 50)
    print("🚀 多车模拟 AGV 启动（自动寻桩充电）")
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print("=" * 50)
    
    for agv in AGV_LIST:
        start_agv(agv)
    
    print(f"\n✅ 共启动 {len(AGV_LIST)} 台模拟 AGV")
    print("车辆列表:")
    for agv in AGV_LIST:
        print(f"   - AGV {agv['id']}: 初始位置 ({agv['x']}, {agv['y']})")
    
    print("\n充电桩列表:")
    for charger in CHARGERS:
        print(f"   - {charger['id']}: ({charger['x']}, {charger['y']})")
    
    print("\n🎯 功能说明:")
    print("   - 点击地图选择目标点，AGV 自动移动")
    print("   - 点击【充电】按钮，AGV 自动前往最近充电桩")
    print("   - 到达充电桩后自动开始充电，电量增加")
    print("   - 充满后自动切换为空闲状态")
    print("   - 多车独立控制，互不干扰")
    print("\n按 Ctrl+C 停止...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 所有模拟 AGV 已停止")
        for agv_id, client in agv_clients.items():
            client.disconnect()

if __name__ == "__main__":
    main()