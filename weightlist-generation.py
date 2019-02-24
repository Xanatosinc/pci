#!/usr/local/bin/python3.6

import math
import re
import sys

MESSAGE_OUTPUT = []

KERF = 0.25
MAX_STOCK = 65
STUB_LIST = ['Stub', 'stub', 'KP', 'kp']

DNL_LIST = ['Plate', 'Cxn', 'Bucket']

MISC_FACTOR = 0.15
STRUCT_PRICE_FACTOR = 2.7

DECKING_PRICE_FACTOR = 12
SAFETY_LINE_PRICE_FACTOR = 20

MF_HOURS_PER_POINT = 4
MF_LABOR_RATE = 85

# CLASSES

class Material:
    def __init__(self, name='', takeOffList={}):
        self.name = name
        self.takeOffList = takeOffList
        self.dropWeight = 0
        self.lf = 0
        self.stockLength = 0
        self.weight = 0
        self.weightPerFoot = 0

    def __str__(self):
        lengths = []
        for tf, tfData in self.takeOffList.items():
            lengths.extend(tfData.lengths)
        return '\t'.join([self.name, str(self.dropWeight), str(self.lf), str(self.weight)])

    def produceLengthList(self):
        lengths = []
        for tf, tfData in self.takeOffList.items():
            lengths.extend(tfData.lengths)
        return sorted(lengths, reverse = True)

class Takeoff:
    def __init__(self, plan='', typeName='', name='', rawName='', description='', sf=0, lf=0, count=0, lengths=[], weight=0, dnl=''):
        self.plan = plan
        self.typeName = typeName
        self.name = name
        self.rawName = rawName
        self.description = description
        self.count = count
        self.sf = sf
        self.lf = lf
        self.lengths = []
        self.weight = weight
        self.dnl = dnl

    def __eq__(self, other):
        return self.plan == other.plan and self.typeName == other.typeName and self.name == other.name

    def __str__(self):
        return '\t'.join([
            str(self.count),
            '',
            self.name,
            str(self.lf),
            "{0:6.2f}".format(self.weight),
            self.plan,
            self.typeName,
            self.description,
            str(self.lengths),
        ])

    def weightList(self):

        # Order: Qty, Name, Length (grouped), Weight (grouped)
        weightPerLf = 0
        if self.lf:
            weightPerLf = float(self.weight) / float(self.lf)
        weightDict = {}

        if self.typeName not in DNL_LIST:
            for length in self.lengths:

                # Round up to nearest 6"
                length = math.ceil(float(length)*2)/2
                feet = math.floor(length)
                lengthOut = "{0:d}\'".format(feet)
                if length % 1: # non-integer foot length
                    lengthOut = lengthOut+" 6\""

                # Existing length
                if (length in weightDict.keys()):
                    weightDict[length]['qty'] += 1
                    weightDict[length]['weight'] += round(weightPerLf * length)

                # New length
                else:
                    weightDict[length] = {
                        'qty' : 1,
                        'plan' : self.plan,
                        'type' : self.typeName,
                        'name' : self.name,
                        'length' : length,
                        'lengthOut' : lengthOut,
                        'weight' : round(weightPerLf * length),
                    }

        output = []
        for length in sorted(weightDict.keys()):
            output.append([
                weightDict[length]['qty'],
                '',
                weightDict[length]['name'],
                weightDict[length]['lengthOut'],
                weightDict[length]['weight'],
                weightPerLf,
            ])
        return output


# FUNCTIONS

def createColDict(colNames):
    """Generate a column dictionary from a list."""
    colDict = {}
    for name in colNames:
        if not isBlank(name):
            colDict[name] = colNames.index(name)
    
    return colDict


def complexFracToDec(match):
    """Convert complex fraction to decimal. Use this in the regex call in nameClean()."""
    componentMatch = re.search(r'(\d+)-(\d+)/(\d+)', match.group())
    dec = float(componentMatch.group(1)) + ( float(componentMatch.group(2)) / float(componentMatch.group(3)) )
    return str(dec)


def deStubString(name, stubList=STUB_LIST):
    """Return a string with the entities of stubList removed."""
    for stub in stubList:
        return re.sub(stub, '', name).rstrip()


def isBlank (myString):
    """Check if string is blank"""
    return not (myString and myString.strip())


def nameClean(name):
    """Clean takeoff name for consistency"""

    # Get rid of spaces surrounding x's
    name = re.sub(r' x ', r'x', name)

    # Get rid of '"' characters
    name = re.sub(r'"', r'', name, re.M)

    # Get rid of "()" sections
    name = re.sub(r'\(.*\)', r'', name, re.M)

    # If starts with HSS or L, convert complex fraction dimensions (>1) to decimal.
    if name.startswith('HSS') or name.startswith('L'):
        name = re.sub(r'\d+-\d+/\d+', complexFracToDec, name)

    # Put a space between the first alpha characters and the first digit: 'W12x50' -> 'W 12x50'
    name = re.sub(r'^([^\W\d_]+)(\d)', r'\1 \2', name)

    # Now we can get rid of any words after the first two, 
    # ... if the third word follows A->B pattern (like for columns, eg. F->L01)
    # ... or if the third word is Beam
    # ... or if the third word is Brace
    if len(name.split()) > 2:
        if bool(re.search(r'\w+->\w+', name.split()[2])):
            name = ' '.join(name.split()[:2])
        elif bool(re.search(r'Beam', name.split()[2])):
            name = ' '.join(name.split()[:2])
        elif bool(re.search(r'Brace', name.split()[2])):
            name = ' '.join(name.split()[:2])

    return name.rstrip()


