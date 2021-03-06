import time
from random import randint
from src.input_simulator import InputSimulator
import board
import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import RPi.GPIO as GPIO

class GPIODataReaderWriter:
    def __init__(self, deploy=False, test_profile=''):
        self.deploy = deploy
        self.test_profile = test_profile
        if deploy:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            GPIO.setmode(GPIO.BCM)
        else:
            self.gpio = [None] * 40
            self.voltage_simulator = InputSimulator(55, test_profile)

    def read_value(self, access_type, access_data):
        if access_type == 'i2c':
            read_value = self._read_i2c(access_data)
        else:
            read_value = None
        return read_value

    def _read_i2c(self, access_data):
        channel_no = access_data['channel_no']
        scale_min = access_data['scale_min']
        scale_max = access_data['scale_max']
        if self.deploy:
            ads = ADS.ADS1015(self.i2c)
            if channel_no == 0:
                analog_input = AnalogIn(ads, ADS.P0)
            if analog_input:
                read_value = scale_min + analog_input.value * (scale_max - scale_min) / 2 ** 15
            else:
                read_value = None
            print('Read ', read_value, ' from channel ', channel_no, ' raw value = ', analog_input.value)
        else:
            raw_value = self.voltage_simulator.get_raw_value()
            read_value = self.voltage_simulator.value
            print('Read simulated value ', read_value, ' from channel ', channel_no, ' raw value = ', raw_value)
        return read_value

    def write_value(self, access_type, access_data, value):
        if access_type == 'gpio':
            write_status = self._write_gpio(access_data, value)
        else:
            write_status = None
        return write_status

    def _write_gpio(self, access_data, value):
        channel_no = access_data['channel_no']
        if self.deploy:
            GPIO.setup(channel_no, GPIO.OUT)
            if value:
                state = GPIO.HIGH
            else:
                state = GPIO.LOW
            GPIO.output(channel_no, state)
        else:
            self.gpio[channel_no] = value
        print('Wrote ', value, ' in channel ', channel_no)
        write_status = True
        return write_status

    def check_gpio_state(self, access_data, value):
        channel_no = access_data['channel_no']
        if self.deploy:
            if value:
                state = GPIO.HIGH
            else:
                state = GPIO.LOW
            current_state = GPIO.input(channel_no)
        else:
            current_state = self.gpio[channel_no]
        return current_state == value
