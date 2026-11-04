"""
Bot de noticias para Telegram, pensado para ejecutarse con GitHub Actions.
Cada ejecución hace UNA pasada: lee los feeds RSS, envía las noticias nuevas
y guarda en seen.json las que ya envió (el workflow sube ese archivo al repo).

Variables de entorno necesarias (se configuran como "Secrets" en GitHub):
    TELEGRAM_BOT_TOKEN   token que te da @BotFather
    TELEGRAM_CHAT_ID     tu chat id (o el de un canal/grupo)
"""

import html
import json
import os
import time
from pathlib import Path

import feedparser
import requests

# ───────────────────────── CONFIGURACIÓN ─────────────────────────

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Añade, quita o cambia los medios: "Nombre": "URL del feed RSS"
FEEDS = {
    "BBC Mundo": "https://feeds.bbci.co.uk/mundo/rss.xml",
    "El País": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
}

MAX_PER_FEED = 5               # máximo de noticias por medio en cada ejecución
SEEN_FILE = Path("seen.json")  # noticias ya enviadas
PREVIEW = True                 # False = sin vista previa del enlace

# ─────────────────────────────────────────────────────────────────


def load_seen() -> list:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return []


def save_seen(seen: list) -> None:
    # Conservamos solo las últimas 3000 para que el archivo no crezca sin fin
    SEEN_FILE.write_text(json.dumps(seen[-3000:], ensure_ascii=False), encoding="utf-8")


def send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": not PREVIEW,
        },
        timeout=20,
    )
    resp.raise_for_status()


def main() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit("Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID.")

    first_run = not SEEN_FILE.exists()
    seen_list = load_seen()
    seen = set(seen_list)

    for source, feed_url in FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"[!] Error leyendo {source}: {e}")
            continue

        # Noticias que aún no hemos visto (los feeds suelen venir de más nueva a más antigua)
        new_entries = [e for e in feed.entries if e.get("link") and e["link"] not in seen]

        # Primera ejecución: solo memorizamos lo existente, sin enviar nada
        if first_run:
            for e in new_entries:
                seen.add(e["link"])
                seen_list.append(e["link"])
            continue

        to_send = new_entries[:MAX_PER_FEED]
        skipped = new_entries[MAX_PER_FEED:]

        # Las que exceden el límite se marcan como vistas para no acumular atraso
        for e in skipped:
            seen.add(e["link"])
            seen_list.append(e["link"])

        # Enviamos de la más antigua a la más nueva
        for e in reversed(to_send):
            title = html.escape(e.get("title", "Sin título"))
            msg = f"📰 <b>{html.escape(source)}</b>\n{title}\n{e['link']}"
            try:
                send_message(msg)
            except Exception as err:
                # Si falla, no la marcamos como vista: se reintenta en la próxima ejecución
                print(f"[!] No se pudo enviar '{title}': {err}")
                continue
            seen.add(e["link"])
            seen_list.append(e["link"])
            time.sleep(1.5)  # evita el límite de mensajes de Telegram

    save_seen(seen_list)
    print("Listo.")


if __name__ == "__main__":
    main()
