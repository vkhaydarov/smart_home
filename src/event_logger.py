from datetime import datetime


def log_event(cfg, module, event, type, text_message):
    output_threshold = cfg['event_logger']['print_level']
    if output_threshold == 'DEBUG':
        print(compose_msg(module, type, text_message))
    elif output_threshold == 'INFO' and type in ['INFO', 'WARN', 'ERR']:
        print(compose_msg(module, type, text_message))
    elif output_threshold == 'WARN' and type in ['WARN', 'ERR']:
        print(compose_msg(module, type, text_message))
    elif output_threshold == 'ERR' and type in ['ERR']:
        print(compose_msg(module, type, text_message))

    if cfg['event_logger']['publish']:
        publish_event(event)


def compose_msg(module, type, text_message):
    msg_str = ''
    msg_str += str(datetime.now())
    msg_str += ' ['+module+']'
    msg_str += get_color(type) + '[' + type + '] ' + '\033[0m'
    msg_str += text_message
    return msg_str


def get_color(type):
    if type == 'INFO':
        return '\033[1m'
    elif type == 'WARN':
        return '\033[93m'
    elif type == 'ERR':
        return '\033[91m'
    else:
        return '\033[0m'


def publish_event(event):
    pass