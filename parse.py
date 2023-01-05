#!/usr/bin/env python3
""" Spit out info from rws file"""
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import Counter, defaultdict
import csv
import re

from bs4 import BeautifulSoup

CONFIG = 'local/parse.cnf'
BUFFER_WIDTH = 12
POSITION_PATTERN = re.compile(r'\((.*), (.*), (.*)\)')
SKILLS = [
        'Shooting', 'Melee', 'Construction', 'Mining', 'Cooking', 'Plants', 'Animals', 'Crafting', 'Artistic', 'Medicine', 'Social', 'Intellectual']

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

def wildlife(soup):
    """ Animals not owned by colonists."""
    animals = Counter()
    def add_animal(thing):
        if attribute(thing, 'def') != 'Human' and not attribute(thing, 'faction') and attribute(thing,'mindstate'):
            animals[attribute(thing, 'def')] += 1
    for thing in soup.find_all('thing'):
        add_animal(thing)
    for animal in sorted(animals):
        print("{},{}".format(animal, animals[animal]))

class Pawn:
    def __init__(self, thing, options):
        self.name = attribute(thing, ('name', 'nick',)) or attribute( thing, ('name', 'first'))
        self.changes = []
        track_changes = False
        olds = {}
        try:
            for idx, score in enumerate(options.get(self.name).split(',')):
                olds[SKILLS[idx]] = score
            track_changes = True
        except AttributeError:
            for skill in SKILLS:
                olds[skill] = '0'
        self.skills = defaultdict(dict)
        for skill in thing.skills.find_all('li'):
            skillname =  attribute(skill, 'def')
            if skillname:
                if olds[skillname] == 'X':
                    self.skills[skillname]['level'] = 'X'
                    self.skills[skillname]['passion'] = None
                else:
                    level = attribute(skill, 'level', '0')
                    self.skills[skillname]['level'] = level
                    self.skills[skillname]['passion'] = attribute(skill, 'passion')
                    if track_changes:
                        change = int(level) - int(olds[skillname])
                        if change:
                            self.changes.append('{:+} {} ({})'.format(change, skillname, level))
        options[self.name] =  ','.join(self.skill_list[1:])
    @property
    def skill_list(self):
        l = [self.name, ]
        for skill in SKILLS:
            l.append(self.skills[skill]['level'])

        return l

def all_pawns(soup, options):
    pawns = []
    def add_pawn(thing):
        if attribute(thing, 'kinddef') == 'Colonist' and attribute(thing, 'faction') == 'Faction_10':
            pawn = Pawn(thing, options)
            pawns.append(pawn)
    for alivepawns in soup.find_all('pawnsalive'):
        for thing in alivepawns.findChildren('li', recursive=False):
            add_pawn(thing)
    for thing in soup.find_all('thing'):
        add_pawn(thing)
    return pawns

def all_prisoners(soup):
    pawns = []
    def add_pawn(thing):
        if attribute(thing, ('guest', 'gueststatus',)) == 'Prisoner':
            pawn = Pawn(thing, {})
            pawns.append(pawn)
    for thing in soup.find_all('thing'):
        add_pawn(thing)
    return pawns

def all_dead(soup):
    for pd in soup.find_all('pawnsdead'):
        for li in pd.find_all('li'):
            if attribute(li, 'def') == 'Human':
                pawn = Pawn(li, {})
                print(pawn.skill_list)

def pawn_skills(soup, options):
    def buffers(skill):
        length = int(skill) // 10 + 1
        buffer_back = (BUFFER_WIDTH - length) // 2
        buffer_front = buffer_back + (BUFFER_WIDTH - length) % 2
        return ' '*buffer_front, ' '*buffer_back
    def format_normal(skill):
        bf, bb = buffers(skill)
        return bf + '\033[00m{}\033[00m'.format(skill) + bb
    def format_minor(skill):
        bf, bb = buffers(skill)
        return bf + '\033[92m{}\033[00m'.format(skill) + bb
    def format_major(skill):
        bf, bb = buffers(skill)
        return bf + '\033[92m\033[01m{}\033[00m'.format(skill) + bb

    pawns = all_pawns(soup, options)
    prisoners = all_prisoners(soup)
    changes = []
    fmt = '  {:10} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12}\n'
    print(fmt.format('Pawn', *SKILLS))
    def print_pawn(pawn):
        items = [pawn.name,]
        for skill in SKILLS:
            passion = pawn.skills[skill]['passion']
            level = pawn.skills[skill]['level']
            if passion == 'Minor':
                items.append(format_minor(level))
            elif passion == 'Major':
                items.append(format_major(level))
            elif level != 'X':
                items.append(format_normal(level))
            else:
                items.append('--')
        print(fmt.format(*items))
    for pawn in sorted(pawns, key=lambda x: x.name):
        if pawn.changes:
            changes.append('{}: {}'.format(pawn.name, ', '.join(pawn.changes)))
        print_pawn(pawn)
    if prisoners:
        print('PRISONERS')
        for pawn in sorted(prisoners, key=lambda x: x.name):
            print_pawn(pawn)
    if changes:
        print('\nCHANGES:')
        for change in changes:
            print(change)
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
                continue
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
    geysers = Counter()
    for thing in soup.find_all('thing'):
        name = attribute(thing, 'def')

        if name == 'SteamGeyser':
            geysers[location(thing)] += 1
            continue

        growth = attribute(thing, 'growth')
        if not growth == '1':
            continue

        if name == 'Plant_Berry':
            berries[location(thing)] += 1
        elif name == 'Plant_TreeDrago':
            herbs[location(thing)] += 1

    print('Herbs/Berries/Geysers')
    for locs in (('NW', 'N', 'NE',), ('W', 'C', 'E',), ('SW', 'S', 'SE',),):
        print('{:2}/{:2}/{:2} | {:2}/{:2}/{:2} | {:2}/{:2}/{:2}'.format(
            herbs[locs[0]], berries[locs[0]], geysers[locs[0]], herbs[locs[1]], berries[locs[1]], geysers[locs[1]], herbs[locs[2]], berries[locs[2]], geysers[locs[2]],
            ))
def practice():
    fmt = '{:^12} {:^12} {:^12} {:^12} {:^12}'
    print(fmt.format('Pawn', *SKILLS[:4]))
    items = ['Cherry', format_major(1), format_major(2), format_major(11), format_major(17)]
    print(fmt.format(*items))

def run(args):
    config = ConfigParser()
    config.read(CONFIG)
    options = config[args.faction]
    with open(options['file']) as f:
        soup = BeautifulSoup(f, 'lxml')
    if args.action == 'skills':
        pawn_skills(soup, options)
        with open(CONFIG, 'w') as f:
            config.write(f)
    elif args.action == 'inventory':
        inventory_list(soup)
    elif args.action == 'equipment':
        equipment_list(soup)
    elif args.action == 'animals':
        animals(soup)
    elif args.action == 'wildlife':
        wildlife(soup)
    elif args.action == 'harvest':
        harvest(soup)
    elif args.action == 'dead':
        all_dead(soup)

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("faction", help="name of faction")
    parser.add_argument("action", choices=['equipment', 'dead', 'skills', 'inventory', 'animals', 'harvest', 'wildlife',], help="skills or inventory")
    args = parser.parse_args()
    run(args)
