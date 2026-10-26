"""ASCII entry point used by Windows batch launchers."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).parent / '\u521d\u59cb\u5316\u6f14\u793a\u8d26\u6237.py'), run_name='__main__')
