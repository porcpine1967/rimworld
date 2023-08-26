#!/usr/bin/env python3
""" Spit out info from rws file"""
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import Counter, defaultdict
import csv
import math
import os
import re
import statistics

from bs4 import BeautifulSoup

CONFIG = 'local/parse.cnf'
BUFFER_WIDTH = 12
POSITION_PATTERN = re.compile(r'\((.*), (.*), (.*)\)')
SKILLS = ['Shooting', 'Melee', 'Construction', 'Mining', 'Cooking', 'Plants', 'Animals', 'Crafting', 'Artistic', 'Medicine', 'Social', 'Intellectual']

COLONIST_FACTIONS = ('Faction_10', 'Faction_21',)

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

BODY_PARTS = {
    '0': 'Torso',
    '1': 'Ribcage',
    '2': 'Sternum',
    '4': 'Spine',
    '7': 'Left Lung',
    '8': 'Right Lung',
    '11': 'Liver',
    '16': 'Left Eye',
    '17': 'Right Eye',
    '20': 'Nose',
    '23': 'Left Shoulder',
    '24': 'Left Clavicle',
    '25': 'Left Arm',
    '26': 'Left humerus',
    '27': 'Left radius',
    '33': 'Left Thumb',
    '36': 'Right arm',
    '44': 'Right Thumb',
    '46': 'Left Leg',
    '49': 'Right foot',
    '50': 'Left toe',
    '52': 'Left toe',
    '55': 'Right Leg',
    '57': 'Right tibia',
    '58': 'Right foot',
    '60': 'Right Toe',
    '61': 'Right Toe',
}

APPAREL_LOCATION = (
    ('Helmet', 'head',),
    ('Tuque', 'head',),
    ('Hat', 'head',),
    ('Headress', 'head',),
    ('Veil', 'head',),
    ('Mask', 'head',),
    ('TribalA', 'skin-top',),
    ('Shirt', 'skin-top',),
    ('Pants', 'skin-bottom',),
    ('Belt', 'belt',),
    ('Duster', 'outer',),
    ('Jacket', 'outer',),
    ('Parka', 'outer',),
    ('FlakVest', 'middle',),
    ('Armor', 'middle',),
)

