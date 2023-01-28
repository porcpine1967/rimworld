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
SKILLS = ['Shooting', 'Melee', 'Construction', 'Mining', 'Cooking', 'Plants', 'Animals', 'Crafting', 'Artistic', 'Medicine', 'Social', 'Intellectual']

SKILL_UPGRADE = {
    0: 1000,
    1: 2000,
    2: 3000,
    3: 4000,
    4: 5000,
    5: 6000,
    6: 7000,
    7: 8000,
    8: 9000,
    9: 10000,
    10: 12000,
    11: 14000,
    12: 16000,
    13: 18000,
    14: 20000,
    15: 22000,
    16: 24000,
    17: 26000,
    18: 28000,
    19: 30000,
    20: 32000,
}

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
                    self.skills[skillname]['pct'] = 0
                else:
                    level = attribute(skill, 'level', '0')
                    self.skills[skillname]['level'] = level
                    self.skills[skillname]['passion'] = attribute(skill, 'passion')
                    self.skills[skillname]['pct'] = float(attribute(skill, 'xpsincelastlevel', '0')) / SKILL_UPGRADE[int(level)]
                    if track_changes:
                        change = int(level) - int(olds[skillname])
                        if change:
                            self.changes.append('{:+} {} ({})'.format(change, skillname, level))
        self.resistance = 0
        self.mood = 0
        if thing.guest.gueststatus and thing.guest.gueststatus.text == 'Prisoner':
                self.resistance = float(thing.guest.resistance.text)
        else:
            self.mood = float(attribute(thing, ('needs', 'needs', 'li', 'curlevel',)))
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
        length = len(skill)
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
    fmt = '  {:15} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12}\n'
    print(fmt.format('Pawn', *SKILLS))
    def print_pawn(pawn):
        if pawn.resistance:
            name = "{} ({:.0f})".format(pawn.name, pawn.resistance)
        elif pawn.mood:
            name = "{} ({:.1f})".format(pawn.name, pawn.mood)
        else:
            name = pawn.name
        items = [name,]
        for skill in SKILLS:
            passion = pawn.skills[skill]['passion']
            level = pawn.skills[skill]['level']
            pct = pawn.skills[skill]['pct']
            if pct < 0:
                level += '(-)'
            elif pct > 0.1:
                level = '{:.2f}'.format(int(level) + pct)
                level = level[:-1] # because it was rounding up to the next level on > .95
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

class Thing:
    CATEGORIES = {
        'Drugs': ('Ambrosia', 'Beer', 'SmokeleafJoint', 'Yayo',),
        'Medicine': ('Neutroamine', 'Penoxycyline',),
        'Ores' : ('Gold', 'Jade', 'Plasteel', 'Silver', 'Steel', 'Uranium',),
        'Raw Food': ('Milk', 'Wort',),
        'Wool': ('Cloth', 'DevilstrandCloth',),
    }
    QUALITY = ('Apparel', 'Gun', 'MeleeWeapon', 'Misc',)
    TRUNCATE = ('Blocks', 'Grenade', 'Meal', 'Medicine', 'Wool',)
    maxes = defaultdict(int)
    def __init__(self, thing):
        name = attribute(thing, 'def')
        self.category = 'Misc'
        self.stuff = None
        self.quality = None
        self.qualifications = []
        self.health = None
        self.biocoded = False
        try:
            self.position = position(thing)
        except AttributeError:
            self.position = (-1, -1,)

        try:
            self.health = int(attribute(thing, 'health'))
        except ValueError:
            self.health = 0

        try:
            self.biocoded = attribute(thing, 'biocoded') == 'True'
        except ValueError:
            pass

        if name.startswith('Meat_'):
            self.category = 'Raw Food'
            name = 'Meat'
        elif name.startswith('Raw'):
            self.category = 'Raw Food'
            name = name[3:]
        elif '_' in name:
            self.category, name = name.split('_', 1)

        for category in Thing.TRUNCATE:
            if name.startswith(category):
                self.category = category
                name = name[len(category):]
        self.base_name = name

        for category, items in Thing.CATEGORIES.items():
            if name in items:
                self.category = category

        if self.category in Thing.QUALITY:
            self.stuff = attribute(thing, 'stuff')
            Thing.maxes[self.max_key] = max(self.health, Thing.maxes[self.max_key])
            quality = attribute(thing, 'quality')
            if self.stuff:
                if self.stuff == 'WoodLog':
                    self.stuff = 'Wood'
                elif self.stuff.startswith('Blocks'):
                    self.stuff = self.stuff[6:]
                self.qualifications.append(self.stuff)
            if quality:
                self.qualifications.append(quality)
            if self.qualifications:
                name = '{:15} ({})'.format(name, ', '.join(self.qualifications))

        self.count = int(attribute(thing, 'stackcount', '1'))

    @property
    def max_key(self):
        if self.stuff:
            return '{} {}'.format(self.stuff, self.base_name)
        else:
            return self.base_name

    @property
    def name(self):
        n = self.base_name
        if self.qualifications:
            n = '{:15} ({}'.format(self.base_name, ', '.join(self.qualifications))
            if self.health and Thing.maxes[self.max_key] and not Thing.maxes[self.max_key] % 5:
                n += ' {}%'.format(int(100 * self.health / Thing.maxes[self.max_key]))

            n += ')'
        return n
