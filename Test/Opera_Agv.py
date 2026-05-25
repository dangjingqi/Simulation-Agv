# save as Test/Opera_Agv.py
import paho.mqtt.client as mqtt
import json
import sqlite3
import threading
import time
from flask import Flask, jsonify, render_template_string, request

# ========== 1. 数据库初始化 ==========
def init_db():
    conn = sqlite3.connect('agv.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agv_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agv_id TEXT,
            battery INTEGER,
            x REAL,
            y REAL,
            speed REAL,
            status TEXT,
            timestamp REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS command_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agv_id TEXT,
            command TEXT,
            params TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成")

def save_status(data):
    conn = sqlite3.connect('agv.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO agv_status (agv_id, battery, x, y, speed, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('agv_id'),
        data.get('battery'),
        data.get('x'),
        data.get('y'),
        data.get('speed'),
        data.get('status'),
        data.get('timestamp')
    ))
    conn.commit()
    conn.close()

def log_command(agv_id, command, params):
    conn = sqlite3.connect('agv.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO command_log (agv_id, command, params)
        VALUES (?, ?, ?)
    ''', (agv_id, command, params))
    conn.commit()
    conn.close()

# ========== 2. MQTT 配置 ==========
latest_status = {}
mqtt_client = None

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ MQTT 连接成功")
        client.subscribe("agv/+/status")
    else:
        print(f"❌ MQTT 连接失败，错误码: {reason_code}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"📥 收到: {topic} -> {payload}")
    
    try:
        data = json.loads(payload)
        save_status(data)
        agv_id = data.get('agv_id')
        if agv_id:
            latest_status[agv_id] = data
    except Exception as e:
        print(f"解析消息出错: {e}")

def start_mqtt():
    global mqtt_client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("localhost", 1883, 60)
    mqtt_client = client
    client.loop_forever()

def send_command(agv_id, command, params=None):
    if mqtt_client is None:
        print("MQTT 客户端未就绪")
        return False
    
    topic = f"agv/{agv_id}/command"
    message = {
        "command": command,
        "params": params or {},
        "from": "cloud_platform",
        "timestamp": time.time()
    }
    payload = json.dumps(message)
    mqtt_client.publish(topic, payload)
    log_command(agv_id, command, json.dumps(params or {}))
    print(f"📤 指令已发送: {topic} -> {payload}")
    return True

# ========== 3. Flask Web 服务 ==========
app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>AGV 云控平台 - 网格厂区地图</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Leaflet CSS/JS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            height: 100vh;
            overflow: hidden;
        }
        
        .navbar {
            background: linear-gradient(135deg, #1a2a4a 0%, #0f1a2e 100%);
            color: white;
            padding: 12px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 1000;
        }
        
        .navbar h1 { font-size: 1.5rem; display: flex; align-items: center; gap: 10px; }
        
        .main-container { display: flex; height: calc(100vh - 60px); }
        .map-panel { flex: 3; margin: 10px; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); background: #1a2a3a; }
        #map { height: 100%; width: 100%; background: #1a2a3a; }
        
        .info-panel { 
            flex: 1; background: white; margin: 10px 10px 10px 0; 
            border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
            display: flex; flex-direction: column; overflow-y: auto;
        }
        
        .stats-section { padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px; }
        .stat-card { background: rgba(255,255,255,0.15); border-radius: 10px; padding: 12px; text-align: center; }
        .stat-number { font-size: 28px; font-weight: bold; }
        .stat-label { font-size: 12px; opacity: 0.9; }
        
        .control-section { padding: 16px; border-bottom: 1px solid #e0e0e0; }
        .control-section h4 { margin-bottom: 12px; color: #1a2a4a; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; }
        button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: all 0.2s; }
        button:hover { opacity: 0.85; transform: translateY(-1px); }
        .btn-primary { background: #4CAF50; color: white; }
        .btn-stop { background: #ff9800; color: white; }
        .btn-info { background: #2196F3; color: white; }
        .btn-purple { background: #9C27B0; color: white; }
        
        .speed-slider { display: flex; align-items: center; gap: 10px; margin-bottom: 15px; }
        .speed-slider input { flex: 1; }
        .coord-input { display: flex; gap: 10px; margin-bottom: 15px; }
        .coord-input input { flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 6px; }
        
        .vehicle-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
            border-left: 4px solid #4CAF50;
            cursor: pointer;
        }
        .vehicle-card.selected { background: #e3f2fd; border-left-color: #2196F3; }
        .vehicle-card.moving { border-left-color: #2196F3; }
        .vehicle-card.charging { border-left-color: #ff9800; }
        .vehicle-card.battery-low { border-left-color: #f44336; }
        
        .vehicles-section { padding: 16px; flex: 1; overflow-y: auto; }
        .vehicle-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .vehicle-id { font-weight: bold; }
        .vehicle-details { font-size: 12px; color: #666; margin-bottom: 8px; }
        .vehicle-actions { display: flex; gap: 5px; flex-wrap: wrap; }
        
        @media (max-width: 900px) {
            .main-container { flex-direction: column; }
            .info-panel { margin: 0 10px 10px 10px; max-height: 50vh; }
            .map-panel { height: 400px; }
        }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>🏭 AGV 智能云控平台 - 网格厂区地图</h1>
        <div>🎮 速度可调 | 📍 点击地图移动 | 🔋 自动寻桩充电</div>
    </div>
    
    <div class="main-container">
        <div class="map-panel">
            <div id="map"></div>
        </div>
        
        <div class="info-panel">
            <div class="stats-section">
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-number" id="totalCount">0</div><div class="stat-label">在线车辆</div></div>
                    <div class="stat-card"><div class="stat-number" id="movingCount">0</div><div class="stat-label">运行中</div></div>
                    <div class="stat-card"><div class="stat-number" id="chargingCount">0</div><div class="stat-label">充电中</div></div>
                    <div class="stat-card"><div class="stat-number" id="avgBattery">0%</div><div class="stat-label">平均电量</div></div>
                </div>
            </div>
            
            <div class="control-section">
                <h4>🎮 速度控制</h4>
                <div class="speed-slider">
                    <span>🐢</span>
                    <input type="range" id="speedControl" min="0" max="2" step="0.1" value="0.8">
                    <span>🐇</span>
                    <span id="speedValue" style="width: 50px;">0.8 m/s</span>
                </div>
                
                <div class="btn-group">
                    <button class="btn-primary" onclick="moveDirection('forward')">▲ 前进</button>
                    <button class="btn-primary" onclick="moveDirection('backward')">▼ 后退</button>
                    <button class="btn-info" onclick="moveDirection('left')">◀ 左移</button>
                    <button class="btn-info" onclick="moveDirection('right')">▶ 右移</button>
                    <button class="btn-stop" onclick="sendStop()">⏹️ 停止</button>
                </div>
                
                <div class="btn-group">
                    <button class="btn-purple" onclick="rotateAgv('left')">🔄 原地左转</button>
                    <button class="btn-purple" onclick="rotateAgv('right')">🔄 原地右转</button>
                </div>
                
                <h4>🎯 点到点移动</h4>
                <div class="coord-input">
                    <input type="number" id="targetX" placeholder="目标 X 坐标" step="0.5">
                    <input type="number" id="targetY" placeholder="目标 Y 坐标" step="0.5">
                    <button class="btn-primary" onclick="moveToCoord()">移动</button>
                </div>
                <div class="btn-group">
                    <button class="btn-purple" onclick="selectAgvForMove('001')">📍 点击地图选点</button>
                </div>
            </div>
            
            <div class="vehicles-section">
                <h3>🚨 车辆状态</h3>
                <div id="vehicleList"></div>
            </div>
        </div>
    </div>

    <script>
        // ========== 网格厂区配置 ==========
        // 厂区范围：X: -50 到 50, Y: -50 到 50
        var gridConfig = {
            minX: -50, maxX: 50,
            minY: -50, maxY: 50,
            cellSize: 10,  // 网格间距 10 米
            center: { lat: 34.45, lng: 109.02 }
        };
        
        // 计算经纬度（网格坐标转实际经纬度）
        function toLatLng(x, y) {
            return {
                lat: gridConfig.center.lat + (y * 0.0008),
                lng: gridConfig.center.lng + (x * 0.0008)
            };
        }
        
        // 计算反向（经纬度转网格坐标）
        function toGridCoords(lat, lng) {
            return {
                x: (lng - gridConfig.center.lng) / 0.0008,
                y: (lat - gridConfig.center.lat) / 0.0008
            };
        }
        
        // 初始化地图
        var map = L.map('map').setView([gridConfig.center.lat, gridConfig.center.lng], 15);
        
        // 添加灰色底图（CartoDB 的暗色底图，免费且不需要 API Key）
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
            subdomains: 'abcd',
            minZoom: 1,
            maxZoom: 19
        }).addTo(map);
        
        // 添加厂区边界（半透明黑色背景，突出网格）
        var bounds = [
            toLatLng(gridConfig.minX, gridConfig.minY),
            toLatLng(gridConfig.maxX, gridConfig.maxY)
        ];
        L.rectangle(bounds, {
            color: "#4a6a7a",
            weight: 2,
            fillColor: "#1a2a3a",
            fillOpacity: 0.7
        }).addTo(map);
        
        // ========== 绘制网格线 ==========
        // 纵向网格线（固定 X，Y 变化）
        for (var x = gridConfig.minX; x <= gridConfig.maxX; x += gridConfig.cellSize) {
            var start = toLatLng(x, gridConfig.minY);
            var end = toLatLng(x, gridConfig.maxY);
            L.polyline([[start.lat, start.lng], [end.lat, end.lng]], {
                color: "#6a8aaa",
                weight: 1,
                opacity: 0.6
            }).addTo(map);
        }
        
        // 横向网格线（固定 Y，X 变化）
        for (var y = gridConfig.minY; y <= gridConfig.maxY; y += gridConfig.cellSize) {
            var start = toLatLng(gridConfig.minX, y);
            var end = toLatLng(gridConfig.maxX, y);
            L.polyline([[start.lat, start.lng], [end.lat, end.lng]], {
                color: "#6a8aaa",
                weight: 1,
                opacity: 0.6
            }).addTo(map);
        }
        
        // 添加坐标轴标签（在网格交叉点显示坐标）
        for (var x = -40; x <= 40; x += 20) {
            for (var y = -40; y <= 40; y += 20) {
                var pos = toLatLng(x, y);
                L.marker([pos.lat, pos.lng], {
                    icon: L.divIcon({
                        html: `<div style="background:rgba(0,0,0,0.6);color:#aaa;font-size:9px;padding:2px 4px;border-radius:4px;">(${x},${y})</div>`,
                        iconSize: [50, 20]
                    })
                }).addTo(map);
            }
        }
        
        // ========== 厂区设施定义 ==========
        // 货架区（用半透明矩形表示）
        var rackAreas = [
            { name: '📦 货架区 A', x: -35, y: -35, width: 15, height: 15, color: '#8B5A2B' },
            { name: '📦 货架区 B', x: -35, y: 20, width: 15, height: 15, color: '#8B5A2B' },
            { name: '📦 货架区 C', x: 20, y: -35, width: 15, height: 15, color: '#8B5A2B' },
            { name: '📦 货架区 D', x: 20, y: 20, width: 15, height: 15, color: '#8B5A2B' },
            { name: '📦 货架区 E', x: -10, y: -10, width: 8, height: 8, color: '#A0522D' }
        ];
        
        rackAreas.forEach(rack => {
            var rectBounds = [
                toLatLng(rack.x, rack.y),
                toLatLng(rack.x + rack.width, rack.y + rack.height)
            ];
            L.rectangle(rectBounds, {
                color: rack.color,
                weight: 1,
                fillColor: rack.color,
                fillOpacity: 0.5
            }).addTo(map).bindPopup(rack.name);
        });
        
        // 充电桩位置
        var chargers = [
            { id: 'charger_1', name: '🔋 充电桩 1', x: -40, y: 40, color: '#FFD700' },
            { id: 'charger_2', name: '🔋 充电桩 2', x: 40, y: 40, color: '#FFD700' },
            { id: 'charger_3', name: '🔋 充电桩 3', x: -40, y: -40, color: '#FFD700' },
            { id: 'charger_4', name: '🔋 充电桩 4', x: 40, y: -40, color: '#FFD700' },
            { id: 'charger_5', name: '🔋 充电桩 5', x: 0, y: -45, color: '#FFD700' }
        ];
        
        chargers.forEach(c => {
            var pos = toLatLng(c.x, c.y);
            var icon = L.divIcon({
                html: `<div style="background:${c.color};color:#333;padding:4px 8px;border-radius:20px;font-weight:bold;font-size:11px;">⚡ ${c.name}</div>`,
                iconSize: [80, 25]
            });
            L.marker([pos.lat, pos.lng], { icon: icon }).addTo(map);
        });
        
        // 工作站
        var stations = [
            { name: '🏭 工作站 1', x: -45, y: 0, color: '#4A90D9' },
            { name: '🏭 工作站 2', x: 45, y: 0, color: '#4A90D9' },
            { name: '🏭 工作站 3', x: 0, y: 45, color: '#4A90D9' }
        ];
        
        stations.forEach(s => {
            var pos = toLatLng(s.x, s.y);
            var icon = L.divIcon({
                html: `<div style="background:${s.color};color:white;padding:4px 8px;border-radius:20px;font-size:11px;">${s.name}</div>`,
                iconSize: [80, 25]
            });
            L.marker([pos.lat, pos.lng], { icon: icon }).addTo(map);
        });
        
        // 添加道路指示线（用虚线连接主要点）
        var roadPoints = [
            [-40, 0], [-20, 0], [0, 0], [20, 0], [40, 0],
            [0, -40], [0, -20], [0, 20], [0, 40]
        ];
        for (var i = 0; i < roadPoints.length - 1; i++) {
            var p1 = toLatLng(roadPoints[i][0], roadPoints[i][1]);
            var p2 = toLatLng(roadPoints[i+1][0], roadPoints[i+1][1]);
            L.polyline([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
                color: "#FFD700",
                weight: 1.5,
                opacity: 0.5,
                dashArray: "5, 5"
            }).addTo(map);
        }
        
        // ========== 全局变量 ==========
        var agvMarkers = {};
        var vehicles = {};
        var selectedAgvId = null;
        var pendingMoveAgv = null;
        var currentSpeed = 0.8;
        
        // 速度滑块
        var speedSlider = document.getElementById('speedControl');
        var speedValue = document.getElementById('speedValue');
        speedSlider.oninput = function() {
            currentSpeed = parseFloat(this.value);
            speedValue.innerText = currentSpeed.toFixed(1) + ' m/s';
        };
        
        function getAgvIcon(battery, status) {
            var color, iconChar;
            if (battery < 20) { color = '#f44336'; iconChar = '⚠️'; }
            else if (status === 'moving') { color = '#2196F3'; iconChar = '🚚'; }
            else if (status === 'charging') { color = '#ff9800'; iconChar = '⚡'; }
            else { color = '#4CAF50'; iconChar = '🚗'; }
            
            var html = `<div style="position:relative;">
                <div style="background:${color};width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:18px;border:2px solid white;box-shadow:0 0 10px ${color};">
                    ${iconChar}
                </div>
                <div style="position:absolute;bottom:-20px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.7);color:white;padding:2px 6px;border-radius:10px;font-size:10px;">
                    ${Math.round(battery)}%
                </div>
            </div>`;
            return L.divIcon({ html: html, iconSize: [36, 45], className: 'agv-marker', popupAnchor: [0, -15] });
        }
        
        function sendCommand(agvId, command, params) {
            fetch('/api/send_command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agv_id: agvId, command: command, params: params || {} })
            }).then(r => r.json()).then(data => {
                if(data.success) showToast(`✅ ${command}`, 'success');
                else showToast(`❌ ${data.message}`, 'error');
            });
        }
        
        function moveDirection(direction) {
            if (!selectedAgvId && Object.keys(vehicles).length === 1) {
                selectedAgvId = Object.keys(vehicles)[0];
            }
            if (!selectedAgvId) { showToast('请先点击选择车辆', 'error'); return; }
            sendCommand(selectedAgvId, 'move', { speed: currentSpeed, direction: direction });
        }
        
        function sendStop() {
            if (!selectedAgvId && Object.keys(vehicles).length === 1) {
                selectedAgvId = Object.keys(vehicles)[0];
            }
            if (!selectedAgvId) return;
            sendCommand(selectedAgvId, 'stop');
        }
        
        function rotateAgv(direction) {
            if (!selectedAgvId && Object.keys(vehicles).length === 1) {
                selectedAgvId = Object.keys(vehicles)[0];
            }
            if (!selectedAgvId) return;
            var angular = direction === 'left' ? 0.8 : -0.8;
            sendCommand(selectedAgvId, 'rotate', { angular: angular });
            setTimeout(() => sendCommand(selectedAgvId, 'stop'), 1000);
        }
        
        function moveToCoord() {
            if (!selectedAgvId && Object.keys(vehicles).length === 1) {
                selectedAgvId = Object.keys(vehicles)[0];
            }
            if (!selectedAgvId) { showToast('请先点击选择车辆', 'error'); return; }
            var x = parseFloat(document.getElementById('targetX').value);
            var y = parseFloat(document.getElementById('targetY').value);
            if (isNaN(x) || isNaN(y)) { showToast('请输入有效坐标', 'error'); return; }
            sendCommand(selectedAgvId, 'move_to', { x: x, y: y });
        }
        
        function sendMoveTo(agvId, x, y) {
            sendCommand(agvId, 'move_to', { x: x, y: y });
        }
        
        function sendChargeToNearest(agvId, agvX, agvY) {
            var nearest = null;
            var minDist = Infinity;
            chargers.forEach(c => {
                var dx = c.x - agvX;
                var dy = c.y - agvY;
                var dist = Math.sqrt(dx*dx + dy*dy);
                if (dist < minDist) { minDist = dist; nearest = c; }
            });
            if (nearest) {
                showToast(`🔋 前往 ${nearest.name}，距离 ${minDist.toFixed(1)} 米`, 'success');
                sendMoveTo(agvId, nearest.x, nearest.y);
            } else {
                showToast('❌ 未找到充电桩', 'error');
            }
        }
        
        function showToast(msg, type) {
            var toast = document.createElement('div');
            toast.textContent = msg;
            toast.style.position = 'fixed';
            toast.style.bottom = '20px';
            toast.style.left = '50%';
            toast.style.transform = 'translateX(-50%)';
            toast.style.background = type === 'success' ? '#4CAF50' : '#f44336';
            toast.style.color = 'white';
            toast.style.padding = '10px 24px';
            toast.style.borderRadius = '30px';
            toast.style.zIndex = 9999;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2000);
        }
        
        function selectAgv(agvId) {
            selectedAgvId = agvId;
            updateUI();
            showToast(`已选中 ${agvId}`, 'success');
        }
        
        function selectAgvForMove(agvId) {
            pendingMoveAgv = agvId;
            showToast(`请在地图上点击目标位置`, 'success');
        }
        
        function updateUI() {
            var vehiclesArray = Object.values(vehicles);
            var movingCount = vehiclesArray.filter(v => v.status === 'moving').length;
            var chargingCount = vehiclesArray.filter(v => v.status === 'charging').length;
            var totalBattery = vehiclesArray.reduce((sum, v) => sum + (v.battery || 0), 0);
            var avgBattery = vehiclesArray.length ? Math.round(totalBattery / vehiclesArray.length) : 0;
            
            document.getElementById('totalCount').innerText = vehiclesArray.length;
            document.getElementById('movingCount').innerText = movingCount;
            document.getElementById('chargingCount').innerText = chargingCount;
            document.getElementById('avgBattery').innerText = avgBattery + '%';
            
            var vehicleList = document.getElementById('vehicleList');
            if (vehiclesArray.length === 0) {
                vehicleList.innerHTML = '<div style="text-align:center;color:#999;padding:20px;">暂无车辆数据<br>请启动桥接节点和仿真小车</div>';
                return;
            }
            
            vehicleList.innerHTML = vehiclesArray.map(v => {
                var statusClass = v.status === 'moving' ? 'moving' : (v.status === 'charging' ? 'charging' : '');
                if (v.battery < 20) statusClass += ' battery-low';
                var selectedClass = (selectedAgvId === v.agv_id) ? 'selected' : '';
                var statusText = v.status === 'moving' ? '🚗 移动中' : (v.status === 'charging' ? '⚡ 充电中' : '⏸️ 空闲');
                return `
                    <div class="vehicle-card ${statusClass} ${selectedClass}" onclick="selectAgv('${v.agv_id}')">
                        <div class="vehicle-header">
                            <span class="vehicle-id">🤖 ${v.agv_id}</span>
                            <span>🔋 ${Math.round(v.battery || 0)}%</span>
                        </div>
                        <div class="vehicle-details">
                            📍 (${v.x?.toFixed(1) || 0}, ${v.y?.toFixed(1) || 0}) | ${statusText}
                        </div>
                        <div class="vehicle-actions">
                            <button class="btn-primary" onclick="event.stopPropagation(); sendCommand('${v.agv_id}', 'move', {speed:${currentSpeed},direction:'forward'})">▶ 前进</button>
                            <button class="btn-stop" onclick="event.stopPropagation(); sendCommand('${v.agv_id}', 'stop')">⏹️ 停止</button>
                            <button class="btn-info" onclick="event.stopPropagation(); sendChargeToNearest('${v.agv_id}', ${v.x || 0}, ${v.y || 0})">🔌 充电</button>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function updateMapMarkers() {
            Object.values(vehicles).forEach(v => {
                var pos = toLatLng(v.x || 0, v.y || 0);
                var icon = getAgvIcon(v.battery || 0, v.status);
                
                if (agvMarkers[v.agv_id]) {
                    agvMarkers[v.agv_id].setLatLng([pos.lat, pos.lng]);
                    agvMarkers[v.agv_id].setIcon(icon);
                } else {
                    agvMarkers[v.agv_id] = L.marker([pos.lat, pos.lng], { icon: icon }).addTo(map);
                    agvMarkers[v.agv_id].bindPopup(`
                        <strong>${v.agv_id}</strong><br>
                        电量: ${Math.round(v.battery || 0)}%<br>
                        状态: ${v.status}<br>
                        位置: (${v.x?.toFixed(1) || 0}, ${v.y?.toFixed(1) || 0})
                    `);
                }
            });
        }
        
        // 地图点击事件：发送目标点
        map.on('click', function(e) {
            if (pendingMoveAgv) {
                var gridCoords = toGridCoords(e.latlng.lat, e.latlng.lng);
                var targetX = Math.max(gridConfig.minX, Math.min(gridConfig.maxX, gridCoords.x));
                var targetY = Math.max(gridConfig.minY, Math.min(gridConfig.maxY, gridCoords.y));
                sendMoveTo(pendingMoveAgv, targetX, targetY);
                pendingMoveAgv = null;
                showToast(`已发送目标点 (${targetX.toFixed(1)}, ${targetY.toFixed(1)})`, 'success');
            }
        });
        
        function loadData() {
            fetch('/api/vehicles')
                .then(r => r.json())
                .then(data => { vehicles = data; updateUI(); updateMapMarkers(); })
                .catch(err => console.error(err));
        }
        
        loadData();
        setInterval(loadData, 1000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/vehicles')
def api_vehicles():
    return jsonify(latest_status)

@app.route('/api/send_command', methods=['POST'])
def api_send_command():
    data = request.get_json()
    agv_id = data.get('agv_id', '001')
    command = data.get('command')
    params = data.get('params', {})
    
    if not command:
        return jsonify({'success': False, 'message': '指令不能为空'})
    
    success = send_command(agv_id, command, params)
    if success:
        return jsonify({'success': True, 'message': f'指令 {command} 已发送'})
    else:
        return jsonify({'success': False, 'message': 'MQTT 未就绪'})

# ========== 4. 主程序 ==========
if __name__ == '__main__':
    init_db()
    
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()
    
    print("=" * 50)
    print("🚀 AGV 云控平台启动成功！")
    print("📡 Web 访问: http://localhost:5000")
    print("🗺️ 网格厂区地图已加载")
    print("🎮 功能: 速度滑块 | 方向控制 | 原地旋转 | 坐标输入 | 网格厂区")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)