BASIN_RIPE_ESTIMATES = {
    'Cotton': 5,
    'Healroot': 5,
    'Rice': 2,
    'Smokeleaf': 5,
}
RIPE_ESTIMATES = {
    'Corn': 21,
    'Devilstrand': 42,
    'Haygrass': 13,
    'Rice': 6,
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

def all_animals(soup):
    """ Animals owned by colonists."""
    owned_animals = []
    def add_animal(thing):
        if attribute(thing, 'def') != 'Human' and attribute(thing, 'faction') and attribute(thing,'mindstate'):
            owned_animals.append(attribute(thing, 'def'))
    for alivepawns in soup.find_all('pawnsalive'):
        for li in alivepawns.findChildren('li', recursive=False):
            add_animal(li)
    for thing in soup.find_all('thing'):
        add_animal(thing)
    return owned_animals

def animals(soup):
    """ Animals owned by colonists."""
    animal_ctr = Counter()
    for animal in all_animals(soup):
        animal_ctr[animal] += 1
    for animal in sorted(animal_ctr):
        print("{},{}".format(animal, animal_ctr[animal]))

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

class MockThing:
    def __init__(self):
        self.name = self.base_name = self.max_key = ''

class Pawn:
    ITEM_CATEGORIES =  ('head',
            'skin-top',
            'skin-bottom',
            'middle',
            'outer',
            'belt',
            'weapon',
            'medicine',
        )

    def __init__(self, thing, options):
        self.name = attribute(thing, ('name', 'nick',)) or attribute( thing, ('name', 'first'))
        self.changes = []
        self.thing = thing
        self.permanent_injuries = []
        self.temporary_injuries = []
        self.items = defaultdict(MockThing)
        self.skills = defaultdict(dict)
        self.missing_body_parts = set()

        self.load_skills(thing, options)
        self.load_injuries(thing)
        self.load_mood(thing)
        self.load_equipment(thing)

    def load_skills(self, thing, options):
        track_changes = False
        olds = {}
        try:
            for idx, score in enumerate(options.get(self.name).split(',')):
                olds[SKILLS[idx]] = score
            track_changes = True
        except AttributeError:
            for skill in SKILLS:
                olds[skill] = '0'
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
        options[self.name] =  ','.join(self.skill_list[1:])

    def load_injuries(self, thing):
        for tracker in thing.find_all('healthtracker'):
            for issue in tracker.find_all('li'):
                issue_def = attribute(issue, 'def')
                if issue_def in ('MissingBodyPart', 'Asthma',):
                    issue_name = issue_def == 'Asthma' and 'Asthma' or 'Missing'
                    part_number = attribute(issue, ('part', 'index',))
                    if not attribute(issue, 'lastinjury') == 'SurgicalCut':
                        if part_number in BODY_PARTS:
                            part = BODY_PARTS[part_number]
                        else:
                            self.missing_body_parts.add(part_number)
                            part = part_number
                        self.permanent_injuries.append((f"{issue_name} {part}",
                                                        float(attribute(issue, 'severity', 0)),))
                    continue
                if issue_def.endswith('Addiction'):
                    self.permanent_injuries.append((issue_def,
                                                   float(attribute(issue, 'severity', 0)),))
                    continue
                if issue_def in ('', 'CochlearImplant',)\
                   or issue_def.startswith('Bionic')\
                   or issue_def.endswith('Tolerance'):
                    continue
                if attribute(issue, 'ispermanent'):
                    part_number = attribute(issue, ('part', 'index',))
                    if part_number in BODY_PARTS:
                        part = BODY_PARTS[part_number]
                    else:
                        self.missing_body_parts.add(part_number)
                        part = part_number

                    self.permanent_injuries.append((f"Injured {part}",
                                                    float(attribute(issue, 'severity', 0)),))
                else:
                    self.temporary_injuries.append((f"Injury",
                                                    float(attribute(issue, 'severity', 0)),))

    @property
    def injury_count(self):
        return len(self.temporary_injuries)

    @property
    def max_severity(self):
        return max([injury[1] for injury in self.temporary_injuries])

    def load_mood(self, thing):
        self.resistance = -1
        self.mood = 0
        if thing.guest.gueststatus and thing.guest.gueststatus.text == 'Prisoner':
            self.resistance = float(thing.guest.resistance.text)
        else:
            try:
                self.mood = float(attribute(thing, ('needs', 'needs', 'li', 'curlevel',)))
            except ValueError:
                pass

    def load_equipment(self, thing):
        for li in thing.apparel.find_all('li'):
            item = Thing(li)
            for name, place in APPAREL_LOCATION:
                if name in item.name:
                    self.items[place] = item
                    break
        for li in thing.equipment.find_all('li'):
            item = Thing(li)
            if item.name:
                self.items['weapon'] = item

        for li in thing.inventory.find_all('li'):
            item_def = attribute(li, 'def', '')
            if item_def.startswith('Medicine'):
                count = attribute(li, 'stackcount')
                item = MockThing()
                if item_def == 'MedicineHerbal':
                    item.name = f"Herbal Med:     {count}"
                elif item_def == 'MedicineIndustrial':
                    item.name = f"Medicine:       {count}"
                elif item_def == 'MedicineUltratech':
                    item.name = f"Glitter Med:    {count}"
                self.items['medicine'] = item

    @property
    def armor_level(self):
        _armor_level = 0
        for item in self.items.values():
            for armor_type in ('Flak', 'Helmet', 'Shield',):
                if armor_type in item.name:
                    _armor_level += 1
            if item.base_name in ('ArmorRecon', 'PowerArmor'):
                _armor_level += 2
            if item.max_key in ('DevilstrandCloth Duster', 'DevilstrandCloth Parka',):
                _armor_level += 1
            if item.max_key in ('Hyperweave Duster', 'Hyperweave Parka',):
                _armor_level += 2
        return _armor_level

    @property
    def combat_info(self):
        if 'weapon' not in self.items:
            combat_role = ''
        else:
            combat_role = self.items['weapon'].category

        _combat_info = ''
        if self.skills['Shooting']['level'] == 'X' and self.skills['Melee']['level'] == 'X':
            _combat_info = '(Non Violent)'
        elif combat_role in ('Gun', 'Grenade',):
            _combat_info = '(Range - {})'.format(self.skills['Shooting']['level'])
        elif combat_role in ('MeleeWeapon',):
            _combat_info = '(Melee - {})'.format(self.skills['Melee']['level'])
        elif not self.items['weapon']:
            _combat_info = '** UNARMED **'
        return _combat_info

    @property
    def max_equipment_description(self):
        max_length = 0
        for item in self.items.values():
            max_length = max(max_length, len(item.name))
        return max_length

    @property
    def skill_list(self):
        l = [self.name, ]
        for skill in SKILLS:
            l.append(self.skills[skill]['level'])
        return l

    @property
    def health(self):
        if not self.injury_count:
            return '         '
        else:
            return f"({self.injury_count:2} {self.max_severity: >4.1f})"

def all_pawns(soup, options):
    pawns = []
    def add_pawn(thing):
        if attribute(thing, 'kinddef') in ('Colonist', 'Tribesperson',) and attribute(thing, 'faction') in COLONIST_FACTIONS:
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
    for alivepawns in soup.find_all('pawnsalive'):
        for thing in alivepawns.findChildren('li', recursive=False):
            add_pawn(thing)
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
    def buffers(skill, buffer_width):
        length = len(skill)
        buffer_back = (buffer_width - length) // 2
        buffer_front = buffer_back + (buffer_width - length) % 2
        return ' '*buffer_front, ' '*buffer_back
    def format_normal(skill, buffer_width=BUFFER_WIDTH):
        bf, bb = buffers(skill, buffer_width)
        return bf + '\033[00m{}\033[00m'.format(skill) + bb
    def format_minor(skill, buffer_width=BUFFER_WIDTH):
        bf, bb = buffers(skill, buffer_width)
        return bf + '\033[92m{}\033[00m'.format(skill) + bb
    def format_major(skill, buffer_width=BUFFER_WIDTH):
        bf, bb = buffers(skill, buffer_width)
        return bf + '\033[92m\033[01m{}\033[00m'.format(skill) + bb

    pawns = all_pawns(soup, options)
    prisoners = all_prisoners(soup)
    changes = []
    fmt = '  {:32} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12}\n'
    print(fmt.format('Pawn             mood  injured', *SKILLS))
    def print_pawn(pawn):
        if pawn.resistance > -1:
            name = "{:15} ({: >3.0f}) {}".format(pawn.name, pawn.resistance, pawn.health)
        elif pawn.mood:
            mood = f"{pawn.mood: >3.1f}"
            if pawn.mood < .25:
                mood = format_major(mood, 0)
            elif pawn.mood < .35:
                mood = format_minor(mood, 0)
            else:
                mood = format_normal(mood, 0)
            name = "{:15} ({}) {}".format(pawn.name, mood, pawn.health)
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
            changes.append('{:15}: {}'.format(pawn.name, ', '.join(pawn.changes)))
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
    TRUNCATE = ('Blocks', 'Grenade', 'Meal', 'Medicine', 'Unfinished', 'Wool',)
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

        self.tainted = attribute(thing, 'wornbycorpse') == 'True'

        if name.startswith('Meat_'):
            self.category = 'Raw Food'
            name = 'Meat'
        elif name.startswith('Raw') or name.startswith('Egg'):
            self.category = 'Raw Food'
            name = name[3:]
        elif name == 'Pemmican':
            self.category = 'Meal'
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

        if self.tainted:
            self.category = 'Tainted'

        if self.category == 'Unfinished':
            self.base_name = attribute(thing, 'recipe').split('_')[-1]
            self.qualifications.append(attribute(thing, 'creatorname'))

        if self.category in Thing.QUALITY:
            self.stuff = attribute(thing, 'stuff')
            if self.health % 5 == 0:
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
            if self.health and Thing.maxes[self.max_key]:
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
    inventory['Medicine']['Industrial'] = 0
    inventory['Medicine']['Herbal'] = 0
    inventory['Wool']['Cloth'] = 0
    inventory['Ores']['Steel'] = 0
    inventory['Misc']['WoodLog'] = 0
    inventory['Raw Food']['Total'] = 0

    top, left, bottom, right = ancient_danger_zone(soup)
    things = []
    for thing in soup.find_all('thing'):
        try:
            rimworld_category = classname(thing)[0]
        except IndexError:
            continue
        if rimworld_category in ('ThingWithComps', 'Medicine', 'Apparel', 'UnfinishedThing'):
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
        if obj.category == 'Raw Food':
            inventory[obj.category]['Total'] += obj.count
    return inventory

def inventory_list(soup):
    critical_levels = {
        'WoodLog': (100, 50,),
        'Steel': (100, 50,),
        'Cloth': (90, 20,),
    }
    pawn_cnt = len(all_pawns(soup, {}))
    critical_levels['Industrial'] = (2*pawn_cnt, 1.5*pawn_cnt,)
    critical_levels['Total'] = (60*pawn_cnt, 30*pawn_cnt,)
    animal_cnt = len(all_animals(soup))
    critical_levels['Herbal'] = (1*animal_cnt, .5*animal_cnt,)
    inventory = things_in_inventory(soup)
    max_width = 0
    for c, k in inventory.items():
        max_width = max(max_width, len(c))
        for item, count in k.items():
            max_width = max(max_width, len(f" {item}: {count}"))
    max_width += 4
    def nth(ctr, idx):
        for index, item_name in enumerate(sorted(ctr)):
            if index == idx:
                content = f"  {item_name}: {ctr[item_name]}"
                if item_name in critical_levels and ctr[item_name] < critical_levels[item_name][1]:
                    return f"\033[92;1m{content:{max_width}}\033[00m"
                elif item_name in critical_levels and ctr[item_name] < critical_levels[item_name][0]:
                    return f"\033[92m{content:{max_width}}\033[00m"
                else:
                    return f"{content:{max_width}}"
        return ''
    try:
        num_columns = math.floor(os.get_terminal_size()[0]/(max_width))

        for category_chunk in chunker(sorted(inventory), num_columns):
            fmt = f"{{:{max_width}}}"*len(category_chunk)
            print(fmt.format(*[category for category in category_chunk]))
            max_count = 0

            for category in category_chunk:
                max_count = max(max_count, len(inventory[category].values()))
            for index in range(max_count):
                print(fmt.format(*[nth(inventory[category], index) for category in category_chunk]))
            print()
    except OSError:
        for c in sorted(inventory):
            print(c)
            for k in sorted(inventory[c]):
                v = inventory[c][k]
                print(' {}: {}'.format(k, v))

def equipment_list(soup, options):
    things_in_inventory(soup) # load Thing.maxes
    pawns = []
    def add_pawn(thing):
        if attribute(thing, 'kinddef') in ('Colonist', 'Tribesperson',) and attribute(thing, 'faction') in COLONIST_FACTIONS:
            pawns.append(Pawn(thing, options))

    for alivepawns in soup.find_all('pawnsalive'):
        for thing in alivepawns.findChildren('li', recursive=False):
            add_pawn(thing)

    for thing in soup.find_all('thing'):
        add_pawn(thing)

    max_width = 0
    for pawn in pawns:
        max_width = max(max_width, pawn.max_equipment_description)

    max_width += 6

    try:
        num_columns = math.floor(os.get_terminal_size()[0]/(max_width))

        for pawn_chunk in chunker(sorted(pawns, key=lambda x: x.name), num_columns):
            fmt = f"{{:{max_width}}}"*len(pawn_chunk)
            print(fmt.format(*[pawn.name for pawn in pawn_chunk]))
            print(fmt.format(*[f"    Armor Level: {pawn.armor_level:2} {pawn.combat_info}" for pawn in pawn_chunk]))
            for key in Pawn.ITEM_CATEGORIES:
                print(fmt.format(*[f"    {pawn.items[key].name}" for pawn in pawn_chunk]))
            print()

    except OSError:
        for pawn in sorted(pawns, key=lambda x: x.name):
            print(pawn.name)
            print(f"    Armor Level: {pawn.armor_level:2} {pawn.combat_info}")
            for item in pawn.items.values():
                print("    {}".format(item.name))

def chunker(seq, size):
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))

