"""
The nomenclature checker.

@todo: Use exceptions for failure handling.
@todo: End vs stop. I guess we should use start/stop (end goes with beginning).
       Or first/last, or acceptor/donor. Anyway, CDS is always denoted with
       start/stop.
       Idea:
       * CDS -> use start/stop
       * splice sites or exons -> acceptor/donor
       * translation -> begin/end
       * any range of bases -> first/last
       * interbase position (if two numbers are used) -> before/after
"""


from operator import itemgetter, attrgetter

import Bio
import Bio.Seq
from Bio.Seq import Seq
from Bio.Alphabet import IUPAC

from mutalyzer import util
from mutalyzer import Retriever
from mutalyzer import GenRecord
from mutalyzer import Crossmap
from mutalyzer import Parser
from mutalyzer import Db
from mutalyzer import Mutator
from mutalyzer import Config


# Used in: _raw_variant
def _is_coding_intronic(loc):
    """
    Check whether a location is an intronic c. position.

    @arg loc: A location from the Parser module.
    @type loc: pyparsing.ParseResults

    @return: True if the location is c. intronic, False otherwise.
    @rtype: boolean
    """
    if not loc:
        return False
    if not loc.PtLoc:
        return False
    if not loc.PtLoc.Offset:
        return False
    return True
#_is_coding_intronic


# Used in: _coding_to_genomic
def _check_intronic_position(main, offset, transcript):
    """
    Check whether a c. position is really in an intron: The main coordinate
    must be a splice site and the offset coordinate must have the correct
    sign.

    @arg main: Main coordinate of the position.
    @type main: integer
    @arg offset: Offset coordinate of the position.
    @type offset: integer
    @arg transcript: Transcript under scrutiny.
    @type transcript: object

    @return: True if the combination (main, offset) is valid for this
             transcript, False otherwise.
    @rtype: boolean

    @todo: Use exceptions.
    """
    main_g = transcript.CM.x2g(main, 0)
    sites = transcript.CM.RNA

    if offset:
        oriented_offset = offset * transcript.CM.orientation
        try:
            i = sites.index(main_g)
            if not i % 2:
                # Splice acceptor, so sign must be -.
                if oriented_offset > 0:
                    return False
            else:
                # Splice donor, so sign must be +.
                if oriented_offset < 0:
                    return False
        except ValueError:
            # The main coordinate is not a splice site.
            return False

    return True
#_check_intronic_position


# Used in: _coding_to_genomic
def _get_offset(location) :
    """
    Convert the offset coordinate in a location (from the Parser) to an
    integer.

    @arg location: A location.
    @type location: pyparsing.ParseResults

    @return: Integer representation of the offset coordinate.
    @rtype: int
    """
    if location.Offset :
        if location.Offset == '?' : # This is highly debatable.
            return 0
        offset = int(location.Offset)
        if location.OffSgn == '-' :
            return -offset
        return offset

    return 0
#_get_offset


# Todo: refactor
def __checkOptArg(ref, p1, p2, arg, O) :
    """
    Do several checks for the optional argument of a variant.


    @arg ref: The reference sequence
    @type ref: string
    @arg p1: Start position of the variant
    @type p1: integer
    @arg p2: End position of the variant
    @type p2: integer
    @arg arg: The optional argument
    @type arg:
    @arg O: The Output object
    @type O: object

    @return: True if the optional argument is correct, False otherwise.
    @rtype: boolean

    @todo: refactor
    @todo: Use exceptions.
    """
    if arg : # The argument is optional, if it is not present, it is correct.
        if arg.isdigit() :         # If it is a digit (3_9del7 for example),
            length = int(arg)      #   the digit must be equal to the length
            interval = p2 - p1 + 1 #   of the given range.
            if length != interval :
                O.addMessage(__file__, 3, "EARGLEN",
                    "The length (%i) differed from that of the range (%i)." % (
                    length, interval))
                return False
            #if
        #if
        else :
            if not util.is_dna(arg) : # If it is not a digit, it muse be DNA.
                O.addMessage(__file__, 4, "ENODNA",
                    "Invalid letters in argument.")
                return False
            #if
            # And the DNA must match the reference sequence.
            ref_slice = str(ref[p1 - 1:p2])
            if ref_slice != str(arg) : # FIXME more informative.
                O.addMessage(__file__, 3, "EREF",
                    "%s not found at position %s, found %s instead." % (
                    arg, util.format_range(p1, p2), ref_slice))
                return False
            #if
        #else
    #if
    return True
#__checkOptArg


