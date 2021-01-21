import threading
import time
from src.gpio_reader_writer import GPIODataReaderWriter
from src.event_logger import log_event
from src.Buffer import BufferEntity


class EdgeNode:
    """
    This class represents the controller and its methods
    """

    def __init__(self, cfg, buffer):

        self.module_name = 'EdgeNd'
        self.buffer = buffer

        # Read information from config file
        self.cfg = cfg
        self.control_interval = cfg['controller']['control_interval']
        self.voltage_access_data = {'channel_no': cfg['controller']['voltage_sensor_channel'],
                                    'scale_min': cfg['controller']['voltage_scale_min'],
                                    'scale_max': cfg['controller']['voltage_scale_max']}
        self.voltage_measurement_name = cfg['influxdb']['voltage_measurement_name']
        self.state_measurement_name = cfg['influxdb']['state_measurement_name']
        self.outputs = cfg['controller']['output_channels']
        self.voltage_threshold = cfg['controller']['voltage_threshold']
        self.critical_level = cfg['controller']['voltage_critical_level']
        self.voltage_limit_min = cfg['controller']['voltage_limit_min']
        self.voltage_limit_max = cfg['controller']['voltage_limit_max']

        # Threads
        self._control_thread = None

        # Mode
        self.mode_auto = True

        # Control input
        self.avg_voltage = 0
        self.voltage_level = None
        self._voltage_data = []
        self.mapping_table = [
            [1, 2, 4],
            [-4],
            [4, 5],
            [-2, -4, -5],
            [2, 3, 4],
            [-4],
            [4, 5],
        ]

        # Control output
        self.gpio_interface = GPIODataReaderWriter()

        # Reset outputs
        self._set_consumption_level(-1)
        self.consumption_level = 0

        # Internal flags
        self._stop_edge = False
        self._stop_control = False
        self._stopped_control = False
        self._stop_data_collection = False
        self._stopped_data_collection = False

    def start(self):
        """
        This methods starts data collection and controller
        :return:
        """
        self._run_data_collection()
        self._run_control()

    def _run_control(self):
        """
        This methods starts the control as a single thread
        :return:
        """
        self._stop_control = False
        self._stopped_control = False
        self._control_thread = threading.Thread(target=self._control)
        self._control_thread.start()
        log_event(self.cfg, self.module_name, '', 'INFO', 'Controller started')

    def _control(self):
        """
        This method executes control steps until the stop flag is set
        :return:
        """
        while not self._stop_control:
            control_step_begin = time.time()
            self._control_step()
            time_till_step_end = self.control_interval - (time.time() - control_step_begin)
            if time_till_step_end > 0:
                time.sleep(time_till_step_end)
        else:
            self._stopped_control = True
            log_event(self.cfg, self.module_name, '', 'INFO', 'Controller stopped')

    def _control_step(self):
        """
        This method represents a single control step. The last voltage data points is evaluated to define output level
        :return:
        """
        decision_level = self._voltage_evaluation()
        if decision_level != self.consumption_level:
            self._set_consumption_level(decision_level)

    def _set_consumption_level(self, level):
        """
        This method sets gpio outputs to get the desired consumption level
        :param level: consumption level
        :return:
        """
        if level == -1:
            changes = [-1, -2, -3, -4, -5]
        else:
            if level > self.consumption_level:
                changes = self.mapping_table[level - 1]
            else:
                changes = [-x for x in self.mapping_table[level]]

        for change in changes:
            channel = self.outputs[abs(change)-1]
            access_data = {'channel_no': channel}
            desired_state = change > 0
            self.gpio_interface.write_value('gpio', access_data, desired_state)

        log_event(self.cfg, self.module_name, '', 'INFO', 'Consumption level set on ' + str(level))
        self.consumption_level = level

        # Add state data in buffer
        data_point = BufferEntity(
            {'measurement': self.state_measurement_name,
             'tags': {'Unit': 'V'},
             'fields': {'Value': level},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

    def _voltage_evaluation(self):
        """
        This method calculates the slope of the voltage values and compare it with a set threshold
        :param voltage_values:
        :return:
        """

        new_level = self.consumption_level

        voltage_values = self._voltage_data

        if not len(voltage_values):
            log_event(self.cfg, self.module_name, '', 'WARN', 'Not enough voltage data points for evaluation')
            return new_level

        avg_voltage = sum(voltage_values) / len(voltage_values)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Calculated average value:' + str(avg_voltage))

        if avg_voltage <= self.critical_level:
            log_event(self.cfg, self.module_name, '', 'INFO', 'The voltage level is too low')
            return -1

        if self.voltage_limit_min < avg_voltage < self.voltage_limit_max:
            new_level = min(new_level+1, 7)
        else:
            if avg_voltage < self.avg_voltage - self.voltage_threshold:
                new_level = max(new_level - 1, 0)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level decreased: ' + str(avg_voltage) + '<' + str(self.avg_voltage))
            elif avg_voltage < self.avg_voltage - self.voltage_threshold:
                new_level = min(new_level + 1, 7)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level increased: ' + str(avg_voltage) + '>' + str(self.avg_voltage))


        self.avg_voltage = avg_voltage

        del self._voltage_data[0:len(voltage_values)]
        print(self._voltage_data)
        return new_level

    def _run_data_collection(self):
        """
        This methods starts the data collection
        :return:
        """
        self._stop_data_collection = False
        self._stopped_data_collection = False

        self._data_collection_thread = threading.Thread(target=self._data_collection)
        self._data_collection_thread.start()
        log_event(self.cfg, self.module_name, '', 'INFO', 'Data collection started')

    def _data_collection(self):
        """
        This method executes repeatedly the data collection step unless stopped
        :return:
        """
        while not self._stop_data_collection:
            start_time = time.time()
            self._data_collection_step()
            time_till_next_step = 1 - (time.time() - start_time)
            if time_till_next_step > 0:
                time.sleep(time_till_next_step)
        else:
            self._stopped_data_collection = True
            log_event(self.cfg, self.module_name, '', 'INFO', 'Data collection stopped')

    def _data_collection_step(self):
        """
        This method is a single data collection step
        :return:
        """
        voltage_value = self.gpio_interface.read_value('i2c', self.voltage_access_data)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Data point collected ' + str(voltage_value))
        self._voltage_data.append(voltage_value)

        # Add voltage data point in buffer
        data_point = BufferEntity(
            {'measurement': self.voltage_measurement_name,
             'tags': {'Unit': 'V',
                      'SclMin': self.voltage_access_data['channel_no'],
                      'SclMax': self.voltage_access_data['channel_no']},
             'fields': {'Value': voltage_value},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

    def _switch_to_auto_mode(self):
        pass

    def _switch_to_manual_mode(self):
        pass

    def get_state(self):
        return self.consumption_level

    def stop_control(self):
        """
        This methods initiates the control thread stop
        :return:
        """
        self._stop_control = True
        self._set_consumption_level(-1)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Control stop initialised')

    def stop_data_collection(self):
        """
        This methods initiates the data collection thread stop
        :return:
        """
        self._stop_data_collection = True
        log_event(self.cfg, self.module_name, '', 'INFO', 'Data collection stop initialised')

    def stop(self):
        """
        This method initiates stopping both control and data collection threads
        :return:
        """
        self.stop_control()
        self.stop_data_collection()
        while not (self._stopped_control and self._stopped_data_collection):
            time.sleep(1)

    def go_safe_state(self):
        """
        This method forces controller to set the safe state
        :return:
        """
        self._stop_control = True
        self._set_consumption_level(-1)

    def reset_safe_state(self):
        """
        This method resets the safe state flag to be able to start the controller again
        :return:
        """
        self._stop_control = False
        self.run_control()
