#!/usr/bin/env python3

# Reads data via optical interface from eBZ DD3
# connected to serial Port
# Publishes Data to InfluxDB

import sys
import serial
import logging
import threading
import json
from influxdb import InfluxDBClient
from datetime import datetime

obis_keys = {
    b'1-0:0.0.0' : ('owner_id', 'text', False),
    b'1-0:96.1.0' : ('device_id', 'text', False),
    b'1-0:1.8.0' : ('consumption_sum_kwh', 'float', True),
    b'1-0:1.8.1' : ('consumption_t1_kwh', 'float', True),
    b'1-0:1.8.2' : ('consumption_t2_kwh', 'float', True),
    b'1-0:16.7.0' : ('power_sum_w', 'float', True),
    b'1-0:36.7.0' : ('power_l1_w', 'float', True),
    b'1-0:56.7.0' : ('power_l2_w', 'float', True),
    b'1-0:76.7.0' : ('power_l3_w', 'float', True),
    b'1-0:32.7.0' : ('voltage_l1', 'float', True),
    b'1-0:52.7.0' : ('voltage_l2', 'float', True),
    b'1-0:72.7.0' : ('voltage_l3', 'float', True),
    b'1-0:96.5.0' : ('status', 'flags', True),
    b'0-0:96.8.0' : ('counter', 'hex', False)
}

class MeterReader(threading.Thread): 
  def __init__(self, influx, serialport): 
    threading.Thread.__init__(self)
    self.ser = serial.Serial(serialport, 9600, parity=serial.PARITY_EVEN, bytesize=7)
    self.influx = influx

  def run(self):
    start = False
    while True:
        line = self.ser.readline().strip()
        logging.debug(f'Line: {line}')
        if len(line) == 0:
            pass
        elif line[0] == ord('/'):
            logging.debug('Start of frame')
            start = True
            timestamp = datetime.now()
            data = dict()
            lineparts = line[1:].split(b'_')
            data['model_id'] = (str(lineparts[0], 'utf-8'), False)
            data['version'] = (str(lineparts[1], 'utf-8'), False)
        elif line[0] == ord('!'):
            logging.debug('End of frame')
            if start == True:
                self.influx.write_points([
                    {
                        {
                            "measurement": data['device_id'][0]
                        },
                        "fields": {k: v for k, (v, log) in data.items() if log == True},
                        "time": timestamp.isoformat()
                    }
                ])
                start = False
        elif start == True:
            lineparts = line.split(b"(")
            key = lineparts[0].split(b"*")[0]
            value = lineparts[1].rstrip(b")").split(b"*")[0]
            if key in obis_keys:
                value_name, value_type, log_value = obis_keys[key]
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

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO,
                        datefmt="%H:%M:%S")
    
    # datetime object containing current date and time
    try:
        with open('meter_reader.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.error('Config file not found!')
        exit(1)
    except json.JSONDecodeError:
        logging.error('Config file not valid JSON!')
        exit(1)

    influx_host = config['influxdb']['host']
    influx_port = config['influxdb']['port']
    influx_username = config['influxdb']['user']
    influx_password = config['influxdb']['password']
    influx_database = config['influxdb']['database']

    influx = InfluxDBClient(influx_host, influx_port, influx_username, influx_password, influx_database)

    threads = list()
    for serialport in config['ports']:
        logging.info(f"Main    : create and start thread for {serialport}")
        x = MeterReader(influx, serialport)
        threads.append(x)
        x.start()

    for index, thread in enumerate(threads):
        logging.info("Main    : before joining thread %d.", index)
        thread.join()
        logging.info("Main    : thread %d done", index)