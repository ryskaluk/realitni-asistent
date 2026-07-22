# 🏡 Realitní asistent — domy a pozemky

Skript, který každý den prohledá realitní servery, vybere domy a pozemky
ve tvé oblasti a cenovém rozpočtu a zobrazí je v přehledném HTML dashboardu.
Nové nabídky od minule zvýrazní zeleným štítkem **NOVÉ**.

> 🌍 **Chceš dashboard dostupný odkudkoli a aktualizovaný sám v cloudu (i při vypnutém
> počítači)?** Postupuj podle **[NAVOD_ONLINE.md](NAVOD_ONLINE.md)** — nasazení zdarma
> na GitHub Pages, běží samo každý den. Návod níže je pro běh přímo na tvém počítači.

## Co hledá (výchozí nastavení)

- **Domy** do **15 000 000 Kč**, jen ve stavu: **velmi dobrý / dobrý / novostavba / po rekonstrukci**
- **Pozemky** do **5 000 000 Kč**, jen **stavební** (pro bydlení / výstavbu)
- V okruhu **+5 km** kolem obcí **Ostravice, Raškovice, Horní Domaslavice, Dolní Domaslavice**
- Zdroje: **Sreality.cz, Bezrealitky.cz, Reality.iDNES.cz, Bazoš.cz**

Vše se dá změnit v horní části souboru `hledej.py` (sekce NASTAVENÍ).

## Soubory

| Soubor | K čemu je |
|---|---|
| `hledej.py` | Hlavní skript — spouštíš tenhle |
| `dashboard_template.py` | Vzhled dashboardu (needituj, pokud nechceš měnit design) |
| `dashboard.html` | **Výsledek** — otevři v prohlížeči (vzniká po spuštění) |
| `seen.json` | Paměť už viděných inzerátů (pro označení nových) — vzniká automaticky |
| `requirements.txt` | Seznam potřebných knihoven |

> V balíčku je přiložený `dashboard.html` s **ukázkovými daty**, ať hned vidíš vzhled.
> Po prvním ostrém spuštění se přepíše skutečnými nabídkami.

## Instalace (macOS, jednorázově)

Otevři aplikaci **Terminál** a spusť:

```bash
cd ~/Downloads/realitni-asistent        # nebo kamkoli složku uložíš
pip3 install -r requirements.txt
```

## Spuštění

```bash
python3 hledej.py            # ostrý běh — stáhne aktuální nabídky
open dashboard.html          # otevře přehled v prohlížeči
```

Vyzkoušení bez internetu (ukázková data):

```bash
python3 hledej.py --demo
```

## Automatické spouštění každé ráno (cron)

Aby se seznam obnovoval sám, přidej si úlohu do cronu. V Terminálu:

```bash
crontab -e
```

Vlož řádek (spuštění každý den v 7:00 ráno — uprav cestu ke složce):

```
0 7 * * * cd /Users/lukas/Downloads/realitni-asistent && /usr/bin/python3 hledej.py >> beh.log 2>&1
```

Ulož a zavři. Od té chvíle se `dashboard.html` každé ráno sám aktualizuje —
stačí si ho otevřít (nebo si ho ulož do záložek/na plochu).

> Tip: pokud chceš, aby se ti dashboard po ránu rovnou otevřel, přidej na konec
> řádku `&& open dashboard.html`.

## Přizpůsobení

Vše v horní části `hledej.py`:

- **Jiné obce / rozpočet** → uprav `OBCE`, `MAX_CENA_DUM`, `MAX_CENA_POZEMEK`, `RADIUS_KM`
- **Vypnout zdroj** → v `ZDROJE_ZAPNUTE` dej `False` (např. `"bazos": False`)
- **Širší/užší okolí u textových zdrojů** (Bazoš, iDNES) → uprav seznam `OBCE_TEXTOVE`
- **Vypnout kvalitativní filtr** → `POZEMEK_JEN_STAVEBNI = False` nebo `DUM_JEN_DOBRY_STAV = False`
- **Jaký stav domu brát** → uprav `SREALITY_DUM_STAV_KODY` (6=novostavba, 5=projekt,
  8=po rekonstrukci, 1=velmi dobrý, 4=ve výstavbě) a klíčová slova `DUM_STAV_KLICOVA`
- **Co je „stavební" pozemek** → klíčová slova `POZEMEK_MUSI_OBSAHOVAT` / `POZEMEK_NESMI_OBSAHOVAT`

### Jak filtr stavu a typu funguje

- **Sreality** filtruje rovnou server přes API (typ pozemku a stav objektu) — přesné.
- **Bezrealitky, iDNES, Bazoš** nemají tento filtr v API, proto se stav/typ pozná
  z **klíčových slov v názvu inzerátu** (např. „novostavba", „po rekonstrukci",
  „stavební pozemek"). Inzerát s chudým názvem, kde stav není uvedený, se u těchto
  zdrojů raději vynechá — takže radši ověřuj i přímo na webu, ať ti nic neuteče.

> ⚠️ Kódy Sreality (`SREALITY_POZEMEK_STAVEBNI_SUB`, `SREALITY_DUM_STAV_KODY`) jsem
> nastavil podle dokumentace, ale nemohl je z tohoto prostředí ověřit naživo.
> Po prvním ostrém běhu se koukni, zda počty sedí; kdyby filtr vracel 0 domů/pozemků,
> zkontroluj tyto kódy (stačí je porovnat s filtrem přímo na sreality.cz).

## Poznámky ke zdrojům

- **Sreality** a **Bezrealitky** používají oficiální datová rozhraní (API) — spolehlivé,
  včetně GPS souřadnic, takže filtr podle vzdálenosti je přesný.
- **iDNES** a **Bazoš** nemají veřejné API, proto se čtou přímo ze stránek (scraping).
  Tyto weby občas mění strukturu — pokud přestanou vracet výsledky, je potřeba upravit
  „selektory" ve funkcích `zdroj_idnes()` / `zdroj_bazos()`. U těchto dvou zdrojů se
  lokalita filtruje podle **názvu obce v textu** (ne podle GPS), viz `OBCE_TEXTOVE`.
- Ceny i dostupnost vždy ověř přímo v inzerátu — dashboard je jen rozcestník.
```
