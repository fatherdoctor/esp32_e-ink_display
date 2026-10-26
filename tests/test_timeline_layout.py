"""Exercise the actual native placement algorithm on hosts with a C++ compiler."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class TimelineLayoutTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'Native C++ layout test runs on Linux CI')
    def test_real_layout_preserves_overlap_headers_and_bounds(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'timeline-layout-test'
            subprocess.run(['g++','-std=c++11','-Wall','-Wextra','-Werror',
                            '-I',str(root),str(root/'tests/timeline_layout_test.cpp'),
                            '-o',str(executable)],check=True,capture_output=True,text=True)
            subprocess.run([str(executable)],check=True,capture_output=True,text=True)
