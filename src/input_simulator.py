from math import sin, pi
from random import randint


class InputSimulator:
    def __init__(self, initial_value, profile):
        self.profile = profile
        self.time_step = 0
        self.lower_limit = 50
        self.upper_limit = 60

        self.value = initial_value
        self.value_raw = self.voltage_to_raw(initial_value)

    def voltage_to_raw(self, voltage):
        return (voltage - self.lower_limit) * 2**15/(self.upper_limit - self.lower_limit)

    def calculate_next_value(self):
        if self.profile == 'constant':
            value = 58
        elif self.profile == 'ascending':
            value = min(self.value+0.1, self.upper_limit)
        elif self.profile == 'descending':
            value = max(self.value-0.1, self.lower_limit)
        elif self.profile == 'sine':
            value = (self.lower_limit + self.upper_limit)/2 +\
                    (self.upper_limit - self.lower_limit)/2 * sin(self.time_step/(2*pi)/3 - pi/2)
        elif self.profile == 'critical_low':
            if self.time_step <= 60:
                value = self.upper_limit
            elif self.time_step <= 90:
                value = self.lower_limit
            else:
                value = self.value
                self.reset_time()
        elif self.profile == 'random':
            value = randint(self.lower_limit, self.upper_limit)
        else:
            value = self.value
        self.time_step += 1
        self.value = value
        self.value_raw = self.voltage_to_raw(value)

    def get_voltage_value(self):
        self.calculate_next_value()
        return self.value

    def get_raw_value(self):
        self.calculate_next_value()
        return self.value_raw

    def reset_time(self):
        self.time_step = 0


if __name__ == '__main__':
    sim = InputSimulator(55, 'sine')
    sim_values = []
    for time_step in range(120):
        sim_values.append(sim.get_raw_value())
