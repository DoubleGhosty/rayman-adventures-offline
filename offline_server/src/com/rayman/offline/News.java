package com.rayman.offline;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * Title screen "Actualites": the game's WebView opens http://127.0.0.1:18080/v1/news/<language>
 * (libuaf patch of GameServerModule::getNewsURL; language = ITF language index, 1 = French). Ubisoft's
 * news pages are gone: this page is made from what the offline server schedules itself - the seasonal
 * event running now and the next ones (SeasonalEvents), the weekend mini event (MiniEvents) and the
 * daily challenge - in French or English.
 */
final class News {

    /** Event ids by type (SeasonalEvents: hunts 1-6 and 9, spin wheels 7 10 13 17, marathons 8 11 12 16). */
    private static final int[] WHEELS = {7, 10, 13, 17};

    private News() {
    }

    private static final class Text {
        final boolean fr;

        Text(boolean fr) {
            this.fr = fr;
        }

        String t(String fr, String en) {
            return this.fr ? fr : en;
        }

        String date(long millis) {
            return new SimpleDateFormat(fr ? "EEEE d MMMM" : "EEEE, MMMM d", fr ? Locale.FRENCH : Locale.ENGLISH)
                    .format(new Date(millis));
        }

        String eventType(long id) {
            for (int m : SeasonalEvents.MARATHONS) {
                if (m == id) {
                    return t("Marathon", "Marathon");
                }
            }
            for (int w : WHEELS) {
                if (w == id) {
                    return t("Expédition (roue)", "Expedition (spin wheel)");
                }
            }
            return t("Chasse au trésor", "Treasure hunt");
        }

        String eventHow(long id) {
            for (int m : SeasonalEvents.MARATHONS) {
                if (m == id) {
                    return t("Le défi quotidien devient la course de l'événement et rapporte sa monnaie.",
                            "The daily challenge becomes the event's run and pays its currency.");
                }
            }
            for (int w : WHEELS) {
                if (w == id) {
                    return t("Ramasse la monnaie de l'événement dans les aventures et fais tourner la roue.",
                            "Collect the event currency in the adventures and spin the wheel.");
                }
            }
            return t("Trouve les doublons cachés dans les aventures.",
                    "Find the doubloons hidden in the adventures.");
        }
    }

    static String page(String lang) {
        Text tx = new Text(lang.startsWith("1"));
        long now = System.currentTimeMillis();
        StringBuilder b = new StringBuilder();

        // seasonal event now
        long[] ev = SeasonalEvents.current();
        b.append(section(tx.t("Événement saisonnier", "Seasonal event")));
        if (now >= ev[1] && now < ev[2]) {
            b.append(card(tx.eventType(ev[0]),
                    tx.t("En cours jusqu'au ", "Running until ") + tx.date(ev[2] - 1)
                            + tx.t(" (encore ", " (") + days(ev[2] - now, tx) + tx.t(").", " left)."),
                    tx.eventHow(ev[0]) + " " + tx.t("Sa boutique vend un costume, un œuf et des tickets.",
                            "Its shop sells a costume, an egg and tickets.")));
        } else if (now >= ev[2] && now < ev[3]) {
            b.append(card(tx.eventType(ev[0]) + tx.t(" : dernière chance", ": last chance"),
                    tx.t("L'événement est fini, sa boutique reste ouverte jusqu'au ",
                            "The event is over, its shop stays open until ") + tx.date(ev[3] - 1) + ".",
                    tx.t("Dépense ta monnaie d'événement avant qu'elle disparaisse.",
                            "Spend your event currency before it is gone.")));
        }
        b.append(note(tx.t("Les événements apparaissent à partir de la 6e aventure.",
                "Events show up from the 6th adventure on.")));

        // next events
        b.append(section(tx.t("Prochains événements", "Next events")));
        for (long[] next : nextEvents(now, 3)) {
            b.append(row(tx.eventType(next[0]), tx.t("à partir du ", "from ") + tx.date(next[1])));
        }

        // weekend mini event
        b.append(section(tx.t("Ce week-end", "This weekend")));
        long[] weekend = weekend(now);
        String mini = MiniEvents.weekendEvent(weekend[0]);
        boolean running = now >= weekend[0];
        b.append(card(mini, (running ? tx.t("En ce moment, jusqu'au ", "Now, until ") + tx.date(weekend[1] - 1)
                        : tx.t("Du ", "From ") + tx.date(weekend[0]) + tx.t(" au ", " to ") + tx.date(weekend[1] - 1)) + ".",
                tx.t("Un mini événement chaque week-end, du vendredi au dimanche.",
                        "A mini event every weekend, from Friday to Sunday.")));

        // daily challenge
        b.append(section(tx.t("Défi quotidien", "Daily challenge")));
        long left = ServerState.secondsToNextDay();
        b.append(card(tx.t("Nouveau défi dans ", "New challenge in ") + (left / 3600) + " h " + String.format(Locale.US, "%02d", left / 60 % 60),
                tx.t("Joue-le pour gagner 25 gemmes et un ticket le lendemain, quel que soit ton rang.",
                        "Play it to win 25 gems and a ticket the next day, whatever your rank."), null));

        // about
        b.append(section(tx.t("À propos", "About")));
        b.append(note(tx.t("Les serveurs d'Ubisoft sont fermés : cette version de Rayman Adventures fonctionne hors ligne. "
                        + "Les événements, les classements et la boutique sont gérés sur ton appareil.",
                "Ubisoft's servers are closed: this version of Rayman Adventures runs offline. "
                        + "Events, leaderboards and the shop are run on your device.")));

        return "<!doctype html><html><head><meta charset=\"utf-8\">"
                + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                + "<title>" + tx.t("Actualités", "News") + "</title><style>"
                + "html,body{margin:0;background:#0b3d5c;color:#fff;font-family:sans-serif}"
                + "main{max-width:40em;margin:0 auto;padding:1em 1.2em 2em}"
                + "h1{font-size:1.7em;margin:.3em 0 .2em;color:#ffd23f}"
                + "h2{font-size:1.15em;margin:1.3em 0 .5em;color:#9fe3ff;text-transform:uppercase;letter-spacing:.04em}"
                + ".card{background:#14557d;border-radius:12px;padding:.8em 1em;margin:.4em 0}"
                + ".card b{display:block;font-size:1.15em;color:#ffd23f;margin-bottom:.2em}"
                + ".card p{margin:.25em 0;line-height:1.35}"
                + ".row{display:flex;justify-content:space-between;gap:1em;padding:.5em .2em;border-bottom:1px solid #24688f}"
                + ".row span:last-child{color:#cfe9f7;text-align:right}"
                + ".note{color:#cfe9f7;font-size:.95em;line-height:1.4;margin:.5em .2em}"
                + "</style></head><body><main><h1>" + tx.t("Actualités", "News") + "</h1>"
                + b + "</main></body></html>";
    }

