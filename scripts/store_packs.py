"""Real-money packs of the store, sold for gems.

The catalogue's primaryStore lists Ubisoft's real-money packs (Google Play). The Mobile SDK reads
each pack's Play product from its trade's "for" object (parser 0x19f9500: title, description,
currency_iso, formatted_price, product_id, price, type); Ubisoft's server filled it per country,
the captured catalogue has "for": {} everywhere, so the game listed no pack at all.

Here the packs that can work offline get a "for" again:
  - product_id "rayman.offline.<keyword>.<trade>.1": the game sorts a pack by keywords of its
    product id (dynamicStore::isEasterEggsPack "easteregg", isChallengeTokenPack
    "challengetoken", getStoreBundleTypeFromPackName "starterpack", "luckypack"... for the
    special packs) and only keeps the ones whose last character is the price tier
    (dynamicStore::packAvailable; getTierFromDeviceCountry always gives 1);
  - formatted_price "<n> {gems}": the text the buttons show; the server puts the word for gems in
    the player's language ("{gems}", OfflineServer.storeCatalog);
  - price <n>: the gem price, read back by the purchase hook (scripts/pack_purchase_hooks.py), which
    takes the gems instead of opening Google Play.

Prices, so that what the cards say stays true in gems:
  - event currency: 3/4 of a gem each (400 -> 300 gems), less the bonus the card shows ("5 %
    offerts"... args[4]): 700 -> 500, 1450 -> 990, 3200 -> 2000, 6650 -> 3990;
  - challenge tokens: 6 gems each, less the card's bonus (args[9]): 50 -> 300, 90 -> 430;
  - special packs: their gems, plus 80% of the gem value of the rest (each item at its price in
    the shop, event currency at 3/4 of a gem). The pack screen shows a discount ("-85%") and the
    "real value" (price / (1 - discount)) from args[1], set for the euro price: it becomes the
    pack's real discount against the gem value of its contents.
Left out: the gem packs (gems for gems makes no sense), and the packs that need a server feature
the offline server does not have: time saving subscriptions, perks, new creature eggs.
"""
import re

GEMS = 3594
EASTER_EGGS = 4178
CHALLENGE_TOKEN = 4647
# items a pack may not contain (no offline server support)
EXCLUDED_ITEMS = {4196: "time saving pack", 5957: "perk pack", 4293: "new creature egg"}

TOKEN_PRICE = 6
EVENT_CURRENCY_VALUE = 0.75
BUNDLE_RATIO = 0.8
# gem value of the items that are not sold alone for gems
ITEM_VALUES = {
    GEMS: 1,
    3604: 85,      # elixir common -> uncommon
    3606: 115,     # elixir anything -> rare
    3608: 40,      # elixir skip time 50% (never sold alone)
    3610: 195,     # elixir force new creature
    3612: 30,      # lucky ticket (never sold alone)
    3614: 100,     # golden lucky ticket
    3616: 1,       # food
    3692: 60,      # beatbox save slot (10 for 600)
    4391: 100,     # magnifying glass
    CHALLENGE_TOKEN: TOKEN_PRICE,
    EASTER_EGGS: EVENT_CURRENCY_VALUE,
}

# catalogue title -> keyword of the product id (strings of getStoreBundleTypeFromPackName 0x1834974)
BUNDLE_KEYWORDS = {
    "THE ICE-AGE PACK": "theiceagepack",
    "THE ICE-AGE DISCOUNT PACK": "theiceagediscountpack",
    "SPY GLASS PACK": "spyglasspack",
    "ALCHEMIST DISCOUNT PACK": "alchemistdiscountpack",
    "ALCHEMIST PACK": "alchemistpack",
    "UBISOFT MEGA PACK": "ubisoftmegapack",
    "CLANCY PACK": "clancypack",
    "WINTER HOLIDAY PACK": "winterholidaypack",
    "DESERT MARATHON PACK": "desertmarathonpack",
    "DESERT MARATHON PACK DISCOUNT": "desertmarathonpackdiscount",
    "CONVERTER PACK": "converterpack",
    "THE ELECTRO PACK": "theelectropack",
    "THE ELECTRO DISCOUNT PACK": "theelectrodiscountpack",
    "REPEATER PACK": "repeaterpack",
    "LUCKY PACK": "luckypack",
    "PRIMAL CRY PACK": "primalcrypack",
    "NEW YEAR PACK": "newyearpack",
    "SPEED PACK": "speedpack",
    "THE GOLDEN MARATHON PACK": "thegoldenmarathonpack",
    "THE GOLDEN MARATHON DISCOUNT PACK": "thegoldenmarathondiscountpack",
    "ASSASSIN RAY COSTUME PACK": "assassinraycostumepack",
    "SNOWBOX COSTUME PACK": "snowboxcostumepack",
    "URSULA COSTUME PACK": "ursulacostumepack",
    "RABBITEEN COSTUME PACK": "rabbiteencostumepack",
    "PACK DE DÉPART": "starterpack",
    "DISCO PACK": "discopack",
    "SAINT PATRICK PACK": "stpatrickpack",
    "ASSASSIN PACK": "assassinpack",
    "OLYMPIC PACK": "olympicpack",
    "DOJO PACK": "dojopack",
    "THE CANDY PACK": "thecandypack",
    "THE CANDY DISCOUNT PACK": "thecandydiscountpack",
    "MEGA MARATHON PACK": "megamarathon",
    "MEGA HELLOWHEEL PACK": "megahellowheel",
    "MEGA HELLOWHEEL DISCOUNT PACK": "megahellowheeldiscount",
    "THE DUNGEON ADVENTURE PACK": "thedungeonadventurepack",
    "THE DUNGEON ADVENTURE DISCOUNT PACK": "thedungeonadventurediscountpack",
    "RAYBEARD COSTUME PACK": "raybeardcostumepack",
    "FREEZE RAY ICE PACK": "freezerayicepack",
    "THE URSULA PACK": "theursulapack",
    "THE SPLINTER RAY PACK": "thesplinterraypack",
    # left out (EXCLUDED_ITEMS), named for the build log
    "TIME SAVING PACK": "comfortpack",
    "TIME SAVING PACK DELUXE": "deluxecomfortpack",
    "TIME SAVING PACK ULTRA": "ultracomfortpack",
    "TIME SAVING DELUXE DISCOUNT PACK": "timesavingdeluxediscountpack",
    "THE MEGA ADVENTURE PACK": "themegaadventurepack",
    "CREATURES DONT EXHAUST": "nosleep",
    "NEW EGG": "neweggpack",
    "NEW EGG FAMILY": "neweggpackfamily",
}


