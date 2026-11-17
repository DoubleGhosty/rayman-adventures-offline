"""Compiles offline_server/src (embedded mock server) into offline_server/build/classes.dex
and generates the self-signed TLS keystore offline_server/assets/offline/server.p12 if missing.

The store catalogue (mock_data/store_v2_fixed.json) is copied to
offline_server/assets/offline/store_v2.json; repackage_apk.py injects the whole
offline_server/assets/ tree into the APK's assets/.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
SRV_DIR = os.path.join(ROOT_DIR, "offline_server")
SRC_DIR = os.path.join(SRV_DIR, "src")
BUILD_DIR = os.path.join(SRV_DIR, "build")
ASSETS_DIR = os.path.join(SRV_DIR, "assets", "offline")

JDK_BIN = r"C:\Program Files\Android\Android Studio\jbr\bin"
SDK = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
BUILD_TOOLS = os.path.join(SDK, "build-tools", "34.0.0")
ANDROID_JAR = os.path.join(SDK, "platforms", "android-34", "android.jar")

KEYSTORE = os.path.join(ASSETS_DIR, "server.p12")
KEYSTORE_PASS = "android"  # must match OfflineServer.KEYSTORE_PASS


def short(path):
    """8.3 short path: d8 crashes on non-ASCII paths (e.g. a user folder with accents)."""
    if os.name != "nt":
        return path
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)
    return buf.value if n else path


def run(cmd, **kw):
    print("  $", " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    subprocess.run(cmd, check=True, **kw)


# ITEM_TYPE attribute of each catalogue item, as tested by online::dynamicStore::isItemOfType
# (the type names are the ones the client asks for; the captured catalogue had lost them).
ITEM_TYPES = {
    3594: "gems",
    3604: "ELIXIR_UNCOMMON",            # elixir common -> uncommon ("silver egg")
    3606: "ELIXIR_ANYTHING",            # elixir anything -> rare ("golden egg")
    3608: "elixir_skip_time_50",        # speed-up
    3610: "elixir_force_new_creature",
    3612: "luckyticket",
    3614: "golden_lucky_ticket",
    3616: "Food",
    3692: "Beatbox_Saving_Slot",
    4178: "easteregg",
    4180: "chocolate_lucky_ticket",
    4182: "chocoegg",
    4196: "timeSavingPack",
    4391: "Magnifying_Glass",
    4647: "challenge_token",
    4669: "challenge_lucky_ticket",
    5931: "Food",                       # FoodRefill
    5957: "perkPack",
}
COSTUME_TYPES = {"Costume_Barbara": "costume_barbara", "Costume_Globox": "costume_globox",
                 "Costume_Rayman": "costume_rayman", "Costume_Teensy": "costume_teensy"}


def item_type(item):
    t = ITEM_TYPES.get(int(item["item_id"]))
    if t:
        return t
    for prefix, name in COSTUME_TYPES.items():
        if item.get("title", "").startswith(prefix):
            return name
    return None


def write_store_catalog(src, dst):
    """Copies the msdk store catalogue, fixed for the Mobile SDK parser in libuaf.

    - Items get their "params": [{"key": "ITEM_TYPE", "value": ...}] attributes back
      (dynamicStore::isItemOfType decides from them which inventory stock an item is: gems,
      elixir of a given type, lucky ticket...). Without them every elixir became an easter-egg
      stock and could never be credited.
    - The parser (0x19f8f20 secondary trades, 0x19f99b8 primary trades) reads "item_id" and
      "amount" of the *received* items with atoi() on the JSON string value: a JSON number has
      no string value, so every pack had a quantity of 0. The "for" (price) side accepts both.
    """
    with open(src, encoding="utf-8") as f:
        store = json.load(f)
    typed = 0
    for item in store.get("items", []):
        t = item_type(item)
        if t:
            item["params"] = [{"key": "ITEM_TYPE", "value": t}]
            typed += 1
    print(f"  store catalogue: ITEM_TYPE set on {typed}/{len(store.get('items', []))} items")
    n = 0
    for section in ("primaryStore", "secondaryStore"):
        for trade in store.get(section, []):
            for item in trade.get("get", {}).get("items", []):
                item["item_id"] = str(item["item_id"])
                item["amount"] = str(item["amount"])
                n += 1
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  store catalogue: {n} received-item quantities written as strings")


def main():
    env = os.environ.copy()
    env["JAVA_HOME"] = os.path.dirname(JDK_BIN)
    env["PATH"] = JDK_BIN + os.pathsep + env.get("PATH", "")

    os.makedirs(ASSETS_DIR, exist_ok=True)
    print("1. Assets")
    write_store_catalog(os.path.join(ROOT_DIR, "mock_data", "store_v2_fixed.json"),
                        os.path.join(ASSETS_DIR, "store_v2.json"))
    # Ubisoft's lucky ticket weight tables (dumped from the game by tools/re/dump_ticket_weights.py)
    shutil.copyfile(os.path.join(ROOT_DIR, "mock_data", "ticket_weights.json"),
                    os.path.join(ASSETS_DIR, "ticket_weights.json"))
    if not os.path.exists(KEYSTORE):
        # legacy PKCS12 (3DES + HmacSHA1): Android BouncyCastle cannot read the PBES2 default
        run([os.path.join(JDK_BIN, "keytool.exe"), "-J-Dkeystore.pkcs12.legacy", "-genkeypair", "-storetype", "PKCS12",
             "-keystore", KEYSTORE, "-storepass", KEYSTORE_PASS, "-keypass", KEYSTORE_PASS,
             "-alias", "ubi", "-keyalg", "RSA", "-keysize", "2048", "-validity", "36500",
             "-dname", "CN=*.ubi.com, O=Rayman Offline, C=FR",
             "-ext", "SAN=dns:*.ubi.com,dns:ubi.com,dns:localhost,ip:127.0.0.1"], env=env)

    print("2. javac")
    classes_dir = os.path.join(BUILD_DIR, "classes")
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    os.makedirs(classes_dir, exist_ok=True)
    sources = glob.glob(os.path.join(SRC_DIR, "**", "*.java"), recursive=True)
    run([os.path.join(JDK_BIN, "javac.exe"), "--release", "8", "-Xlint:-options",
         "-cp", ANDROID_JAR, "-d", classes_dir] + sources, env=env)

    print("3. d8")
    jar = os.path.join(BUILD_DIR, "classes.jar")
    run([os.path.join(JDK_BIN, "jar.exe"), "cf", jar, "-C", classes_dir, "."], env=env)
    run([os.path.join(BUILD_TOOLS, "d8.bat"), "--release", "--min-api", "19",
         "--lib", short(ANDROID_JAR), "--output", short(BUILD_DIR), short(jar)], env=env)

    dex = os.path.join(BUILD_DIR, "classes.dex")
    if not os.path.exists(dex):
        sys.exit("d8 did not produce classes.dex")
    print(f"[DONE] {dex} ({os.path.getsize(dex)} bytes)")


if __name__ == "__main__":
    main()
