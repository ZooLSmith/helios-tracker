@echo off
rem Runs the mod in the game as a .sdkmod (built from the repo) instead of the dev junction. "use_sdkmod tps": the Pre-Sequel, "use_sdkmod bl1": Borderlands 1.
python "%~dp0build_sdkmod.py" install %*
pause
