#!/usr/bin/python3
""" Rebuilds the conf file with existing scenarios"""
from argparse import ArgumentParser
from configparser import ConfigParser
import os
import shutil
import time

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

def factions(old_config):
    to_return = list()
    skip = ('DEFAULT', 'path',)
    for x in old_config:
        if x not in skip:
            to_return.append(x)
    return to_return

def choose_faction(fs):
    print('Choose faction:')
    for f in fs:
        print(f"  {f}")
    faction = input()
    if not faction in fs:
        print('Not a faction')
        return choose_faction(fs)
    return faction

def run(args):
    old_config = ConfigParser()
    old_config.read(CONFIG)
    if args.action == 'list':
        skip = ('DEFAULT', 'path',)
        for faction in factions(old_config):
            print(faction)
    if args.action in ('save', 'restore'):
        fs = factions(old_config)
        if args.f:
            faction = args.f
            if not faction in fs:
                print(f"'{faction}' is not a valid faction")
                return
        elif len(fs) == 1:
            faction = fs[0]
        else:
            faction = choose_faction(fs)
        orig_file = old_config[faction]['file']
        backup_file = f"{old_config[faction]['file']}.bu"
        if args.action == 'save':
            shutil.copy(orig_file, backup_file)
        else:
            if not os.path.exists(backup_file):
                print(f"No backup file for {faction} exists")
                return
            if time.time() - os.path.getmtime(backup_file) > 24*60*60:
                if input("This backup file is over one day old. Continue? (y/N)  ") != 'y':
                    return
            shutil.copy2(backup_file, orig_file)
    else:
        add_new_remove_absent(old_config)

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('action', choices=('list', 'reset', 'save', 'restore'))
    parser.add_argument("-f", help="faction for save/restore")
    args = parser.parse_args()
    run(args)
