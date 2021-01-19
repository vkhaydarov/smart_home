import threading
import time
from src.gpio_reader_writer import GPIODataReaderWriter
from src.event_logger import log_event
from src.Buffer import BufferEntity


class Controller:
    """
    This class represents the controller and its methods.
    """

    def __init__(self, cfg, buffer):
        self.control_interval = cfg['controller']['control_interval']
        self.cfg = cfg

        self.mode_auto = True
        self.voltage_level = None
        self.consumption_level = 0

        self.buffer = buffer

        self.module_name = 'Contrl'

        self.voltage_access_data = {'channel_no': cfg['controller']['voltage_sensor_channel'],
                                    'scale_min': cfg['controller']['voltage_scale_min'],
                                    'scale_max': cfg['controller']['voltage_scale_max']}

        self.voltage_measurement_name = cfg['influxdb']['voltage_measurement_name']
        self.state_measurement_name = cfg['influxdb']['state_measurement_name']

        self.outputs = cfg['controller']['output_channels']

        self.gpio_interface = GPIODataReaderWriter()

        self._stop = False
        self._stopped = False

        self._control_thread = None

        self.mapping_table = [
            [0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0],
            [0, 1, 0, 0, 0],
            [0, 0, 1, 0, 0],
            [0, 0, 0, 1, 0],
            [0, 0, 0, 1, 1],
            [1, 1, 1, 1, 1],
        ]

        self.limits = cfg['controller']['voltage_limits']

    def run_control(self):
        """
        This methods starts the control loop.
        :return:
        """
        self._stop = False
        self._stopped = False
        self._control_thread = threading.Thread(target=self._control)
        self._control_thread.start()
        log_event(self.cfg, self.module_name, '', 'INFO', 'Controller started')

    def _control(self):
        while not self._stop:
            self._control_step()
        else:
            self._stopped = True
            log_event(self.cfg, self.module_name, '', 'INFO', 'Controller stopped')

    def _control_step(self):
        """
        This method represents a single control step. Every step, the next level with a higher energy consumption
        will be switched on and the voltage level is to evaluate. In case, the voltage level drops, a lower consumption
        level will be switched on.
        :return:
        """
        log_event(self.cfg, self.module_name, '', 'INFO', 'Control step begin')
        control_step_begin = time.time()

        # Collect voltage data
        voltage_data = self._collect_voltage_data(int(self.control_interval - 1))

        if self._stop:
            return

        # Data processing
        decision_level = self._voltage_evaluation(voltage_data)

        # Control
        self._set_consumption_level(decision_level)
        time_till_step_end = self.control_interval - (time.time() - control_step_begin)
        if time_till_step_end > 0:
            time.sleep(time_till_step_end)

    def _set_consumption_level(self, level):

        state_set = self.mapping_table[level]

        for idx, channel in enumerate(self.outputs):
            access_data = {'channel_no': channel}
            desired_state = state_set[idx]
            attempt = 0
            while not self.gpio_interface.check_gpio_state(access_data, desired_state):
                self.gpio_interface.write_value('gpio', access_data, desired_state)
                time.sleep(0.01)
                attempt += attempt
                if attempt >= 10:
                    break  # TODO: add error message output and program exit

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

    def _voltage_evaluation(self, voltage_values):
        """
        This method calculates the slope of the voltage values and compare it with a set threshold
        :param voltage_values:
        :return:
        """

        new_level = 0

        if not len(voltage_values):
            log_event(self.cfg, self.module_name, '', 'WARN', 'No voltage data received within control loop')
            return new_level

        avg_voltage = sum(voltage_values) / len(voltage_values)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Calculated average value:' + str(avg_voltage))

        if avg_voltage <= self.limits['low'][0]:
            log_event(self.cfg, self.module_name, '', 'INFO', 'Calculated average is lower than the lowest')
            new_level = 0

        if avg_voltage >= self.limits['low'][6]:
            log_event(self.cfg, self.module_name, '', 'INFO', 'Calculated average is greater than the greatest')
            new_level = 6

        for limit in range(len(self.limits['low'])):
            if self.limits['low'][limit] < avg_voltage <= self.limits['high'][limit]:
                new_level = limit

        old_level = self.consumption_level
        log_event(self.cfg, self.module_name, '', 'INFO',
                  'State change from ' + str(old_level) + ' to ' + str(new_level))
        return new_level

    def _collect_voltage_data(self, duration):
        """
        This method collects voltage data for given duration
        :param duration: duration in seconds
        :return: voltage data as a list
        """
        voltage_data = []

        # Collect voltage data
        for time_step in range(int(duration)):
            if self._stop:
                break
            start_time = time.time()
            voltage_value = self.gpio_interface.read_value('i2c', self.voltage_access_data)
            log_event(self.cfg, self.module_name, '', 'INFO', 'Data point collected ' + str(voltage_value))
            voltage_data.append(voltage_value)

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

            time_till_next_step = 1 - (time.time() - start_time)
            if time_till_next_step > 0:
                time.sleep(time_till_next_step)

        return voltage_data

    def _switch_to_auto_mode(self):
        pass

    def _switch_to_manual_mode(self):
        pass

    def get_state(self):
        return self.consumption_level

    def stop_control(self):
        self._stop = True
        log_event(self.cfg, self.module_name, '', 'INFO', 'Stop initialised')

    def go_safe_state(self):
        self._stop = True
        self._set_consumption_level(0)

    def reset_safe_state(self):
        self._stop = False
        self.run_control()
