import os
import sys
import zipfile
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))

APK_DIR = os.path.join(ROOT_DIR, 'apk')
BIN_DIR = os.path.join(ROOT_DIR, 'binaries')

BASE_APK = os.path.join(APK_DIR, 'base_original.apk')
PATCHED_SO = os.path.join(BIN_DIR, 'libuaf_emulated.so')
KEYSTORE = os.path.join(APK_DIR, 'offline_testkey.jks')

UNALIGNED_APK = os.path.join(APK_DIR, 'RaymanAdventures_unaligned.apk')
ALIGNED_APK = os.path.join(APK_DIR, 'RaymanAdventures_aligned.apk')
FINAL_APK = os.path.join(ROOT_DIR, 'RaymanAdventures_Offline.apk')

# Common SDK / JDK tools paths on Windows
JAVA_BIN = r"C:\Program Files\Android\Android Studio\jbr\bin\java.exe"
KEYTOOL_BIN = r"C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
BUILD_TOOLS_DIR = os.environ.get("ANDROID_BUILD_TOOLS") or os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "build-tools", "34.0.0")
ZIPALIGN_BIN = os.path.join(BUILD_TOOLS_DIR, "zipalign.exe")
APKSIGNER_BAT = os.path.join(BUILD_TOOLS_DIR, "apksigner.bat")

print("--- REPACKAGE RAYMAN ADVENTURES OFFLINE APK ---")

if not os.path.exists(BASE_APK):
    print(f"Error: Base APK not found at {BASE_APK}")
    sys.exit(1)

if not os.path.exists(PATCHED_SO):
    print(f"Error: Patched libuaf.so not found at {PATCHED_SO}")
    print("Please run scripts/build_libuaf_offline.py first!")
    sys.exit(1)

sys.path.insert(0, BASE_DIR)
from patch_manifest import patch_manifest

# Game data (OBB) embedded in the APK by default: one file to install. --no-obb builds the light
# APK that needs the separate main.2086.com.ubisoft.raymanadventures.obb in Android/obb/.
OBB_FILE = os.path.join(APK_DIR, 'main.2086.com.ubisoft.raymanadventures.obb')
EMBED_OBB = "--no-obb" not in sys.argv
if EMBED_OBB and not os.path.exists(OBB_FILE):
    print(f"Error: OBB not found at {OBB_FILE} (or build with --no-obb)")
    sys.exit(1)

SERVER_DEX = os.path.join(ROOT_DIR, 'offline_server', 'build', 'classes.dex')
SERVER_ASSETS = os.path.join(ROOT_DIR, 'offline_server', 'assets')
if not os.path.exists(SERVER_DEX):
    print(f"Error: embedded server dex not found at {SERVER_DEX}")
    print("Please run scripts/build_offline_server.py first!")
    sys.exit(1)