def _add_batch_output(O):
    """
    Format the results to a batch output.

    Filter the mutalyzer output and reformat it for use in the batch system
    as output object 'batchDone'.

    @arg O: The Output object
    @type O: Modules.Output.Output

    @todo: More documentation.
    """
    goi, toi = O.getOutput("geneSymbol")[-1] # Two strings [can be empty]
    tList   = []                             # Temporary List
    tDescr  = []                             # Temporary Descr

    reference = O.getOutput("reference")[-1]
    recordType = O.getOutput("recordType")[0]
    descriptions = O.getOutput("NewDescriptions")
        #iName, jName, mType, cDescr, pDescr, gAcc, cAcc, pAcc,
        #fullDescr, fullpDescr

    if len(descriptions) == 0:
        #No descriptions generated [unlikely]
        return
    if O.Summary()[0]:
        #There were errors during the run, return.
        return
    for descr in descriptions:
        if goi in descr[0] and toi in descr[1]: # Gene and Transcript
            if tDescr:
                # Already inserted a value in the tDescr
                tDescr, tList = [], descriptions
                break
            tDescr = descr

    tList = descriptions

    var = O.getOutput("variant")[-1]

    # Generate output
    outputline = ""
    if tDescr: #Filtering worked, only one Description left
        (gName, trName, mType, cDescr,
            pDescr, gAcc, cAcc, pAcc, fullD, fullpD) = tDescr

        gene = "%s_v%.3i" % (gName, int(trName))

        outputline += "%s\t%s\t%s\t" % (reference, gene, var)

        #Add genomic Description
        outputline += "%s\t" % O.getOutput("gDescription")[0]

        #Add coding Description & protein Description
        outputline += "%s\t%s\t" % (cDescr, pDescr)

        gc = cDescr and "%s:%s" % (gene, cDescr)
        gp = pDescr and "%s:%s" % (gene, pDescr)

        #Add mutation with GeneSymbols
        outputline += "%s\t%s\t" % (gc, gp)

        #Add References, should get genomic ref from parsed data
        if recordType == "LRG":
            gAcc = reference
        if recordType == "GB":
            geno = ["NC", "NG", "AC", "NT", "NW", "NZ", "NS"]
            for g in geno:
                if reference.startswith(g):
                    gAcc = reference
                    break
        outputline += "%s\t%s\t%s\t" % (gAcc or "", cAcc or "", pAcc or "")

    else:
        outputline += "\t"*11

    #Add list of affected transcripts "|" seperator
    if tList:
        outputline += "%s\t" % "|".join(e[-2] for e in tList)
        outputline += "%s\t" % "|".join(e[-1] for e in tList)
    else:
        outputline += "\t"*2

    #Link naar additional info:
    #outputline+="http://localhost/mutalyzer2/redirect?mutationName=%s" %\
    #        "todovariant"


    O.addOutput("batchDone", outputline)
#_add_batch_output


def apply_substitution(position, original, substitute, mutator, record, O):
    """
    Do a semantic check for a substitution, do the actual substitution and
    give it a name.

    @arg position: Genomic location of the substitution.
    @type position: int
    @arg original: Nucleotide in the reference sequence.
    @type original: string
    @arg substitute: Nucleotide in the mutated sequence.
    @type substitute: string
    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg O: The Output object.
    @type O: Modules.Output.Output

    @todo: Exception instead of O.addMessage().
    """
    if not util.is_dna(substitute):
        # This is not DNA.
        #O.addMessage(__file__, 4, "ENODNA", "Invalid letter in input")
        # todo: exception
        return

    if original == substitute:
        # This is not a real change.
        O.addMessage(__file__, 3, 'ENOVAR',
                     'No mutation given (%c>%c) at position %i.' % \
                     (original, substitute, position))

    mutator.subM(position, substitute)

    record.name(position, position, 'subst', mutator.orig[position - 1],
                substitute, None)
#apply_substitution


def apply_deletion_duplication(first, last, type, mutator, record, O):
    """
    Do a semantic check for a deletion or duplication, do the actual
    deletion/duplication and give it a name.

    @arg first: Genomic start position of the del/dup.
    @type first: int
    @arg last: Genomic end position of the del/dup.
    @type last: int
    @arg type: The variant type (del or dup).
    @type type: string
    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg O: The Output object.
    @type O: Modules.Output.Output

    @todo: Exception instead of O.addMessage().
    """
    roll = util.roll(mutator.orig, first, last)
    shift = roll[1]

    # In the case of RNA, check if we roll over a splice site. If so, make
    # the roll shorter, just up to the splice site.
    if record.record.molType == 'n':
        splice_sites = record.record.geneList[0].transcriptList[0] \
                       .mRNA.positionList
        for acceptor, donor in util.grouper(splice_sites):
            # Note that acceptor and donor splice sites both point to the
            # first, respectively last, position of the exon, so they are
            # both at different sides of the boundary.
            if last < acceptor and last + roll[1] >= acceptor:
                shift = acceptor - 1 - last
                break
            if last <= donor and last + roll[1] > donor:
                shift = donor - last
                break

    if shift:
        new_first = first + shift
        new_stop = last + shift
        O.addMessage(__file__, 2, 'WROLL',
            'Sequence "%s" at position %s was given, however, ' \
            'the HGVS notation prescribes that it should be "%s" at ' \
            'position %s.' % (
            mutator.visualiseLargeString(str(mutator.orig[first - 1:last])),
            util.format_range(first, last),
            mutator.visualiseLargeString(str(mutator.orig[new_first - 1:new_stop])),
            util.format_range(new_first, new_stop)))

    if shift != roll[1]:
        # The original roll was decreased because it crossed a splice site.
        incorrect_first = first + roll[1]
        incorrect_stop = last + roll[1]
        O.addMessage(__file__, 1, 'IROLLBACK',
            'Sequence "%s" at position %s was not corrected to "%s" at ' \
            'position %s, since they reside in different exons.' % (
            mutator.visualiseLargeString(str(mutator.orig[first - 1:last])),
            util.format_range(first, last),
            mutator.visualiseLargeString(str(mutator.orig[incorrect_first - 1:incorrect_stop])),
            util.format_range(incorrect_first, incorrect_stop)))

    if type == 'del':
        mutator.delM(first, last)
    else :
        mutator.dupM(first, last)

    record.name(first, last, type, '', '', (roll[0], shift))
#apply_deletion_duplication


