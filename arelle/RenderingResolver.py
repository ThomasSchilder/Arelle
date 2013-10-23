'''
Created on Sep 13, 2011

@author: Mark V Systems Limited
(c) Copyright 2011 Mark V Systems Limited, All rights reserved.
'''
import os, sys
from arelle import XbrlConst
from arelle.ModelObject import ModelObject
from arelle.ModelValue import QName
from arelle.ModelFormulaObject import Aspect
from arelle.ModelRenderingObject import (ModelEuTable, ModelTable, ModelBreakdown,
                                         ModelEuAxisCoord, ModelDefinitionNode, ModelClosedDefinitionNode, ModelRuleDefinitionNode,
                                         ModelRelationshipDefinitionNode, ModelSelectionDefinitionNode, ModelFilterDefinitionNode,
                                         ModelConceptRelationshipDefinitionNode, ModelDimensionRelationshipDefinitionNode,
                                         ModelCompositionDefinitionNode, ModelTupleDefinitionNode, StructuralNode,
                                         ROLLUP_NOT_ANALYZED, CHILDREN_BUT_NO_ROLLUP, CHILD_ROLLUP_FIRST, CHILD_ROLLUP_LAST,
                                         OPEN_ASPECT_ENTRY_SURROGATE)
from arelle.PrototypeInstanceObject import FactPrototype

class ResolutionException(Exception):
    def __init__(self, code, message, **kwargs):
        self.kwargs = kwargs
        self.code = code
        self.message = message
        self.args = ( self.__repr__(), )
    def __repr__(self):
        return _('[{0}] exception {1}').format(self.code, self.message % self.kwargs)

def resolveAxesStructure(view, viewTblELR):
    if isinstance(viewTblELR, (ModelEuTable, ModelTable)):
        # called with a modelTable instead of an ELR
        
        # find an ELR for this table object
        table = viewTblELR
        for rel in view.modelXbrl.relationshipSet((XbrlConst.tableBreakdown, XbrlConst.tableBreakdownMMDD, XbrlConst.tableBreakdown201305, XbrlConst.tableBreakdown201301, XbrlConst.tableAxis2011)).fromModelObject(table):
            # find relationships in table's linkrole
            view.axisSubtreeRelSet = view.modelXbrl.relationshipSet((XbrlConst.tableBreakdownTree, XbrlConst.tableBreakdownTreeMMDD, XbrlConst.tableBreakdownTree201305, XbrlConst.tableDefinitionNodeSubtree, XbrlConst.tableDefinitionNodeSubtreeMMDD, XbrlConst.tableDefinitionNodeSubtree201305, XbrlConst.tableDefinitionNodeSubtree201301, XbrlConst.tableAxisSubtree2011), rel.linkrole)
            return resolveTableAxesStructure(view, table,
                                             view.modelXbrl.relationshipSet((XbrlConst.tableBreakdown, XbrlConst.tableBreakdownMMDD, XbrlConst.tableBreakdown201305, XbrlConst.tableBreakdown201301, XbrlConst.tableAxis2011), rel.linkrole))
        # no relationships from table found
        return (None, None, None, None)
    
    # called with an ELR or list of ELRs
    tblAxisRelSet = view.modelXbrl.relationshipSet(XbrlConst.euTableAxis, viewTblELR)
    if len(tblAxisRelSet.modelRelationships) > 0:
        view.axisSubtreeRelSet = view.modelXbrl.relationshipSet(XbrlConst.euAxisMember, viewTblELR)
    else: # try 2011 roles
        tblAxisRelSet = view.modelXbrl.relationshipSet((XbrlConst.tableBreakdown, XbrlConst.tableBreakdownMMDD, XbrlConst.tableBreakdown201305, XbrlConst.tableBreakdown201301, XbrlConst.tableAxis2011), viewTblELR)
        view.axisSubtreeRelSet = view.modelXbrl.relationshipSet((XbrlConst.tableBreakdown, XbrlConst.tableBreakdownMMDD, XbrlConst.tableBreakdown201305, XbrlConst.tableBreakdownTree, XbrlConst.tableBreakdownTreeMMDD, XbrlConst.tableBreakdownTree201305, XbrlConst.tableDefinitionNodeSubtree, XbrlConst.tableDefinitionNodeSubtreeMMDD, XbrlConst.tableDefinitionNodeSubtree201305, XbrlConst.tableDefinitionNodeSubtree201301, XbrlConst.tableAxisSubtree2011), viewTblELR)
    if tblAxisRelSet is None or len(tblAxisRelSet.modelRelationships) == 0:
        view.modelXbrl.modelManager.addToLog(_("no table relationships for {0}").format(viewTblELR))
        return (None, None, None, None)
    
    # table name
    modelRoleTypes = view.modelXbrl.roleTypes.get(viewTblELR)
    if modelRoleTypes is not None and len(modelRoleTypes) > 0:
        view.roledefinition = modelRoleTypes[0].definition
        if view.roledefinition is None or view.roledefinition == "":
            view.roledefinition = os.path.basename(viewTblELR)    
    try:
        for table in tblAxisRelSet.rootConcepts:
            return resolveTableAxesStructure(view, table, tblAxisRelSet)
    except ResolutionException as ex:
        view.modelXbrl.error(ex.code, ex.message, **ex.kwargs);        
    
    return (None, None, None, None)