print("1. Injecting patched libuaf.so, offline server and manifest into base APK...")
with zipfile.ZipFile(BASE_APK, 'r') as zin:
    names = set(zin.namelist())
    with zipfile.ZipFile(UNALIGNED_APK, 'w') as zout:
        for item in zin.infolist():
            if item.filename.startswith("META-INF/"):
                continue
            if item.filename == "lib/arm64-v8a/libuaf.so":
                continue
            data = zin.read(item.filename)
            if item.filename == "AndroidManifest.xml":
                data = patch_manifest(data)
                print("  AndroidManifest.xml: OfflineServerProvider declared")
            if item.filename == "res/raw/game.properties" and EMBED_OBB:
                # Ubisoft's own "OBB in the APK" mode: InstallActivity.launchGameInstaller copies
                # every assets/*.obb into getObbDir() when the OBB is missing, then starts the game.
                old = b"package.main.Location = SERVER"
                assert old in data, "game.properties: package.main.Location not found"
                data = data.replace(old, b"package.main.Location = ASSET")
                print("  res/raw/game.properties: package.main.Location = ASSET")
            zout.writestr(item, data)

        if EMBED_OBB:
            # Stored (not deflated): the OBB is a zip of already packed bundles, and a stored
            # asset is copied at disk speed on the first launch.
            zout.write(OBB_FILE, "assets/" + os.path.basename(OBB_FILE), compress_type=zipfile.ZIP_STORED)
            print(f"  assets/{os.path.basename(OBB_FILE)}: game data embedded ({os.path.getsize(OBB_FILE)} bytes)")

        orig_info = zin.getinfo("lib/arm64-v8a/libuaf.so")
        compress_type = orig_info.compress_type

        with open(PATCHED_SO, 'rb') as f:
            so_data = f.read()

        so_info = zipfile.ZipInfo("lib/arm64-v8a/libuaf.so")
        so_info.compress_type = compress_type
        zout.writestr(so_info, so_data)

        # Embedded server code goes into the next free classesN.dex (native multidex, API 21+;
        # androidx MultiDexApplication handles older devices).
        n = 2
        while f"classes{n}.dex" in names:
            n += 1
        dex_info = zipfile.ZipInfo(f"classes{n}.dex")
        dex_info.compress_type = zipfile.ZIP_DEFLATED
        with open(SERVER_DEX, 'rb') as f:
            zout.writestr(dex_info, f.read())
        print(f"  classes{n}.dex: embedded offline server")

        for root, _, files in os.walk(SERVER_ASSETS):
            for fn in files:
                path = os.path.join(root, fn)
                arc = "assets/" + os.path.relpath(path, SERVER_ASSETS).replace(os.sep, "/")
                info = zipfile.ZipInfo(arc)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(path, 'rb') as f:
                    zout.writestr(info, f.read())
                print(f"  {arc}")

print(f"  Created unaligned APK ({os.path.getsize(UNALIGNED_APK)} bytes).")

print("2. Aligning APK (zipalign 4-byte)...")
if os.path.exists(ALIGNED_APK):
    os.remove(ALIGNED_APK)

env = os.environ.copy()
if os.path.exists(os.path.dirname(JAVA_BIN)):
    env["JAVA_HOME"] = os.path.abspath(os.path.join(os.path.dirname(JAVA_BIN), ".."))
    env["PATH"] = os.path.dirname(JAVA_BIN) + ";" + env.get("PATH", "")

if os.path.exists(ZIPALIGN_BIN):
    subprocess.run([ZIPALIGN_BIN, "-p", "-f", "4", UNALIGNED_APK, ALIGNED_APK], check=True, env=env)
else:
    print("Warning: zipalign not found in default path, using unaligned APK as fallback.")
    shutil.copyfile(UNALIGNED_APK, ALIGNED_APK)

print("3. Checking or creating signing key...")
if not os.path.exists(KEYSTORE) and os.path.exists(KEYTOOL_BIN):
    cmd = [
        KEYTOOL_BIN, "-genkeypair", "-v",
        "-keystore", KEYSTORE,
        "-alias", "offline_key",
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", "android",
        "-keypass", "android",
        "-dname", "CN=RaymanOffline, OU=Gaming, O=Preservation, C=FR"
    ]
    subprocess.run(cmd, check=True, env=env)

print("4. Signing APK with apksigner...")
if os.path.exists(FINAL_APK):
    os.remove(FINAL_APK)

shutil.copyfile(ALIGNED_APK, FINAL_APK)

if os.path.exists(APKSIGNER_BAT) and os.path.exists(KEYSTORE):
    cmd = [
        APKSIGNER_BAT, "sign",
        "--ks", KEYSTORE,
        "--ks-key-alias", "offline_key",
        "--ks-pass", "pass:android",
        "--key-pass", "pass:android",
        "--v1-signing-enabled", "true",
        "--v2-signing-enabled", "true",
        "--v3-signing-enabled", "true",
        FINAL_APK
    ]
    subprocess.run(cmd, env=env, check=True)
    print("  APK signed successfully.")
    
    # Verify
    cmd_verify = [APKSIGNER_BAT, "verify", "-v", FINAL_APK]
    res_v = subprocess.run(cmd_verify, env=env, capture_output=True, text=True)
    print("  Verification:", "SUCCESS" if res_v.returncode == 0 else "WARNING")
else:
    print("Warning: apksigner not found, outputting unsigned APK.")

print(f"\n[DONE] Standalone Offline APK is ready at:\n  {FINAL_APK}")
print(f"Size: {os.path.getsize(FINAL_APK) / (1024*1024):.2f} MB")