def harvest(soup):
    counters = {
        'herbs': Counter(),
        'berries': Counter(),
        'trees': Counter(),
        'geysers': Counter(),
        'ambrosia': Counter(),
    }
    for thing in soup.find_all('thing'):
        name = attribute(thing, 'def')

        if name == 'SteamGeyser':
            counters['geysers'][location(thing)] += 1
            continue

        growth = attribute(thing, 'growth')
        if not growth == '1':
            continue

        if name in ('Plant_Berry', 'Plant_Agave',):
            counters['berries'][location(thing)] += 1
        elif name in ('HealrootWild',):
            counters['herbs'][location(thing)] += 1
        elif name in ('Plant_TreeDrago', 'Plant_SaguaroCactus',):
            counters['trees'][location(thing)] += 1
        elif name == 'Plant_Ambrosia':
            counters['ambrosia'][location(thing)] += 1
    title_list = []
    data = []
    formats = []
    for key, counter in counters.items():
        if counter:
            title_list.append(key)
            data.append(counter)
            formats.append('{:2}')
    fmt = f"{'/'.join(formats)} | {'/'.join(formats)} | {'/'.join(formats)}"
    print('/'.join(title_list))
    for locs in (('NW', 'N', 'NE',), ('W', 'C', 'E',), ('SW', 'S', 'SE',),):
        data_points = []
        for loc in locs:
            for counter in data:
                data_points.append(counter[loc])
        print(fmt.format(*data_points))

