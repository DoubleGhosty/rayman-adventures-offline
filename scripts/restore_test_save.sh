#!/bin/sh
# Restores the WSA test save (backups/*.tgz, Aventure 17) on a rooted device/emulator.
# Usage: sh scripts/restore_test_save.sh
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
P=com.ubisoft.raymanadventures
adb shell am force-stop $P
adb shell "mkdir -p /sdcard/rayman_backup"
adb push backups/data.tgz /sdcard/rayman_backup/data.tgz >/dev/null
adb push backups/extdata.tgz /sdcard/rayman_backup/extdata.tgz >/dev/null
adb shell "su -c 'U=\$(stat -c %u /data/data/$P); rm -rf /data/data/$P/*; tar xzf /sdcard/rayman_backup/data.tgz -C /data/data; chown -R \$U:\$U /data/data/$P; restorecon -R /data/data/$P; rm -rf /data/media/0/Android/data/$P; tar xzf /sdcard/rayman_backup/extdata.tgz -C /sdcard/Android/data; chown -R \$U /data/media/0/Android/data/$P; echo restored uid=\$U'"
