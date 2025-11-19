#!/usr/bin/env python3

__author__ = 'Tim'
import json
import sys
import config

# Load given specFile. Specfile was created from original
# RESOL Configuration File XML shipped with RSC (Resol Service Center)
# using XML to JSON converter at http://www.utilities-online.info/xmltojson
with open(config.spec_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
    try:
        spec = data['vbusSpecification']
    except Exception:
        sys.exit('Cannot load Spec')

if config.debug:
    for device in spec.get('device', []):
        print(device)

    for packet in spec.get('packet', []):
        print(packet)
        for field in packet.get('field', []):
            print("  " + str(field))

#json_data.close()