def apply_inversion(first, last, mutator, record, O) :
    """
    Do a semantic check for an inversion, do the actual inversion, and give
    it a name.

    @arg first: Genomic start position of the inversion.
    @type first: int
    @arg last: Genomic end position of the inversion.
    @type last: int
    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg O: The Output object.
    @type O: Modules.Output.Output

    @todo: Exception instead of O.addMessage().
    """
    snoop = util.palinsnoop(mutator.orig[first - 1:last])

    if snoop:
        # We have a reverse-complement-palindromic prefix.
        if snoop == -1 :
            # Actually, not just a prefix, but the entire selected sequence is
            # a 'palindrome'.
            O.addMessage(__file__, 2, 'WNOCHANGE',
                'Sequence "%s" at position %i_%i is a palindrome ' \
                '(its own reverse complement).' % (
                mutator.visualiseLargeString(str(mutator.orig[first - 1:last])),
                first, last))
            return
        else:
            O.addMessage(__file__, 2, 'WNOTMINIMAL',
                'Sequence "%s" at position %i_%i is a partial ' \
                'palindrome (the first %i nucleotide(s) are the reverse ' \
                'complement of the last one(s)), the HGVS notation ' \
                'prescribes that it should be "%s" at position %i_%i.' % (
                mutator.visualiseLargeString(str(mutator.orig[first - 1:last])),
                first, last, snoop,
                mutator.visualiseLargeString(
                    str(mutator.orig[first + snoop - 1: last - snoop])),
                first + snoop, last - snoop))
            first += snoop
            last -= snoop

    mutator.invM(first, last)

    if first == last:
        O.addMessage(__file__, 2, 'WWRONGTYPE', 'Inversion at position ' \
            '%i is actually a substitution.' % first_g)
        record.name(first, first, 'subst', mutator.orig[first - 1],
            Bio.Seq.reverse_complement(mutator.orig[first - 1]), None)
    else :
        record.name(first, last, 'inv', '', '', None)
#apply_inversion


def apply_insertion(before, after, s, mutator, record, O):
    """
    Do a semantic check for an insertion, do the actual insertion, and give
    it a name.

    @arg before: Genomic position before the insertion.
    @type before: int
    @arg after: Genomic position after the insertion.
    @type after: int
    @arg s: Nucleotides to be inserted.
    @type s: string
    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg O: The Output object.
    @type O: Modules.Output.Output

    @todo: Exception instead of O.addMessage().
    """
    if before + 1 != after:
        O.addMessage(__file__, 3, 'EINSRANGE',
            '%i and %i are not consecutive positions.' % (before, after))
        return

    if not s or not util.is_dna(s):
        O.addMessage(__file__, 3, 'EUNKVAR', 'Although the syntax of this ' \
            'variant is correct, the effect can not be analysed.')
        return

    insertion_length = len(s)

    mutator.insM(before, s)
    new_before = mutator.shiftpos(before)
    new_stop = mutator.shiftpos(before) + insertion_length

    roll = util.roll(mutator.mutated, new_before + 1, new_stop)
    shift = roll[1]

    # In the case of RNA, check if we roll over a splice site. If so, make
    # the roll shorter, just up to the splice site.
    if record.record.molType == 'n' :
        splice_sites = record.record.geneList[0].transcriptList[0] \
                       .mRNA.positionList
        for acceptor, donor in util.grouper(splice_sites):
            # Note that acceptor and donor splice sites both point to the
            # first, respectively last, position of the exon, so they are
            # both at different sides of the boundary.
            if new_stop < acceptor and new_stop + roll[1] >= acceptor:
                shift = acceptor - 1 - new_stop
                break
            if new_stop <= donor and new_stop + roll[1] > donor:
                shift = donor - new_stop
                break

    if roll[0] + shift >= insertion_length:
        # Todo: Could there also be a IROLLBACK message in this case?
        O.addMessage(__file__, 2, 'WINSDUP',
            'Insertion of %s at position %i_%i was given, ' \
            'however, the HGVS notation prescribes that it should be a ' \
            'duplication of %s at position %i_%i.' % (
            s, before, before + 1,
            mutator.mutated[new_before + shift:new_stop + shift], before + shift,
            before + shift + insertion_length - 1))
        after += shift - 1
        before = after - insertion_length + 1
        record.name(before, after, 'dup', '', '',
                    (roll[0] + shift - insertion_length, 0))
    else:
        if shift:
            O.addMessage(__file__, 2, 'WROLL', 'Insertion of %s at position ' \
                '%i_%i was given, however, the HGVS notation prescribes ' \
                'that it should be an insertion of %s at position %i_%i.' % (
                s, before, before + 1,
                mutator.mutated[new_before + shift:new_stop + shift],
                new_before + shift, new_before + shift + 1))
        if shift != roll[1]:
            O.addMessage(__file__, 1, 'IROLLBACK',
                'Insertion of %s at position %i_%i was not corrected to an ' \
                'insertion of %s at position %i_%i, since they reside in ' \
                'different exons.' % (
                s, before, before + 1,
                mutator.mutated[new_before + roll[1]:new_stop + roll[1]],
                new_before + roll[1], new_before + roll[1] + 1))
        record.name(before, before + 1, 'ins',
                    mutator.mutated[new_before + shift:new_stop + shift], '',
                    (roll[0], shift))
#apply_insertion


