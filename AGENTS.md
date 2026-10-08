# Local build and delivery

- The user's target instance is `/Users/crococrystal/Library/Application Support/PrismLauncher/instances/VOID PROTOCOL 1.21.1`.
- After a successful build, immediately install the resulting IC2 JAR in that instance's `minecraft/mods`, replacing previous IC2 builds. Keep exactly one enabled IC2 JAR.
- Back up replaced files outside `minecraft/mods`. Also deploy any scripts, resources, or dependency mods changed as part of the task to this instance.
- Launch this instance through PrismLauncher after installation. If its Minecraft process is already running, avoid a duplicate launch and explain that a full restart is needed to load new Java code. Do not kill the user's running game without an explicit request.
- Verify the installed JAR matches the successful build and check the instance's startup log for the expected mod version and script errors.
- Downloads may contain a convenience copy, but delivery there alone does not complete the task.
- Use `python3 scripts/build-and-launch-void.py` for normal build/install/launch. Its `--install-only` option installs an already checked build.
- Preserve user edits to the instance's KubeJS configuration unless the task explicitly changes them; back up conflicting files before applying an authorized update.
- Creative-tab grouping and design belong in the modpack's ModernTabs/KubeJS configuration; avoid custom creative-screen rendering in IC2R.
