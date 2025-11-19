#!/usr/bin/env python3
"""Parsing helpers to decode raw VBUS bytes into a result dict.

Public API:
- parse_raw_bytes(raw_bytes) -> dict

This module re-implements the parsing parts of `resol.py` to allow
offline parsing of captured binary files.
"""

from typing import Dict
import spec
import config


def bytes_to_int(b):
    if isinstance(b, int):
        return b
    if isinstance(b, (bytes, bytearray)) and len(b) == 1:
        return b[0]
    raise TypeError('Unsupported byte value')


def format_byte(byte):
    if isinstance(byte, int):
        v = byte
    elif isinstance(byte, (bytes, bytearray)) and len(byte) >= 1:
        v = byte[0]
    else:
        raise TypeError('Unsupported byte')
    return '0x%02x' % v


def integrate_septett(frame: bytes) -> bytes:
    septet = bytes_to_int(frame[4])
    out = bytearray()
    for j in range(4):
        b = bytes_to_int(frame[j])
        if septet & (1 << j):
            out.append(b | 0x80)
        else:
            out.append(b)
    return bytes(out)


def gb(data: bytes, begin: int, end: int) -> int:
    segment = data[begin:end]
    wbg = sum([0xff << (i * 8) for i, b in enumerate(segment)])
    s = sum([b << (i * 8) for i, b in enumerate(segment)])
    if s >= wbg / 2:
        s = -1 * (wbg - s)
    return s


def get_compare_length(mask: str) -> int:
    i = 1
    while i < 6 and mask[i] != '0':
        i += 1
    return i + 1


def get_source_name_from_msg(msg: bytes) -> str:
    src = format_byte(msg[3]) + format_byte(msg[2])[2:]
    for device in spec.spec.get('device', []):
        if src[:get_compare_length(device['mask'])].lower() == device['address'][:get_compare_length(device['mask'])].lower():
            return device['name'] if get_compare_length(device['mask']) == 7 else str(device['name']).replace('#', device['address'][get_compare_length(device['mask']) - 1:], 1)
    return ''


def get_protocolversion(msg: bytes) -> str:
    v = bytes_to_int(msg[4])
    if v == 0x10:
        return 'PV1'
    if v == 0x20:
        return 'PV2'
    if v == 0x30:
        return 'PV3'
    return 'UNKNOWN'


def get_frame_count(msg: bytes) -> int:
    return gb(msg, 7, 8)


def get_payload(msg: bytes) -> bytes:
    payload = b''
    for i in range(get_frame_count(msg)):
        payload += integrate_septett(msg[9 + (i * 6):15 + (i * 6)])
    return payload


def get_source(msg: bytes) -> str:
    return format_byte(msg[3]) + format_byte(msg[2])[2:]


def get_destination(msg: bytes) -> str:
    return format_byte(msg[1]) + format_byte(msg[0])[2:]


def get_command(msg: bytes) -> str:
    # msg[5:6] is a single-byte slice
    return format_byte(msg[6]) + format_byte(msg[5:6])[2:]


def parse_message(msg: bytes, result: Dict):
    # Only PV1 is parsed into fields currently
    if get_protocolversion(msg) != 'PV1':
        return

    payload = get_payload(msg)
    if config.debug:
        print('Parsing payload length', len(payload))

    for packet in spec.spec.get('packet', []):
        if packet['source'].lower() == get_source(msg).lower() and packet['destination'].lower() == get_destination(msg).lower() and packet['command'].lower() == get_command(msg).lower():
            name = get_source_name_from_msg(msg)
            result[name] = {}
            for field in packet.get('field', []):
                offset = int(field['offset'])
                bit_size = int(field['bitSize'])
                length = (bit_size + 1) // 8
                val = gb(payload, offset, offset + length)
                factor = float(field['factor']) if 'factor' in field else 1
                unit = field['unit'] if 'unit' in field else ''
                result[name][field['name'][0]] = str(val * factor) + unit


def parse_raw_bytes(raw: bytes) -> Dict:
    """Parse raw bytes (may contain multiple messages / sync bytes) and return result dict."""
    result = {}
    parts = raw.split(b'\xAA')
    # take the message parts (non-empty middle parts)
    msgs = [p for p in parts if p]
    for msg in msgs:
        # msg here is the chunk after 0xAA and before next 0xAA
        try:
            parse_message(msg, result)
        except Exception:
            # be tolerant of malformed frames
            continue
    return result