def resolveTableAxesStructure(view, table, tblAxisRelSet):
    view.dataCols = 0
    view.dataRows = 0
    view.colHdrNonStdRoles = []
    view.colHdrDocRow = False
    view.colHdrCodeRow = False
    view.colHdrRows = 0
    view.rowHdrNonStdRoles = []
    view.rowHdrCols = 0
    view.rowHdrColWidth = [0,]
    view.rowNonAbstractHdrSpanMin = [0,]
    view.rowHdrDocCol = False
    view.rowHdrCodeCol = False
    view.zAxisRows = 0
    view.aspectModel = table.aspectModel
    view.zmostOrdCntx = None
    view.modelTable = table
    view.topRollup = {"x": ROLLUP_NOT_ANALYZED, "y": ROLLUP_NOT_ANALYZED}
    view.aspectEntryObjectId = 0
    
    xTopStructuralNode = yTopStructuralNode = zTopStructuralNode = None
    # must be cartesian product of top level relationships
    tblAxisRels = tblAxisRelSet.fromModelObject(table)
    facts = view.modelXbrl.factsInInstance
    # do z's first to set variables needed by x and y axes expressions
    for disposition in ("z", "x", "y"):
        for i, tblAxisRel in enumerate(tblAxisRels):
            definitionNode = tblAxisRel.toModelObject
            if (tblAxisRel.axisDisposition == disposition and 
                isinstance(definitionNode, (ModelEuAxisCoord, ModelBreakdown, ModelDefinitionNode))):
                if disposition == "x" and xTopStructuralNode is None:
                    xTopStructuralNode = StructuralNode(None, definitionNode, view.zmostOrdCntx, breakdownTableNode=table)
                    xTopStructuralNode.hasOpenNode = False
                    if isinstance(definitionNode,(ModelBreakdown, ModelClosedDefinitionNode)) and definitionNode.parentChildOrder is not None:
                        view.xTopRollup = CHILD_ROLLUP_LAST if definitionNode.parentChildOrder == "children-first" else CHILD_ROLLUP_FIRST
                    expandDefinition(view, xTopStructuralNode, definitionNode, 1, disposition, facts, i, tblAxisRels)
                    view.dataCols = xTopStructuralNode.leafNodeCount
                    break
                elif disposition == "y" and yTopStructuralNode is None:
                    yTopStructuralNode = StructuralNode(None, definitionNode, view.zmostOrdCntx, breakdownTableNode=table)
                    yTopStructuralNode.hasOpenNode = False
                    if isinstance(definitionNode,(ModelBreakdown, ModelClosedDefinitionNode)) and definitionNode.parentChildOrder is not None:
                        view.yAxisChildrenFirst.set(definitionNode.parentChildOrder == "children-first")
                        view.yTopRollup = CHILD_ROLLUP_LAST if definitionNode.parentChildOrder == "children-first" else CHILD_ROLLUP_FIRST
                    expandDefinition(view, yTopStructuralNode, definitionNode, 1, disposition, facts, i, tblAxisRels)
                    view.dataRows = yTopStructuralNode.leafNodeCount
                    break
                elif disposition == "z" and zTopStructuralNode is None:
                    zTopStructuralNode = StructuralNode(None, definitionNode, breakdownTableNode=table)
                    zTopStructuralNode.hasOpenNode = False
                    expandDefinition(view, zTopStructuralNode, definitionNode, 1, disposition, facts, i, tblAxisRels)
                    break
    view.colHdrTopRow = view.zAxisRows + 1 # need rest if combobox used (2 if view.zAxisRows else 1)
    for i in range(view.rowHdrCols):
        if view.rowNonAbstractHdrSpanMin[i]:
            lastRowMinWidth = view.rowNonAbstractHdrSpanMin[i] - sum(view.rowHdrColWidth[i] for j in range(i, view.rowHdrCols - 1))
            if lastRowMinWidth > view.rowHdrColWidth[view.rowHdrCols - 1]:
                view.rowHdrColWidth[view.rowHdrCols - 1] = lastRowMinWidth 
    #view.rowHdrColWidth = (60,60,60,60,60,60,60,60,60,60,60,60,60,60)
    # use as wraplength for all row hdr name columns 200 + fixed indent and abstract mins (not incl last name col)
    view.rowHdrWrapLength = 200 + sum(view.rowHdrColWidth[i] for i in range(view.rowHdrCols - 1))
    view.dataFirstRow = view.colHdrTopRow + view.colHdrRows + len(view.colHdrNonStdRoles)
    view.dataFirstCol = 1 + view.rowHdrCols + len(view.rowHdrNonStdRoles)
    #view.dataFirstRow = view.colHdrTopRow + view.colHdrRows + view.colHdrDocRow + view.colHdrCodeRow
    #view.dataFirstCol = 1 + view.rowHdrCols + view.rowHdrDocCol + view.rowHdrCodeCol
    #for i in range(view.dataFirstRow + view.dataRows):
    #    view.gridView.rowconfigure(i)
    #for i in range(view.dataFirstCol + view.dataCols):
    #    view.gridView.columnconfigure(i)
    view.modelTable = table
    
    # organize hdrNonStdRoles so code (if any) is after documentation (if any)
    for hdrNonStdRoles in (view.colHdrNonStdRoles, view.rowHdrNonStdRoles):
        iCodeRole = -1
        for i, hdrNonStdRole in enumerate(hdrNonStdRoles):
            if 'code' in os.path.basename(hdrNonStdRole).lower():
                iCodeRole = i
                break
        if iCodeRole >= 0 and len(hdrNonStdRoles) > 1 and iCodeRole < len(hdrNonStdRoles) - 1:
            del hdrNonStdRoles[iCodeRole]
            hdrNonStdRoles.append(hdrNonStdRole)

    if view.topRollup["x"]:
        view.xAxisChildrenFirst.set(view.topRollup["x"] == CHILD_ROLLUP_LAST)
    if view.topRollup["y"]:
        view.yAxisChildrenFirst.set(view.topRollup["y"] == CHILD_ROLLUP_LAST)

    return (tblAxisRelSet, xTopStructuralNode, yTopStructuralNode, zTopStructuralNode)

