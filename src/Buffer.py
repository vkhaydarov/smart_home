from src.event_logger import log_event


class BufferEntity:
    """
    Buffer entity class consists of opc ua node information as well as read opcua invariant
    """

    def __init__(self, data):
        self.data = data

    def convert_to_line_protocol(self):
        """
        This function converts received data into influxdb line protocol
        :return:
        """

        try:
            # Measurement
            data_line = self.data['measurement']

            # Tags
            if 'tags' in self.data:
                for key, value in self.data['tags'].items():
                    if isinstance(value, (int, float)):
                        data_line += ',' + key + '=' + str(value)
                    else:
                        value = value.replace(' ', '')
                        data_line += ',' + key + '=' + value

            # Backspace between tags and fields
            data_line += ' '

            # Fields
            for key, value in self.data['fields'].items():
                if isinstance(value, bool):
                    value = int(value)
                if isinstance(value, (int, float)):
                    data_line += key + '=' + str(value) + ','
                else:
                    value = value.replace(' ', '')
                    data_line += key + '="' + value + '",'

            # Removing last comma
            data_line = data_line[:-1]

            # Adding timestamp
            data_line += ' ' + str(self.data['timestamp'])

            return [True, data_line]

        except Exception as err:
            return [False, err]


class Buffer:
    """
    Buffer class plays role a temporary FIFO storage for data points before ingestion into influx db
    """

    def __init__(self, cfg):
        """
        Initialisation
        :param cfg: Set of parameters including maximal buffer size and text output parameters
        """
        self.module_name = 'Buffer'
        self.cfg = cfg
        self.max_buffer_size = self.cfg['buffer']['max_size']
        self.buffer = []

    def add_point(self, buffer_entity):
        """
        This function puts additional entity into buffer
        :param buffer_entity: buffer entity consisted of node instance and opcua variant
        :return:
        """

        # If after adding a point, the buffer will be overfilled, we will remove the first entity in the buffer
        if len(self.buffer) + 1 > self.max_buffer_size:
            self.remove_point(0)
            log_event(self.cfg, self.module_name, '', 'WARN', 'Buffer is full (' + str(len(self.buffer)) + ')')

        # Append entity
        self.buffer.append(buffer_entity)
        log_event(self.cfg, self.module_name, '', 'INFO', 'Point copied into buffer (size=' + str(self.len()) + ')')

    def remove_point(self, idx=0):
        """
        This function removes specified element of the buffer. If not specified, removes the very first element.
        :param idx: Index of the element to remove
        :return:
        """

        # Removing operation is only valid if valid index is provided
        if (idx < 0) or (idx > len(self.buffer) - 1):
            log_event(self.cfg, self.module_name, '', 'WARN', str(idx) + ' element does not exist in buffer')
            return
        del self.buffer[idx]
        log_event(self.cfg, self.module_name, '', 'INFO',
                  'Point ' + str(idx) + ' removed from buffer (size=' + str(self.len()) + ')')

    def remove_points(self, idx):
        """
        This function removes a set of elements.
        :param idx: list of indices
        :return:
        """
        # Removing duplicates
        idx = list(dict.fromkeys(idx))

        # Loop within sorted and reversed list
        for i in sorted(idx, reverse=True):
            self.remove_point(i)
        log_event(self.cfg, self.module_name, '', 'INFO',
                  str(len(idx)) + ' points removed from buffer (size=' + str(self.len()) + ')')

    def len(self):
        """
        This function returns the actual length of the buffer
        :return: Actual length of the buffer
        """
        return len(self.buffer)

    def get_snapshot(self):
        """
        This function creates a snapshot of the buffer in order to decouple data with the mutable list object
        :return:
        """
        return list(self.buffer)
