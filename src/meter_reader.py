#!/usr/bin/env python3

# Reads data via optical interface from electronic meters
# connected to serial Port
# Publishes Data to InfluxDB

import os
import sys
import serial
import logging
import threading
import requests
from glob import glob
from influxdb import InfluxDBClient
from datetime import datetime
import paho.mqtt.client as mqtt_client

class MeterReader(threading.Thread):
    obis_keys = {
        # eBZ GmbH
        "ebz" : {
            b'1-0:0.0.0' : ('owner_id', 'text', False),
            b'1-0:96.1.0' : ('device_id', 'text', False),
            b'1-0:1.8.0' : ('consumption_sum_kwh', 'float', True),
            b'1-0:1.8.1' : ('consumption_t1_kwh', 'float', True),
            b'1-0:1.8.2' : ('consumption_t2_kwh', 'float', True),
            b'1-0:2.8.0' : ('delivery_sum_kwh', 'float', True),
            b'1-0:16.7.0' : ('power_sum_w', 'float', True),
            b'1-0:36.7.0' : ('power_l1_w', 'float', True),
            b'1-0:56.7.0' : ('power_l2_w', 'float', True),
            b'1-0:76.7.0' : ('power_l3_w', 'float', True),
            b'1-0:32.7.0' : ('voltage_l1', 'float', True),
            b'1-0:52.7.0' : ('voltage_l2', 'float', True),
            b'1-0:72.7.0' : ('voltage_l3', 'float', True),
            b'1-0:96.5.0' : ('status', 'flags', True),
            b'0-0:96.8.0' : ('counter', 'hex', False)
        },
        # Easymeter
        "esy" : { 
            b'1-0:0.0.0' : ('owner_id', 'text', False),
            b'1-0:96.1.255' : ('device_id', 'text', False),
            b'1-0:1.8.0' : ('consumption_sum_kwh', 'float', True),
            b'1-0:1.8.1' : ('consumption_t1_kwh', 'float', True),
            b'1-0:1.8.2' : ('consumption_t2_kwh', 'float', True),
            b'1-0:2.8.0' : ('delivery_sum_kwh', 'float', True),
            b'1-0:15.8.0' : ('total_sum_kwh', 'float', True),
            b'1-0:1.7.0' : ('power_sum_w', 'float', True),
            b'1-0:21.7.0' : ('power_l1_w', 'float', True),
            b'1-0:41.7.0' : ('power_l2_w', 'float', True),
            b'1-0:61.7.0' : ('power_l3_w', 'float', True),
            # Some flags are known
            b'1-0:96.5.5' : ('status', 'flags', True)
        }
    }

    def __init__(self, mqttc, influx, serialport): 
        threading.Thread.__init__(self)
        
        try:
            self.ser = serial.Serial(serialport, 9600, parity=serial.PARITY_EVEN, bytesize=7)
        except serial.SerialException:
            logging.error('Error opening port "{serialport}"!')
            exit(2)
            
        self.influx = influx

    def run(self):
        start = False
        points = []
        while True:
            line = self.ser.readline().strip()
            logging.debug(f'Line: {line}')
            if len(line) == 0:
                pass
            elif line[0] == ord('/'):
                logging.debug('Start of frame')
                timestamp = datetime.now()
                data = dict()
                
                lineparts = line[1:].split(b'_')
                data['model_id'] = (str(lineparts[0], 'utf-8'), False)
                data['version'] = (str(lineparts[1], 'utf-8'), False)
                
                model = str(data['model_id'][0][0:3]).lower()
                
                if model in self.obis_keys:
                    start = True
                    logging.debug('Model {model}')
                else:
                    logging.error('Unknown model "{model}"!')
            elif line[0] == ord('!'):
                logging.debug('End of frame')
                if start == True:
                    if self.influx:
                        points += [{
                            "measurement": data['device_id'][0],
                            "fields": {k: v for k, (v, log) in data.items() if log == True},
                            "time": timestamp.isoformat()
                        }]
                        try:
                            self.influx.write_points(points)
                            points = []
                        except requests.exceptions.ConnectionError:
                            logging.error('Error sending data points! {} points cached.'.format(len(points)))
                    if self.mqttc:
                        for key, (value, log) in data.items():
                            if log == True:
                                self.mqttc.publish(f"/{mqtt_topic}/{data['device_id'][0]}/{key}", value)
                    
                    start = False
            elif start == True:
                lineparts = line.split(b"(")
                key = lineparts[0].split(b"*")[0]
                value = lineparts[1].rstrip(b")").split(b"*")[0]
                if key in self.obis_keys[model]:
                    value_name, value_type, log_value = self.obis_keys[model][key]
                    if value_type == 'float':
                        try:
                            data[value_name] = (float(value), log_value)
                        except ValueError:
                            logging.error(f'ValueError in {value_name}: {value} is not a float.')
                    elif value_type == 'text':
                        data[value_name] = (str(value, 'utf-8').strip(), log_value)
                    elif value_type == 'flags':
                        # Nothing of interest known in the flags, just save the int
                        try:
                            data[value_name] = (int(value, 16), log_value)
                        except ValueError:
                            logging.error(f'ValueError in {value_name}: {value} is not a base 16 int.')
                    elif value_type == 'hex':
                        try:
                            data[value_name] = (int(value, 16), log_value)
                        except ValueError:
                            logging.error(f'ValueError in {value_name}: {value} is not a base 16 int.')

def mqtt_on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logging.error(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
    else:
        # we should always subscribe from on_connect callback to be sure
        # our subscribed is persisted across reconnections.
        None

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO,
                        datefmt="%H:%M:%S")
    
    if os.getenv('MQTT_HOST') != None:
        mqtt_host = os.getenv('MQTT_HOST')
        mqtt_port = int(os.getenv('MQTT_PORT', '1883')) 
        mqtt_username = os.getenv('MQTT_USER')
        mqtt_password = os.getenv('MQTT_PASSWORD')
        mqtt_topic = os.getenv('MQTT_TOPIC', 'meter')

        mqttc = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        mqttc.on_connect = mqtt_on_connect
        mqttc.enable_logger()
        mqttc.loop_start()
        mqttc.username_pw_set(mqtt_username, mqtt_password)
        mqttc.connect(mqtt_host, mqtt_port, 60)
    else:
        mqttc = None
    
    if os.getenv('INFLUXDB_HOST') != None:
        influx_host = os.getenv('INFLUXDB_HOST')
        influx_port = int(os.getenv('INFLUXDB_PORT', '8086')) 
        influx_username = os.getenv('INFLUXDB_USER', 'meter_reader')
        influx_password = os.getenv('INFLUXDB_PASSWORD')
        influx_database = os.getenv('INFLUXDB_DATABASE', 'meter_reader')

        influx = InfluxDBClient(influx_host, influx_port, influx_username, influx_password, influx_database)
    else:
        influx = None
    
    threads = list()
    serial_ports = glob('/dev/ttyMETER*')
    if len(serial_ports) == 0:
        logging.info("No serial ports found!")
    else:
        for serialport in serial_ports:
            logging.info(f"Create and start thread for {serialport}")
            x = MeterReader(mqttc, influx, serialport)
            threads.append(x)
            x.start()

        for index, thread in enumerate(threads):
            logging.info("Main    : before joining thread %d.", index)
            thread.join()
            logging.info("Main    : thread %d done", index)
