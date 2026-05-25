import paho.mqtt.client as mqtt

def on_message(client, userdata, msg):
    print(f'收到: {msg.payload.decode()}')

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect('localhost', 1883, 60)

# +是单级通配符，匹配任意一级内容，订阅所有agv/*/status格式的主题， #多级同配符,匹配任意一级内容
client.subscribe('agv/+/status')
print('等待消息中...')
client.loop_forever()