def tgdRead(filename):
    """Read Takeoff Geomoetry Detail File (Items)"""
    tgdFile = open(filename, 'r')
    
    colDict = {}
    takeOffs = {'struct': {}, 'deck': {}, 'cxn': {}, 'materialList': {}}
    firstLine = 1
    tf = Takeoff()
    materialName = ''
    mat = Material()
    dnl = ''
    for line in tgdFile:

        # First line expected to have column names. Collect them and move along.
        if firstLine:
            colNames = line.strip().split(',')
            colNames = [i.strip('\"') for i in colNames]
            colDict = createColDict(colNames)
            firstLine = 0
            continue

        data = line.strip('\"').strip().split(',')
        data = [i.strip('\"') for i in data] # Remove double quotes
    
        # Skip lines that start with 'STACK'
        if data[colDict['Plan Name']].startswith('STACK') or isBlank(line):
            continue

        # New entry in Plan Name column; new takeoff
        elif not isBlank(data[colDict['Plan Name']]):

            rawName = data[colDict['Name']]
            name = nameClean(rawName)
            description = data[colDict['Description']]

            index = re.sub(r' ', '', str(data[colDict['Plan Name']]+'|'+data[colDict['Type']]+'|'+name))
            rawIndex = re.sub(r' ', '', str(data[colDict['Plan Name']]+'|'+data[colDict['Type']]+'|'+rawName))

            # Check for special types that get their own calculations and listings. Everything else goes into materialList and struct.
            listings = {'Decking': 'deck', 'Cxn': 'cxn'}
            if data[colDict['Type']] in listings:
                listing = listings[data[colDict['Type']]]
            else:
                listing = 'struct'

            # Buckets get DNL listing
            if data[colDict['Type']] == 'Bucket' or data[colDict['Type']] == 'Cxn' or data[colDict['Type']] == 'Plate':
                dnl = 'DNL'

            # Type 'None' encountered
            if data[colDict['Type']] == 'None':
                MESSAGE_OUTPUT.append("WARN: Type of 'None' encountered: "
                    +data[colDict['Plan Name']]+" | "
                    +data[colDict['Type']]+" | "
                    +data[colDict['EA']]+" | "
                    +data[colDict['Name']]+" | "
                    +data[colDict['Description']]
                )

            # If we already have this index, don't create a new Takeoff. The name, description, and index variables remain unchanged,
            # so we add more data to the same Takeoff and Material after this line (eg. length data below).
            if index in takeOffs[listing]:
                tf.count += int(data[colDict['EA']])
                if takeOffs[listing][index].rawName == rawName:
                    MESSAGE_OUTPUT.append("WARN: Duplicate entry of "+index+" in Takeoff Geometry Detail. Unedited Name is "+rawName)

            else:

                # If name ends with "stub" or "KP", create an alternately named Takeoff so we can add lengths, LF, and weight data to the original.
                lastName = ""
                if name.split():
                    lastName = name.split()[-1]
                if lastName in STUB_LIST:
                    #MESSAGE_OUTPUT.append("NOTE: "+name+" were included as stubs. Their lengths, lineal footage, and weight are included in the more generic "+deStubString(name)+" listing; their counts are not.")
    
                    indexStub = index
                    index = deStubString(index, STUB_LIST)
                    tfStub = Takeoff(
                        data[colDict['Plan Name']],
                        data[colDict['Type']],
                        name,
                        rawName,
                        description,
                        '', # Ignore SF
                        '', # Ignore LF
                        int(data[colDict['EA']])
                    )
                    takeOffs[listing][indexStub] = tfStub
                    nameDeStubbed = deStubString(name, STUB_LIST)

                    if nameDeStubbed in takeOffs['materialList']:
                        takeOffs['materialList'][nameDeStubbed].takeOffList[index].count += int(data[colDict['EA']])
                    else:
                        takeOffs['materialList'][nameDeStubbed] = mat
    
                # Else create the Takeoff, add it to the takeOffs[listing] dictionary
                else:
                    tf = Takeoff(
                        data[colDict['Plan Name']],
                        data[colDict['Type']],
                        name,
                        rawName,
                        description,
                        float(data[colDict['SF']]),
                        float(data[colDict['LF']]),
                        int(data[colDict['EA']]), # count
                    )
                    tf.dnl = dnl
                    takeOffs[listing][index] = tf

                    # reset dnl
                    dnl = ''

                materialName = deStubString(name, STUB_LIST)

                # If material is already listed, append takeoff
                if materialName in takeOffs['materialList']:
                    takeOffs['materialList'][materialName].takeOffList[index] = tf

                else:
                    mat = Material(materialName, {index: tf})
                    takeOffs['materialList'][materialName] = mat

            isTfColNameLine = 1
    
        # Column names for takeoff -- skip
        elif isTfColNameLine:
            isTfColNameLine = 0
            continue
    
        # Gather length data
        else:
            mat = takeOffs['materialList'][materialName]
            lfEntry = data[colDict['LF']]

            # Special reading of lengths for Columns
            if tf.typeName == 'Column' or tf.typeName == 'Diagonal':
                descriptionAsNum = re.search(r'^\d+\.?\d*', description, re.M).group()
                tf.lengths.append(float(descriptionAsNum))
                tf.lf += float(descriptionAsNum)
                mat.lf += float(descriptionAsNum)

            # All other types
            elif (not isBlank(lfEntry)) and (float(lfEntry) != 0):
                tf.lengths.append(float(lfEntry))
                mat.lf += float(lfEntry)

            mat.takeOffList[index] = tf
            takeOffs['materialList'][materialName] = mat

    return takeOffs


