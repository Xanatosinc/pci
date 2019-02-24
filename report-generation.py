#!/usr/local/bin/python3.6

import math
import re
import sys

MESSAGE_OUTPUT = []

KERF = 0.25
MAX_STOCK = 65
STUB_LIST = ['Stub', 'stub', 'KP', 'kp']

MISC_FACTOR = 0.15
STRUCT_PRICE_FACTOR = 3.2

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
        self.rowCount = 2

    def __eq__(self, other):
        return self.plan == other.plan and self.typeName == other.typeName and self.name == other.name

    def __str__(self):
        rowOne = '\t'.join([
            self.dnl,
            self.plan, 
            self.typeName,
            str(self.count),
            '', # blank for space between count and name
            self.name,
            self.description,
            str(self.lf),
            str(self.weight),
        ])
        rowTwo = '\t\t\t\t\t'+str(self.lengths)

        if self.rowCount == 1:
            return rowOne
        else:
            return rowOne+'\n'+rowTwo

    def deckingSummary(self):
        return '\t'.join([
            self.dnl,
            self.plan,
            self.typeName,
            str(self.count),
            '', # blank for space between count and name
            self.description,
            str(self.sf),
            str(self.lf),
        ])

    def isBlank(self):
        return isBlank(self.name)

    def mfSummary(self):
        return '\t'.join([
            self.dnl,
            self.plan,
            self.typeName,
            str(self.count),
            '', # blank for space between count and name
            self.name,
        ])

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


def tgdRead(tgdFile):
    """Read Takeoff Geomoetry Detail File (Items)"""
    
    colDict = {}
    takeOffs = {'struct': {}, 'deck': {}, 'cxn': {}, 'materialList': {}}
    firstLine = 1
    tf = Takeoff()
    materialName = ''
    mat = Material()
    dnl = ''
    tfRowCount = 2
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

            #index is a concatenation of <Plan Name>|<Type>|<Name>
            index = re.sub(r' ', '', str(data[colDict['Plan Name']]+'|'+data[colDict['Type']]+'|'+name))
            rawIndex = re.sub(r' ', '', str(data[colDict['Plan Name']]+'|'+data[colDict['Type']]+'|'+rawName))

            # Check for special types that get their own calculations and listings. Everything else goes into materialList and struct.
            listings = {'Decking': 'deck', 'Cxn': 'cxn'}
            if data[colDict['Type']] in listings:
                listing = listings[data[colDict['Type']]]
            else:
                listing = 'struct'

            # Buckets, Plate, and Cxn get DNL listing; they also don't print an extra row with lengths
            if data[colDict['Type']] == 'Bucket' or data[colDict['Type']] == 'Cxn' or data[colDict['Type']] == 'Plate':
                dnl = 'DNL'
                tfRowCount = 1

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
                        if index in takeOffs['materialList'][nameDeStubbed].takeOffList:
                            takeOffs['materialList'][nameDeStubbed].takeOffList[index].count += int(data[colDict['EA']])
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
                            takeOffs['materialList'][nameDeStubbed].takeOffList[index] = tf
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
                    tf.rowCount = tfRowCount
                    takeOffs[listing][index] = tf

                    # reset dnl, rowCount
                    dnl = ''
                    tfRowCount = 2

                materialName = deStubString(name, STUB_LIST)

                # If material is already listed, append takeoff
                if materialName in takeOffs['materialList']:
                    takeOffs['materialList'][materialName].takeOffList[index] = tf

                else:
                    mat = Material(materialName, {index: tf})
                    takeOffs['materialList'][materialName] = mat

            isTfColNameLine = 1
    
        # Column names for each takeoff -- skip
        elif isTfColNameLine:
            isTfColNameLine = 0
            continue
    
        # Gather length data
        else:
            mat = takeOffs['materialList'][materialName]
            lfEntry = data[colDict['LF']]

            # Special reading of lengths for Columns
            if tf.typeName == 'Column' or tf.typeName == 'Diagonal':
                if description:
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


def icbtRead(icbtFile, takeOffs):
    """Read Item Cost by Type File (Cost)"""
    
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
            tf.rowCount = 1
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
            pass
#            MESSAGE_OUTPUT.append(tf.name+' was added to the material list from the cost report.')

    return takeOffs


