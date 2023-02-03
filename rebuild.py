#!/usr/bin/python3
""" Rebuilds the conf file with existing scenarios"""
from argparse import ArgumentParser
from configparser import ConfigParser
import os

from parse import CONFIG

def add_new_remove_absent(old_config):
    new_config = ConfigParser()
    new_config.add_section('path')
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
    
def run(args):
    old_config = ConfigParser()
    old_config.read(CONFIG)
    if args.l:
        skip = ('DEFAULT', 'path',)
        for x in old_config:
            if x not in skip:
                print(x)
    else:
        add_new_remove_absent(old_config)
if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("-l", action="store_true", default=False, help="List existing")
    args = parser.parse_args()
    run(args)
