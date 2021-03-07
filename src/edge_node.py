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
        self.running = False

        # Read information from config file
        self.cfg = cfg
        self.control_interval = cfg['controller']['control_interval']
        self.voltage_access_data = {'channel_no': cfg['controller']['voltage_sensor_channel'],
                                    'scale_min': cfg['controller']['voltage_scale_min'],
                                    'scale_max': cfg['controller']['voltage_scale_max']}
        self.voltage_measurement_name = cfg['influxdb']['voltage_measurement_name']
        self.state_measurement_name = cfg['influxdb']['state_measurement_name']
        self.consumption_measurement_name = cfg['influxdb']['consumption_measurement_name']
        self.output_measurement_name = cfg['influxdb']['output_measurement_name']
        self.mode_measurement_name = cfg['influxdb']['mode_measurement_name']
        self.outputs = cfg['controller']['output_channels']
        self.voltage_threshold = cfg['controller']['voltage_threshold']
        self.critical_level = cfg['controller']['voltage_critical_level']
        self.voltage_limit_min = cfg['controller']['voltage_limit_min']
        self.voltage_limit_max = cfg['controller']['voltage_limit_max']

        # Threads
        self._control_thread = None

        # Mode
        self.auto_mode_requested = True
        self.mode_auto = True
        self.mode_manual = False

        # Control input
        self.voltage_average = 0
        self.voltage_value = None
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
        self.load_mapping = cfg['controller']['loads']
        self.load = 0

        # Simulation
        self.deploy = not cfg['controller']['input_simulation']
        self.sim_profile = cfg['controller']['simulation_profile']

        # Control output
        self.gpio_interface = GPIODataReaderWriter(deploy=self.deploy, test_profile='constant')

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
        self.running = True

    def _control(self):
        """
        This method executes control steps until the stop flag is set
        :return:
        """
        while not self._stop_control:
            control_step_begin = time.time()
            while self.control_interval - (time.time() - control_step_begin) > 1:
                if not self._stop_control:
                    time.sleep(0.1)
                else:
                    break
            if self._stop_control:
                break
            self._control_step()
            time_till_step_end = self.control_interval - (time.time() - control_step_begin)
            if time_till_step_end > 0:
                time.sleep(time_till_step_end)
        self._stopped_control = True

    def _control_step(self):
        """
        This method represents a single control step. The last voltage data points is evaluated to define output level
        :return:
        """
        decision_level = self._voltage_evaluation()
        if decision_level != self.consumption_level:
            self._set_consumption_level(decision_level)

    def increase_consumption_level(self):
        self._set_consumption_level(self.consumption_level+1)

    def decrease_consumption_level(self):
        self._set_consumption_level(self.consumption_level-1)

    def _set_consumption_level(self, level):
        """
        This method sets gpio outputs to get the desired consumption level
        :param level: consumption level
        :return:
        """
        if level == -1:
            changes = [-1, -2, -3, -4, -5]
            level = 0
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
        self.load = self.load_mapping[level]
        self.consumption_level = level

        data_point = BufferEntity(
            {'measurement': self.state_measurement_name,
             'tags': {'Unit': 'V'},
             'fields': {'Value': level},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

        data_point_consumption = BufferEntity(
            {'measurement': self.consumption_measurement_name,
             'fields': {'Value': self.load_mapping[level]},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point_consumption)

    def _voltage_evaluation(self):
        """
        This method calculates average voltage valuea and check wherther it decreases or does not
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
            if avg_voltage < self.voltage_average - self.voltage_threshold:
                new_level = max(new_level - 1, 0)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level decreased: ' + str(avg_voltage) + '<' + str(self.voltage_average))
            else:
                new_level = min(new_level + 1, 7)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level increased: ' + str(avg_voltage) + '>' + str(self.voltage_average))

        self.voltage_average = avg_voltage

        del self._voltage_data[0:len(voltage_values)]
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
            self._data_collection_step_voltage_input()
            self._data_collection_step_output_states()
            time_till_next_step = 1 - (time.time() - start_time)
            if time_till_next_step > 0:
                time.sleep(time_till_next_step)
        else:
            self._stopped_data_collection = True
            log_event(self.cfg, self.module_name, '', 'INFO', 'Data collection stopped')

    def _data_collection_step_voltage_input(self):
        """
        This method is a single data collection step
        :return:
        """
        voltage_value = self.gpio_interface.read_value('i2c', self.voltage_access_data)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Data point collected ' + str(voltage_value))
        self._voltage_data.append(voltage_value)

        self.voltage_value = voltage_value

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

    def _data_collection_step_output_states(self):
        output_state = self.get_gpio_state()

        # Add data point in buffer
        data_point_level = BufferEntity(
            {'measurement': self.output_measurement_name,
             'fields': {'Output1': output_state[0],
                        'Output2': output_state[1],
                        'Output3': output_state[2],
                        'Output4': output_state[3],
                        'Output5': output_state[4]},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point_level)

    def switch_to_auto_mode(self):
        log_event(self.cfg, self.module_name, '', 'INFO', 'Changing mode to automatic...')
        self._set_consumption_level(-1)
        self.auto_mode_requested = True
        self._run_control()
        self.mode_auto = True
        self.mode_manual = False
        log_event(self.cfg, self.module_name, '', 'INFO', 'Mode changed to automatic')
        self._write_mode()

    def switch_to_manual_mode(self):
        log_event(self.cfg, self.module_name, '', 'INFO', 'Changing mode to manual...')
        self._set_consumption_level(-1)
        self.auto_mode_requested = False
        self.stop_control()
        self.mode_auto = False
        self.mode_manual = True
        log_event(self.cfg, self.module_name, '', 'INFO', 'Mode changed to manual')
        self._data_collection_mode()

    def _data_collection_mode(self):
        # Write mode change in influxdb
        data_point = BufferEntity(
            {'measurement': self.mode_measurement_name,
             'fields': {'Value': int(self.mode_auto)},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

    def get_consumption_level(self):
        return self.consumption_level

    def get_gpio_state(self):
        output_state = []
        for channel in self.outputs:
            access_data = {'channel_no': channel}
            state = self.gpio_interface.check_gpio_state(access_data, True)
            output_state.append(state)
        return output_state

    def set_gpio_state(self, output_no, state):
        channel = self.outputs[output_no]
        access_data = {'channel_no': channel}
        self.gpio_interface.write_value('gpio', access_data, state)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Channel ' + str(channel) + ' set to ' + str(state))

    def stop_control(self):
        """
        This methods initiates the control thread stop
        :return:
        """
        self._stop_control = True
        self._set_consumption_level(-1)
        log_event(self.cfg, self.module_name, '', 'WARN', 'Control stop initialised')
        while not self._stopped_control:
            pass
        log_event(self.cfg, self.module_name, '', 'WARN', 'Control stopped')

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