def apply_delins(first, last, delete, insert, mutator, record, output):
    """
    Do a semantic check for an delins, do the actual delins, and give
    it a name.

    @arg first: Genomic start position of the delins.
    @type first: int
    @arg last: Genomic end position of the delins.
    @type last: int
    @arg delete: Sequence to delete (may be None, in which case it will be
                 constructed from the reference sequence).
    @type delete: string
    @arg insert: Sequence to insert.
    @type insert: string
    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg output: The Output object.
    @type output: Modules.Output.Output

    @todo: Exception instead of O.addMessage().
    """
    if not delete:
        delete = mutator.orig[first - 1:last]

    if str(delete) == str(insert):
        output.addMessage(__file__, 2, 'WNOCHANGE',
                          'Sequence "%s" at position %i_%i is identical to ' \
                          'the variant.' % (
                mutator.visualiseLargeString(str(mutator.orig[first - 1:last])),
                              first, last))
        return

    delete_trimmed, insert_trimmed, lcp, lcs = util.trim_common(delete, insert)

    if not len(delete_trimmed):
        output.addMessage(__file__, 2, 'WWRONGTYPE', 'The given DelIns ' \
                          'is actually an insertion.')
        apply_insertion(first + lcp - 1, first + lcp, insert_trimmed, mutator,
                        record, output)
        return

    if len(delete_trimmed) == 1 and len(insert_trimmed) == 1:
            output.addMessage(__file__, 2, 'WWRONGTYPE', 'The given DelIns ' \
                              'is actually a substitution.')
            apply_substitution(first + lcp, delete_trimmed, insert_trimmed,
                               mutator, record, output)
            return

    if not len(insert_trimmed):
        output.addMessage(__file__, 2, 'WWRONGTYPE', 'The given DelIns ' \
                          'is actually a deletion.')
        apply_deletion_duplication(first + lcp, last - lcs, 'del',
                                   mutator, record, output)
        return

    if str(Bio.Seq.reverse_complement(delete_trimmed)) == insert_trimmed:
        output.addMessage(__file__, 2, 'WWRONGTYPE', 'The given DelIns ' \
                          'is actually an inversion.')
        apply_inversion(first + lcp, last - lcs, mutator,
                        record, output)
        return

    if len(insert) != len(insert_trimmed):
        output.addMessage(__file__, 2, 'WNOTMINIMAL',
                'Sequence "%s" at position %i_%i has the same prefix or ' \
                'suffix as the inserted sequence "%s". The HGVS notation ' \
                'prescribes that it should be "%s" at position %i_%i.' % (
                mutator.visualiseLargeString(str(mutator.orig[first - 1:last])),
                first, last, insert, insert_trimmed, first + lcp, last - lcs))

    mutator.delinsM(first + lcp, last - lcs, insert_trimmed)

    record.name(first + lcp, last - lcs, 'delins', insert_trimmed, '', None)
#apply_delins


def _intronic_to_genomic(location, transcript):
    """
    Get genomic location from IVS location.

    @arg location: A location.
    @type location: pyparsing.ParseResults
    @arg transcript: todo
    @type transcript: todo

    @return: Genomic location represented by given IVS location.
    @rtype: int
    """
    ivs_number = int(location.IVSNumber)

    if ivs_number < 1 or ivs_number > transcript.CM.numberOfIntrons():
        # Todo: Exception?
        return None

    if location.OffSgn == '+':
        return transcript.CM.getSpliceSite(ivs_number * 2 - 1) + \
               transcript.CM.orientation * int(location.Offset)
    else:
        return transcript.CM.getSpliceSite(ivs_number * 2) - \
               transcript.CM.orientation * int(location.Offset)
#_intronic_to_genomic


def _exonic_to_genomic(location, transcript) :
    """
    Get genomic range from EX location.

    @arg location: A location.
    @type location: pyparsing.ParseResults
    @arg transcript: todo
    @type transcript: todo

    @return: A tuple of:
        - first: Genomic start location represented by given EX location.
        - last:  Genomic end location represented by given EX location.
    @rtype: tuple(int, int)

    @todo: We probably want to treat this as a-?_b+?, so take the centers of
           flanking exons.
    @todo: Exceptions instead of returning None?
    """
    first_exon = int(location.EXNumberStart)
    if first_exon < 1 or first_exon > transcript.CM.numberOfExons():
        return None
    first = transcript.CM.getSpliceSite(first_exon * 2 - 2)

    if location.EXNumberStop:
        last_exon = int(location.EXNumberStop)
        if last_exon < 1 or last_exon > transcript.CM.numberOfExons():
            return None
        last = transcript.CM.getSpliceSite(last_exon * 2 - 1)
    else:
        last = transcript.CM.getSpliceSite(first_exon * 2 - 1)

    return first, last
#_exonic_to_genomic


def _genomic_to_genomic(first_location, last_location):
    """
    Get genomic range from parsed genomic location.

    @arg first_location: The start location (g.) of the variant.
    @type first_location: pyparsing.ParseResults
    @arg last_location: The start location (g.) of the variant.
    @type last_location: pyparsing.ParseResults

    @return: A tuple of:
        - first: Genomic start location represented by given location.
        - last:  Genomic end location represented by given location.
    @rtype: tuple(int, int)

    @todo: Exceptions.
    """
    if not first_location.Main.isdigit():
        # For ? in a position.
        return None, None

    if not last_location.Main.isdigit():
        # For ? in a position.
        return None, None

    first = int(first_location.Main)
    last = int(last_location.Main)

    return first, last


