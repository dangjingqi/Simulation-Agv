# save as Test/fake_agv.py
import paho.mqtt.client as mqtt
import time
import random
import json

# AGV 配置
AGV_ID = "001"

# 创建 MQTT 客户端，和和到指定回调函数版本，避免警告
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)

#f在字符串中嵌入变量
print(f"模拟 AGV {AGV_ID} 启动，开始上报状态...")
print("按 Ctrl+C 停止")

#执行主代码，如果出错或被中断，执行except
try:
    while True:
        # 模拟小车状态
        status = {
            "agv_id": AGV_ID,
            "battery": random.randint(80, 100),      # 电量 80-100%
            "x": round(random.uniform(0, 100), 1),   # X坐标 0-100
            "y": round(random.uniform(0, 100), 1),   # Y坐标 0-100
            "speed": round(random.uniform(0, 1.5), 1), # 速度 0-1.5 m/s
            "status": random.choice(["idle", "moving", "charging"]),
            "timestamp": time.time()
        }
        
        # 发布到主题 agv/001/status
        # .publish(主题名，数据)    主题名是agv/id/status,将Python字典转为Json字符串
        client.publish(f"agv/{AGV_ID}/status", json.dumps(status))

        print(f"上报: {status}")
        
        time.sleep(3)  # 每3秒上报一次

#KeyboardInterrupt，用户按ctrl+c触发的异常     
except KeyboardInterrupt:
    print("\n模拟 AGV 已停止")
    #断开MQTT连接
    client.disconnect()