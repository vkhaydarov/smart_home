from src.influxdb_writer import InfluxDBWriter
from src.Buffer import Buffer
from src.edge_node import EdgeNode
import time
import yaml

if __name__ == '__main__':

    # Import config
    cfg_file = 'config.yaml'
    with open(cfg_file) as config_file:
        cfg = yaml.safe_load(config_file)

    # Initialise buffer
    data_buffer = Buffer(cfg)

    # Start influxdb writer
    #idb = InfluxDBWriter(cfg=cfg, buffer=data_buffer)
    #idb.connect()

    # Start controller
    ctrl = EdgeNode(cfg=cfg, buffer=data_buffer)
    ctrl.start()