def _coding_to_genomic(first_location, last_location, transcript):
    """
    Get genomic range from parsed c. location.

    @arg first_location: The start location (c.) of the variant.
    @type first_location: pyparsing.ParseResults
    @arg last_location: The start location (c.) of the variant.
    @type last_location: pyparsing.ParseResults
    @arg transcript: todo
    @type transcript: todo

    @return: A tuple of:
        - first: Genomic start location represented by given location.
        - last:  Genomic end location represented by given location.
    @rtype: tuple(int, int)

    @todo: Exceptions.
    """
    if not first_location.Main.isdigit():
        # For ? in a position.
        return None, None

    if not last_location.Main.isdigit():
        # For ? in a position.
        return None, None

    first_main = transcript.CM.main2int(first_location.MainSgn + \
                                        first_location.Main)
    first_offset = _get_offset(first_location)
    first = transcript.CM.x2g(first_main, first_offset)

    last_main = transcript.CM.main2int(last_location.MainSgn + \
                                       last_location.Main)
    last_offset = _get_offset(last_location)
    last = transcript.CM.x2g(last_main, last_offset)

    # Todo: Exceptions.
    # todo: wat does check_intronic do and _is_intronic etc?
    if not _check_intronic_position(first_main, first_offset, transcript):
        return None, None
    if not _check_intronic_position(last_main, last_offset, transcript):
        return None, None

    if transcript.CM.orientation == -1:
        first, last = last, first

    return first, last
#_coding_to_genomic


def _process_raw_variant(mutator, variant, record, transcript, output):
    """
    Process a raw variant.

    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg variant: A parsed raw (simple, noncompound) variant.
    @type variant: pyparsing.ParseResults
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg transcript: A transcript object.
    @type transcript: Modules.GenRecord.Locus
    @arg output: The Output object.
    @type output: Modules.Output.Output

    @todo: Documentation.
    @todo: Exceptions.
    """
    if transcript and transcript.CM.orientation == -1:
        s1 = Bio.Seq.reverse_complement(variant.Arg1)
        s2 = Bio.Seq.reverse_complement(variant.Arg2)
    else:
        s1 = variant.Arg1
        s2 = variant.Arg2

    if variant.EXLoc:
        first, last = _exonic_to_genomic(variant.EXLoc, transcript)
        if not first:
            output.addMessage(__file__, 3, 'EPOS', 'Invalid EX position given.')
            return
        if last < first:
            # Todo: huh?
            first, last = last, first
    else:
        if variant.StartLoc:
            if variant.StartLoc.IVSLoc:
                if record.record.molType != 'g':
                    output.addMessage(__file__, 3, 'ENOINTRON', 'Intronic ' \
                        'position given for a non-genomic reference sequence.')
                    return
                first = _intronic_to_genomic(variant.StartLoc.IVSLoc, transcript)
                if not first:
                    output.addMessage(__file__, 3, 'EPOS',
                        'Invalid IVS position given.')
                    return
                last = first
                if variant.EndLoc and variant.EndLoc.IVSLoc:
                    # Todo: fixme
                    last = _intronic_to_genomic(variant.EndLoc.IVSLoc, transcript)
                    if last < first:
                        first, last = last, first
            else:
                if record.record.molType != 'g' and \
                       (_is_coding_intronic(variant.StartLoc) or
                        _is_coding_intronic(variant.EndLoc)):
                    output.addMessage(__file__, 3, 'ENOINTRON', 'Intronic ' \
                        'position given for a non-genomic reference sequence.')
                    return
                first_location = variant.StartLoc.PtLoc
                if variant.EndLoc:
                    last_location = variant.EndLoc.PtLoc
                else:
                    last_location = first_location
                if transcript:
                    first, last = _coding_to_genomic(first_location, last_location, transcript)
                else:
                    first, last = _genomic_to_genomic(first_location, last_location)
                if not first:
                    output.addMessage(__file__, 3, 'ESPLICE', 'Invalid intronic ' \
                        'position given.')
                    return
        else:
            # Not variant.StartLoc.
            output.addMessage(__file__, 4, 'EUNKNOWN', 'An unknown error occurred.')
            return

    if last < first:
        output.addMessage(__file__, 3, 'ERANGE', 'End position is smaller than ' \
                          'the begin position.')
        return

    if first < 1:
        output.addMessage(__file__, 4, 'ERANGE', 'Position %i is out of range.' %
                          first)
        return

    if last > len(mutator.orig):
        output.addMessage(__file__, 4, 'ERANGE', 'Position %s is out of range.' %
                          last)
        return

    if transcript and util.over_splice_site(first, last, transcript.CM.RNA):
        output.addMessage(__file__, 2, 'WOVERSPLICE',
                          'Variant hits one or more splice sites.')

    if variant.MutationType in ['del', 'dup', 'subst', 'delins']:
        __checkOptArg(mutator.orig, first, last, s1, output)

    # Substitution.
    if variant.MutationType == 'subst':
        apply_substitution(first, s1, s2, mutator, record, output)

    # Deletion or duplication.
    if variant.MutationType in ['del', 'dup']:
        apply_deletion_duplication(first, last, variant.MutationType, mutator,
                                   record, output)

    # Inversion.
    if variant.MutationType == 'inv':
        apply_inversion(first, last, mutator, record, output)

    # Insertion.
    if variant.MutationType == 'ins':
        apply_insertion(first, last, s1, mutator, record, output)

    # DelIns.
    if variant.MutationType == 'delins':
        apply_delins(first, last, s1, s2, mutator, record, output)
