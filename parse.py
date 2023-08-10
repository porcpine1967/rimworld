#!/usr/bin/env python3
""" Spit out info from rws file"""
from argparse import ArgumentParser
from configparser import ConfigParser
from collections import Counter, defaultdict
import csv
import math
import os
import re

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

PARTS = {
    '7': 'Left Lung',
    '8': 'Right Lung',
    '16': 'Left Eye',
    '25': 'Left Arm',
    '33': 'Left Thumb',
    '46': 'Left Leg',
    '55': 'Right Leg',
    '60': 'Right Toe',
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
        self.thing = thing
        self.permanent_injuries = []

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
        self.injury_count = self.max_severity = 0
        for tracker in thing.find_all('healthtracker'):
            for issue in tracker.find_all('li'):
                issue_def = attribute(issue, 'def')
                if attribute(issue, 'ispermanent'):
                    part_number = attribute(issue, ('part', 'index',))
                    part = part_number in PARTS and PARTS[part_number] or part_number

                    self.permanent_injuries.append((f"Injured {part}",
                                                    float(attribute(issue, 'severity', 0)),))
                    continue
                if issue_def in ('MissingBodyPart', 'Asthma',):
                    issue_name = issue_def == 'Asthma' and 'Asthma' or 'Missing'
                    part_number = attribute(issue, ('part', 'index',))
                    part = part_number in PARTS and PARTS[part_number] or part_number
                    if not attribute(issue, 'lastinjury') == 'SurgicalCut':
                        self.permanent_injuries.append((f"{issue_name} {part}",
                                                        float(attribute(issue, 'severity', 0)),))
                    continue
                if issue_def.endswith('Addiction'):
                    self.permanent_injuries.append((issue_def,
                                                   float(attribute(issue, 'severity', 0)),))
                    continue
                if issue_def == ''\
                   or issue_def.startswith('Bionic')\
                   or issue_def.endswith('Tolerance'):
                    continue
                self.injury_count += 1
                self.max_severity = max([self.max_severity, float(attribute(issue, 'severity', 0))])
        self.resistance = -1
        self.mood = 0
        if thing.guest.gueststatus and thing.guest.gueststatus.text == 'Prisoner':
            self.resistance = float(thing.guest.resistance.text)
        else:
            try:
                self.mood = float(attribute(thing, ('needs', 'needs', 'li', 'curlevel',)))
            except ValueError:
                pass
        options[self.name] =  ','.join(self.skill_list[1:])
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
        if attribute(thing, 'kinddef') == 'Colonist' and attribute(thing, 'faction') in COLONIST_FACTIONS:
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
    fmt = '  {:27} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12} {:^12}\n'
    print(fmt.format('Pawn        mood  injured', *SKILLS))
    def print_pawn(pawn):
        if pawn.resistance > -1:
            name = "{:10} ({: >3.0f}) {}".format(pawn.name, pawn.resistance, pawn.health)
        elif pawn.mood:
            name = "{:10} ({: >3.1f}) {}".format(pawn.name, pawn.mood, pawn.health)
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
        elif name.startswith('Egg'):
            self.category = 'Raw Food'
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

        if self.tainted:
            self.category = 'Tainted'

        if self.category == 'Unfinished':
            self.base_name = attribute(thing, 'recipe').split('_')[-1]
            self.qualifications.append(attribute(thing, 'creatorname'))

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
    max_width = 0
    def add_pawn(thing):
        max_width = 0
        if attribute(thing, 'kinddef') == 'Colonist' and attribute(thing, 'faction') in COLONIST_FACTIONS:
            pawn = Pawn(thing, options)
            armor_level = 0
            key = attribute(thing, ('name', 'nick',)) or attribute(thing, ('name', 'first',))
            armed = False
            combat_role = ''
            for li in thing.apparel.find_all('li'):
                item = Thing(li)
                max_width = max(max_width, len(item.name))
                for a in armors:
                    if a in item.name:
                        armor_level += 1
                if item.base_name in ('ArmorRecon', 'PowerArmor'):
                    armor_level += 2
                if item.max_key in ('DevilstrandCloth Duster', 'DevilstrandCloth Parka',):
                    armor_level += 1
                if item.max_key in ('Hyperweave Duster', 'Hyperweave Parka',):
                    armor_level += 2
                people[key].append(item.name)
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

            people[key].insert(0, 'Armor Level: {:2} {}'.format(armor_level, combat_info))
            for _ in range(len(people[key]), 8):
                people[key].append('')

        return max_width + 6
    for alivepawns in soup.find_all('pawnsalive'):
        for thing in alivepawns.findChildren('li', recursive=False):
            max_width = max(max_width, add_pawn(thing))

    for thing in soup.find_all('thing'):
        max_width = max(max_width, add_pawn(thing))
    def chunker(dictionary, size):
        seq = sorted([key for key in dictionary.keys()])
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    try:
        num_columns = math.floor(os.get_terminal_size()[0]/(max_width))

        for person_chunk in chunker(people, num_columns):
            fmt = f"{{:{max_width}}}"*len(person_chunk)
            print(fmt.format(*[person for person in person_chunk]))
            for i in range(8):
                print(fmt.format(*[f"    {people[person][i]}" for person in person_chunk]))
            print()
    except OSError:
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

    @property
    def formatted_recipe(self):
        recipe = self.recipe
        recipe = recipe.split('_')[-1]
        recipe = re.sub(r'StoneBlocks(.*)', r'\1 Blocks', recipe)
        recipe = recipe.replace('Bulk', ' (x4)')
        recipe = recipe.replace('CookMealFine', 'FineMeal')
        recipe = recipe.replace('MedicineIndustrial', 'Medicine')
        recipe = re.sub(r'([a-z])([A-Z])', r'\1 \2', recipe)
        return recipe

    def __lt__(self, other):
        return self.recipe < other.recipe

def injuries(soup, options):
    for pawn in sorted(all_pawns(soup, options), key=lambda x: x.name):
        if pawn.permanent_injuries:
            print(pawn.name)
            for name, severity in pawn.permanent_injuries:
                print(f"  {name:20} {severity:.2f}")

def queue(soup):
    basins = Counter()
    crops = Counter()
    repeat_bills = []
    target_bills = []
    forever_bills = []

    for thing in soup.find_all('thing'):
        try:
            rimworld_category = classname(thing)[0]
        except IndexError:
            continue
        name = attribute(thing, 'def')
        if name == 'HydroponicsBasin':
            if attribute(thing, 'poweron') == 'False':
                plant = 'Off'
            else:
                plant = attribute(thing, 'plantdeftogrow').replace('Plant_', '')
            basins[plant] += 1
        if attribute(thing, 'sown') == 'True':
            crops[name.replace('Plant_', '')] += 1
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
            in_basin = basins[crop] * 4
            count = crops[crop] - in_basin
            if count > 0:
                print(f"  {crop:15}: {count:4}")
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

def test(soup, options):
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
    elif args.action == 'test':
        test(soup, options)
if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("faction", help="name of faction")
    parser.add_argument("action", choices=['equipment', 'dead', 'skills', 'inventory', 'animals', 'harvest', 'wildlife', 'quests', 'queue', 'injury', 'test',], help="skills or inventory")
    args = parser.parse_args()
    run(args)