def sortkey(obj):
    if isinstance(obj, ModelObject):
        return obj.objectIndex
    return obj

def expandDefinition(view, structuralNode, definitionNode, depth, axisDisposition, facts, i=None, tblAxisRels=None, processOpenDefinitionNode=True):
    subtreeRelationships = view.axisSubtreeRelSet.fromModelObject(definitionNode)
    
    def checkLabelWidth(structuralNode, checkBoundFact=False):
        if axisDisposition == "y":
            # messages can't be evaluated, just use the text portion of format string
            label = structuralNode.header(lang=view.lang, 
                                          returnGenLabel=not checkBoundFact, 
                                          returnMsgFormatString=not checkBoundFact)
            if label:
                # need to et more exact word length in screen units
                widestWordLen = max(len(w) * 16 for w in label.split())
                # abstract only pertains to subtree of closed nodesbut not cartesian products or open nodes
                while structuralNode.depth >= len(view.rowHdrColWidth):
                    view.rowHdrColWidth.append(0)
                if definitionNode.isAbstract or not subtreeRelationships: # isinstance(definitionNode, ModelOpenDefinitionNode):                    
                    if widestWordLen > view.rowHdrColWidth[structuralNode.depth]:
                        view.rowHdrColWidth[structuralNode.depth] = widestWordLen
                else:
                    if widestWordLen > view.rowNonAbstractHdrSpanMin[structuralNode.depth]:
                        view.rowNonAbstractHdrSpanMin[structuralNode.depth] = widestWordLen
                        
    if structuralNode and isinstance(definitionNode, (ModelBreakdown, ModelEuAxisCoord, ModelDefinitionNode)):
        try:
            #cartesianProductNestedArgs = (view, depth, axisDisposition, facts, tblAxisRels, i)
            ordCardinality, ordDepth = definitionNode.cardinalityAndDepth(structuralNode)
            if (not definitionNode.isAbstract and
                isinstance(definitionNode, ModelClosedDefinitionNode) and 
                ordCardinality == 0):
                view.modelXbrl.error("xbrlte:closedDefinitionNodeZeroCardinality",
                    _("Closed definition node %(xlinkLabel)s does not contribute at least one structural node"),
                    modelObject=(view.modelTable,definitionNode), xlinkLabel=definitionNode.xlinkLabel, axis=definitionNode.localName)
            nestedDepth = depth + ordDepth
            # HF test
            cartesianProductNestedArgs = [view, nestedDepth, axisDisposition, facts, tblAxisRels, i]
            if axisDisposition == "z":
                if depth == 1: # choices (combo boxes) don't add to z row count
                    view.zAxisRows += 1 
            elif axisDisposition == "x":
                if ordDepth:
                    if nestedDepth > view.colHdrRows: view.colHdrRows = nestedDepth 
                    '''
                    if not view.colHdrDocRow:
                        if definitionNode.header(role="http://www.xbrl.org/2008/role/documentation",
                                                       lang=view.lang): 
                            view.colHdrDocRow = True
                    if not view.colHdrCodeRow:
                        if definitionNode.header(role="http://www.eurofiling.info/role/2010/coordinate-code"): 
                            view.colHdrCodeRow = True
                    '''
                hdrNonStdRoles = view.colHdrNonStdRoles
            elif axisDisposition == "y":
                if ordDepth:
                    #if not definitionNode.isAbstract:
                    #    view.dataRows += ordCardinality
                    if nestedDepth > view.rowHdrCols: 
                        view.rowHdrCols = nestedDepth
                        for j in range(1 + ordDepth):
                            view.rowHdrColWidth.append(16)  # min width for 'tail' of nonAbstract coordinate
                            view.rowNonAbstractHdrSpanMin.append(0)
                    checkLabelWidth(structuralNode, checkBoundFact=False)
                    ''' 
                    if not view.rowHdrDocCol:
                        if definitionNode.header(role="http://www.xbrl.org/2008/role/documentation",
                                             lang=view.lang): 
                            view.rowHdrDocCol = True
                    if not view.rowHdrCodeCol:
                        if definitionNode.header(role="http://www.eurofiling.info/role/2010/coordinate-code"): 
                            view.rowHdrCodeCol = True
                    '''
                hdrNonStdRoles = view.rowHdrNonStdRoles
            if axisDisposition in ("x", "y"):
                hdrNonStdPosition = -1  # where a match last occured
                for rel in view.modelXbrl.relationshipSet(XbrlConst.elementLabel).fromModelObject(definitionNode):
                    if rel.toModelObject is not None and rel.toModelObject.role != XbrlConst.genStandardLabel:
                        labelLang = rel.toModelObject.xmlLang
                        labelRole = rel.toModelObject.role
                        if (labelLang == view.lang or labelLang.startswith(view.lang) or view.lang.startswith(labelLang)
                            or ("code" in labelRole)):
                            labelRole = rel.toModelObject.role
                            if labelRole in hdrNonStdRoles:
                                hdrNonStdPosition = hdrNonStdRoles.index(labelRole)
                            else:
                                hdrNonStdRoles.insert(hdrNonStdPosition + 1, labelRole)
            isCartesianProductExpanded = False
            if not isinstance(definitionNode, ModelFilterDefinitionNode):
                # note: reduced set of facts should always be passed to subsequent open nodes
                for axisSubtreeRel in subtreeRelationships:
                    isCartesianProductExpanded = True
                    childDefinitionNode = axisSubtreeRel.toModelObject
                    if childDefinitionNode.isRollUp:
                        structuralNode.rollUpStructuralNode = StructuralNode(structuralNode, childDefinitionNode)
                        if not structuralNode.childStructuralNodes: # first sub ordinate is the roll up
                            structuralNode.subtreeRollUp = CHILD_ROLLUP_FIRST
                        else: 
                            structuralNode.subtreeRollUp = CHILD_ROLLUP_LAST
                        if not view.topRollup.get(axisDisposition):
                            view.topRollup[axisDisposition] = structuralNode.subtreeRollUp
                    else:
                        if (isinstance(definitionNode, (ModelBreakdown, ModelCompositionDefinitionNode)) and
                            isinstance(childDefinitionNode, ModelRelationshipDefinitionNode)): # append list products to composititionAxes subObjCntxs
                            childStructuralNode = structuralNode
                        else:
                            childStructuralNode = StructuralNode(structuralNode, childDefinitionNode) # others are nested structuralNode
                            if axisDisposition != "z":
                                structuralNode.childStructuralNodes.append(childStructuralNode)
                        if axisDisposition != "z":
                            expandDefinition(view, childStructuralNode, childDefinitionNode, depth+ordDepth, axisDisposition, facts) #recurse
                            cartesianProductExpander(childStructuralNode, *cartesianProductNestedArgs)
                        else:
                            childStructuralNode.indent = depth - 1
                            structuralNode.choiceStructuralNodes.append(childStructuralNode)
                            expandDefinition(view, structuralNode, childDefinitionNode, depth + 1, axisDisposition, facts) #recurse
                    # required when switching from abstract to roll up to determine abstractness
                    #if not structuralNode.subtreeRollUp and structuralNode.childStructuralNodes and definitionNode.tag.endswith("Node"):
                    #    structuralNode.subtreeRollUp = CHILDREN_BUT_NO_ROLLUP
            #if not hasattr(structuralNode, "indent"): # probably also for multiple open axes
            if processOpenDefinitionNode:
                if isinstance(definitionNode, ModelRelationshipDefinitionNode):
                    structuralNode.isLabeled = False
                    selfStructuralNodes = {} if definitionNode.axis.endswith('-or-self') else None
                    for rel in definitionNode.relationships(structuralNode):
                        if not isinstance(rel, list):
                            relChildStructuralNode = addRelationship(definitionNode, rel, structuralNode, cartesianProductNestedArgs, selfStructuralNodes)
                        else:
                            addRelationships(definitionNode, rel, relChildStructuralNode, cartesianProductNestedArgs)
                    if axisDisposition == "z":
                        # if definitionNode is first structural node child remove it
                        if structuralNode.choiceStructuralNodes and structuralNode.choiceStructuralNodes[0].definitionNode == definitionNode:
                            del structuralNode.choiceStructuralNodes[0]
                        # flatten hierarchy of nested structural nodes inot choice nodes (for single listbox)
                        def flattenChildNodesToChoices(childStructuralNodes, indent):
                            while childStructuralNodes:
                                choiceStructuralNode = childStructuralNodes.pop(0)
                                choiceStructuralNode.indent = indent
                                structuralNode.choiceStructuralNodes.append(choiceStructuralNode)
                                flattenChildNodesToChoices(choiceStructuralNode.childStructuralNodes, indent + 1)
                        flattenChildNodesToChoices(structuralNode.childStructuralNodes, 0)
                    # set up by definitionNode.relationships
                    if isinstance(definitionNode, ModelConceptRelationshipDefinitionNode):
                        if (definitionNode._sourceQname != XbrlConst.qnXfiRoot and
                            definitionNode._sourceQname not in view.modelXbrl.qnameConcepts):
                            view.modelXbrl.error("xbrlte:invalidConceptRelationshipSource",
                                _("Concept relationship rule node %(xlinkLabel)s source %(source)s does not refer to an existing concept."),
                                modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, source=definitionNode._sourceQname)
                    elif isinstance(definitionNode, ModelDimensionRelationshipDefinitionNode):
                        dim = view.modelXbrl.qnameConcepts.get(definitionNode._dimensionQname)
                        if dim is None or not dim.isExplicitDimension:
                            view.modelXbrl.error("xbrlte:invalidExplicitDimensionQName",
                                _("Dimension relationship rule node %(xlinkLabel)s dimension %(dimension)s does not refer to an existing explicit dimension."),
                                modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, dimension=definitionNode._dimensionQname)
                        domMbr = view.modelXbrl.qnameConcepts.get(definitionNode._sourceQname)
                        if domMbr is None or not domMbr.isDomainMember:
                            view.modelXbrl.error("xbrlte:invalidDimensionRelationshipSource",
                                _("Dimension relationship rule node %(xlinkLabel)s source %(source)s does not refer to an existing domain member."),
                                modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, source=definitionNode._sourceQname)
                    if (definitionNode._axis in ("child", "child-or-self", "parent", "parent-or-self", "sibling", "sibling-or-self") and
                        (not isinstance(definitionNode._generations, _NUM_TYPES) or definitionNode._generations > 1)):
                        view.modelXbrl.error("xbrlte:relationshipNodeTooManyGenerations ",
                            _("Relationship rule node %(xlinkLabel)s formulaAxis %(axis)s implies a single generation tree walk but generations %(generations)s is greater than one."),
                            modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, axis=definitionNode._axis, generations=definitionNode._generations)
                    
                elif isinstance(definitionNode, ModelSelectionDefinitionNode):
                    structuralNode.setHasOpenNode()
                    structuralNode.isLabeled = False
                    isCartesianProductExpanded = True
                    varQn = definitionNode.variableQname
                    if varQn:
                        selections = sorted(structuralNode.evaluate(definitionNode, definitionNode.evaluate) or [], 
                                            key=lambda obj:sortkey(obj))
                        if isinstance(selections, (list,set,tuple)) and len(selections) > 1:
                            for selection in selections: # nested choices from selection list
                                childStructuralNode = StructuralNode(structuralNode, definitionNode, contextItemFact=selection)
                                childStructuralNode.variables[varQn] = selection
                                childStructuralNode.indent = 0
                                if axisDisposition == "z":
                                    structuralNode.choiceStructuralNodes.append(childStructuralNode)
                                    childStructuralNode.zSelection = True
                                else:
                                    structuralNode.childStructuralNodes.append(childStructuralNode)
                                    expandDefinition(view, childStructuralNode, definitionNode, depth, axisDisposition, facts, processOpenDefinitionNode=False) #recurse
                                    cartesianProductExpander(childStructuralNode, *cartesianProductNestedArgs)
                        else:
                            structuralNode.variables[varQn] = selections
                elif isinstance(definitionNode, ModelFilterDefinitionNode):
                    structuralNode.setHasOpenNode()
                    structuralNode.isLabeled = False
                    isCartesianProductExpanded = True
                    structuralNode.abstract = True # spanning ordinate acts as a subtitle
                    filteredFactsPartitions = structuralNode.evaluate(definitionNode, 
                                                                      definitionNode.filteredFactsPartitions, 
                                                                      evalArgs=(facts,))
                    if structuralNode._rendrCntx.formulaOptions.traceVariableFilterWinnowing:
                        view.modelXbrl.info("table:trace",
                            _("Filter node %(xlinkLabel)s facts partitions: %(factsPartitions)s"), 
                            modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel,
                            factsPartitions=str(filteredFactsPartitions))
                        
                    # ohly for fact entry (true if no parent open nodes or all are on entry prototype row)
                    if axisDisposition != "z":
                        childList = structuralNode.childStructuralNodes
                        if structuralNode.isEntryPrototype(default=True):
                            for i in range(getattr(view, "openBreakdownLines", 
                                                   # for file output, 1 entry row if no facts
                                                   0 if filteredFactsPartitions else 1)):
                                view.aspectEntryObjectId += 1
                                filteredFactsPartitions.append([FactPrototype(view, {"aspectEntryObjectId": OPEN_ASPECT_ENTRY_SURROGATE + str(view.aspectEntryObjectId)})])
                                if structuralNode.isEntryPrototype(default=False):
                                    break # only one node per cartesian product under outermost nested open entry row
                    else:
                        childList = structuralNode.choiceStructuralNodes
                    for factsPartition in filteredFactsPartitions:
                        childStructuralNode = StructuralNode(structuralNode, definitionNode, contextItemFact=factsPartition[0])
                        childStructuralNode.indent = 0
                        childStructuralNode.depth -= 1  # for label width; parent is merged/invisible
                        childList.append(childStructuralNode)
                        checkLabelWidth(childStructuralNode, checkBoundFact=True)
                        #expandDefinition(view, childStructuralNode, definitionNode, depth, axisDisposition, factsPartition, processOpenDefinitionNode=False) #recurse
                        cartesianProductNestedArgs[3] = factsPartition
                        # note: reduced set of facts should always be passed to subsequent open nodes
                        if subtreeRelationships:
                            for axisSubtreeRel in subtreeRelationships:
                                child2DefinitionNode = axisSubtreeRel.toModelObject
                                child2StructuralNode = StructuralNode(childStructuralNode, child2DefinitionNode) # others are nested structuralNode
                                childStructuralNode.childStructuralNodes.append(child2StructuralNode)
                                expandDefinition(view, child2StructuralNode, child2DefinitionNode, depth+ordDepth, axisDisposition, factsPartition) #recurse
                                cartesianProductExpander(child2StructuralNode, *cartesianProductNestedArgs)
                        else:
                            cartesianProductExpander(childStructuralNode, *cartesianProductNestedArgs)
                    # sort by header (which is likely to be typed dim value, for example)
                    childList.sort(key=lambda childStructuralNode: 
                                   childStructuralNode.header(lang=view.lang, 
                                                              returnGenLabel=False, 
                                                              returnMsgFormatString=False) 
                                   or '') # exception on trying to sort if header returns None
                    
                    # TBD if there is no abstract 'sub header' for these subOrdCntxs, move them in place of parent structuralNode 
                elif isinstance(definitionNode, ModelTupleDefinitionNode):
                    structuralNode.abstract = True # spanning ordinate acts as a subtitle
                    matchingTupleFacts = structuralNode.evaluate(definitionNode, 
                                                                 definitionNode.filteredFacts, 
                                                                 evalArgs=(facts,))
                    for tupleFact in matchingTupleFacts:
                        childStructuralNode = StructuralNode(structuralNode, definitionNode, contextItemFact=tupleFact)
                        childStructuralNode.indent = 0
                        structuralNode.childStructuralNodes.append(childStructuralNode)
                        expandDefinition(view, childStructuralNode, definitionNode, depth, axisDisposition, [tupleFact]) #recurse
                    # sort by header (which is likely to be typed dim value, for example)
                    if any(sOC.header(lang=view.lang) for sOC in structuralNode.childStructuralNodes):
                        structuralNode.childStructuralNodes.sort(key=lambda childStructuralNode: childStructuralNode.header(lang=view.lang) or '')
                elif isinstance(definitionNode, ModelRuleDefinitionNode):
                    for constraintSet in definitionNode.constraintSets.values():
                        for aspect in constraintSet.aspectsCovered():
                            if not constraintSet.aspectValueDependsOnVars(aspect):
                                if aspect == Aspect.CONCEPT:
                                    conceptQname = definitionNode.aspectValue(view.modelXbrl.rendrCntx, Aspect.CONCEPT)
                                    concept = view.modelXbrl.qnameConcepts.get(conceptQname)
                                    if concept is None or not concept.isItem or concept.isDimensionItem or concept.isHypercubeItem:
                                        view.modelXbrl.error("xbrlte:invalidQNameAspectValue",
                                            _("Rule node %(xlinkLabel)s specifies concept %(concept)s does not refer to an existing primary item concept."),
                                            modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, concept=conceptQname)
                                elif isinstance(aspect, QName):
                                    dim = view.modelXbrl.qnameConcepts.get(aspect)
                                    memQname = definitionNode.aspectValue(view.modelXbrl.rendrCntx, aspect)
                                    mem = view.modelXbrl.qnameConcepts.get(memQname)
                                    if dim is None or not dim.isDimensionItem:
                                        view.modelXbrl.error("xbrlte:invalidQNameAspectValue",
                                            _("Rule node %(xlinkLabel)s specifies dimension %(concept)s does not refer to an existing dimension concept."),
                                            modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, concept=aspect)
                                    if isinstance(memQname, QName) and (mem is None or not mem.isDomainMember):
                                        view.modelXbrl.error("xbrlte:invalidQNameAspectValue",
                                            _("Rule node %(xlinkLabel)s specifies domain member %(concept)s does not refer to an existing domain member concept."),
                                            modelObject=definitionNode, xlinkLabel=definitionNode.xlinkLabel, concept=memQname)
    
                if axisDisposition == "z":
                    if structuralNode.choiceStructuralNodes:
                        choiceNodeIndex = view.zOrdinateChoices.get(definitionNode, 0)
                        if choiceNodeIndex < len(structuralNode.choiceStructuralNodes):
                            structuralNode.choiceNodeIndex = choiceNodeIndex
                        else:
                            structuralNode.choiceNodeIndex = 0
                    view.zmostOrdCntx = structuralNode
                        
                if not isCartesianProductExpanded or axisDisposition == "z":
                    cartesianProductExpander(structuralNode, *cartesianProductNestedArgs)
                        
                if not structuralNode.childStructuralNodes: # childless root ordinate, make a child to iterate in producing table
                    subOrdContext = StructuralNode(structuralNode, definitionNode)
        except ResolutionException as ex:
            if sys.version[0] >= '3':
                #import traceback
                #traceback.print_tb(ex.__traceback__)
                raise ex.with_traceback(ex.__traceback__)  # provide original traceback information
            else:
                raise ex
        except Exception as ex:
            e = ResolutionException("arelle:resolutionException",
                                    _("Exception in resolution of definition node %(node)s: %(error)s"),
                                    modelObject=definitionNode, node=definitionNode.qname, error=str(ex)
                                    )
            if sys.version[0] >= '3':
                raise e.with_traceback(ex.__traceback__)  # provide original traceback information
            else:
                raise e
            