def quests(soup):
    def untag(string):
        return re.sub(r'(<[^>]+>|\([*/][^)]+\))', '', string).replace('\n\n', '\n')
    for quests in soup.find_all('quests'):
        for li in quests.findChildren('li', recursive=False):
            if not attribute(li, 'cleanedup'):
                print(attribute(li, 'name'))
                print(untag(attribute(li, 'description')))
                print('='*25)

class Bill:
    def __init__(self, bill_node):
        self.suspended = attribute(bill_node, 'suspended') == 'True'
        self.recipe = attribute(bill_node, 'recipe')
        self.repeat_type = attribute(bill_node, 'repeatmode')
        if self.repeat_type == 'TargetCount':
            self.count = int(attribute(bill_node, 'targetcount', 0))
        elif attribute(bill_node, 'repeatmode') == 'RepeatCount':
            self.count = int(attribute(bill_node, 'repeatcount', 0))
        elif attribute(bill_node, 'repeatmode') == 'Forever':
            self.count = -1

        self.materials = []
        for li in bill_node.ingredientfilter.alloweddefs.find_all('li'):
            self.materials.append(li.text)

    @property
    def formatted_recipe(self):
        recipe = self.recipe
        recipe = recipe.split('_')[-1]
        recipe = re.sub(r'StoneBlocks(.*)', r'\1 Blocks', recipe)
        recipe = recipe.replace('Bulk', ' (x4)')
        recipe = recipe.replace('CookMealFine', 'FineMeal')
        recipe = recipe.replace('MedicineIndustrial', 'Medicine')
        recipe = re.sub(r'([a-z])([A-Z])', r'\1 \2', recipe)
        if 'Apparel' in self.recipe and len(self.materials) == 1:
            recipe = f"{self.materials[0]} {recipe}"
        return recipe

    def __lt__(self, other):
        return self.recipe < other.recipe

