# 🌍 Dashboard online — dostupný odkudkoli (zdarma, přes GitHub)

Tímto způsobem poběží asistent **v cloudu**, sám se každý den aktualizuje
(i když máš vypnutý počítač) a dashboard si otevřeš na webové adrese
z mobilu, notebooku, odkudkoli.

Jak to funguje:
1. **GitHub Actions** každé ráno v cloudu spustí `hledej.py` (odtud se na reality dostane).
2. Výsledek uloží jako `index.html` a paměť inzerátů do `seen.json` přímo do repozitáře.
3. **GitHub Pages** ten `index.html` zveřejní na adrese typu
   `https://tvojejmeno.github.io/realitni-asistent/`.

Není potřeba žádný server ani placená služba.

---

## Krok za krokem (cca 10 minut, bez programování)

### 1) Založ si účet a repozitář
1. Zaregistruj se na <https://github.com> (pokud účet nemáš) — zdarma.
2. Vpravo nahoře **+ → New repository**.
3. Název např. `realitni-asistent`, nech **Public**, klikni **Create repository**.

> Poznámka k soukromí: veřejný repozitář i Pages jsou čitelné pro kohokoli, kdo zná
> adresu (jsou to jen veřejné realitní inzeráty, takže to většinou nevadí).
> Privátní GitHub Pages vyžaduje placený tarif.

### 2) Nahraj soubory projektu
Na stránce repozitáře klikni **Add file → Upload files** a přetáhni tam **celý obsah
této složky** (včetně skryté složky `.github`):

```
hledej.py
dashboard_template.py
requirements.txt
index.html
.github/workflows/hledej.yml
README.md
NAVOD_ONLINE.md
```

Pak dole **Commit changes**.

> Kdyby se ti přes web nedařilo nahrát složku `.github` (skryté složky někdy web skrývá),
> nejjednodušší je nainstalovat **GitHub Desktop** (<https://desktop.github.com>),
> složku do repozitáře zkopírovat a kliknout *Commit* + *Push*.

### 3) Zapni GitHub Pages
1. V repozitáři jdi na **Settings → Pages**.
2. V sekci **Build and deployment → Source** zvol **Deploy from a branch**.
3. Branch: **main**, složka **/(root)**, klikni **Save**.
4. Po chvíli se nahoře objeví adresa tvého dashboardu:
   `https://<tvůj-login>.github.io/realitni-asistent/`
   Tu si ulož do záložek (funguje i na mobilu).

### 4) Zapni a poprvé spusť automat
1. V repozitáři jdi na záložku **Actions**.
2. Pokud GitHub zeptá, potvrď **I understand my workflows, go ahead and enable them**.
3. Vlevo vyber **„Realitní asistent — denní běh"** a vpravo klikni
   **Run workflow → Run workflow** (spustí to hned, ať nečekáš do rána).
4. Po doběhnutí (1–2 min) se `index.html` aktualizuje skutečnými nabídkami
   a dashboard na tvé adrese ukáže reálné inzeráty.

Hotovo. Od teď to jede samo každý den v 7:00 (ČR). Nové nabídky se na dashboardu
zvýrazní štítkem **NOVÉ**.

---

## Časté úpravy

- **Změnit čas běhu** → v `.github/workflows/hledej.yml` uprav `cron` (čas je v UTC;
  ČR = UTC+1 v zimě, UTC+2 v létě). Např. `0 5 * * *` = 7:00 letního času.
- **Změnit kritéria** (obce, cena, stav) → uprav horní část `hledej.py` a nahraj změnu.
  Při nejbližším běhu se projeví.
- **Ruční spuštění kdykoli** → Actions → Run workflow.
- **Kontrola, že běh proběhl** → záložka Actions ukáže zelené fajfky / případné chyby.

## Když něco nefunguje

- **Dashboard je prázdný / same demo** → ještě neproběhl ostrý běh; spusť ho ručně
  v Actions (krok 4).
- **Actions hlásí chybu u scraping zdrojů (iDNES/Bazoš)** → weby mohly změnit strukturu;
  můžeš je dočasně vypnout v `ZDROJE_ZAPNUTE` (`"idnes": False`, `"bazos": False`).
  Sreality a Bezrealitky (oficiální API) jedou dál.
- **Sreality vrací 0** → zkontroluj kódy `SREALITY_DUM_STAV_KODY` /
  `SREALITY_POZEMEK_STAVEBNI_SUB` (viz README).

## Alternativy k GitHubu

Pokud bys nechtěl GitHub, stejný skript se dá nasadit i na:
- **PythonAnywhere** (má vestavěný plánovač úloh + hosting) — jednoduché pro Python.
- **Render.com / Railway.app** — cron job + statický hosting.
Princip je stejný: spouštět `hledej.py` na serveru a `index.html` někde vystavit.
GitHub je ale nejjednodušší a zdarma, proto ho doporučuju jako první volbu.
