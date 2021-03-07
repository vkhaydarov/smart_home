from flask import Flask, jsonify, render_template
import threading
import time
from random import randint

class Frontend:
    def __init__(self, host, port, edge_node_obj, idb_obj):
        self.host = host
        self.port = port
        self.edge_node_obj = edge_node_obj
        self.idb_obj = idb_obj
        self.app = None

    def start(self):
        # Initialise flask app
        app = Flask('Frontend', template_folder='src/templates', static_folder='src/static')
        self.app = app

        edge_node_obj = self.edge_node_obj
        idb_obj = self.idb_obj

        def get_values():
            output_states = edge_node_obj.get_gpio_state()
            return {
                "status_edge_node": edge_node_obj.running,
                "status_influxdb": idb_obj.connection_status,
                "mode_auto": edge_node_obj.mode_auto,
                "mode_manual": edge_node_obj.mode_manual,
                "auto_mode_requested": edge_node_obj.auto_mode_requested,
                "consumption_level": edge_node_obj.consumption_level,
                "load": edge_node_obj.load,
                "voltage_value": edge_node_obj.voltage_value,
                "voltage_average": edge_node_obj.voltage_average,
                "output1": output_states[0],
                "output2": output_states[1],
                "output3": output_states[2],
                "output4": output_states[3],
                "output5": output_states[4],
            }

        # Main page
        @app.route("/")
        def main():
            return render_template('index.html', data=get_values())

        @app.route("/api/info")
        def send_and_receive_info():
            return jsonify(get_values())

        @app.route('/Emergency')
        def emergency():
            print('EMERGENCY')
            edge_node_obj.switch_to_manual_mode()
            return "Nothing"

        @app.route('/IncreaseLevel')
        def increase_consumption_level():
            print('IncreaseLevel')
            edge_node_obj.increase_consumption_level()
            return "Nothing"

        @app.route('/DecreaseLevel')
        def decrease_consumption_level():
            print('DecreaseLevel')
            edge_node_obj.decrease_consumption_level()
            return "Nothing"

        @app.route('/AutoMode')
        def switch_to_auto():
            print('AutoMode')
            edge_node_obj.switch_to_auto_mode()
            return "Nothing"

        @app.route('/ManualMode')
        def switch_to_manual():
            print('ManualMode')
            edge_node_obj.switch_to_manual_mode()
            return "Nothing"

        _thread = threading.Thread(target=app.run, kwargs={'host': self.host, 'port': self.port})
        _thread.start()
