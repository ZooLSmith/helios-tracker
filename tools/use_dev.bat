@echo off
rem Back to the dev junction (edits live in game): the .sdkmod removed. "use_dev tps": the Pre-Sequel, "use_dev bl1": Borderlands 1.
python "%~dp0build_sdkmod.py" dev %*
pause