def multing(materialList):
    """Change LF and weight using lengths and multing heuristics"""
    maxLen = MAX_STOCK
    kerf = KERF
    for materialName, mat in materialList.items():
        first = True
        overallStockList = []
        singleStockList = []
        dropList = []
        lengthList = mat.produceLengthList()

        # singleStockList describes the pieces that fit within one maximum stock length (eg. 65'),
        # overallStockList is a list of singleStockLists. Flattened, it would look like our original lengthList. 

        for length in lengthList:
            if length > maxLen:

                if sum(singleStockList) > 0:
                    overallStockList.append(singleStockList)
                    singleStockList = []
                overallStockList.append([length])

            elif sum(singleStockList) == 0: # empty list, no kerf. Add length to Single, add to Overall.
                singleStockList = [length] # new singleList
                overallStockList.append(singleStockList)

            elif sum(singleStockList) + kerf + length > maxLen: # can't add, would be too long
                oldOverall = overallStockList.copy()
                singleStockList = [length] # new singleList
                overallStockList.append(singleStockList) # put in OSL

            else: # good to add
                singleStockList.append(kerf)
                singleStockList.append(length)

        totalDropLength = 0
        for singleStock in overallStockList:
            stockLength = math.ceil(float(sum(singleStock)/5))*5
            dropLength = stockLength - sum(singleStock)
            totalDropLength = totalDropLength + dropLength
        mat.dropWeight = mat.weightPerFoot*totalDropLength

    return materialList