    /** The next {@code n} events that have not started yet. */
    private static List<long[]> nextEvents(long now, int n) {
        List<long[]> out = new ArrayList<>();
        int year = Calendar.getInstance().get(Calendar.YEAR);
        for (int y = year; y <= year + 1 && out.size() < n; y++) {
            for (int s = 0; s < SeasonalEvents.CALENDAR.length && out.size() < n; s++) {
                long[] ev = SeasonalEvents.slot(y, s);
                if (ev[1] > now) {
                    out.add(ev);
                }
            }
        }
        return out;
    }

    /** {start, end} of this weekend's mini event window (Friday 00:00 to Monday 00:00), or the next one.
     *  The pages show end - 1 ms: the last day (Sunday). */
    private static long[] weekend(long now) {
        Calendar c = Calendar.getInstance();
        c.setTimeInMillis(now);
        c.set(Calendar.HOUR_OF_DAY, 0);
        c.set(Calendar.MINUTE, 0);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        int dow = c.get(Calendar.DAY_OF_WEEK);
        int back = dow == Calendar.FRIDAY ? 0 : dow == Calendar.SATURDAY ? 1 : dow == Calendar.SUNDAY ? 2 : -1;
        if (back >= 0) {
            c.add(Calendar.DAY_OF_MONTH, -back);
        } else {
            while (c.get(Calendar.DAY_OF_WEEK) != Calendar.FRIDAY) {
                c.add(Calendar.DAY_OF_MONTH, 1);
            }
        }
        long start = c.getTimeInMillis();
        c.add(Calendar.DAY_OF_MONTH, 3);
        return new long[]{start, c.getTimeInMillis()};
    }

    private static String days(long millis, Text tx) {
        long d = (millis + 86399999L) / 86400000L;
        return d + (d > 1 ? tx.t(" jours", " days") : tx.t(" jour", " day"));
    }

    private static String section(String title) {
        return "<h2>" + esc(title) + "</h2>";
    }

    private static String card(String title, String line1, String line2) {
        return "<div class=\"card\"><b>" + esc(title) + "</b><p>" + esc(line1) + "</p>"
                + (line2 == null ? "" : "<p>" + esc(line2) + "</p>") + "</div>";
    }

    private static String row(String left, String right) {
        return "<div class=\"row\"><span>" + esc(left) + "</span><span>" + esc(right) + "</span></div>";
    }

    private static String note(String text) {
        return "<p class=\"note\">" + esc(text) + "</p>";
    }

    private static String esc(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }
}
