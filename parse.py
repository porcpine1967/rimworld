#!/usr/bin/env python3
""" Spit out info from rws file"""
from argparse import ArgumentParser
from collections import Counter

from bs4 import BeautifulSoup

def classname(node):
    for k, v in node.attrs.items():
        if k.lower() == 'class':
            return v
    return []

def pawn_skills(soup):
    inventory = Counter()
    pawns = []
    for thing in soup.find_all('thing'):
        try:
            if thing.kinddef.text != 'Colonist':
                continue
        except AttributeError:
            continue
        pawn = [thing.find('name').nick.text]
        for skill in thing.skills.skills:
            try:
                if skill.find('def').text:
                    try:
                        pawn.append(skill.find('level').text)
                    except AttributeError:
                        pawn.append('0')
            except(AttributeError):
                pass
        pawns.append(','.join(pawn))
    for pawn in sorted(pawns):
        print(pawn)
            
def inventory_list(soup):
    inventory = Counter()
    for thing in soup.find_all('thing'):
        try:
            category = classname(thing)[0]
        except IndexError:
            continue
        if category in ('ThingWithComps', 'Medicine', 'Apparel'):
            name = thing.find('def').text
            try:
                value = int(thing.find('stackcount').text)
                inventory[name] += value
            except (TypeError, AttributeError):
                print(thing)
        if "MinifiedThing" in category:
            subthing = thing.innercontainer.innerlist.li.find('def').text
            inventory[subthing] += 1

    for k in sorted(inventory):
        v = inventory[k]
        print(','.join((k, str(v),)))
    
def run(args):
    with open(args.filename) as f:
        soup = BeautifulSoup(f, 'lxml')
    if args.action == 'skills':
        pawn_skills(soup)
    elif args.action == 'inventory':
        inventory_list(soup)

    
if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("filename", help="Path to file to parser")
    parser.add_argument("action", choices=['skills', 'inventory'], help="skills or inventory")
    args = parser.parse_args()
    run(args)