def injuries(soup, options):
    missing = set()
    def print_injuries(pawn):
        if pawn.permanent_injuries or pawn.temporary_injuries:
            missing.update(pawn.missing_body_parts)
            print(pawn.name)
            for name, severity in sorted(pawn.temporary_injuries, key=lambda x: x[1], reverse=True):
                print(f"  {name:20} {severity: >5.2f}")
            for name, severity in sorted(pawn.permanent_injuries, key=lambda x: x[0]):
                print(f"\033[38:5:249m  {name:20} {severity: >5.2f}\033[0m")
    for pawn in sorted(all_pawns(soup, options), key=lambda x: x.name):
        print_injuries(pawn)

    for pawn in sorted(all_prisoners(soup), key=lambda x: x.name):
        print_injuries(pawn)

    for m in sorted(list(missing)):
        print(m)

def hydroponics_positions(thing):
    x, y = position(thing)
    rot = attribute(thing, 'rot')
    if not rot:
        return ((x, y - 1,), (x, y,), (x, y + 1,), (x, y + 2,),)
    if rot == '2':
        return ((x, y - 2,), (x, y - 1,), (x, y,), (x, y + 1,),)
    if rot == '1':
        return ((x - 1, y,), (x, y,), (x + 1, y,), (x + 2, y,),)
    if rot == '3':
        return ((x - 2, y,), (x - 1, y,), (x, y,), (x + 1, y,),)

