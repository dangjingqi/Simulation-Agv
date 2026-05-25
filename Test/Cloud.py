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
    <title>AGV 云控平台 - 智能调度</title>
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
        
        /* 顶部导航栏 */
        .navbar {
            background: linear-gradient(135deg, #1a2a4a 0%, #0f1a2e 100%);
            color: white;
            padding: 12px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 1000;
            position: relative;
        }
        
        .navbar h1 { font-size: 1.5rem; display: flex; align-items: center; gap: 10px; }
        .navbar .status-badge { background: #4CAF50; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; }
        
        /* 主容器 */
        .main-container { display: flex; height: calc(100vh - 60px); }
        
        /* 左侧地图区域 */
        .map-panel { flex: 3; position: relative; margin: 10px; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        #map { height: 100%; width: 100%; }
        
        /* 右侧信息面板 */
        .info-panel { flex: 1; background: white; margin: 10px 10px 10px 0; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; flex-direction: column; overflow: hidden; }
        
        /* 统计卡片 */
        .stats-section { padding: 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px; }
        .stat-card { background: rgba(255,255,255,0.15); border-radius: 10px; padding: 12px; text-align: center; backdrop-filter: blur(5px); }
        .stat-number { font-size: 28px; font-weight: bold; }
        .stat-label { font-size: 12px; opacity: 0.9; margin-top: 4px; }
        
        /* 车辆列表 */
        .vehicles-section { flex: 1; overflow-y: auto; padding: 16px; }
        .vehicles-section h3 { margin-bottom: 12px; color: #1a2a4a; font-size: 16px; }
        
        .vehicle-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
            border-left: 4px solid #4CAF50;
            transition: all 0.2s;
            cursor: pointer;
        }
        .vehicle-card.selected { background: #e3f2fd; border-left-color: #2196F3; }
        .vehicle-card.battery-low { border-left-color: #f44336; background: #fff5f5; }
        .vehicle-card.moving { border-left-color: #2196F3; }
        .vehicle-card.charging { border-left-color: #ff9800; }
        
        .vehicle-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .vehicle-id { font-weight: bold; font-size: 16px; }
        .vehicle-battery { font-size: 14px; font-weight: bold; }
        .vehicle-details { font-size: 12px; color: #666; margin-bottom: 10px; }
        .vehicle-actions { display: flex; gap: 8px; flex-wrap: wrap; }
        
        button {
            padding: 6px 12px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }
        .btn-move { background: #4CAF50; color: white; }
        .btn-stop { background: #ff9800; color: white; }
        .btn-charge { background: #2196F3; color: white; }
        .btn-goto { background: #9C27B0; color: white; }
        button:hover { opacity: 0.85; transform: translateY(-1px); }
        
        /* 滚动条 */
        .vehicles-section::-webkit-scrollbar { width: 6px; }
        .vehicles-section::-webkit-scrollbar-track { background: #e0e0e0; border-radius: 3px; }
        .vehicles-section::-webkit-scrollbar-thumb { background: #888; border-radius: 3px; }
        
        @media (max-width: 900px) {
            .main-container { flex-direction: column; }
            .info-panel { margin: 0 10px 10px 10px; height: 400px; }
            .map-panel { height: 400px; }
        }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>🚗 AGV 智能云控平台</h1>
        <div>📍 点击地图选择目标点 | 🔋 自动寻桩充电</div>
    </div>
    
    <div class="main-container">
        <div class="map-panel">
            <div id="map"></div>
        </div>
        
        <div class="info-panel">
            <div class="stats-section">
                <div style="font-size: 14px; opacity: 0.9;">📊 实时统计</div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="stat-number" id="totalCount">0</div><div class="stat-label">在线车辆</div></div>
                    <div class="stat-card"><div class="stat-number" id="movingCount">0</div><div class="stat-label">运行中</div></div>
                    <div class="stat-card"><div class="stat-number" id="chargingCount">0</div><div class="stat-label">充电中</div></div>
                    <div class="stat-card"><div class="stat-number" id="avgBattery">0%</div><div class="stat-label">平均电量</div></div>
                </div>
            </div>
            
            <div class="vehicles-section">
                <h3>🚨 车辆状态列表（点击选择）</h3>
                <div id="vehicleList"></div>
            </div>
        </div>
    </div>

    <script>
        // ========== 陕汽厂区配置 ==========
        var factoryCenter = { lat: 34.45, lng: 109.02 };
        var map = L.map('map').setView([factoryCenter.lat, factoryCenter.lng], 16);
        
        // 高德底图
        L.tileLayer('https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
            attribution: '&copy; <a href="https://www.amap.com/">高德地图</a>',
            maxZoom: 18
        }).addTo(map);
        
        // 厂区示意圆
        L.circle([factoryCenter.lat, factoryCenter.lng], {
            color: '#2196F3', weight: 2, opacity: 0.6, fillOpacity: 0.05, radius: 800
        }).addTo(map);
        
        // 充电桩列表（用于自动寻桩）
        var chargers = [
            { id: 'charger_1', name: '🔋 充电桩 1', lat: 34.446, lng: 109.015, x: -40, y: -50 },
            { id: 'charger_2', name: '🔋 充电桩 2', lat: 34.454, lng: 109.025, x: 40, y: 50 },
            { id: 'charger_3', name: '🔋 充电桩 3', lat: 34.448, lng: 109.018, x: -20, y: -20 }
        ];
        
        // 添加充电桩标记
        chargers.forEach(c => {
            var icon = L.divIcon({ 
                html: `<div style="background:#FFD700;color:#333;padding:4px 8px;border-radius:20px;font-size:11px;font-weight:bold;">⚡ ${c.name}</div>`, 
                iconSize: [80, 25] 
            });
            L.marker([c.lat, c.lng], { icon: icon }).addTo(map);
        });
        
        // 添加其他设施标记
        var facilities = [
            { lat: 34.448, lng: 109.018, name: '📦 货架区 A', color: '#8B5A2B' },
            { lat: 34.452, lng: 109.022, name: '📦 货架区 B', color: '#8B5A2B' },
            { lat: 34.450, lng: 109.020, name: '🏭 工作站', color: '#4A90D9' }
        ];
        facilities.forEach(f => {
            var icon = L.divIcon({ html: `<div style="background:${f.color};color:white;padding:4px 8px;border-radius:20px;font-size:11px;">${f.name}</div>`, iconSize: [80, 25] });
            L.marker([f.lat, f.lng], { icon: icon }).addTo(map);
        });
        
        // ========== 全局变量 ==========
        var agvMarkers = {};
        var vehicles = {};
        var selectedAgvId = null;
        
        // ========== 自定义图标 ==========
        function getAgvIcon(battery, status) {
            var color, iconChar, glowColor;
            if (battery < 20) { color = '#f44336'; iconChar = '⚠️'; glowColor = '#f44336'; }
            else if (status === 'moving') { color = '#2196F3'; iconChar = '🚚'; glowColor = '#2196F3'; }
            else if (status === 'charging') { color = '#ff9800'; iconChar = '⚡'; glowColor = '#ff9800'; }
            else { color = '#4CAF50'; iconChar = '🚗'; glowColor = '#4CAF50'; }
            
            var html = `<div style="position:relative;cursor:pointer;">
                <div style="background:${color};width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:20px;box-shadow:0 0 15px ${glowColor};border:2px solid white;">
                    ${iconChar}
                </div>
                <div style="position:absolute;bottom:-22px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.75);color:white;padding:2px 8px;border-radius:12px;font-size:10px;white-space:nowrap;">
                    ${Math.round(battery)}%
                </div>
            </div>`;
            return L.divIcon({ html: html, iconSize: [40, 50], className: 'agv-marker', popupAnchor: [0, -20] });
        }
        
        // ========== 发送指令 ==========
        function sendCommand(agvId, command, params) {
            fetch('/api/send_command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agv_id: agvId, command: command, params: params || {} })
            }).then(r => r.json()).then(data => {
                if(data.success) showToast(`✅ ${command} 指令已发送`, 'success');
                else showToast(`❌ ${data.message || '发送失败'}`, 'error');
            }).catch(err => showToast('❌ 网络错误', 'error'));
        }
        
        // 移动到目标点
        function sendMoveTo(agvId, x, y) {
            sendCommand(agvId, 'move_to', { x: x, y: y });
        }
        
        // 自动寻桩充电
        function sendChargeToNearest(agvId, agvX, agvY) {
            // 计算距离最近的充电桩
            var nearest = null;
            var minDist = Infinity;
            chargers.forEach(c => {
                var dx = c.x - agvX;
                var dy = c.y - agvY;
                var dist = Math.sqrt(dx*dx + dy*dy);
                if (dist < minDist) {
                    minDist = dist;
                    nearest = c;
                }
            });
            if (nearest) {
                showToast(`🔋 找到最近充电桩 ${nearest.name}，距离 ${minDist.toFixed(1)} 米`, 'success');
                sendMoveTo(agvId, nearest.x, nearest.y);
                // 到达充电桩后会自动开始充电（由 fake_agv.py 处理）
            } else {
                showToast('❌ 未找到可用充电桩', 'error');
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
            toast.style.fontSize = '14px';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        // ========== 更新界面 ==========
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
                vehicleList.innerHTML = '<div style="text-align:center;color:#999;padding:40px;">暂无车辆数据<br>请启动 fake_agv.py</div>';
                return;
            }
            
            vehicleList.innerHTML = vehiclesArray.map(v => {
                var statusClass = '';
                if (v.battery < 20) statusClass = 'battery-low';
                else if (v.status === 'moving') statusClass = 'moving';
                else if (v.status === 'charging') statusClass = 'charging';
                var selectedClass = (selectedAgvId === v.agv_id) ? 'selected' : '';
                
                var statusText = v.status === 'moving' ? '🚗 移动中' : (v.status === 'charging' ? '⚡ 充电中' : '⏸️ 空闲');
                return `
                    <div class="vehicle-card ${statusClass} ${selectedClass}" onclick="selectAgv('${v.agv_id}')">
                        <div class="vehicle-header">
                            <span class="vehicle-id">🤖 ${v.agv_id}</span>
                            <span class="vehicle-battery" style="color:${v.battery < 20 ? '#f44336' : '#4CAF50'}">🔋 ${Math.round(v.battery || 0)}%</span>
                        </div>
                        <div class="vehicle-details">
                            📍 位置: (${v.x?.toFixed(1) || 0}, ${v.y?.toFixed(1) || 0}) &nbsp;|&nbsp;
                            ${statusText}
                        </div>
                        <div class="vehicle-actions">
                            <button class="btn-move" onclick="event.stopPropagation(); sendCommand('${v.agv_id}', 'move')">▶ 移动</button>
                            <button class="btn-stop" onclick="event.stopPropagation(); sendCommand('${v.agv_id}', 'stop')">⏹️ 停止</button>
                            <button class="btn-charge" onclick="event.stopPropagation(); sendChargeToNearest('${v.agv_id}', ${v.x || 0}, ${v.y || 0})">🔌 充电</button>
                            <button class="btn-goto" onclick="event.stopPropagation(); selectAgvForMove('${v.agv_id}')">📍 点选目标</button>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function selectAgv(agvId) {
            selectedAgvId = agvId;
            updateUI();
            showToast(`已选中 ${agvId}，可在地图上点击设置目标点`, 'success');
        }
        
        var pendingMoveAgv = null;
        function selectAgvForMove(agvId) {
            pendingMoveAgv = agvId;
            showToast(`请在地图上点击目标位置`, 'success');
        }
        
        function updateMapMarkers() {
            var vehiclesArray = Object.values(vehicles);
            
            vehiclesArray.forEach(v => {
                var lat = factoryCenter.lat + (v.y * 0.0001);
                var lng = factoryCenter.lng + (v.x * 0.0001);
                var icon = getAgvIcon(v.battery || 0, v.status);
                
                if (agvMarkers[v.agv_id]) {
                    agvMarkers[v.agv_id].setLatLng([lat, lng]);
                    agvMarkers[v.agv_id].setIcon(icon);
                } else {
                    agvMarkers[v.agv_id] = L.marker([lat, lng], { icon: icon }).addTo(map);
                    agvMarkers[v.agv_id].bindPopup(`
                        <div style="min-width: 150px;">
                            <strong>🤖 ${v.agv_id}</strong><br>
                            🔋 电量: ${Math.round(v.battery || 0)}%<br>
                            📍 状态: ${v.status}<br>
                            📍 坐标: (${v.x?.toFixed(1) || 0}, ${v.y?.toFixed(1) || 0})<br>
                            <hr>
                            <button onclick="sendCommand('${v.agv_id}', 'move')">▶ 移动</button>
                            <button onclick="sendCommand('${v.agv_id}', 'stop')">⏹️ 停止</button>
                            <button onclick="sendChargeToNearest('${v.agv_id}', ${v.x || 0}, ${v.y || 0})">🔌 充电</button>
                        </div>
                    `);
                }
            });
        }
        
        // 地图点击事件：发送目标点
        map.on('click', function(e) {
            if (pendingMoveAgv) {
                var targetLat = e.latlng.lat;
                var targetLng = e.latlng.lng;
                var targetX = (targetLng - factoryCenter.lng) / 0.0001;
                var targetY = (targetLat - factoryCenter.lat) / 0.0001;
                sendMoveTo(pendingMoveAgv, targetX, targetY);
                pendingMoveAgv = null;
                showToast(`已发送目标点 (${targetX.toFixed(1)}, ${targetY.toFixed(1)})`, 'success');
            } else if (selectedAgvId) {
                var targetLat2 = e.latlng.lat;
                var targetLng2 = e.latlng.lng;
                var targetX2 = (targetLng2 - factoryCenter.lng) / 0.0001;
                var targetY2 = (targetLat2 - factoryCenter.lat) / 0.0001;
                sendMoveTo(selectedAgvId, targetX2, targetY2);
                showToast(`已发送 ${selectedAgvId} 移动到 (${targetX2.toFixed(1)}, ${targetY2.toFixed(1)})`, 'success');
            }
        });
        
        function loadData() {
            fetch('/api/vehicles')
                .then(r => r.json())
                .then(data => { vehicles = data; updateUI(); updateMapMarkers(); })
                .catch(err => console.error('加载失败:', err));
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
    print("🗺️ 高德地图已集成")
    print("🔋 自动寻桩充电: 点击充电按钮，AGV 自动前往最近充电桩")
    print("🎯 点对点移动: 点击地图选择目标点")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)