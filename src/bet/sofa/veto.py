from typing import List

from bet.sofa.contracts import Veto, SheetRow

def match_vetoes(row: SheetRow, vetoes: List[Veto]) -> List[Veto]:
    matches = []
    for veto in vetoes:
        if veto.sofascore_event_id != row.sofascore_event_id:
            continue
        if veto.market is not None and veto.market != row.market:
            continue
        if veto.subject is not None and veto.subject != row.subject:
            continue
        if veto.line is not None and veto.line != row.line:
            continue
        if veto.direction is not None and veto.direction != row.direction:
            continue
        matches.append(veto)
    return matches

def find_unmatched_vetoes(sheet_rows: List[SheetRow], vetoes: List[Veto]) -> List[Veto]:
    unmatched = []
    for veto in vetoes:
        matched = False
        for row in sheet_rows:
            if veto.sofascore_event_id != row.sofascore_event_id:
                continue
            if veto.market is not None and veto.market != row.market:
                continue
            if veto.subject is not None and veto.subject != row.subject:
                continue
            if veto.line is not None and veto.line != row.line:
                continue
            if veto.direction is not None and veto.direction != row.direction:
                continue
            matched = True
            break
        if not matched:
            unmatched.append(veto)
    return unmatched