def ancient_danger_zone(soup):
    """ Coordinates around all ancient cryptosleep caskets +/- 5"""
    top = left = 250 # max position = 249
    bottom = right = 0
    for thing in soup.find_all('thing'):
        try:
            rimworld_category = classname(thing)[0]
        except IndexError:
            continue
        if rimworld_category == 'Building_AncientCryptosleepCasket':
            try:
                if not thing.innercontainer.innerlist.li:
                    continue
            except AttributeError:
                continue
            current_x, current_y = position(thing)
            if position:
                top = min(top, current_y)
                bottom = max(bottom, current_y)
                left = min(left, current_x)
                right = max(right, current_x)
    return top - 5, bottom + 5, left - 5, right + 5

def things_in_inventory(soup):
    inventory = defaultdict(Counter)
    top, left, bottom, right = ancient_danger_zone(soup)
    things = []
    for thing in soup.find_all('thing'):
        try:
            rimworld_category = classname(thing)[0]
        except IndexError:
            continue
        if rimworld_category in ('ThingWithComps', 'Medicine', 'Apparel'):
            obj = Thing(thing)
            if top < obj.position[1] < bottom and left < obj.position[0] < right:
                continue
            things.append(obj)
        if "MinifiedThing" in rimworld_category:
            obj = Thing(thing.innercontainer.innerlist.li)
            things.append(obj)
    for obj in things:
        if not obj.biocoded:
            inventory[obj.category][obj.name] += obj.count
    return inventory

def inventory_list(soup):
    inventory = things_in_inventory(soup)
    for c in sorted(inventory):
        print(c)
        for k in sorted(inventory[c]):
            v = inventory[c][k]
            print(' {}: {}'.format(k, v))

def equipment_list(soup, options):
    things_in_inventory(soup) # load Thing.maxes
    armors = ('Flak', 'Helmet', )
    people = defaultdict(list)
    def add_pawn(thing):
        if attribute(thing, 'kinddef') == 'Colonist' and attribute(thing, 'faction') == 'Faction_10':
            pawn = Pawn(thing, options)
            armor_level = 0
            key = attribute(thing, ('name', 'nick',)) or attribute(thing, ('name', 'first',))
            armed = False
            combat_role = ''
            for li in thing.apparel.find_all('li'):
                item = Thing(li)
                for a in armors:
                    if a in item.name:
                        armor_level += 1
                if item.base_name == 'PowerArmor':
                    armor_level += 2
                if item.max_key in ('DevilstrandCloth Duster', 'DevilstrandCloth Parka',):
                    armor_level += 1
                people[key].append("{}".format(item.name))
            people[key].sort()
            for li in thing.equipment.find_all('li'):
                weapon = attribute(li, 'def')
                if weapon:
                    armed = True
                    item = Thing(li)
                    people[key].append(item.name)
                    combat_role = item.category
            combat_info = ''
            if pawn.skills['Shooting']['level'] == 'X' and pawn.skills['Melee']['level'] == 'X':
                combat_info = '(Non Violent)'
            elif combat_role in ('Gun', 'Grenade',):
                combat_info = '(Range - {})'.format(pawn.skills['Shooting']['level'])
            elif combat_role in ('MeleeWeapon',):
                combat_info = '(Melee - {})'.format(pawn.skills['Melee']['level'])
            elif not armed:
                people[key].append('** UNARMED **')

            people[key].insert(0, 'Armor Level: {} {}'.format(armor_level, combat_info))
    for alivepawns in soup.find_all('pawnsalive'):
        for thing in alivepawns.findChildren('li', recursive=False):
            add_pawn(thing)

    for thing in soup.find_all('thing'):
        add_pawn(thing)
    for person in sorted(people):
        print(person)
        for item in people[person]:
            print("    {}".format(item))

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
def quests(soup):
    def untag(string):
        return re.sub(r'(<[^>]+>|\([*/][^)]+\))', '', string).replace('\n\n', '\n')
    for quests in soup.find_all('quests'):
        for li in quests.findChildren('li', recursive=False):
            if not attribute(li, 'cleanedup'):
                print(attribute(li, 'name'))
                print(untag(attribute(li, 'description')))
                print('='*25)

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
        equipment_list(soup, options)
    elif args.action == 'animals':
        animals(soup)
    elif args.action == 'wildlife':
        wildlife(soup)
    elif args.action == 'harvest':
        harvest(soup)
    elif args.action == 'dead':
        all_dead(soup)
    elif args.action == 'quests':
        quests(soup)
if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("faction", help="name of faction")
    parser.add_argument("action", choices=['equipment', 'dead', 'skills', 'inventory', 'animals', 'harvest', 'wildlife', 'quests',], help="skills or inventory")
    args = parser.parse_args()
    run(args)