def icbtRead(filename, takeOffs):
    """Read Item Cost by Type File (Cost)"""
    icbtFile = open(filename, 'r')
    
    isFirstLine = 1
    colNameLine = 0
    colDict = {}
    for line in icbtFile:
        data = line.strip().split(',')
        data = [i.strip('\"') for i in data] # Remove double quotes

        # Skip empty lines
        if isBlank(data[0]):
            break

        # Expecting first line to only have 'Material' in first cell
        if data[0].strip('\"') == 'Material' and isFirstLine:
            isFirstLine = 0
            colNameLine = 1
            continue

        # Expecting next line to be column names
        if colNameLine:
            colNames = line.strip().split(',')
            colNames = [i.strip('\"') for i in colNames]
            colDict = createColDict(colNames)
            colNameLine = 0
            continue

        # Ignore everything including and after the line that only has 'Summary' as first cell
        if data[0] == 'Summary':
            break
        
        rawName = data[colDict['Name']]
        name = nameClean(rawName)

        index = str(data[colDict['Plan Name']]+'|'+data[colDict['Type']]+'|'+name)
        index = re.sub(r' ', '', index)
        
        # This takeoff already has an entry:
        if index in takeOffs['struct']:
            takeOffs['struct'][index].weight += float(data[colDict['Qty']])

        # Or it's new from the cost report:
        else:
            tf = Takeoff(
                data[colDict['Plan Name']],
                data[colDict['Type']],
                name,
                rawName,
                '', # No description
                '', # No SF
                '', # No LF
                '', # No EA
                '', # No lengths
                float(data[colDict['Qty']])
            )
            tf.dnl = 'DNL'
            takeOffs['struct'][index] = tf

            if tf.name.startswith('HSS') and ( tf.typeName == 'Beam' or tf.typeName == 'Column' ):
                MESSAGE_OUTPUT.append(tf.name+' ('+tf.typeName+') was added in the cost report. This might be an item not found in STACK (eg. HSS 7x3x1/4 -> HSS 6x4x1/4), or a pipe column.')

        # This has an entry in material list:
        if name in takeOffs['materialList']:
            mat = takeOffs['materialList'][name]

            mat.weight += float(data[colDict['Qty']])
            if mat.lf > 0:
                mat.weightPerFoot = float(mat.weight) / float(mat.lf)

            takeOffs['materialList'][name] = mat

        # Or it's new in the cost report:
        else:
            if (tf.typeName not in DNL_LIST) and ('Plate' not in tf.name):
                MESSAGE_OUTPUT.append(tf.name+' was added to the material list from the cost report.')
                MESSAGE_OUTPUT.append(tf)

    return takeOffs


def main():

    if len(sys.argv) < 3:
        print('USAGE: report-generation.py TakeoffGeometry.csv CostByType.csv')
        exit(1)

    file1name = sys.argv[1]
    file2name = sys.argv[2]

    # Geometry Detail (Items)
    takeOffs = tgdRead(file1name)

    # Item Cost by Type (Cost)
    takeOffs = icbtRead(file2name, takeOffs)

    # Print Items

    print('Qty'+'\t\t'+'Description'+'\t'+'Length'+'\t'+'Weight')
    isFirstTransition = 1
    for index, tfOut in takeOffs['struct'].items():
        wL = tfOut.weightList()
        if wL:
            for row in wL:
                firstCell = 1
                for cell in row:
                    if firstCell:
                        print(cell, end='')
                        firstCell = 0
                    else:
                        print('\t'+str(cell), end='')
                print('')

    # Warnings / Messages
    print('')
    for message in MESSAGE_OUTPUT:
        print(message)

main()
