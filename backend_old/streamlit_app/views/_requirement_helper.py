# Small helper utilities for the requirement analyzer view to keep manager.py edits minimal

def _epic_key(epic_idx):
    return f"req_epic_{epic_idx}"


def _story_key(epic_idx, story_idx):
    return f"req_epic_{epic_idx}_story_{story_idx}"
