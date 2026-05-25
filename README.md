# AGV 云控平台

基于 MQTT + Flask + ROS2 的 AGV 云控平台，支持：
- 模拟 AGV 控制
- 实时状态监控
- Web 可视化界面
- Gazebo 仿真集成

## 技术栈
- Python
- MQTT (mosquitto)
- Flask
- ROS2 + Gazebo

## 快速开始
```bash
# 安装依赖
pip install -r requirements.txt

# 启动云控平台
python cloud.py

# 启动模拟 AGV
python fake_agv.py
