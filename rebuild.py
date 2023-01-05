#!/usr/bin/python3
""" Rebuilds the conf file with existing scenarios"""
from configparser import ConfigParser
import os

from parse import CONFIG
def run():
    new_config = ConfigParser()
    new_config.add_section('path')
    old_config = ConfigParser()
    old_config.read(CONFIG)
    save_dir = old_config['path']['saves']
    new_config['path']['saves'] = save_dir
    rws_files = set()
    for filename in os.listdir(save_dir):
        if filename.endswith('rws'):
            rws_files.add(save_dir + filename)
    for section in old_config:
        try:
            if os.path.exists(old_config[section]['file']):
                rws_files.discard(old_config[section]['file'])
                new_config[section] = old_config[section]
        except KeyError:
            continue
    for rws in rws_files:
        print('Name for {}:'.format(rws))

        name = input()
        new_config[name] = {'file': rws}
    with open(CONFIG, 'w') as f:
        new_config.write(f)
if __name__ == '__main__':
    run()
