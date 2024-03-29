import threading
import time
from src.gpio_reader_writer import GPIODataReaderWriter
from src.event_logger import log_event
from src.Buffer import BufferEntity

import board
import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


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
                [1, 3, 5, 10],
                [2, -3, -5, 6],
                [-1, 3, 4, 5, -6],
                [-2, -3, -4, -5, 8],
                [2, 4, 7],
                [3, -8],
                [-2, -4, 8],
                [2, 5, -8],
                [8],
                [-2, -5, 9, -10, 11],
                [-3, 6, -8, -9, -11],
                [2, -6, 8, 9, 11],
                [1, -11],
                [-1, 3, 4, -8, 11],
                [1, -2, -3, -4, 6, -11, 12],
                [10, -12],
                [-1, 4, -10, 11, 12],
                [-4, -6, -7, 10, -12],
                [8],
                [6, -8, 12],
                [4, -6, -12],
                [6, 12],
                [-4, 5, -6],
        ]
        self.load = 0

        # Current regime
        self.regime = 0
        self.regime_str = ""

        # Control output 
        self.gpio_interface = GPIODataReaderWriter(not self.cfg['simulation']['active'])

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
            while self.cfg['controller']['control_interval'] - (time.time() - control_step_begin) > 1:
                if not self._stop_control:
                    time.sleep(0.1)
                else:
                    break
            if self._stop_control:
                break
            self._control_step()
            time_till_step_end = self.cfg['controller']['control_interval'] - (time.time() - control_step_begin)
            if time_till_step_end > 0:
                time.sleep(time_till_step_end)
        self._stopped_control = True

    def _control_step(self):
        """
        This method represents a single control step. The last voltage data points is evaluated to define output level
        :return:
        """
        log_event(self.cfg, self.module_name, '', 'INFO', 'Control step')
        self.read_regime()
        decision_level = self._voltage_evaluation()
        if decision_level != self.consumption_level:
            self._set_consumption_level(decision_level)

    def read_regime(self):
        regime_names = ['not defined', 'bulk', 'absorb', 'float']
        input_absorb = self.gpio_interface.read_value('GPIO', self.cfg['gpio']['regime_inputs']['absorb'])
        input_float = self.gpio_interface.read_value('GPIO', self.cfg['gpio']['regime_inputs']['float'])
        if input_absorb and not input_float:
            regime = 2
        elif not input_absorb and input_float:
            regime = 3
        elif not input_absorb and input_float:
            regime = 1
        else:
            regime = 0
        regime = 2
        self.regime = regime
        self.regime_str = regime_names[regime]
        log_event(self.cfg, self.module_name, '', 'INFO', 'Phase: ' + regime_names[self.regime])

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
            changes = [-1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -11, -12, -13]
            level = 0
        else:
            if level > self.consumption_level:
                changes = self.mapping_table[level - 1]
            else:
                changes = [-x for x in self.mapping_table[level]]

        for change in changes:
            channel = self.cfg['gpio']['relays_outputs']['channels'][abs(change)-1]
            desired_state = change > 0
            self.gpio_interface.write_gpio(channel, desired_state)

        log_event(self.cfg, self.module_name, '', 'INFO', 'Consumption level set on ' + str(level))
        self.load = self.cfg['controller']['loads'][level]
        self.consumption_level = level

        data_point = BufferEntity(
            {'measurement': self.cfg['influxdb']['state_measurement_name'],
             'tags': {'Unit': 'V'},
             'fields': {'Value': level},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

        data_point_consumption = BufferEntity(
            {'measurement': self.cfg['influxdb']['consumption_measurement_name'],
             'fields': {'Value': self.cfg['controller']['loads'][level]},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point_consumption)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Consumption level ' + str(self.consumption_level))

    def _voltage_evaluation(self):
        """
        This method calculates average voltage value and check whether it changes or does not
        :return:
        """

        new_level = self.consumption_level

        voltage_values = self._voltage_data

        if not len(voltage_values):
            log_event(self.cfg, self.module_name, '', 'WARN', 'Not enough voltage data points for evaluation')
            return new_level

        avg_voltage = sum(voltage_values) / len(voltage_values)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Calculated average value:' + str(avg_voltage))

        if avg_voltage <= self.cfg['controller']['voltage_critical_level']:
            log_event(self.cfg, self.module_name, '', 'INFO', 'The voltage level is too low')
            return -1

        if self.regime == 0:
            return -1

        if self.regime == 1:
            if avg_voltage >= self.cfg['controller']['voltage_absorb_limit_max']:
                new_level = min(new_level+1, 23)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level is to increase: ' + str(avg_voltage) + '>=' + str(self.voltage_average))
            if avg_voltage <= self.cfg['controller']['voltage_absorb_limit_min']:
                new_level = max(new_level - 1, 0)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level is to decrease: ' + str(avg_voltage) + '<=' + str(self.voltage_average))

        if self.regime == 2:
            if avg_voltage >= self.cfg['controller']['voltage_float_limit_max']:
                new_level = min(new_level+1, 23)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level is to increase: ' + str(avg_voltage) + '>=' + str(self.voltage_average))
            if avg_voltage <= self.cfg['controller']['voltage_float_limit_min']:
                new_level = max(new_level - 1, 0)
                log_event(self.cfg, self.module_name, '', 'INFO',
                          'The consumption level is to decrease: ' + str(avg_voltage) + '<=' + str(self.voltage_average))

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
            self._data_collection_step_regime()
            self._data_collection_step_voltage_input()
            self._data_collection_step_output_states()
            time_till_next_step = 1 - (time.time() - start_time)
            if time_till_next_step > 0:
                time.sleep(time_till_next_step)
        else:
            self._stopped_data_collection = True
            log_event(self.cfg, self.module_name, '', 'INFO', 'Data collection stopped')

    def _data_collection_step_regime(self):
        """
        This method is a single data collection step
        :return:
        """

        # Add regime data point in buffer
        data_point = BufferEntity(
            {'measurement': self.cfg['influxdb']['regime_measurement_name'],
             'fields': {'Value': self.regime},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

    def _data_collection_step_voltage_input(self):
        """
        This method is a single data collection step
        :return:
        """
        voltage_value = self.gpio_interface.read_value('i2c', self.cfg['gpio']['voltage_sensor'])
        log_event(self.cfg, self.module_name, '', 'INFO', 'Data point collected ' + str(voltage_value))
        self._voltage_data.append(voltage_value)

        self.voltage_value = voltage_value

        # Add voltage data point in buffer
        data_point = BufferEntity(
            {'measurement': self.cfg['influxdb']['voltage_measurement_name'],
             'tags': {'Unit': 'V',
                      'SclMin': self.cfg['gpio']['voltage_sensor']['scale_min'],
                      'SclMax': self.cfg['gpio']['voltage_sensor']['scale_max']},
             'fields': {'Value': voltage_value},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

    def _data_collection_step_output_states(self):
        output_state = self.get_gpio_state()

        # Add data point in buffer
        data_point_level = BufferEntity(
            {'measurement': self.cfg['influxdb']['output_measurement_name'],
             'fields': {'Output01': output_state[0],
                        'Output02': output_state[1],
                        'Output03': output_state[2],
                        'Output04': output_state[3],
                        'Output05': output_state[4],
                        'Output06': output_state[5],
                        'Output07': output_state[6],
                        'Output08': output_state[7],
                        'Output09': output_state[8],
                        'Output10': output_state[9],
                        'Output11': output_state[10],
                        'Output12': output_state[11],
                        'Output13': output_state[12]},
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
            {'measurement': self.cfg['influxdb']['mode_measurement_name'],
             'fields': {'Value': int(self.mode_auto)},
             'timestamp': round(time.time() * 1000)}
        )
        self.buffer.add_point(data_point)

    def get_consumption_level(self):
        return self.consumption_level

    def get_gpio_state(self):
        output_state = []
        for channel in self.cfg['gpio']['relays_outputs']['channels']:
            #state = True
            state = self.gpio_interface.check_gpio_state(channel, False)
            output_state.append(state)
        return output_state

    def set_gpio_state(self, output_no, state):
        channel = self.cfg['gpio']['relays_outputs']['channels'][output_no]
        self.gpio_interface.write_gpio('gpio', channel, state)
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
