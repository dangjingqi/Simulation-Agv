# save as mqtt_test.py，导入mqtt库
import paho.mqtt.client as mqtt

#-------接收消息--------
#每当订阅的主题收到新消息时，自动触发,msg是消息对象包含主题内容信息
def on_message(client,userdata,msg):
    #msg.payload消息内容的原始字节数据,.decode将字节数据转为字符串
    print(f"收到:{msg.payload.decode()}")
client = mqtt.Client()
client.on_message = on_message
client.connect("localhost",1883,60)
client.subscribe("agv/status")
print("等待消息中...")
#启动网络循环，loopforever阻塞当前线程，loop_start()启动后台线程不阻塞
client.loop_forever()



