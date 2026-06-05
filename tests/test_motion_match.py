import pytest
from backend.video_editor.motion_match import extract_and_normalize_pose, cosine_similarity, find_match_cut

def generate_mock_landmarks(seed=42):
    """Generates 33 mock landmarks for testing."""
    import random
    random.seed(seed)
    return [{'x': random.uniform(0, 1), 'y': random.uniform(0, 1), 'z': random.uniform(0, 1)} for _ in range(33)]

def test_fallback_no_landmarks():
    """Codex: Test safe fallback when landmarks are missing."""
    v = extract_and_normalize_pose([])
    assert len(v) == 99
    assert sum(v) == 0.0

def test_cosine_similarity_identical():
    """Codex: Test similarity logic."""
    v1 = [1.0] * 99
    v2 = [1.0] * 99
    sim = cosine_similarity(v1, v2)
    assert round(sim, 2) == 1.00

def test_find_match_cut():
    """Codex: Test the 80% threshold matching logic."""
    # Clip A target frame
    clip_a = [{'timestamp_s': 1.0, 'landmarks': generate_mock_landmarks(1)}]
    
    # Clip B sequence
    clip_b = [
        {'timestamp_s': 2.0, 'landmarks': generate_mock_landmarks(2)}, # Random pose
        {'timestamp_s': 2.1, 'landmarks': generate_mock_landmarks(3)}, # Random pose
        {'timestamp_s': 2.2, 'landmarks': generate_mock_landmarks(1)}, # EXACT same pose as Clip A!
        {'timestamp_s': 2.3, 'landmarks': generate_mock_landmarks(4)}
    ]
    
    result = find_match_cut(clip_a, clip_b)
    
    # The algorithm should find the exact match at 2.2s
    assert result['match_found'] is True
    assert result['cut_time_b'] == 2.2
    assert result['similarity'] > 0.99
