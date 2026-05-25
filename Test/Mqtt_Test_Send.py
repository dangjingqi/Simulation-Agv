import paho.mqtt.client as mqtt

#-------发布消息--------
#创建一个客户端对象，Client()会生成一个唯一的客户端Id,也可以指定Id(client_id="my_agv_001")
client = mqtt.Client()  
#连接Mqtt服务器，连接Mqtt Broker,1883是Mqtt默认端口号，网站名默认是80端口,60s没通信就发送心跳包
client.connect("localhost", 1883, 60)
#发布消息，向指定主题发布消息，（标签/频道，消息内容），结果是Broker把消息在转发给所有订阅了的agv/status的客户端
client.publish("agv/status", '{"agv_id": "001", "battery": 85}')
print("消息已发送")