def cartesianProductExpander(childStructuralNode, view, depth, axisDisposition, facts, tblAxisRels, i):
    if i is not None: # recurse table relationships for cartesian product
        for j, tblRel in enumerate(tblAxisRels[i+1:]):
            tblObj = tblRel.toModelObject
            if isinstance(tblObj, (ModelEuAxisCoord, ModelDefinitionNode)) and axisDisposition == tblRel.axisDisposition:
                #if tblObj.cardinalityAndDepth(childStructuralNode)[1] or axisDisposition == "z":
                if axisDisposition == "z":
                    subOrdTblCntx = StructuralNode(childStructuralNode, tblObj)
                    childStructuralNode.childStructuralNodes.append(subOrdTblCntx)
                else: # non-ordinate composition
                    subOrdTblCntx = childStructuralNode
                # predefined axes need facts sub-filtered
                if isinstance(childStructuralNode.definitionNode, ModelClosedDefinitionNode):
                    matchingFacts = childStructuralNode.evaluate(childStructuralNode.definitionNode, 
                                                        childStructuralNode.definitionNode.filteredFacts, 
                                                        evalArgs=(facts,))
                else:
                    matchingFacts = facts
                # returns whether there were no structural node results
                expandDefinition(view, subOrdTblCntx, tblObj, 
                            depth, # depth + (0 if axisDisposition == 'z' else 1), 
                            axisDisposition, matchingFacts, j + i + 1, tblAxisRels) #cartesian product
                break
                
