#!/usr/bin/env python3

# Talk with Resol VBUS over LAN or serial UART (Python 3 port)

import socket
import sys
import json

# Load settings
try:
    import config
except Exception:
    sys.exit("config.py not found!")

if config.connection == "serial":
    # import serial (pyserial) only if it's configured to not force installing it without needing
    import serial

# Load Message specification
try:
    import spec
except Exception:
    sys.exit("Could not load Message Specification")


def bytes_to_int(b):
    # b can be an int (Python3 bytes indexing) or a single-byte bytes object
    if isinstance(b, int):
        return b
    if isinstance(b, bytes) and len(b) == 1:
        return b[0]
    raise TypeError("Unsupported byte value: %r" % (b,))


def format_byte(byte):
    # Accept int or single-byte bytes
    if isinstance(byte, int):
        v = byte
    elif isinstance(byte, (bytes, bytearray)) and len(byte) >= 1:
        v = byte[0]
    else:
        raise TypeError("Unsupported byte: %r" % (byte,))
    return '0x%02x' % v


def login():
    dat = recv()

    # Check if device answered
    if dat != b"+HELLO\n":
        return False

    # Send Password
    send(("PASS %s\n" % config.vbus_pass).encode('ascii'))

    dat = recv()

    return dat.startswith(b"+OK")


def load_data():
    if config.connection == "lan":
        # Request Data
        send(b"DATA\n")

        dat = recv()

        # Check if device is ready to send Data
        if not dat.startswith(b"+OK"):
            return

    while len(result) < config.expected_packets:
        buf = readstream()
        msgs = splitmsg(buf)
        if config.debug:
            print(str(len(msgs)) + " Messages, " + str(len(result)) + " Resultlen")
        for msg in msgs:
            if config.debug:
                print(get_protocolversion(msg))
            if "PV1" == get_protocolversion(msg):
                if config.debug:
                    print(format_message_pv1(msg))
                parse_payload(msg)
            elif "PV2" == get_protocolversion(msg):
                if config.debug:
                    print(format_message_pv2(msg))


def recv():
    # return bytes
    if config.connection == "serial" or config.connection == "stdin":
        dat = sock.read(1024)
    else:
        dat = sock.recv(1024)
    return dat


def send(dat):
    # dat should be bytes
    sock.send(dat)


def readstream():
    data = recv()
    while data.count(b'\xAA') < 4:
        data += recv()
    return data


def splitmsg(buf):
    return buf.split(b'\xAA')[1:-1]


def get_protocolversion(msg):
    v = bytes_to_int(msg[4])
    if v == 0x10:
        return "PV1"
    if v == 0x20:
        return "PV2"
    if v == 0x30:
        return "PV3"
    return "UNKNOWN"


def get_destination(msg):
    return format_byte(msg[1]) + format_byte(msg[0])[2:]


def get_source(msg):
    return format_byte(msg[3]) + format_byte(msg[2])[2:]


def get_command(msg):
    return format_byte(msg[6]) + format_byte(msg[5:6])[2:]


def get_frame_count(msg):
    return gb(msg, 7, 8)


def integrate_septett(frame):
    # frame is bytes-like of length >=5, last byte is septet
    septet = bytes_to_int(frame[4])
    out = bytearray()
    for j in range(4):
        b = bytes_to_int(frame[j])
        if septet & (1 << j):
            out.append(b | 0x80)
        else:
            out.append(b)
    return bytes(out)


def get_payload(msg):
    payload = b''
    for i in range(get_frame_count(msg)):
        payload += integrate_septett(msg[9 + (i * 6):15 + (i * 6)])
    return payload


def parse_payload(msg):
    payload = get_payload(msg)

    if config.debug:
        print('ParsePacket Payload ' + str(len(payload)))

    for packet in spec.spec['packet']:
        if packet['source'].lower() == get_source(msg).lower() and packet['destination'].lower() == get_destination(msg).lower() and packet['command'].lower() == get_command(msg).lower():
            result[get_source_name(msg)] = {}
            for field in packet['field']:
                offset = int(field['offset'])
                bit_size = int(field['bitSize'])
                length = (bit_size + 1) // 8
                val = gb(payload, offset, offset + length)
                factor = float(field['factor']) if 'factor' in field else 1
                unit = field['unit'] if 'unit' in field else ''
                result[get_source_name(msg)][field['name'][0]] = str(val * factor) + unit