def queue(soup):
    basins = Counter()
    basin_crops = Counter()
    crops = Counter()
    repeat_bills = []
    target_bills = []
    forever_bills = []
    basin_growths = defaultdict(list)
    growths = defaultdict(list)
    hydroponics_zones = []
    mine_ctr = 0

    for designations in soup.find_all('alldesignations'):
        for li in designations.find_all('li'):
            if attribute(li, 'def') == 'Mine':
                mine_ctr += 1

    for thing in soup.find_all('thing'):
        if attribute(thing, 'def') == 'HydroponicsBasin':
            if attribute(thing, 'poweron') == 'False':
                plant = 'Off'
            else:
                plant = attribute(thing, 'plantdeftogrow').replace('Plant_', '')
            basins[plant] += 1
            hydroponics_zones.extend(hydroponics_positions(thing))
    for thing in soup.find_all('thing'):
        name = attribute(thing, 'def')
        if attribute(thing, 'sown') == 'True':
            x, y = position(thing)
            name = name.replace('Plant_', '')
            if (x, y,) in hydroponics_zones:
                basin_crops[name] += 1
                basin_growths[name].append(float(attribute(thing, 'growth', 0)))
            else:
                crops[name] += 1
                growths[name].append(float(attribute(thing, 'growth', 0)))
        for stack in thing.find_all('bills'):
            for bill_node in stack.find_all('li', recursive=False):
                bill = Bill(bill_node)
                if bill.suspended:
                    continue
                if bill.count == 0:
                    continue
                if  bill.repeat_type == 'TargetCount':
                    target_bills.append(bill)
                elif bill.repeat_type == 'RepeatCount':
                    repeat_bills.append(bill)
                elif bill.repeat_type == 'Forever':
                    forever_bills.append(bill)
    if basins:
        print('Basins')
        for basin in sorted(basins):
            print(f"  {basin:15}: {basins[basin]:4}")
        print()
    if crops:
        print('Crops')
        for crop in sorted(crops):
            count = crops[crop]
            if crop in RIPE_ESTIMATES:
                estimate = RIPE_ESTIMATES[crop]
                mean = f"{statistics.mean([estimate*(1 - growth) for growth in growths[crop]]): >4.1f}"
                maximum = f"{min([estimate*(1 - growth) for growth in growths[crop]]): >4.1f}"
            else:
                mean = f"{statistics.mean(growths[crop]):.2f}"
                maximum = f"{max(growths[crop]):.2f}"
            print(f"  {crop:15}: {count:4} ({mean}, {maximum})")
        print()
    if basin_crops:
        print('Basin Crops')
        for crop in sorted(basin_crops):
            count = basin_crops[crop]
            if crop in BASIN_RIPE_ESTIMATES:
                estimate = BASIN_RIPE_ESTIMATES[crop]
                mean = f"{statistics.mean([estimate*(1 - growth) for growth in basin_growths[crop]]): >4.1f}"
                maximum = f"{min([estimate*(1 - growth) for growth in basin_growths[crop]]): >4.1f}"
            else:
                mean = f"{statistics.mean(basin_growths[crop]):.2f}"
                maximum = f"{max(basin_growths[crop]):.2f}"
            print(f"  {crop:15}: {count:4} ({mean}, {maximum})")
        print()
    if repeat_bills:
        print('Bills')
        for bill in sorted(repeat_bills):
            print(f"  {bill.formatted_recipe:20}: {bill.count:3}")
        print()
    if target_bills:
        print('Bills with Target')
        for bill in sorted(target_bills):
            print(f"  {bill.formatted_recipe:20}: {bill.count:3}")
        print()
    if forever_bills:
        print('Repeat Forever')
        for bill in sorted(forever_bills):
            print(f"  {bill.formatted_recipe}")

    if mine_ctr:
        print()
        print(f"{mine_ctr} mines")