def addRelationship(relDefinitionNode, rel, structuralNode, cartesianProductNestedArgs, selfStructuralNodes=None):
    variableQname = relDefinitionNode.variableQname
    conceptQname = relDefinitionNode.conceptQname
    coveredAspect = relDefinitionNode.coveredAspect(structuralNode)
    if not coveredAspect:
        return None
    if selfStructuralNodes is not None:
        fromConceptQname = rel.fromModelObject.qname
        # is there an ordinate for this root object?
        if fromConceptQname in selfStructuralNodes:
            childStructuralNode = selfStructuralNodes[fromConceptQname]
        else:
            childStructuralNode = StructuralNode(structuralNode, relDefinitionNode)
            structuralNode.childStructuralNodes.append(childStructuralNode)
            selfStructuralNodes[fromConceptQname] = childStructuralNode
            if variableQname:
                childStructuralNode.variables[variableQname] = []
            if conceptQname:
                childStructuralNode.variables[conceptQname] = fromConceptQname
            childStructuralNode.aspects[coveredAspect] = fromConceptQname
        relChildStructuralNode = StructuralNode(childStructuralNode, relDefinitionNode)
        childStructuralNode.childStructuralNodes.append(relChildStructuralNode)
    else:
        relChildStructuralNode = StructuralNode(structuralNode, relDefinitionNode)
        structuralNode.childStructuralNodes.append(relChildStructuralNode)
    preferredLabel = rel.preferredLabel
    if preferredLabel == XbrlConst.periodStartLabel:
        relChildStructuralNode.tagSelector = "table.periodStart"
    elif preferredLabel == XbrlConst.periodStartLabel:
        relChildStructuralNode.tagSelector = "table.periodEnd"
    if variableQname:
        relChildStructuralNode.variables[variableQname] = rel
    toConceptQname = rel.toModelObject.qname
    if conceptQname:
        relChildStructuralNode.variables[conceptQname] = toConceptQname
    relChildStructuralNode.aspects[coveredAspect] = toConceptQname
    cartesianProductExpander(relChildStructuralNode, *cartesianProductNestedArgs)
    return relChildStructuralNode

def addRelationships(relDefinitionNode, rels, structuralNode, cartesianProductNestedArgs):
    childStructuralNode = None # holder for nested relationships
    for rel in rels:
        if not isinstance(rel, list):
            # first entry can be parent of nested list relationships
            childStructuralNode = addRelationship(relDefinitionNode, rel, structuralNode, cartesianProductNestedArgs)
        elif childStructuralNode is None:
            childStructuralNode = StructuralNode(structuralNode, relDefinitionNode)
            structuralNode.childStructuralNodes.append(childStructuralNode)
            addRelationships(relDefinitionNode, rel, childStructuralNode, cartesianProductNestedArgs)
        else:
            addRelationships(relDefinitionNode, rel, childStructuralNode, cartesianProductNestedArgs)
            