def format_message_pv1(msg):
    parsed = "PARSED: \n"
    parsed += "    ZIEL".ljust(15, '.') + ": " + get_destination(msg) + "\n"
    parsed += "    QUELLE".ljust(15, '.') + ": " + get_source(msg) + " " + get_source_name(msg) + "\n"
    parsed += "    PROTOKOLL".ljust(15, '.') + ": " + get_protocolversion(msg) + "\n"
    parsed += "    BEFEHL".ljust(15, '.') + ": " + get_command(msg) + "\n"
    parsed += "    ANZ_FRAMES".ljust(15, '.') + ": " + str(get_frame_count(msg)) + "\n"
    parsed += "    CHECKSUM".ljust(15, '.') + ": " + format_byte(msg[8]) + "\n"
    for i in range(get_frame_count(msg)):
        integrated = integrate_septett(msg[9 + (i * 6):15 + (i * 6)])
        parsed += ("    NB" + str(i * 4 + 1)).ljust(15, '.') + ": " + format_byte(msg[9 + (i * 6)]) + " - " + format_byte(integrated[0]) + "\n"
        parsed += ("    NB" + str(i * 4 + 2)).ljust(15, '.') + ": " + format_byte(msg[10 + (i * 6)]) + " - " + format_byte(integrated[1]) + "\n"
        parsed += ("    NB" + str(i * 4 + 3)).ljust(15, '.') + ": " + format_byte(msg[11 + (i * 6)]) + " - " + format_byte(integrated[2]) + "\n"
        parsed += ("    NB" + str(i * 4 + 4)).ljust(15, '.') + ": " + format_byte(msg[12 + (i * 6)]) + " - " + format_byte(integrated[3]) + "\n"
        parsed += ("    SEPTETT" + str(i + 1)).ljust(15, '.') + ": " + format_byte(msg[13 + (i * 6)]) + "\n"
        parsed += ("    CHECKSUM" + str(i + 1)).ljust(15, '.') + ": " + format_byte(msg[14 + (i * 6)]) + "\n"
    parsed += "    PAYLOAD".ljust(15, '.') + ": " + (" ".join(format_byte(b) for b in get_payload(msg))) + "\n"
    return parsed


def format_message_pv2(msg):
    parsed = "PARSED: \n"
    parsed += "    ZIEL1".ljust(15, '.') + ": " + format_byte(msg[0:1]) + "\n"
    parsed += "    ZIEL2".ljust(15, '.') + ": " + format_byte(msg[1:2]) + "\n"
    parsed += "    QUELLE1".ljust(15, '.') + ": " + format_byte(msg[2:3]) + "\n"
    parsed += "    QUELLE2".ljust(15, '.') + ": " + format_byte(msg[3:4]) + "\n"
    parsed += "    PROTOKOLL".ljust(15, '.') + ": " + format_byte(msg[4:5]) + "\n"
    parsed += "    BEFEHL1".ljust(15, '.') + ": " + format_byte(msg[5:6]) + "\n"
    parsed += "    BEFEHL2".ljust(15, '.') + ": " + format_byte(msg[6:7]) + "\n"
    parsed += "    ID1".ljust(15, '.') + ": " + format_byte(msg[7:8]) + "\n"
    parsed += "    ID2".ljust(15, '.') + ": " + format_byte(msg[8:9]) + "\n"
    parsed += "    WERT1".ljust(15, '.') + ": " + format_byte(msg[9:10]) + "\n"
    parsed += "    WERT2".ljust(15, '.') + ": " + format_byte(msg[10:11]) + "\n"
    parsed += "    WERT3".ljust(15, '.') + ": " + format_byte(msg[11:12]) + "\n"
    parsed += "    WERT4".ljust(15, '.') + ": " + format_byte(msg[12:13]) + "\n"
    parsed += "    SEPTETT".ljust(15, '.') + ": " + format_byte(msg[13:14]) + "\n"
    parsed += "    CHECKSUM".ljust(15, '.') + ": " + format_byte(msg[14:15]) + "\n"
    return parsed


def get_compare_length(mask):
    i = 1
    while i < 6 and mask[i] != '0':
        i += 1
    return i + 1


def get_source_name(msg):
    src = format_byte(msg[3]) + format_byte(msg[2])[2:]
    for device in spec.spec['device']:
        if src[:get_compare_length(device['mask'])].lower() == device['address'][:get_compare_length(device['mask'])].lower():
            return device['name'] if get_compare_length(device['mask']) == 7 else str(device['name']).replace('#', device['address'][get_compare_length(device['mask']) - 1:], 1)
    return ""


def gb(data, begin, end):  # GetBytes
    # data is bytes-like; interpret little-endian signed integer
    segment = data[begin:end]
    wbg = sum([0xff << (i * 8) for i, b in enumerate(segment)])
    s = sum([b << (i * 8) for i, b in enumerate(segment)])
    if s >= wbg / 2:
        s = -1 * (wbg - s)
    return s


if __name__ == '__main__':
    if config.connection == "serial":
        sock = serial.Serial(config.port, baudrate=config.baudrate, timeout=0)
    elif config.connection == "lan":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(config.address)
        login()
    elif config.connection == "stdin":
        # use buffer to read raw bytes from stdin
        sock = sys.stdin.buffer
    else:
        sys.exit('Unknown connection type. Please check config.')

    result = dict()
    load_data()

    print(json.dumps(result))

    if config.connection == "lan":
        try:
            sock.shutdown(0)
        except Exception:
            pass
    try:
        sock.close()
    except Exception:
        pass
    sock = None