def main():

    if len(sys.argv) < 3:
        print('USAGE: report-generation.py TakeoffGeometry.csv CostByType.csv')
        exit(1)

    file1name = sys.argv[1]
    file2name = sys.argv[2]

    # Geometry Detail (Items)
    tgdFile = open(file1name, 'r')
    takeOffs = tgdRead(tgdFile)

    # Item Cost by Type (Cost)
    icbtFile = open(file2name, 'r')
    takeOffs = icbtRead(icbtFile, takeOffs)

    # Multing
    takeOffs['materialList'] = multing(takeOffs['materialList'])

    # Printing / Reporting
    spacing = '\t\t\t\t\t'

    # Column Definitions
    weightColumn = 'I'
    weightColumnTwo = chr(ord(weightColumn) + 1)
    dataColumn = 'G'
    dataColumnTwo = chr(ord(dataColumn) + 1)
    countColumn = 'D'
    sfColumn = 'G'
    lfColumn = chr(ord(sfColumn) + 1)

    initialWeight = 0.0

    # Print Struct Items
    printRange = [3,3]

    print('Struct')
    print('DNL'+'\t'+'Plan'+'\t'+'Type'+'\t'+'EA'+'\t\t'+'Name'+'\t'+'Description'+'\t'+'LF'+'\t'+'Weight')
    isFirstTransition = 1
    prevType = ''
    prevPlan = ''
    for index, tfOut in takeOffs['struct'].items():
        if tfOut.typeName != prevType or tfOut.plan != prevPlan:
            if isFirstTransition:
                isFirstTransition = 0
            else:
                print('')
                printRange[1] += 1
        initialWeight += tfOut.weight
        print(tfOut)
        printRange[1] += tfOut.rowCount
        prevPlan = tfOut.plan
        prevType = tfOut.typeName

    dropWeight = 0
    for matName, mat in takeOffs['materialList'].items():
        dropWeight += mat.dropWeight

    # Print Struct Calculations
    print('')
    print(spacing, 'Prelim Weight', '\t', '=SUM({}{}:{}{})'.format(weightColumn, printRange[0], weightColumn, printRange[1]), '\t', str(MISC_FACTOR), sep='')
    print(spacing, 'Misc Weight', '\t', '=PRODUCT({}{}:{}{})'.format(dataColumn, printRange[1]+1, dataColumnTwo, printRange[1]+1), sep='')
    print(spacing, 'Drop Weight', '\t', dropWeight, '\t(%.2f%%)' % (100 * dropWeight / initialWeight), sep='')
    print(spacing, 'Final Weight', '\t', '=SUM({}{}:{}{})'.format(dataColumn, printRange[1]+1, dataColumn, printRange[1]+3), '\t', STRUCT_PRICE_FACTOR, sep='')
    print(spacing, 'Struct Price', '\t', '=PRODUCT({}{}:{}{})'.format(dataColumn, printRange[1]+4, dataColumnTwo, printRange[1]+4), sep='')

    grandTotalLine = '={}{}'.format(dataColumn, printRange[1]+5)
    printRange = [printRange[1]+6, printRange[1]+6]

    if bool(takeOffs['deck']):

        # Print Decking Items
        deckSf = 0.0
        deckLf = 0.0
        print('')
        print('Decking')
        print('\t'.join(['DNL', 'Plan', 'Type', 'EA', '', 'Name', 'SF', 'LF']))

        printRange = [printRange[1]+3, printRange[1]+3]

        for index, tfOut in takeOffs['deck'].items():
            deckSf += tfOut.sf
            deckLf += tfOut.lf
            print(tfOut.deckingSummary())
            printRange[1] += 1
    
        # Print Decking Calculations
        print('')
        print(spacing, 'Total SF\t', '=SUM({}{}:{}{})'.format(sfColumn, printRange[0], sfColumn, printRange[1]), '\t', str(DECKING_PRICE_FACTOR), sep='')
        print(spacing, 'Decking Subtotal\t', '=PRODUCT({}{}:{}{})'.format(dataColumn, printRange[1]+1, dataColumnTwo, printRange[1]+1), sep='')
        print(spacing, 'Total LF\t', '=SUM({}{}:{}{})'.format(lfColumn, printRange[0], lfColumn, printRange[1]), '\t', str(SAFETY_LINE_PRICE_FACTOR), sep='')
        print(spacing, 'Safety Line Subtotal\t', '=PRODUCT({}{}:{}{})'.format(dataColumn, printRange[1]+3, dataColumnTwo, printRange[1]+3), sep='')
        print(spacing, 'Decking Total\t', '={}{}+{}{}'.format(dataColumn, printRange[1]+2, dataColumn, printRange[1]+4), sep='')

        grandTotalLine = grandTotalLine+'+{}{}'.format(dataColumn, printRange[1]+5)
        printRange = [printRange[1]+6, printRange[1]+6]

    mfCost = 0
    if bool(takeOffs['cxn']):

        # Print MF Labor
        mfPoints = 0
        print('')
        print('MF Labor')
        print('\t'.join(['DNL', 'Plan', 'Type', 'EA', '', 'Name']))

        printRange = [printRange[1]+3, printRange[1]+3]

        for index, tfOut in takeOffs['cxn'].items():
            mfPoints += tfOut.count
            print(tfOut.mfSummary())
            printRange[1] += 1
    
        # Print MF Labor Calculations
        print('')
        print(spacing, 'Total Points\t', '=SUM({}{}:{}{})'.format(countColumn, printRange[0], countColumn, printRange[1]), '\t', MF_HOURS_PER_POINT, sep='')
        print(spacing, 'Total Hours\t', '=PRODUCT({}{}:{}{})'.format(dataColumn, printRange[1]+1, dataColumnTwo, printRange[1]+1), '\t', MF_LABOR_RATE, sep='')
        print(spacing, 'MF Labor Cost\t', '=PRODUCT({}{}:{}{})'.format(dataColumn, printRange[1]+2, dataColumnTwo, printRange[1]+2), sep='')

        grandTotalLine = grandTotalLine+'+{}{}'.format(dataColumn, printRange[1]+3)
        printRange = [printRange[1]+4, printRange[1]+4]

    # Print Total Line
    totalCell = '{}{}'.format(dataColumn, printRange[1]+1)
    roundedTotal = '=MAX(MIN(ROUNDUP('+totalCell+',-1),ROUNDDOWN('+totalCell+',-3)+990),ROUNDDOWN('+totalCell+',-3)+700)'
    print('')
    print(spacing, 'Total Price\t', grandTotalLine, '\t', roundedTotal, sep='')

    # Placeholder for sheet range and date. Has to be manually entered.
    print('')
    print('Exclude:\tAny and all misc. steel, stairs, and handrails.')
    print('\tAESS Unless Otherwise Noted')
    print('Pages:')
    print('Date:')

    # Warnings / Messages
    print('')
    for message in MESSAGE_OUTPUT:
        print(message)

main()

# TODO:
# √ Read and stitch cost data
# √ HSS Beam bug
# √ Warn for 'None' Type
# √ Pull out decking
# √ Pull out MF cxns
# √ Multing -- increase LF
# √ Reporting -- print after grouping, sorting
# √ Accomodate 'None' Type
# Pull out camber (?)