def _round(price):
    step = 5 if price < 100 else 10
    return max(step, int(round(price / step)) * step)


def _keyword(trade):
    title = trade["get"]["title"].strip()
    if title == "Easter Eggs":
        return "easteregg"
    if title == "Challenge Token":
        return "challengetoken"
    m = re.fullmatch(r"DYNAMIC PACK BUNDLE (\d)", title)
    if m:
        return "dynamicpack" + m.group(1)
    return BUNDLE_KEYWORDS.get(title)


def shop_values(store):
    """Gem value of one unit of each item sold in the shop, mostly costumes (event currency at 3/4
    of a gem); the first trade of an item counts (the single unit, before the bulk discounts)."""
    values = {}
    for trade in store.get("secondaryStore", []):
        price = trade["for"]["items"][0]
        got = trade["get"]["items"]
        if len(got) != 1:
            continue
        rate = {GEMS: 1, EASTER_EGGS: EVENT_CURRENCY_VALUE}.get(int(price["item_id"]))
        if rate:
            values.setdefault(int(got[0]["item_id"]), int(price["amount"]) * rate / int(got[0]["amount"]))
    return values


def _bonus(trade, index):
    arg = trade["args"][index] if len(trade["args"]) > index else ""
    return int(arg) if arg.isdigit() else 0


def gem_price(trade, values):
    """(price, value) in gems; value = what the contents are worth one by one."""
    keyword = _keyword(trade)
    items = [(int(i["item_id"]), int(i["amount"])) for i in trade["get"]["items"]]
    value = sum(values[i] * n for i, n in items)
    if keyword == "easteregg":
        return _round(value / (1 + _bonus(trade, 4) / 100)), value
    if keyword == "challengetoken":
        return _round(value / (1 + _bonus(trade, 9) / 100)), value
    gems = sum(n for i, n in items if i == GEMS)
    return gems + _round((value - gems) * BUNDLE_RATIO), value


def sell_packs_for_gems(store):
    """Gives the packs that work offline a Play product sold for gems (see the module doc)."""
    values = shop_values(store)
    values.update(ITEM_VALUES)
    sold, skipped, seen = [], [], set()
    for trade in store.get("primaryStore", []):
        title = trade["get"]["title"]
        keyword = _keyword(trade)
        items = {int(i["item_id"]) for i in trade["get"]["items"]}
        why = None
        if keyword is None:
            why = "gem pack" if items == {GEMS} else "no product name the game knows"
        elif items & EXCLUDED_ITEMS.keys():
            why = ", ".join(EXCLUDED_ITEMS[i] for i in items & EXCLUDED_ITEMS.keys())
        elif any(i not in values for i in items):
            why = "item without a gem value"
        key = (keyword, tuple(sorted((int(i["item_id"]), int(i["amount"])) for i in trade["get"]["items"])))
        if why is None and key in seen:
            why = "same pack as another trade"     # the starter pack exists once per price tier
        if why:
            trade["for"] = {}
            skipped.append((trade["trade_id"], title, why))
            continue
        seen.add(key)
        price, value = gem_price(trade, values)
        if keyword not in ("easteregg", "challengetoken"):
            discount = int(round(100 * (1 - price / value)))
            trade["args"][1] = str(discount) if discount > 0 else ""
        trade["for"] = {
            "title": title,
            "description": trade["get"].get("description", title),
            "currency_iso": "GEMS",
            "formatted_price": f"{price} {{gems}}",
            "product_id": f"rayman.offline.{keyword}.{trade['trade_id']}.1",
            "price": str(price),
            "type": "consumable",
        }
        sold.append((trade["trade_id"], title, price))
    return sold, skipped


if __name__ == "__main__":
    import json
    import os
    import sys
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with open(os.path.join(root, "mock_data", "store_v2_fixed.json"), encoding="utf-8") as f:
        store = json.load(f)
    sold, skipped = sell_packs_for_gems(store)
    by_id = {t["trade_id"]: t for t in store["primaryStore"]}
    for t, title, price in sold:
        print(f"  {t:>6} {title:<36} {price:>6} gems  args[1]={by_id[t]['args'][1]}")
    print(f"{len(sold)} packs for gems; left out:")
    for t, title, why in skipped:
        print(f"  {t:>6} {title:<36} {why}")
    sys.exit(0)
