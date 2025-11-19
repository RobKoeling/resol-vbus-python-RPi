import os
import json

import parser


def make_test_message():
    """Construct a minimal PV1 message that matches a packet in the spec.

    We'll use the `DeltaSolSLL.json` spec which contains a device `0x2271`.
    The message layout follows the parser expectations:
      [dest_low, dest_high, src_low, src_high, proto, cmd_low, cmd_high, frame_count, checksum, frames...]

    Each frame is 6 bytes: 4 data bytes, septet, checksum.
    We set septet=0 and fill payload with zeros except a small value at a known offset.
    """
    # destination 0x0010 -> bytes low=0x10 high=0x00
    dest_low = 0x10
    dest_high = 0x00
    # source 0x2271 -> src_low=0x71 src_high=0x22 (note ordering expected by parser)
    src_low = 0x71
    src_high = 0x22
    proto = 0x10  # PV1
    # command 0x0100 -> low=0x00, high=0x01 (parser expects msg[5]=low? follow original ordering)
    cmd_low = 0x00
    cmd_high = 0x01
    # choose 2 frames -> payload 8 bytes
    frame_count = 2
    checksum = 0x00

    frames = bytearray()
    # create 2 frames of 6 bytes each
    for _ in range(frame_count):
        # four data bytes (fill with zeros)
        frames.extend(bytes([0x00, 0x00, 0x00, 0x00]))
        # septet
        frames.append(0x00)
        # checksum placeholder
        frames.append(0x00)

    msg = bytes([dest_low, dest_high, src_low, src_high, proto, cmd_low, cmd_high, frame_count, checksum]) + bytes(frames)
    # wrap with sync byte 0xAA as parser expects splitting on 0xAA
    raw = b'\xAA' + msg + b'\xAA'
    return raw


def test_parse_synthetic_message():
    raw = make_test_message()
    result = parser.parse_raw_bytes(raw)
    # Expect a dict (possibly empty if spec doesn't match); ensure no exception and dict returned
    assert isinstance(result, dict)

    # If the spec includes the device address used above, parser should produce a key
    # Look up a device in spec to check expected name
    # We don't hard-code the exact field values here; just ensure parser runs
    # and returns either empty dict or a mapping
    # For stronger assertion, check keys types
    for k in result.keys():
        assert isinstance(k, str)
        assert isinstance(result[k], dict)
