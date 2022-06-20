#!/usr/bin/env python3
""" Spit out info from rws file"""
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import Counter, defaultdict
import re

from bs4 import BeautifulSoup

POSITION_PATTERN = re.compile(r'\((.*), (.*), (.*)\)')

def classname(node):
    for k, v in node.attrs.items():
        if k.lower() == 'class':
            return v
    return []

def location(thing):
    """ Which cardinal location an object is in"""
    x, y = position(thing)
    if x < 83:
        if y < 83:
            return 'SW'
        elif y < 167:
            return 'W'
        else:
            return 'NW'
    if x < 167:
        if y < 83:
            return 'S'
        elif y < 167:
            return 'C'
        else:
            return 'N'
    else:
        if y < 83:
            return 'SE'
        elif y < 167:
            return 'E'
        else:
            return 'NE'

def position(thing):
    """ Returns x,y coordinates of object """
    x, _, y = POSITION_PATTERN.match(attribute(thing, 'pos')).groups()
    return int(x), int(y)

def attribute(node, tags, default=''):
    """ Returns the text for the node at the end of the tag chain or '' """
    current_node = node
    if isinstance(tags, str):
        tags = (tags,)
    for tag in tags:
        try:
            current_node = current_node.find(tag, recursive=False)
        except AttributeError:
            return default
    return current_node and current_node.text or default

def animals(soup):
    """ Animals owned by colonists."""
    animals = Counter()
    def add_animal(thing):
        if attribute(thing, 'def') != 'Human' and attribute(thing, 'faction') and attribute(thing,'mindstate'):
            animals[attribute(thing, 'def')] += 1
    for alivepawns in soup.find_all('pawnsalive'):
        for li in alivepawns.findChildren('li', recursive=False):
            add_animal(li)
    for thing in soup.find_all('thing'):
        add_animal(thing)
    for animal in sorted(animals):
        print("{},{}".format(animal, animals[animal]))

def pawn_skills(soup):
    inventory = Counter()
    pawns = []
    def add_pawn(thing):
        if attribute(thing, 'kinddef') == 'Colonist':
            pawn = [attribute(thing, ('name', 'nick',))]
            for skill in thing.skills.find_all('li'):
                if attribute(skill, 'def'):
                    pawn.append(attribute(skill, 'level', '0'))
            pawns.append(','.join(pawn))
    for alivepawns in soup.find_all('pawnsalive'):
        for thing in alivepawns.findChildren('li', recursive=False):
            add_pawn(thing)
    for thing in soup.find_all('thing'):
        add_pawn(thing)
    for pawn in sorted(pawns):
        print(pawn)

def inventory_list(soup):
    inventory = Counter()
    equipment = Counter()
    for thing in soup.find_all('thing'):
        try:
            category = classname(thing)[0]
        except IndexError:
            continue
        if category in ('ThingWithComps', 'Medicine', 'Apparel'):
            name = attribute(thing, 'def')
            if name == 'Luciferium':
                print(thing)
                raise RuntimeError
            value = int(attribute(thing, 'stackcount', '0'))
            if value:
                inventory[name] += value
        if "MinifiedThing" in category:
            subthing = thing.innercontainer.innerlist.li.find('def').text
            inventory[subthing] += 1

    for k in sorted(inventory):
        v = inventory[k]
        print(','.join((k, str(v),)))

def equipment_list(soup):
    people = defaultdict(list)
    for thing in soup.find_all('thing'):
        category = classname(thing)
        if category == ['Pawn',] and attribute(thing, 'kinddef') == 'Colonist':
            key = attribute(thing, ('name', 'nick',))

            for item in thing.apparel.find_all('li'):
                people[key].append("  {:15} ({})".format(attribute(item, 'def')[8:], attribute(item, 'stuff')))
            for item in thing.equipment.find_all('li'):
                weapon = attribute(item, 'def')
                if weapon:
                    _, name = weapon.split('_', 2)
                    people[key].append("  {:15} ({})".format(name, attribute(item, 'quality')))
    for person in sorted(people):
        print(person)
        for item in people[person]:
            print("  {}".format(item))

def harvest(soup):
    herbs = Counter()
    berries = Counter()
    for thing in soup.find_all('thing'):
        growth = attribute(thing, 'growth')
        if not growth == '1':
            continue
        name = attribute(thing, 'def')
        
        if name == 'Plant_Berry':
            berries[location(thing)] += 1
        elif name == 'Plant_HealrootWild':
            herbs[location(thing)] += 1
    print('Herbs/Berries')
    for locs in (('NW', 'N', 'NE',), ('W', 'C', 'E',), ('SW', 'S', 'SE',),):
        print('{:2}/{:2} | {:2}/{:2} | {:2}/{:2}'.format(
            herbs[locs[0]], berries[locs[0]], herbs[locs[1]], berries[locs[1]], herbs[locs[2]], berries[locs[2]],
            ))
            
def run(args):
    config = ConfigParser()
    config.read('local/parse.cnf')
    options = config[args.faction]
    with open(options['file']) as f:
        soup = BeautifulSoup(f, 'lxml')
    if args.action == 'skills':
        pawn_skills(soup)
    elif args.action == 'inventory':
        inventory_list(soup)
    elif args.action == 'equipment':
        equipment_list(soup)
    elif args.action == 'animals':
        animals(soup)
    elif args.action == 'harvest':
        harvest(soup)

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("faction", help="name of faction")
    parser.add_argument("action", choices=['equipment', 'skills', 'inventory', 'animals', 'harvest',], help="skills or inventory")
    args = parser.parse_args()
    run(args)
