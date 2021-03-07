import threading
import time
from influxdb import InfluxDBClient
from src.event_logger import log_event


class InfluxDBWriter:
    """
    This class represents an OPC UA server and offers necessary functionality to connect to an INFLUX DB server
    as well as ingest data from buffer
    """

    def __init__(self, cfg, buffer):
        """
        Initialisation
        :param cfg: Set of parameters including connection information and data about metrics
        :param buffer: Link to a buffer object, where to save gathered data points
        """
        # Module name
        self.module_name = 'Influx'

        # Extraction of configuration parameters relevant for connectivity of the OPC UA server
        self.cfg = cfg
        self.host = cfg['influxdb']['host']
        self.port = cfg['influxdb']['port']
        self.user = cfg['influxdb']['user']
        self.password = cfg['influxdb']['password']
        self.db_name = cfg['influxdb']['database']
        self.db_user = cfg['influxdb']['db_user']
        self.db_password = cfg['influxdb']['db_password']
        self.write_interval = cfg['influxdb']['write_interval']
        self.reconnect_interval = cfg['influxdb']['reconnect_interval']

        # Creation of INFLUXDB client object
        self.client = None

        # Connectivity variables
        self.connection_status = False
        self._connectivity_thread = []

        # Ingestion thread
        self._ingestion_thread = []

        # Buffer
        self.buffer = buffer

        # Exit and stop ingestion flags to complete activities
        self._exit = False
        self._stop_ingest = False

    def _single_connect(self):
        """
        Single connection to the INFLUXDB server
        :return: True - if connection successfully established and False - if not
        """
        log_event(self.cfg, self.module_name, '', 'INFO',
                  'Connecting to INFLUXDB server ' + str(self.host) + ':' + str(self.port) + '...')
        self.client = InfluxDBClient(host=self.host, port=self.port, username=self.user, password=self.password,
                                     database=self.db_name)
        self._check_connection_status()
        if self.connection_status:
            log_event(self.cfg, self.module_name, '', 'INFO', 'Connection established')
            return True
        else:
            log_event(self.cfg, self.module_name, '', 'ERR', 'Connection failed')
            self.connection_status = False
            return False

    def connect(self):
        """
        Creates separate thread to take care of connectivity
        :return:
        """
        self._connectivity_thread = threading.Thread(target=self._connectivity)
        self._connectivity_thread.start()

    def _check_connection_status(self):
        """
        This functions checks periodically connection status to the influxdb server and writes it into
        connection_status variable
        :return:
        """
        log_event(self.cfg, self.module_name, '', 'INFO', 'Checking connection to INFLUXDB server...')
        try:
            self.client.ping()
            self.connection_status = True
        except Exception as err:
            log_event(self.cfg, self.module_name, '', 'WARN', 'No connection to INFLUXDB server' + ': ' + str(err))
            self.connection_status = False

    def get_connection_status(self):
        """
        This function returns current status of connection to the INFLUXDB server.
        :return: dict with 'code' and 'status' as text
        """
        if self.connection_status:
            return {'code': self.connection_status, 'status': 'Connected'}
        return {'code': self.connection_status, 'status': 'Disconnected'}

    def _connectivity(self):
        """
        This function checks connection and reconnect to the INFLUXDB server as required.
        :return:
        """
        while True:
            # If exit flag received, we stop the thread
            if self._exit:
                self.disconnect()
                time.sleep(1)
                break

            # If connection established, we check connection status periodically
            if self.connection_status:
                try:
                    # Request INFLUX DB connection status
                    self.client.ping()

                except Exception as err:
                    # In case of missing connection, we do cleanup procedure and wait a little bit to let
                    # opcua-python close subscription threads
                    log_event(self.cfg, self.module_name, '', 'WARN', 'No connection to INFLUXDB server' + ': ' + str(err))
                    self.connection_status = False
                    self.disconnect()
                    time.sleep(1)

            # If connection does not exist yet/anymore, we try to establish one
            else:

                # Try to connect to OPC UA server
                connected = self._single_connect()
                # In case of successful connection, start monitoring
                if connected:
                    self._start_ingestion()
                # In case of unsuccessful connection, repeat again after given reconnection interval
                else:
                    time.sleep(self.reconnect_interval / 1000)

            # Wait a little bit until next connection check
            time.sleep(0.5)

    def disconnect(self):
        """
        This function stop data transfer and disconnect from the INFLUXDB server.
        :return: Success of the disconnection procedure
        """
        log_event(self.cfg, self.module_name, '', 'INFO', 'Disconnecting from INFLUXDB server ' + self.host + '...')
        self._stop_ingestion()
        time.sleep(self.write_interval / 1000.0)
        try:
            self.client.close()
            log_event(self.cfg, self.module_name, '', 'INFO', 'Disconnection successful')
        except Exception as err:
            log_event(self.cfg, self.module_name, '', 'ERR', 'Disconnection failed' + ': ' + str(err))

    def _start_ingestion(self):
        """
        This function begins data ingestion within a separate thread
        :return: ingestion status
        """
        res = self._create_db()
        if res:
            self._stop_ingest = False
            self._ingestion_thread = threading.Thread(target=self._ingest_data)
            self._ingestion_thread.start()
        else:
            log_event(self.cfg, self.module_name, '', 'ERR', 'Ingestion failed due to inability to create database')
            return False

    def _stop_ingestion(self):
        """
        This function initiates stop of data ingestion
        :return:
        """
        self._stop_ingest = True

    def _ingest_data(self):
        """
           This function ingest data from the buffer into INFLUXDB. If successful, transferred data entities
           will be removed from the buffer.
           :return:
           """
        while True:
            start_time = time.time()
            buffer_snapshot = self.buffer.get_snapshot()
            buffer_len = len(buffer_snapshot)
            if buffer_len:
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'Ingesting ' + str(buffer_len) + ' elements from buffer into INFLUXDB')
                original_idx = 0
                for idx, buffer_entity in enumerate(buffer_snapshot):
                    res_conversion, data_line = buffer_entity.convert_to_line_protocol()
                    if res_conversion:
                        res_write = self._ingest_data_point(data_line)
                        if res_write and self.buffer.len() != self.buffer.max_buffer_size:
                            original_idx += original_idx
                            self.buffer.remove_point(original_idx)
                    else:
                        log_event(self.cfg, self.module_name, '', 'ERR', 'Problem with generating line protocol' + ': ' + str(data_line))
                        self.buffer.remove_point(original_idx)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'Ingestion of ' + str(buffer_len) + ' point(s) took ' + str(time.time() - start_time))
            if self._stop_ingest:
                break
            time.sleep(self.write_interval / 1000.0)

    def _create_db(self):
        """
        This function creates a database in the INFLUX DB server, if a database with such a name does not exist yet
        :return: True if database either already exists or was created, False - if creation process failed
        """
        try:
            db_list = self.client.get_list_database()
            if not any(d['name'] == self.db_name for d in db_list):
                self.client.create_database(self.db_name)
                log_event(self.cfg, self.module_name, '', 'INFO', 'Database ' + self.db_name + ' successfully created')
            return True
        except Exception as err:
            log_event(self.cfg, self.module_name, '', 'ERR', 'Cannot create database' + self.db_name + ': ' + str(err))
            return False

    def _ingest_data_point(self, data_line):
        """
        This function ingest one line into INFLUX DB
        :param data_line: data line to ingest
        :return: status of ingestion process
        """
        if data_line:
            try:
                ret = self.client.write_points(data_line, database=self.db_name, time_precision='ms', protocol='line')
                log_event(self.cfg, self.module_name, '', 'INFO', 'Line >' + data_line + '< inserted in influxdb')
                return True
            except Exception as err:
                log_event(self.cfg, self.module_name, '', 'WARN', 'Data insertion failed:' + str(err))
                return False

    def exit(self):
        """
        Initiates closing of threads and disconnection from the INFLUXDB server
        :return:
        """
        self._exit = True
