import os
import sys

if sys.platform == "darwin":
    os.environ["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib:" + os.environ.get("DYLD_LIBRARY_PATH", "")


from src.samples.check_dualsense_controls import check_controls


if __name__ == '__main__':
    check_controls()
