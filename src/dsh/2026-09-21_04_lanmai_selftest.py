import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from lanmai.pipeline import selftest
selftest()
print('lanmai CLI 自检通过')
