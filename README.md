# Reads smart meter data and publishes it to Influx and/or MQTT.

[![Build and publish the container image](https://github.com/BjoernSch/meter_reader/actions/workflows/push-to-registry.yaml/badge.svg)](https://github.com/BjoernSch/meter_reader/actions/workflows/push-to-registry.yaml)

Reads smart meter data from smart meters manufactured by Easymeter and eBZ GmbH and publishes it to Influx and/or MQTT

Connect IR -> USB converter to your meter and the server and link the interfaces to /dev/ttyMETER* (0,1,etc). Either by creating links on the local machine (ln -s /dev/ttyUSB0 /dev/ttyMETER0) or forwarding it in your virtualization and adding the device to your Docker container as /dev/ttyMETER*.
Multiple Interfaces at the same time are supported.
ASCII Format is expected.

Docker Container:

https://github.com/BjoernSch/meter_reader/pkgs/container/meter_reader

``ghcr.io/bjoernsch/meter_reader:latest``

## Supported enviroment variables:
If *_HOST is not set, the function is disabled:

### MQTT Support and defaults:
- *MQTT_HOST*

- MQTT_USER
- MQTT_PASSWORD
- MQTT_PORT 1883
- MQTT_TOPIC meter

### InfluxDB Support and defaults:
- *INFLUXDB_HOST*

- INFLUXDB_USER meter_reader
- INFLUXDB_PASSWORD
- INFLUXDB_PORT 8086
- INFLUXDB_DATABASE meter_reader
