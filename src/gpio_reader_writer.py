#import time
#import board
#import busio
#import adafruit_ads1x15.ads1015 as ADS
#from adafruit_ads1x15.analog_in import AnalogIn
#import RPi.GPIO as GPIO
from random import randint


class GPIODataReaderWriter:
    def __init__(self):
        #self.i2c = busio.I2C(board.SCL, board.SDA)
        #GPIO.setmode(GPIO.BOARD)
        pass

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

        #ads = ADS.ADS1015(self.i2c)
        if channel_no == 0:
            #analog_input = AnalogIn(ads, ADS.P0)
            analog_input = randint(0, 32000)
        if analog_input:
            #read_value = scale_min + analog_input.value * (scale_max-scale_min)/2**15
            read_value = scale_min + analog_input * (scale_max-scale_min)/2**15
        else:
            read_value = None
        print('Read ', read_value, ' from channel ', channel_no)
        return read_value

    def write_value(self, access_type, access_data, value):
        if access_type == 'gpio':
            write_status = self._write_gpio(access_data, value)
        else:
            write_status = None
        return write_status

    def _write_gpio(self, access_data, value):
        channel_no = access_data['channel_no']
        #GPIO.setup(channel_no, GPIO.OUT)
        #if value:
        #    state = GPIO.HIGH
        #else:
        #    state = GPIO.LOW
        #write_status = GPIO.output(channel_no, state)
        print('Wrote ', value, ' in channel ', channel_no)
        write_status = True
        return write_status


    def check_gpio_state(self, access_data, value):
        channel_no = access_data['channel_no']
        #if value:
        #    state = GPIO.HIGH
        #else:
        #    state = GPIO.LOW
        #current_state = GPIO.input(channel_no, state)
        current_state = value
        return current_state == value