def top(soup, quantity, options):
    top = defaultdict(list)
    null_skill = {'level': 0, 'passion': None, 'pct': 0}
    pawn_objs = all_pawns(soup, options)
    useful = {}
    half_useful = {}
    for pawn in pawn_objs:
        useful[pawn.name] = []
        half_useful[pawn.name] = []
        for skill in SKILLS:
            try:
                int(pawn.skills[skill]['level'])
                top[skill].append((pawn.name, pawn.skills[skill],))
            except ValueError:
                top[skill].append((pawn.name, null_skill,))
    def formatted_pawn(pawn):
        name, skill_info = pawn
        if skill_info['passion'] == 'Major':
            return f"{name:>20} (\033[92;1m{skill_info['level']:>2}\033[00m)"
        if skill_info['passion'] == 'Minor':
            return f"{name:>20} (\033[92m{skill_info['level']:>2}\033[00m)"
        return f"{name:>20} ({skill_info['level']:>2})"
    useful_skills = {'Construction', 'Mining', 'Cooking', 'Plants', 'Crafting', 'Intellectual',}
    for skill in SKILLS:
        pawns = sorted(top[skill], key=lambda x: int(x[1]['level']) + float(x[1]['pct']), reverse=True)
        print(f"{skill:14} {''.join([formatted_pawn(pawn) for pawn in pawns[:quantity or 4]])}\n")
        if skill in useful_skills:
            for idx, pawn in enumerate(pawns):
                if idx < 4:
                    useful[pawn[0]].append(skill)
                elif int(pawn[1]['level']) > 6:
                    half_useful[pawn[0]].append(skill)
    print('\nProduction Utility')
    for pawn in sorted(useful, key=lambda x: len(useful[x]) + len(half_useful[x])/2, reverse=True):
        print(f"{pawn}: {', '.join(useful[pawn])}")
def test(soup, option):
    """
    For ad hoc
    """

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
    elif args.action == 'injury':
        injuries(soup, options)
    elif args.action == 'quests':
        quests(soup)
    elif args.action == 'queue':
        queue(soup)
    elif args.action == 'top':
        top(soup, args.quantity, options)
    elif args.action == 'test':
        test(soup, options)
if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("faction", help="name of faction")
    parser.add_argument("action", choices=['equipment', 'dead', 'skills', 'inventory', 'animals', 'harvest', 'wildlife', 'quests', 'queue', 'injury', 'top', 'test',], help="skills or inventory")
    parser.add_argument("--quantity", help="How ever many of whatever, not for everything", type=int)
    args = parser.parse_args()
    run(args)