#_process_raw_variant


def _process_variant(mutator, description, record, output):
    """
    @arg mutator: A Mutator object.
    @type mutator: Modules.Mutator.Mutator
    @arg description: Parsed HGVS variant description.
    @type description: pyparsing.ParseResults
    @arg record: A GenRecord object.
    @type record: Modules.GenRecord.GenRecord
    @arg output: The Output object.
    @type output: Modules.Output.Output

    @todo: Documentation.
    @todo: Exceptions.
    """
    if not description.RawVar and not description.SingleAlleleVarSet:
        # Nothing to do. Exception?
        return

    if description.RefType == 'r':
        output.addMessage(__file__, 4, "ERNA", "Descriptions on RNA level " \
                          "are not supported.")
        return

    if description.RefType in ['c', 'n']:

        gene, transcript = None, None
        gene_symbol, transcript_id = output.getOutput('geneSymbol')[-1]

        if description.LrgAcc:
            # LRG case, pick the top gene.
            gene = record.record.geneList[0]
            if transcript_id:
                transcript = gene.findLocus(transcript_id)
                if not transcript:
                    output.addMessage(__file__, 4, "ENOTRANSCRIPT",
                        "Multiple transcripts found for gene %s. Please " \
                        "choose from: %s" %(gene.name,
                            ", ".join(gene.listLoci())))
            else:
                # No transcript id given.
                if len(gene.transcriptList) == 1:
                    # No transcript given, only 1 found, pick that.
                    transcript = gene.transcriptList[0]
                else:
                    output.addMessage(__file__, 4, "ENOTRANSCRIPT",
                        "No transcript given for gene %s. Please " \
                        "choose from: %s" %(gene.name,
                            ", ".join(gene.listLoci())))

        else:
            # Not an LRG, find our gene manually.
            genes = record.record.listGenes()
            transcript_id = transcript_id and "%.3i" % int(transcript_id)

            if gene_symbol in genes:
                # We found our gene.
                gene = record.record.findGene(gene_symbol)
            elif (len(genes) == 1) and not(gene_symbol):
                # No gene given and there is only one gene in the record.
                # Todo: message?
                gene = record.record.geneList[0]
            else:
                output.addMessage(__file__, 4, "EINVALIDGENE",
                    "Gene %s not found. Please choose from: %s" % (
                    gene_symbol, ", ".join(genes)))

            if gene:
                # Find transcript.
                transcripts = gene.listLoci()
                if transcript_id in transcripts:
                    # Found our transcript.
                    transcript = gene.findLocus(transcript_id)
                elif (len(transcripts) == 1) and not(transcript_id):
                    # No transcript given and there is only one transcript for
                    # this gene.
                    transcript = gene.transcriptList[0]
                else:
                    output.addMessage(__file__, 4, "ENOTRANSCRIPT",
                        "Multiple transcripts found for gene %s. Please " \
                        "choose from: %s" %(gene.name,
                        ", ".join(gene.listLoci())))

        # Add selected gene symbol to output
        output.addOutput('geneSymbol', (gene and gene.name or '',
                                        transcript and transcript.name or ''))

        # Return if no transcript is selected
        if not transcript:
            # Skip all BatchJobs with the same preColon data.
            output.addOutput('BatchFlags',
                             ('S2', output.getOutput('preColon')[-1]))
            # Explicit return in case of an error.
            return

    else:
        # Not description.RefType in ['c', 'n'].
        transcript = None

    if transcript and not transcript.transcribe:
        return

    if description.SingleAlleleVarSet:
        for var in description.SingleAlleleVarSet:
            _process_raw_variant(mutator, var.RawVar, record, transcript,
                                 output)
    else:
        _process_raw_variant(mutator, description.RawVar, record, transcript,
                             output)

    if not transcript:
        # Genomic given or error with transcript.
        return

    if not record.record.geneList:
        # EST
        return

    # Add exon table to output.
    for i in range(0, transcript.CM.numberOfExons() * 2, 2):
        acceptor = transcript.CM.getSpliceSite(i)
        donor = transcript.CM.getSpliceSite(i + 1)
        output.addOutput('exonInfo', [acceptor, donor,
                                      transcript.CM.g2c(acceptor),
                                      transcript.CM.g2c(donor)])

    # Add CDS info to output.
    cds_stop = transcript.CM.info()[2]
    output.addOutput('cdsStart_g', transcript.CM.x2g(1, 0))
    output.addOutput('cdsStart_c', 1)
    output.addOutput('cdsStop_g', transcript.CM.x2g(cds_stop, 0))
    output.addOutput('cdsStop_c', cds_stop)

    # Add transcript info to output.
    if transcript.transcribe:
        output.addOutput('myTranscriptDescription', transcript.description)
        output.addOutput('origMRNA',
            str(util.splice(mutator.orig, transcript.mRNA.positionList)))
        output.addOutput('mutatedMRNA',
            str(util.splice(mutator.mutated,
                        mutator.newSplice(transcript.mRNA.positionList))))

    # Add protein prediction to output.
    if transcript.translate:
        cds_original = Seq(str(util.splice(mutator.orig, transcript.CDS.positionList)),
                           IUPAC.unambiguous_dna)
        cds_variant = Seq(str(util.__nsplice(mutator.mutated,
                                        mutator.newSplice(transcript.mRNA.positionList),
                                        mutator.newSplice(transcript.CDS.location),
                                        transcript.CM.orientation)),
                          IUPAC.unambiguous_dna)

        #output.addOutput('origCDS', cds_original)

        if transcript.CM.orientation == -1:
            cds_original = Bio.Seq.reverse_complement(cds_original)
            cds_variant = Bio.Seq.reverse_complement(cds_variant)

        if '*' in cds_original.translate(table=transcript.txTable)[:-1]:
            output.addMessage(__file__, 3, 'ESTOP',
                              'In frame stop codon found.')
            return

        protein_original = cds_original.translate(table=transcript.txTable,
                                                  to_stop=True)
        protein_variant = cds_variant.translate(table=transcript.txTable,
                                                to_stop=True)

        # Note: addOutput('origCDS', ...) was first before the possible
        #       reverse complement operation above.
        output.addOutput('origCDS', cds_original)
        output.addOutput("newCDS", cds_variant[:(len(str(protein_variant)) + 1) * 3])

        output.addOutput('oldprotein', protein_original + '*')

        # Todo: Don't generate the fancy HTML protein views here, do this in
        # wsgi.py.
        # I think it would also be nice to include the mutated list of splice
        # sites.
        if not protein_variant or protein_variant[0] != 'M':
            # Todo: Protein differences are not color-coded,
            # use something like below in protein_description().
            util.print_protein_html(protein_original + '*', 0, 0, output,
                                    'oldProteinFancy')
            if str(cds_variant[0:3]) in \
                   Bio.Data.CodonTable.unambiguous_dna_by_id \
                   [transcript.txTable].start_codons:
                output.addOutput('newprotein', '?')
                util.print_protein_html('?', 0, 0, output, 'newProteinFancy')
                output.addOutput('altStart', str(cds_variant[0:3]))
                if str(protein_original[1:]) != str(protein_variant[1:]):
                    output.addOutput('altProtein',
                                     'M' + protein_variant[1:] + '*')
                    util.print_protein_html('M' + protein_variant[1:] + '*', 0, 0,
                                            output, 'altProteinFancy')
            else :
                output.addOutput('newprotein', '?')
                util.print_protein_html('?', 0, 0, output, 'newProteinFancy')

        else:
            cds_length = util.cds_length(
                mutator.newSplice(transcript.CDS.positionList))
            descr, first, last_original, last_variant = \
                   util.protein_description(cds_length, protein_original,
                                            protein_variant)

            # This is never used.
            output.addOutput('myProteinDescription', descr)

            util.print_protein_html(protein_original + '*', first, last_original,
                                    output, 'oldProteinFancy')
            if str(protein_original) != str(protein_variant):
                output.addOutput('newprotein', protein_variant + '*')
                util.print_protein_html(protein_variant + '*', first, last_variant,
                                        output, 'newProteinFancy')
