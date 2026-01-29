import pytest
import json
import sys
import os

# Ad-hoc path insertion to allow importing 'core' when running pytest from root or inside tests/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from unittest.mock import patch, MagicMock
from core.viofo_extractor import ViofoMetadataExtractor

@pytest.fixture
def mock_exiftool_output():
    return json.dumps([
        {
            "SourceFile": "test.mp4",
            "MIMEType": "video/mp4",
            "ImageWidth": 3840,
            "ImageHeight": 2160
        },
        {
            # Case 1: Single records
            "GPSDateTime": "2024:03:23 12:35:19Z",
            "GPSLatitude": 48.1173,
            "GPSLongitude": 11.51666,
            "GPSSpeed": 41.48
        },
        {
             # Case 2: Arrays (what we just added support for)
             "GPSLatitude": [10.0, 10.1],
             "GPSLongitude": [20.0, 20.1],
             "GPSDateTime": ["2024:01:01 00:00:01Z", "2024:01:01 00:00:02Z"],
             "GPSSpeed": [10, 15]
        }
    ])

@patch('subprocess.run')
def test_extraction(mock_subprocess, mock_exiftool_output):
    # Setup mock
    mock_result = MagicMock()
    mock_result.stdout = mock_exiftool_output
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result

    extractor = ViofoMetadataExtractor("dummy.mp4")
    data = extractor.extract_metadata()
    
    # Verify subprocess was called correctly
    mock_subprocess.assert_called_once()
    args = mock_subprocess.call_args[0][0]
    assert args[0] == 'exiftool'
    assert '-ee3' in args
    
    # Verify parsing
    # We expect 1 record from the first dict, and 2 records from the array dict -> Total 3
    assert len(data) == 3, "Should find 3 GPS records"
    
    # Check the single record
    record0 = data[0]
    assert record0['timestamp'] == '2024:03:23 12:35:19Z'
    
    # Check the flattened records
    record1 = data[1]
    assert record1['latitude'] == 10.0
    assert record1['timestamp'] == '2024:01:01 00:00:01Z'
    
    record2 = data[2]
    assert record2['latitude'] == 10.1
    assert record2['speed_kmh'] == 15