#_process_variant


def check_variant(description, config, output):
    """
    Check the variant described by {description} according to the HGVS variant
    nomenclature and populate the {output} object with various information
    about the variant and its reference sequence.

    @arg description: Variant description in HGVS notation.
    @type description: string
    @arg config: A configuration object.
    @type config: Modules.Config.Config
    @arg output: An output object.
    @type output: Modules.Output.Output

    @return: A GenRecord object.
    @rtype: Modules.GenRecord.GenRecord

    @todo: documentation
    """
    output.addOutput('inputvariant', description)

    parser = Parser.Nomenclatureparser(output)
    parsed_description = parser.parse(description)

    if not parsed_description:
        # Parsing went wrong.
        return None

    if parsed_description.Version:
        record_id = parsed_description.RefSeqAcc + '.' + parsed_description.Version
    else:
        record_id = parsed_description.RefSeqAcc

    gene_symbol = transcript_id = ''

    database = Db.Cache(config.Db)
    if parsed_description.LrgAcc:
        filetype = 'LRG'
        record_id = parsed_description.LrgAcc
        transcript_id = parsed_description.LRGTranscriptID
        retriever = Retriever.LRGRetriever(config.Retriever, output, database)
    else:
        if parsed_description.Gene:
            gene_symbol = parsed_description.Gene.GeneSymbol or ''
            transcript_id = parsed_description.Gene.TransVar or ''
            if parsed_description.Gene.ProtIso:
                output.addMessage(__file__, 4, 'EPROT', 'Indexing by ' \
                                  'protein isoform is not supported.')
        retriever = Retriever.GenBankRetriever(config.Retriever, output,
                                               database)
        filetype = 'GB'

    # Add recordType to output for output formatting.
    output.addOutput('recordType', filetype)

    output.addOutput('reference', record_id)

    # Note: geneSymbol[0] is used as a filter for batch runs.
    output.addOutput('geneSymbol', (gene_symbol, transcript_id))

    # Note: preColon is used to filter out Batch entries that will result in
    # identical errors.
    output.addOutput('preColon', description.split(':')[0])
    output.addOutput('variant', description.split(':')[-1])

    retrieved_record = retriever.loadrecord(record_id)

    if not retrieved_record:
        return None

    record = GenRecord.GenRecord(output, config.GenRecord)
    record.record = retrieved_record
    record.checkRecord()

    mutator = Mutator.Mutator(record.record.seq, config.Mutator, output)

    # Note: The GenRecord instance is carrying the sequence in .record.seq.
    #       So is the Mutator instance in .mutator.orig.

    _process_variant(mutator, parsed_description, record, output)

    # Protein.
    for gene in record.record.geneList:
        for transcript in gene.transcriptList:
            if not ';' in transcript.description \
                   and transcript.CDS and transcript.translate:
                cds_original = Seq(str(util.splice(mutator.orig, transcript.CDS.positionList)),
                                   IUPAC.unambiguous_dna)
                cds_variant = Seq(str(util.__nsplice(mutator.mutated,
                                                mutator.newSplice(transcript.mRNA.positionList),
                                                mutator.newSplice(transcript.CDS.location),
                                                transcript.CM.orientation)),
                                  IUPAC.unambiguous_dna)
                if transcript.CM.orientation == -1:
                    cds_original = Bio.Seq.reverse_complement(cds_original)
                    cds_variant = Bio.Seq.reverse_complement(cds_variant)

                #if '*' in cds_original.translate()[:-1]:
                #    output.addMessage(__file__, 3, "ESTOP",
                #                      "In frame stop codon found.")
                #    return
                ##if

                if not len(cds_original) % 3:
                    try:
                        # FIXME this is a bit of a rancid fix.
                        protein_original = cds_original.translate(table=transcript.txTable,
                                                                  cds=True,
                                                                  to_stop=True)
                    except Bio.Data.CodonTable.TranslationError:
                        output.addMessage(__file__, 4, "ETRANS", "Original " \
                                          "CDS could not be translated.")
                        return record
                    protein_variant = cds_variant.translate(table=transcript.txTable,
                                                            to_stop=True)
                    cds_length = util.cds_length(mutator.newSplice(transcript.CDS.positionList))
                    transcript.proteinDescription = util.protein_description(
                        cds_length, protein_original, protein_variant)[0]
                else:
                    output.addMessage(__file__, 2, "ECDS", "CDS length is " \
                        "not a multiple of three in gene %s, transcript " \
                        "variant %s." % (gene.name, transcript.name))
                    transcript.proteinDescription = '?'

    reference = output.getOutput('reference')[-1]
    if ';' in record.record.description:
        generated_description = '[' + record.record.description + ']'
    else:
        generated_description = record.record.description

    output.addOutput('genomicDescription', '%s:%c.%s' % \
                     (reference, record.record.molType, generated_description))
    output.addOutput('gDescription', '%c.%s' % \
                     (record.record.molType, generated_description))
    output.addOutput('molType', record.record.molType)

    if record.record.chromOffset:
        if ';' in record.record.chromDescription:
            chromosomal_description = '[' + record.record.chromDescription + ']'
        else:
            chromosomal_description = record.record.chromDescription
        output.addOutput('genomicChromDescription', '%s:%c.%s' % \
                         (record.record.recordId,
                          record.record.molType, chromosomal_description))

    # Now we add variant descriptions for all transcripts, including protein
    # level descriptions. In the same loop, we also create the legend.

    for gene in record.record.geneList:
        for transcript in sorted(gene.transcriptList, key=attrgetter('name')):

            # Note: I don't think genomic_id is ever used, because it is
            # always ''.
            coding_description = ''
            protein_description = ''
            full_description = ''
            full_protein_description = ''
            genomic_id = coding_id = protein_id = ''

            if ';' in transcript.description:
                generated_description = '[' + transcript.description + ']'
            else:
                generated_description = transcript.description

            if record.record._sourcetype == 'LRG':
                if transcript.name:
                    full_description = '%st%s:%c.%s' % \
                                       (reference, transcript.name,
                                        transcript.molType,
                                        generated_description)
                    output.addOutput('descriptions', full_description)
                else:
                    output.addOutput('descriptions', gene.name)
            else:
                full_description = '%s(%s_v%s):%c.%s' % \
                                   (reference, gene.name, transcript.name,
                                    transcript.molType,
                                    generated_description)
                output.addOutput('descriptions', full_description)

            if transcript.molType == 'c':
                coding_description = 'c.%s' % generated_description
                protein_description = transcript.proteinDescription
                if record.record._sourcetype == 'LRG':
                    full_protein_description = '%sp%s:%s' % \
                                               (reference, transcript.name,
                                                protein_description)
                else:
                    full_protein_description = '%s(%s_i%s):%s' % \
                                               (reference, gene.name,
                                                transcript.name,
                                                protein_description)

                coding_id, protein_id = \
                           transcript.transcriptID, transcript.proteinID
                output.addOutput('protDescriptions',
                                 full_protein_description)

            # The 'NewDescriptions' field is currently not used.
            output.addOutput('NewDescriptions',
                             (gene.name, transcript.name,
                              transcript.molType, coding_description,
                              protein_description, genomic_id, coding_id,
                              protein_id, full_description,
                              full_protein_description))

            # Now add to the legend, but exclude nameless transcripts.
            if not transcript.name:
                continue

            output.addOutput('legends',
                             ['%s_v%s' % (gene.name, transcript.name),
                              transcript.transcriptID, transcript.locusTag,
                              transcript.transcriptProduct,
                              transcript.linkMethod])

            if transcript.translate:
                output.addOutput('legends',
                                 ['%s_i%s' % (gene.name, transcript.name),
                                  transcript.proteinID, transcript.locusTag,
                                  transcript.proteinProduct,
                                  transcript.linkMethod])

    # Add GeneSymbol and Transcript Var to the Output object for batch.
    if parsed_description.Gene:
        output.addOutput('geneOfInterest',
                         dict(parsed_description.Gene.items()))
    else:
        output.addOutput('geneOfInterest', dict())

    _add_batch_output(output)

    output.addOutput('original', str(mutator.orig))
    output.addOutput('mutated', str(mutator.mutated))

    return record
#check_variant
