# Modele dla hokeja, koszykówki i siatkówki — przegląd literatury i projekt

Stan: 2026-10-02 (dokument badawczo-projektowy), z dopiskiem 2026-10-05.

**Od 2026-10-05 08:30Z (`bet.sofa.epochs.SPORTS_ON_COUPON_FROM_UTC`)
nogi hokeja, koszykówki, siatkówki i CS2 drukują się na jednym kuponie**
(`runs/sofa/<d>/KUPON_<d>.pdf`, artefakt `11_coupon.json`). Ich pewność to
model wyników (`src/bet/sofa/score_model.py`) albo silnik CS2
(`src/bet/sofa/cs2_engine.py`) przepuszczony przez krzywą kalibracji bez
cen — `config/sofa_sport_confidence_calibration.json`
(`scripts/sofa/fit_sport_confidence.py --before <d>`, tylko między dniami;
dolna granica Wilsona kubełka, `realised_lo95` tylko dla klucza
dopuszczonego, `min_bucket` 200, `max_overstatement` 0,03). Etapy:
SPORT_IDENTITY (`run_sport_identity.py`, przypięte id Sofascore →
`sport_fixtures.json`) i SPORT_CONFIDENCE (`run_sport_confidence.py` →
`08_confidence_sports.json`); cena jest tylko filtrem (x ≥ 0,90, marża grupy
≤ 15%, cena nie starsza niż 3 h). Model niesie się na nodze jako
`forecast_p` (`forecast_source` `score_model` / `cs2_engine`). Pomiar
poza próbą: [`RAPORT_KALIBRACJA_SPORTOW_2026-10-05.md`](RAPORT_KALIBRACJA_SPORTOW_2026-10-05.md).
Pomiar `SHADOW` / `SHADOW_SETTLE` (`runs/sofa/shadow/<sport>/<data>/`)
zostaje i jest wejściem tych etapów.

Historyczne (wycofane 2026-10-05 od 08:30Z): osobne kupony sportowe
(`KUPON_<d>_{HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf`, `run_sport_coupon.py`) były
cenowe — pewność z devigu Superbetu, od rana 10-05 przekalibrowana
`config/sofa_sport_price_calibration.json` — i nie czytały żadnego modelu.
Ich pliki do poranka 10-05 zostają i są rozliczane po staremu
(`settle_sport_coupon.py`). Tekst poniżej (2026-10-02) opisuje drogę modelu
do tamtych kuponów; tam, gdzie mówi „kupon sportowy”, czytaj go jako zapis
historyczny. Wynik każdego modelu jako pomiaru nadal nigdy nie jest łączony
z wynikiem kuponu.

Cel ustalony przez operatora (2026-10-02): **pobicie ceny Superbetu NIE jest
celem.** Operator przyjmuje wniosek literatury, że te rynki są trudne do
pobicia, i akceptuje grę do ~10% poniżej ceny. Model ma być **prognozą i
selektorem** (które nogi, które rynki, które ligi) dla kuponów sportowych i
analizy; cena jest kontekstem, nie poprzeczką. Porównanie model–cena (Brier
względem ceny bez marży, CLV) raportujemy uczciwie jako informację — nigdy
go nie ukrywamy.

Oznaczenia źródeł: **[W]** — zweryfikowane (pobrana strona arXiv / RePEc /
OUCI / wydawcy / autora potwierdza cytat i twierdzenie); **[S]** — tylko
streszczenie z wyszukiwarki (De Gruyter, SAGE, Springer, T&F, Wiley,
ScienceDirect odmawiały pobrania). **MR** — wynik zmierzony (recenzowany lub
odtwarzalny), **PC** — twierdzenie praktyka (blog, branża, heurystyka
książkowa). Cytaty zebrał pod-agent literaturowy 2026-10-02; to, czego nie
znalazł, jest wypisane wprost w §A.6.

---

## 0. Co już wiemy z własnych pomiarów

| co | wynik | źródło |
|---|---|---|
| model wyniku (`score_model.py`) vs cena, 09-29+09-30, bootstrap po meczach | Brier blendu − ceny: hokej −0,0005 [−0,0029; +0,0019], kosz −0,0014 [−0,0045; +0,0016], siatka −0,0116 [−0,0290; +0,0025] (16 meczów) | commit e39f5dda |
| test kombinacji `logit(y) ~ model + cena` | totale niosą informację ponad cenę (hokej b 0,98 [−0,07; 2,14], kosz 0,70), zwycięzcy nie (b ≤ 0) | e39f5dda, `measure_model_information.py` |
| odrzucone po pomiarze | back-to-back w koszu (+0,06 pkt, se 0,64), wspólny szok w hokeju (cov −0,04), szum seta i model serwisu w siatce (model serwisu poprawił total setów, zepsuł zwycięzcę) | `score_model.py` komentarze, e39f5dda |
| CS2 round-race | lepszy od stopy bazowej na historii, przegrywa z ceną (0,2532 vs 0,2418; b −0,35 [−3,77; 2,86]) | 6acac84a |

**Nowy pomiar z tego przeglądu (2026-10-02, PODEJRZENIE, nie wynik):**
strona OVER linii zawodników trafia rzadziej, niż mówi cena bez marży
(`fair_p`, metoda potęgowa `cs2.group_fair`). Z `settled.json` 09-29..10-01,
tylko strona OVER, bootstrap po meczach (2000 losowań):

| | linie OVER | mecze | trafienie − fair_p |
|---|---|---|---|
| hokej, zawodnicy (wszystkie rodziny) | 777 | 10 | **−0,063** [−0,117; −0,004] |
| kosz, zawodnicy (wszystkie rodziny) | 1 386 | 25 | **−0,060** [−0,108; −0,008] |
| hokej, total + total drużyny (regulamin) | 1 123 | 126 | +0,028 [−0,027; +0,084] |
| kosz, total + total drużyny | 2 234 | 134 | −0,059 [−0,156; +0,036] |

To trzy dni i 10 / 25 meczów; linie jednego wieczoru są skorelowane ponad
mecz (wspólne tempo dnia), więc przedział jest zbyt wąski i to **nie jest**
reguła. Zgadza się jednak kierunkowo z literaturą o preferencji graczy dla
„overów” (B25, B21, H28) i jest pierwszą rzeczą do sprawdzenia na większej
próbie. Rodzinami: hokej `player_points` 0,384 vs 0,468 (146 linii),
`player_pp_points` 0,136 vs 0,204; kosz `player_points` 0,456 vs 0,500,
`player_rebounds` 0,435 vs 0,498, `player_blocks` 0,152 vs 0,274.

Marża Superbetu (średni overround grup, ta sama próba): hokej linie dwudrogowe
drużyn 4–6%, zawodnicy 6,3–7,2%, 1X2 ~11%; kosz drużyny 4,4–5,7%, zawodnicy
8,0–8,6%, parzyste/nieparzyste 8,6–8,7%, 1X2 9,3–9,5%; siatka dwudrogowe
6,5–8,6%, dokładny wynik w setach **19%**.

---

## A. Przegląd literatury

### A.1 Hokej na lodzie

**Wynik, totale, handicapy.**
- Gole są w przybliżeniu procesem Poissona ze stałą intensywnością zależną od
  sportu; to, kto strzela, jest bliskie losowania Bernoulliego — Merritt &
  Clauset (2014), *Scoring dynamics across professional team sports*, EPJ
  Data Science 3:4, https://arxiv.org/abs/1310.4461 — MR [W] (H5).
- Intensywność bramek zależy od obu drużyn, gospodarza i **stanu liczebnego**
  (przewaga/osłabienie); model nadaje się do handicapów i decyzji o
  wycofaniu bramkarza — Buttrey, Washburn, Price (2011), *Estimating NHL
  scoring rates*, JQAS 7(3) art. 24,
  https://ideas.repec.org/a/bpj/jqsprt/v7y2011i3n24.html — MR [S] (H3).
- Dwuwymiarowe rozkłady Poissona w hokeju (czeska Extraliga 1999–2012), nowy
  wariant z alternatywnej konstrukcji — Marek, Šedivá, Ťoupal (2014),
  *Modeling and prediction of ice hockey match results*, JQAS 10(3):357–365,
  https://ideas.repec.org/a/bpj/jqsprt/v10y2014i3p9n4.html — MR [W] (H1).
- Czasy między golami lepiej opisuje proces semi-Markowa (posiadanie,
  strefa) niż prosty Poisson — Thomas (2007), JQAS 3(3),
  doi 10.2202/1559-0410.1064 — MR [S] (H2).
- Model intensywności goli + kar, symulacja Markowa; zakłady przy rozjeździe
  z rynkiem dały dodatni, istotny statystycznie ROI — Buttrey (2016),
  *Beating the market betting on NHL hockey games*, JQAS,
  https://ouci.dntb.gov.ua/en/works/7peVpyo4/ — MR [W] (H4). Uwaga: jedna
  praca, dane sprzed lat; M4 niżej ostrzega, że pojedyncze „nieefektywności”
  zwykle są przypadkiem.
- Bradley–Terry z rozdzieleniem regulaminu / dogrywki / karnych (wygrana w
  OT/SO liczona jako 1/3) — Whelan & Klein (2021),
  https://arxiv.org/abs/2112.01267 — MR (metoda) [W] (H6).
- NHL i MLB to najbardziej „losowe” ligi; NBA ma największy rozrzut talentu
  i przewagę gospodarza — Lopez, Matthews, Baumer (2018), *How often does the
  best team win?*, AoAS 12(4):2483–2516, https://arxiv.org/abs/1701.05976 —
  MR [W] (H7). Praktyczny sufit trafności pojedynczego meczu NHL ~60–62%
  (Weissbock & Inkpen, ~2014) — MR słaby [S] (H8); praca deklarująca ~90%
  (Gu i in. 2019, Expert Systems with Applications) to ostrzeżenie przed
  przeciekiem, nie wynik (H9).
- Dixon–Coles / zero-inflation dla hokeja: **brak** recenzowanej pracy;
  jedynie blog (pbulsink 2016) — H10.

**Bramkarz i jakość strzałów.**
- Brak „gorącej ręki” bramkarzy: 48 431 strzałów, 93 bramkarzy; dobra
  niedawna skuteczność wręcz lekko obniża skuteczność przy kolejnym
  strzale — Ding, Cribben, Ingolfsson, Tran (2021/2024),
  https://arxiv.org/abs/2102.09689 — MR [W] (H14). Wniosek dla nas: nie
  ważyć ostatniej serii save%.
- Skuteczność obron słabo powtarzalna (sezon do sezonu ~0,12) — hockey-graphs
  2015 — PC [S] (H16).
- Ważone strzały „dobrze, ale nie lepiej niż tradycyjne statystyki” —
  Macdonald, Lennon, Sturdivant (2012), https://arxiv.org/abs/1205.1746 —
  MR [W] (H12); adjusted plus-minus — Macdonald (2011), JQAS 7(3),
  https://arxiv.org/abs/1006.4310 — MR [S] (H11); modele hazardu
  konkurujących procesów — Thomas, Ventura, Jensen, Ma (2013), AoAS 7(3),
  https://arxiv.org/abs/1208.0799 — MR [W] (H13).
- xG Evolving-Hockey: XGBoost per stan liczebny, AUC 0,78 (5v5), 0,72 (PP),
  https://evolving-hockey.com/blog/a-new-expected-goals-model-for-predicting-goals-in-the-nhl/
  — PC odtwarzalne [W] (H17). Wymaga play-by-play z lokalizacją strzałów —
  **nie mamy**.
- MoneyPuck (model przedmeczowy): wagi szanse 54% / bramkarz 29% /
  „umiejętność wygrywania” 17%; gospodarz ~54%; back-to-back ~−4 pp szansy
  wygranej; log loss 0,658/0,661, https://moneypuck.com/about.htm — PC [W]
  (H18).
- Karne: małe różnice talentu strzelców, marginalne bramkarzy — Lopez &
  Schuckers (2017), J Sports Sci 35(9) — MR [S] (H15). Zgadza się z naszym
  pomiarem (zwycięzca OT ściągnięty w połowie drogi do monety: 0,2485 vs
  0,2500).

**Pusta bramka, dogrywka, efekt wyniku, odpoczynek.**
- Optymalne wycofanie bramkarza następuje wcześniej niż w praktyce —
  Beaudoin & Swartz (2010), Am Stat 64:197–204 — MR [S] (H19); wycofanie
  mniej niż podwaja intensywność drużyny przegrywającej i ~czterokrotnie
  zwiększa rywala — Asness & Brown (2018), SSRN 3132563 — MR (model) [S]
  (H20); od sezonu 2014-15 bramkarzy wycofuje się wcześniej → więcej goli do
  pustej — ESPN 2022 — PC [S] (H21). Nasz model ma już empty-net 0,2 /
  6-na-5 0,05 przy prowadzeniu 1–2 golami (tune 0,20558 → 0,20514).
- Efekt wyniku (prowadzący oddaje strzały) — score-adjusted Corsi, hockeyviz
  — PC [S] (H22). Ma znaczenie dla propsów strzałów: drużyna prowadząca
  strzela mniej.
- Punkt za porażkę w OT zwiększył odsetek remisów w regulaminie — „Fit to be
  tied” — MR [S], autorzy niepotwierdzeni (H23).
- Odpoczynek: brak recenzowanej pracy dla NHL; RotoWire: back-to-back +
  strefy czasowe 46,8% vs 49,5% — PC (H24); 1 409 startów bramkarzy w
  back-to-back bez spadku save% (selekcja: trener wystawia rezerwowego) —
  PC (H25).

**Efektywność rynku.**
- Odwrócony faworyt–longshot (opłacalni underdogowie) w NHL 1990–96 —
  Woodland & Woodland (2001), Southern Econ J 67(4):983–995 — MR [S] (H26);
  nadal istotny, mniejszy — Gandar, Zuber, Johnson (2004), JSE 5(2):152–168
  — MR [S] (H27).
- **Skrzywienie na „under” w totalach NHL**, zwłaszcza przy wysokich liniach —
  Woodland & Woodland (2010), Economics Bulletin 30(4) — MR [S] (H28).
- Bukmacherzy nie równoważą księgi; gracze przeceniają (wyjazdowych)
  faworytów — Paul & Weinbach (2012), J Econ Finance 36(1):123–135 — MR
  (H29); efekty informacyjne zniekształcają ceny NHL — Ryan, Gramm, McKinney
  (2012/13), J Gambling Bus & Econ 6(1) — MR [W] (H30).

### A.2 Koszykówka

**Wynik, totale, handicapy.**
- Różnica punktów jako ruch Browna z dryfem (493 mecze NBA) — Stern (1994),
  JASA 89(427):1128–1134 — MR [S] (B1); implikowana zmienność meczu z
  handicapu i kursu na zwycięzcę — Polson & Stern (2015), JQAS 11(3):145–153
  — MR (metoda) [S] (B2).
- Zdobywanie punktów to słabo obciążone błądzenie losowe, odstępy prawie bez
  pamięci (6 087 meczów) — Gabel & Redner (2012), JQAS 8(1),
  https://arxiv.org/abs/1109.2825 — MR [W] (B3); „bezpieczne prowadzenie” —
  Clauset, Kogan, Redner (2015), Phys Rev E 91:062815,
  https://arxiv.org/abs/1503.03509 — MR [W] (B4); w większości Poisson,
  ale bliskie końcówki z ogonem potęgowym — Martín-González i in. (2016),
  Physica A 464:182–190 — MR [S] (B5).
- **Remis po regulaminie ~2,7× częstszy, niż przewiduje model gaussowski**
  (6,26% vs 2,29%; skok w ostatnich 40 s) — Ely / Hinnosaar (2009),
  https://cheaptalk.org/2009/06/10/the-overtime-spike-in-nba-basketball/ —
  PC (ekonomiści, dane) [W] (B6). Wniosek: rozkład normalny różnicy
  zaniża dogrywkę i wąskie marginesy — a wszystkie pełnomeczowe linie kosza
  na Superbecie są „(z dogrywką)”.
- Posiadania, tempo, ORtg/DRtg, cztery czynniki, usage — Kubatko, Oliver,
  Pelton, Rosenbaum (2007), *A starting point for analyzing basketball
  statistics*, JQAS 3(3) — MR (metodologia) [S] (B7); Oliver (2004),
  *Basketball on Paper*; wzory:
  https://www.basketball-reference.com/about/glossary.html — PC standard [W]
  (B8). Cztery czynniki działają nieliniowo, z interakcjami — Poropudas &
  Halme (2023), https://arxiv.org/abs/2305.13032 — MR [W] (B9).
- Dwuwymiarowy rozkład normalny wyników drużyn (researchgate 328934883) — MR
  [S] (B12). Nasz pomiar: wspólny szok meczu (tempo) cov 1,57 > wewnątrz
  drużyny 0,73 na kwartę — to ta sama struktura.
- Elo FiveThirtyEight (K=20, mnożnik MOV, gospodarz 100 Elo ≈ 3,5 pkt) —
  **niezweryfikowane** (strona nie istnieje) (B10); „σ marginesu NBA ≈ 12”
  z *Mathletics* (Winston 2009) — **niepotwierdzone** (B11).
- Odpoczynek > 1 dzień: +1,1 pkt (gospodarz) / +1,6 (gość); przewaga
  gospodarza spadła z ~6 do ~3 pkt w 8 lat — Steenland & Deddens (1997),
  Sleep 20(5):366–369 — MR [S] (B13); nieliniowa interakcja odpoczynku i
  gospodarza — Wang i in. (2023), Chaos Solitons Fractals 174:113698 — MR
  [S] (B14); mniejsza przewaga bez publiczności (bańka) — Higgs & Stavness
  2021, Leota 2021 — MR, z drugiej ręki (B15). Nasz pomiar back-to-back:
  +0,06 pkt, se 0,64 — nie włączony.

**Zawodnicy (propsy) — tu literatura jest najcieńsza.**
- Standard praktyków: projekcja minut × stawka na minutę, rozkład ujemny
  dwumianowy (NB2) dla nadmiernie rozproszonych liczników — PC (B22).
- Gospodarz, odpoczynek i rywal przewidują wynik zawodnika ponad pensje DFS
  (efektywność odrzucona) — Paul, Weinbach, Losak (2020), J Prediction
  Markets 14(2), https://www.ubplj.org/index.php/jpm/article/view/1813 — MR
  [W] (B17); profesjonalne projekcje fantasy obniżają błąd naiwny o < 10%,
  nieobciążoność odrzucona dla 3 z 4 dostawców — J Econ Finance (2023) — MR
  [S] (B18).
- „Gorąca ręka” istnieje po korekcie obciążenia — Miller & Sanjurjo (2018),
  Econometrica 86(6):2019–2047 — MR [S] (B19). Efekt mały; nie podstawa
  modelu propsów.
- Definicja „garbage time” (minuty w rozstrzygniętym meczu) — Cleaning the
  Glass — PC [S] (B20). Istotne dla minut gwiazd przy dużym handicapie.
- DataStreak: 8 681 propsów punktowych NBA, over trafił w 46,1% — PC [S]
  (B21). Kierunkowo jak nasze −6 pp z §0.
- **LUKA: brak recenzowanej pracy o efektywności rynku propsów NBA/NHL ani o
  ich marżach.**

**Efektywność rynku.**
- Gracze wolą „over”; undery przy wysokich totalach > 52,4%, ale nieistotnie
  zyskowne — Paul, Weinbach, Wilson (2004), QREF 44(4):624–632 — MR (B25);
  2012–19 rynek bardziej efektywny — Moore (2021), QREF 82:26–29 — MR [W]
  (B26); faworyci przeceniani, duzi underdogowie-gospodarze — Paul &
  Weinbach (2005), JSE — MR [S] (B27); na początku sezonu undery 58,2% w 1.
  tygodniu — Girdner i in. (2013), J Prediction Markets 7(2) — MR [W] (B28).
- **Brak akademickiego badania efektywności rynku koszykówki europejskiej**
  (B29).

### A.3 Siatkówka

- Dokładne prawdopodobieństwa seta i meczu z prawdopodobieństw wygrania
  wymiany przy własnym serwisie i przy przyjęciu — Ferrante & Fonseca
  (2014), *On the winning probabilities and mean durations of volleyball*,
  JQAS 10:91–98 — MR [S] (V1); uogólnienie na model Markowa per rotacja —
  González-Cabrera, Herrera, González (2020), JQAS 16(1):41–55 — MR [S] (V2).
- Side-out 69,3% mężczyźni / 64,9% kobiety (MŚ 2003); prowadzenie 3 pkt przy
  20 wygrywa seta w ≥ 90% (mężczyźni) — Ogawa & Kurogo (2005), J Volleyball
  Sci 7(1) — MR [W] (V3). Nasz pomiar użył side-out 0,62 i model serwisu
  przegrał zwycięzcę — odrzucony.
- Hierarchiczny model bayesowski wyników — Gabrio (2021), J Appl Stat
  48(2):301–321, https://arxiv.org/abs/1911.08791 — MR [W] (V4).
- **Model łączny: zwycięzca seta logistycznie + punkty przegranego jako ucięty
  NB z inflacją Poissona** — Egidi & Ntzoufras (2020), JRSS-C,
  https://arxiv.org/abs/1911.01815 — MR [W] (V5); modele różnicy setów —
  Ntzoufras, Palaskas, Drikos (2021), IMA JMM,
  https://arxiv.org/abs/1911.04541 — MR [W] (V6). Te modele potrzebują
  **tylko wyników setów**, które już mamy w cache.
- Ważność umiejętności (siatkówka kobiet) — Miskin, Fellingham, Florence
  (2010), JQAS 6 — MR [S] (V7); „gorąca ręka” istnieje na poziomie zawodnika
  — Raab, Gula, Gigerenzer (2012), J Exp Psychol Applied 18(1):81–94 — MR [S]
  (V8) — argument przeciw niezależności wymian; po czasie side-out wraca do
  bazowego — Huynh i in. (2025), J Human Sport & Exercise 20(3) — MR [W]
  (V9).
- **Brak akademickiego badania efektywności rynku zakładów na siatkówkę.**

### A.4 Efektywność rynków — ogólnie

- Ceny są efektywne w pierwszym przybliżeniu — Sauer (1998), JEL
  36(4):2021–2064 — MR (przegląd) (M1); bukmacher wykorzystuje preferencje
  graczy zamiast równoważyć księgę — Levitt (2004), Economic Journal
  114:223–246 — MR (M2); przegląd efektywności handicapów — Vandenbruaene i
  in. (2022), JSE — MR (M3).
- **Jednosezonowe „nieefektywności” są zgodne z przypadkiem; żadna nie
  utrzymuje się przez 14 sezonów** — Winkelmann i in. (2024), JSE
  25(1):54–97 — MR [W] (M4). Najważniejsze ostrzeżenie dla §0.
- Faworyt–longshot, teoria — Whelan (2024), Economica — MR (M5).
- Opublikowana przewaga w tenisie to głównie jeden zakład z błędnym kursem —
  Clegg & Cartlidge (2025), IJF 41(2):798–802,
  https://arxiv.org/abs/2306.01740 — MR [W] (M6).
- Gra przeciw „miękkim” bukmacherom z konsensusem kursów zamknięcia była
  zyskowna, konta ograniczano — Kaunitz, Zhong, Kreiner (2017),
  https://arxiv.org/abs/1710.02824 — MR [W] (M7); Ramesh i in. (2019),
  https://arxiv.org/abs/1910.08858 — MR słaby (M8).
- Gdzie bukmacherzy są najsłabsi — **stan dowodów:** recenzowane prace
  dotyczą głównie sides/totals w NBA/NHL i są stare (1990–2010); propsy
  zawodników i niższe ligi to dziś **twierdzenia praktyków**, bez pracy
  recenzowanej (B29, luka propsów). Nasze −6 pp na OVER zawodników to
  jedyny lokalny pomiar i jest podejrzeniem.

### A.5 Praktyka ewaluacji

- Reguły właściwe (proper scoring) — Gneiting & Raftery (2007), JASA
  102(477):359–378 (E1); dekompozycja Briera na kalibrację / rozdzielczość /
  niepewność — Murphy (1973) (E2); paski spójności na diagramach
  niezawodności — Bröcker & Smith (2007), Weather & Forecasting 22:651–661
  (E3); log-score lepszy od Briera i RPS w symulacji — Wheatcroft (2021),
  JQAS 17(4), https://arxiv.org/abs/1908.08980 [W] (E4).
- Zdejmowanie marży: Shin lepszy od normalizacji — Štrumbelj (2014), IJF
  30(4):934–943 [W cytat] (E5); GLM faworyt–longshot z samych kursów bije
  multiplikatywną / Shin / potęgową na 90 014 meczach piłki — Goto, Takeishi,
  Yairi (2026), https://arxiv.org/abs/2604.17194 — preprint [W] (E6). Nasz
  `measure_devig.py`: potęgowa zostaje (0,20047 vs Shin 0,20038 vs
  proporcjonalna 0,20088).
- NBA: odkorelowanie modelu od bukmachera + portfel → zysk — Hubáček,
  Šourek, Železný (2019), IJF 35(2):783–796 [W] (E7). **Wybór modelu po
  kalibracji, nie trafności**: ROI NBA +34,69% vs −35,17% — Walsh & Joshi
  (2024), https://arxiv.org/abs/2303.06021 [W] (E8). To jest podstawa reguły
  z §B.1.
- CLV: efektywność kursów zamknięcia Pinnacle (piłka) — Buchdahl (2016) — PC
  odtwarzalne (E9); **brak recenzowanej walidacji CLV dla hokeja / kosza /
  siatki** (E10).
- Testy poza próbą, rolling origin — Tashman (2000), IJF 16(4):437–450 (E11);
  **bootstrap klastrowy przy 5–30 klastrach odrzuca za często** — Cameron,
  Gelbach, Miller (2008), REStat 90(3):414–427 (E12). U nas: klastry =
  mecze (dziesiątki–setki), ale dni to 2–3 klastry — za mało, by
  bootstrapować po dniach, i to trzeba mówić. Ramy ML dla sportu — Bunker &
  Thabtah (2019) (E13). Bardzo wysoka trafność = przeciek (H9).

### A.6 Czego nie znaleziono

Whelan & Wodon, Sarkar/Simmons, Lee & Chin (siatkówka), Dixon–Coles dla
hokeja, recenzowanych badań odpoczynku w NHL, **żadnej pracy o efektywności
rynku propsów**, żadnej o rynku siatkówki ani koszykówki europejskiej.

---

## A.7 Dane: co da Sofascore, a czego nie

Sprawdzone na cache (`data/sofa.db`, tylko odczyt, 2026-10-02):

| endpoint | co ma (hokej / kosz / siatka) | w cache dziś |
|---|---|---|
| `/team/{id}/events/last/{p}` (listingi) | `homeScore.period1..N`, `normaltime`, `overtime`, `penalties`, `winnerCode`, `status.description` (Ended/AET/AP), `startTimestamp`, `tournament.uniqueTournament`, `hasEventPlayerStatistics` | 27 151 / 46 253 / 14 061 zakończonych meczów w listingach |
| `/event/{id}` | to samo + `defaultPeriodLength`, `defaultOvertimeLength`, `roundInfo`, `season`, (kosz) `officials` | 139 / 137 / 40 (z SHADOW_SETTLE) |
| `/event/{id}/lineups` | **hokej**: `secondsPlayed`, `shots`, `goals`, `assists`, `points`, `powerPlay*`, `shortHanded*`, `evenStrength*`, `plusMinus`, `hits`, `blocked`, `faceOffWins/Taken`, `giveaways`, `takeaways`, `penaltyMinutes`, bramkarz: `saves`, `shotsAgainst`, `savePercentage` (też per stan liczebny); `position` C/L/R/D/G. **kosz**: `secondsPlayed`, `points`, `rebounds` (+off/def), `assists`, `steals`, `blocks`, `turnovers`, `personalFouls`, `fieldGoal*`, `threePoint*`, `twoPoint*`, `freeThrow*`, `plusMinus`; Euroliga dodatkowo `usage`, `pir`, `trueShootingPercentage`. **siatka**: nie sprawdzone (brak w cache). | 4 hokej (NHL), 7 kosz (NBL, Euroliga, BBL, WNBA), 0 siatka |
| `/event/{id}/statistics` | **kształt nieznany dla tych sportów** — nigdy nie pytany; trzeba odczytać po pierwszym kawałku backfillu | 0 / 0 / 0 |

`hasEventPlayerStatistics = True` w listingach (730 dni): hokej 6 793 z
23 120 (NHL, Liiga, Extraliga, SHL, Tipsport Liga, CHL, KHL), kosz 29 740 z
37 328, siatka 1 064 z 10 381 (`None` to „nie podano”, nie „nie ma” — nie
filtrujemy po nim, bo tego nie zmierzono). Uwaga: `confirmed: false` w
`/lineups` dla NBL/BBL — skład nie był potwierdzony nawet po meczu.

**Czego nie dostaniemy:** play-by-play z lokalizacją strzałów (xG, H17),
czas na lodzie per stan liczebny poza tym, co w `/lineups`, dane trackingowe,
newsy o kontuzjach i bramkarzu startowym przed meczem, składy przedmeczowe
(notatka 10-01: **brak składów 9 h przed meczem**; sonda bliżej startu
czeka). Wniosek: model zawodnika musi prognozować minuty z historii, a
nieobecność rozstrzyga reguła Superbetu — **zawodnik, który nie zagrał, ma
zakład zwrócony (DNP → VOID, `shadow.player_value`)**, więc ryzykiem nie jest
nieobecność, lecz zmiana roli (ograniczenie minut, powrót po kontuzji,
nieobecny kolega przejmujący posiadania), o której rynek wie, a my nie.

---

## B. Projekt per sport

### B.1 Reguła awansu (zastępuje „blend CI < 0”)

> Dopisek 2026-10-05: reguła poniżej była napisana dla wycofanych kuponów
> sportowych. Na jednym kuponie model wchodzi inaczej — przez krzywą
> `config/sofa_sport_confidence_calibration.json` i warunek F6 (pewność poza
> próbą nie wyższa od zrealizowanej o > 3 pp w kubełkach z n ≥ 200), opisany
> w planie `PLAN_2026-10-05_SETTLE_I_KUPON.md`, część 5.

Model nogi `p_model` przechodzi z pomiaru do **selekcji w kuponie sportowym**
(nigdy do kuponu oficjalnego), gdy na **≥ 2 rozliczonych dniach** i
**≥ 30 meczach** danej rodziny (rodzina = `family` z `shadow.MARKETS` /
`PLAYER_MARKETS`):

1. **Skalibrowany** na rozliczonych liniach:
   - diagram niezawodności w kubełkach `p_model` (np. 0–0,3 / 0,3–0,45 /
     0,45–0,55 / 0,55–0,7 / 0,7–1), w każdym kubełku z ≥ 20 liniami
     przedział bootstrapu **po meczach** dla (średnie `p_model` − trafienie)
     zawiera 0;
   - nachylenie kalibracji (`y ~ logit p_model`) z przedziałem zawierającym 1;
   - **obie połówki** po parzystości `sofascore_event_id` dają ten sam obraz
     (żadna nie łamie powyższego) — tani test, czy wynik nie jest jednym
     wieczorem;
   - kalibracja mierzona **w podzbiorze wybranym** przez selektor, nie tylko
     na wszystkich liniach: model skalibrowany średnio może być przeszacowany
     dokładnie tam, gdzie się rozjeżdża z ceną (notatka „disagreement with
     the price is an anti-signal”, 88 tys. wierszy piłki).
2. **EV przy oferowanym kursie nie gorsze niż −10%**:
   `EV = p_model × kurs − 1 ≥ −0,10` dla każdej wybranej nogi (ex ante), oraz
   zrealizowany zwrot wybranych nóg `mean(y × kurs − 1)` ≥ −10% (punkt), z
   przedziałem bootstrapu po meczach **raportowanym** obok.
3. **Raportowane zawsze, nie bramkujące:** odległość od ceny
   (`p_model − fair_p`, średnia i rozkład), Brier modelu vs Brier `fair_p`,
   test kombinacji b (`measure_model_information.py`), CLV
   (`capture_closing.py` / `audit_clv.py`), marża grupy.

Arytmetyka, którą trzeba znać: noga wzięta dokładnie po cenie bez marży ma
średnio `EV ≈ 1/(1+m) − 1 ≈ −m/(1+m)` (m = overround grupy; metoda
potęgowa przesuwa marżę z faworyta na longshota, ale średnio tyle). Stąd:
linie dwudrogowe drużyn (m 4–6%) ≈ −4…−6%, propsy hokeja (6–7%) ≈ −6…−7%,
propsy kosza (8–8,6%) ≈ −7,5…−8%, 1X2 (9–11%) ≈ −8,5…−10%, dokładny wynik
w setach (19%) ≈ −16%. Wniosek: na liniach drużyn próg −10% zostawia
skalibrowanemu modelowi kilka punktów zapasu, na propsach kosza już tylko
~2 pp (model przeszacowany o 2 pp w wybranym podzbiorze wystarczy, by
wypaść), na 1X2 próg leży na samej marży, a dokładny wynik w setach nie
przejdzie go bez modelu wyraźnie lepszego od ceny. **Wiążąca jest
kalibracja w wybranym podzbiorze** — i to, że selektor powinien preferować
rynki o niskiej marży.

Etykiety zostają: wiersz z modelu niesie `UNFITTED_CONSTANTS` dopóki stałe
nie zostały dopasowane poza próbą, a kupon sportowy pozostaje
„eksperymentalny” i rozliczany osobno (`settle_sport_coupon.py`, ledger per
wariant) — historyczne: kupony sportowe wycofane 2026-10-05; od tego dnia
nogi tych sportów rozlicza 7c kuponu (tabela sportów mierzonych, po
przypiętym id).

### B.2 Wspólne zasady pomiaru

- Ocena przez to samo `shadow.actual_value` / `shadow.player_value` /
  `shadow.grade`, którym ocenia `SHADOW_SETTLE` (semantyka linii:
  regulamin vs dogrywka, DNP → VOID, push).
- Narzędzie w stylu `measure_score_model.py`: model budowany z historii
  **ściśle sprzed dnia**, `p_model` obok `fair_p`, Brier i bootstrap po
  meczach; nowa flaga `--players` dla rodzin zawodników i wypis kalibracji
  w kubełkach + połówki po parzystości id.
- Podział czasu (strojenie): sezon NHL / Euroligi trwa od października do
  czerwca, więc lato nie jest próbą testową dla propsów tych lig. Plan:
  **strojenie 2025-10-01..2026-02-28, test 2026-03-01..2026-06-30** (sezon
  2025-26), potem pomiar na żywo od 2026-10 na liniach Superbetu. Ligi letnie
  (WNBA, NBL, ligi skandynawskie latem) wchodzą do testu osobno i nie są
  łączone z zimowymi bez etykiety.
- Przeciek: `/lineups` to dane **po meczu** (`secondsPlayed` meczu, który
  prognozujemy, nie może być cechą; `substitute`/starter też jest post hoc).
  Cechy wyłącznie z meczów sprzed startu. Cena Superbetu nie jest cechą
  modelu kalibrowanego (inaczej porównanie z ceną staje się kołowe); blend
  liczymy osobno.
- Klastry: bootstrap po meczach; przy 2–3 dniach bootstrap po dniach jest
  niewiarygodny (E12) — raportujemy liczbę dni i mówimy to wprost.

### B.3 Hokej — pierwszy: propsy strzałów i obron bramkarza, potem punkty zawodnika

**Dlaczego:** zwycięzcy nie niosą informacji ponad cenę (b ≤ 0), totale
niosą (b 0,98); propsy to miejsce, gdzie literatura nie pokazuje efektywnego
rynku (luka), Superbet bierze na nich 6,3–7,2% marży, a OVER zawodników
trafiał o 6 pp rzadziej niż cena (§0, podejrzenie). Strzały i obrony to
liczniki o dużej liczbie zdarzeń (mniejszy szum niż gole/punkty), związane
z totalem, w którym nasz model ma informację.

**Model (kolejność budowy):**
1. **Strzały celne zawodnika** (`230023`, klucz `shots`):
   `E[strzały] = TOI_prog × stawka_na_60 × korekta_rywala`, gdzie
   `TOI_prog` = ważona średnia `secondsPlayed` z ostatnich ~10 meczów
   (z obcięciem meczów z kontuzją/karą meczu), `stawka_na_60` shrinkowana
   do pozycji (C/L/R/D) i drużyny (gamma–Poisson ⇒ rozkład NB),
   `korekta_rywala` = strzały dopuszczane przez rywala / średnia ligi (z
   sumy `shots` zawodników rywala w jego meczach albo z `/statistics`, gdy
   poznamy kształt). Efekt wyniku (H22): prowadzący strzela mniej — przez
   oczekiwaną różnicę z `score_model`.
2. **Obrony bramkarza** (`230026`, `saves`): `saves = strzały rywala −
   gole wpuszczone`; strzały rywala z modelu z pkt 1 sumowanego po drużynie,
   gole z `score_model` (Poisson regulaminowy + OT). Skuteczność obron
   **mocno shrinkowana do ligi** (powtarzalność ~0,12, H16; brak gorącej
   ręki, H14). Bramkarz, który nie zagrał → VOID; zmieniony w trakcie →
   liczy się, więc ryzyko to zejście po 3–4 golach (modelować jako
   mieszaninę).
3. **Punkty / asysty / PP-punkty zawodnika** (`236265`, `236264`, `232584`):
   `P(punkty ≥ k)` z Poissona o intensywności `udział_w_golach_drużyny ×
   E[gole drużyny]`, udział z historii (`points` / gole drużyny, gdy na
   lodzie — przybliżenie: na mecz), gole drużyny z `score_model` (tam jest
   informacja). PP-punkty dodatkowo przez kary — których nie mamy per mecz
   bez `/statistics`; do tego czasu rodzina zostaje na cenie.
4. Totale drużyn (regulamin) — istniejący model, tylko nowa reguła §B.1.

**Wejścia z Sofascore:** `/event/{id}/lineups` (klucze wyżej), listingi
(wynik, okresy), `/event/{id}/statistics` (strzały drużyny, kary — kształt
do potwierdzenia).
**Ryzyka:** brak składów przedmeczowych (rola zawodnika: przesunięcie do
innej formacji/PP to rzecz, którą rynek zna); bramkarz startowy nieznany
(dla obron VOID chroni, dla strzałów rywala nie); NHL linie tylko
„(z dogrywką)” — model musi doliczyć OT (OT 3-na-3 ma inną stawkę strzałów;
na start: skalowanie czasem). Mała liczba meczów z propsami (10 meczów w 3
dni, głównie NHL) — awans nie wcześniej niż po ~3 tygodniach sezonu NHL.

### B.4 Koszykówka — pierwszy: propsy punktów/zbiórek/asyst/trójek przez minuty × tempo

**Dlaczego:** największy wolumen propsów (25 meczów / 3 dni, ~1 400 linii
OVER), OVER −6 pp względem
ceny (§0, podejrzenie, zgodne z B21/B25), a totale niosą informację (b 0,70)
— tempo meczu, które już modelujemy (`bb_game_sd`), jest wspólnym czynnikiem
wszystkich propsów jednego meczu. Koszt: marża propsów 8,0–8,6% zostawia
pod progiem −10% tylko ~2 pp zapasu (§B.1), więc kalibracja musi być
ścisła, a totale drużyn (m ~5%) są bezpieczniejszym pierwszym rynkiem dla
selekcji, jeśli propsy nie przejdą.

**Model:**
1. **Minuty**: ważona średnia `secondsPlayed` z ostatnich ~10 meczów,
   korekta na oczekiwany margines z `score_model` (duży handicap ⇒ mniej
   minut gwiazd, „garbage time”, B20), mieszanina z małą masą „krótkiego
   meczu” (faule, uraz). DNP → VOID.
2. **Stawki na minutę** (`points`, `rebounds`, `assists`, `threePointsMade`,
   `steals`, `blocks`): shrinkowane do pozycji i drużyny; korekta tempa =
   oczekiwane posiadania meczu / średnia ligi (posiadania z `/statistics`
   albo z sumy box score: FGA + 0,44·FTA − ORB + TO, B7/B8); korekta rywala
   przez DRtg / zbiórki dopuszczane.
3. **Rozkład**: NB dla zbiórek, asyst, trójek, przechwytów, bloków; punkty
   jako NB lub normalny z wariancją zmierzoną; **kombinacje (P+R+A, P+R, P+A,
   R+A) symulowane łącznie** z jednym szokiem tempa meczu i szokiem minut
   zawodnika (te same minuty mnożą wszystkie składniki — nie wolno ich
   traktować jako niezależnych).
4. **Dogrywka**: wszystkie propsy są „(z dogrywką)”; prawdopodobieństwo OT
   **kalibrowane empirycznie** (model gaussowski zaniża remis ~2,7×, B6).
5. Usage (Euroliga ma `usage` w `/lineups`): gdy kolega z wysokim usage
   nie gra — nie wiemy tego przed meczem (brak składów), więc nie
   modelujemy redystrybucji; to ryzyko, które zostaje.

**Wejścia:** `/lineups` (klucze wyżej), listingi, `/statistics`
(posiadania/tempo drużyny, gdy poznamy kształt).
**Ryzyka:** zmiana roli i ograniczenia minut (rynek wie), `confirmed: false`
w niektórych ligach (box score może się zmienić — backfill nie pyta meczów
młodszych niż 72 h), homonimy nazwisk (`build_player_box` już je usuwa),
ligi z niepełnym box score (suma punktów ≠ wynik → `ok=False`, linie nie
oceniane).

### B.5 Siatkówka — pierwszy: model wyniku setów Egidi–Ntzoufras na samych wynikach

**Dlaczego:** Superbet nie wystawia propsów zawodników w siatkówce
(`PLAYER_MARKETS["volleyball"]` puste), `/lineups` dla siatki nie jest
sprawdzony, a `hasEventPlayerStatistics` jest prawdziwe dla 10% meczów.
Najlepiej udokumentowany model (V5, V6) potrzebuje **tylko wyników setów**,
które już mamy — nie potrzebuje backfillu. Nasz model serwisu (side-out
0,62) przegrał zwycięzcę, ale poprawił total setów — zgodnie z tym, że
totale, nie zwycięzcy, niosą informację.

**Model:** zwycięzca seta logistycznie z ratingu (istniejący RatingBook na
punktach/set), punkty przegranego seta jako ucięty NB z inflacją przy
„deuce” (Egidi & Ntzoufras 2020), set decydujący do 15. Rynki docelowe:
total setów (`230058`), total punktów (`230060`), punkty seta (`782`),
dogrywka seta „na przewagi” (`100077`), dokładny wynik (`785` — marża 19%,
EV po samej cenie ≈ −16%, więc §B.1 pkt 2 wyklucza go, dopóki model nie
jest wyraźnie lepszy od ceny).
**Wejścia:** listingi (period1..5). `/statistics` (asy, błędy serwisu,
skuteczność przyjęcia) tylko jeśli kształt okaże się użyteczny —
ewentualnie do modelu side-out per drużyna (V1, V3).
**Ryzyka:** mała próba na żywo (16–40 meczów w 3 dni), ligi kobiece
dominują w historii (NCAA Women 5 026 meczów) — rating i krzywe muszą być
rozdzielone klasą (`women`, jak w piłce, CLAUDE.md „pooled number must say
what it pooled across”).

### B.6 Kolejność prac

1. Backfill `/statistics` + `/lineups` hokej i kosz (§C), w kawałkach
   7 min; siatka tylko `/statistics` (bez `--with-lineups`), po
   sprawdzeniu kształtu na pierwszym kawałku.
2. `measure_score_model.py --players` (kalibracja w kubełkach, połówki,
   EV przy kursie, odległość od ceny) — pomiar wspólny.
3. Hokej: strzały + obrony; kosz: minuty × tempo dla P/R/A/3PM.
4. Siatka: model setów na wynikach (bez danych z backfillu).
5. Powtórzenie pomiaru „OVER −6 pp” na ≥ 2 tygodniach i ≥ 100 meczach,
   zanim ktokolwiek użyje go jako reguły.

---

## C. Backfill: `scripts/sofa/backfill_event_stats.py --sport {hockey,basketball,volleyball} [--with-lineups]`

Od 2026-10-02. Piłka i tenis bez zmian. Różnice dla sportów pomiarowych:
- „zapytano” liczone **per kolumna**: `SHADOW_SETTLE` zapisuje same
  `/lineups` (`statistics_json` NULL) — reguła piłkarska „wiersz istnieje”
  uznałaby takie mecze za 404 statystyk. Dlatego 404 `/statistics` w tych
  sportach zapisuje się jako `{}`;
- `--with-lineups` pyta też `/lineups` (404 → `{}`, fakt „nic nie
  opublikowano”); jałowe ligi (25 pudeł bez trafienia) liczone osobno per
  trasa;
- mecze młodsze niż 72 h (`PROVISIONAL_FETCH_HOURS`) i sparingi pomijane;
- `--board-days N` czyta tablice pomiaru (`runs/sofa/shadow/<sport>/<d>/`):
  identyfikatory drużyn z zapisanego `/event` rozliczonych meczów i nazwy
  z `snapshots.jsonl` zweryfikowane już przez RESOLVE (`sofa_entity`).

Dry-run 2026-10-02 (`--days 730 --with-lineups`, tylko odczyt):

| sport | zakończone mecze w listingach | cele | `/statistics` | `/lineups` | żądania |
|---|---|---|---|---|---|
| hokej | 27 151 | 21 985 | 21 985 | 21 985 | 43 970 |
| kosz | 46 253 | 36 709 | 36 709 | 36 709 | 73 418 |
| siatka | 14 061 | 10 322 | 10 322 | 10 322 | 20 644 |
| razem | | | | | **138 032** |

Czas przy ~12 req/s w kawałkach 7 min pracy / 3 min przerwy (5 040 żądań na
kawałek): hokej ~8,7 kawałka ≈ **1 h 27 min**, kosz ~14,6 ≈ **2 h 26 min**,
siatka ~4,1 ≈ **41 min**; razem ~27 kawałków ≈ **4 h 34 min** zegara. Same
`/statistics` — połowa. To **górna granica**: ligi bez statystyk odpadną
po 25 pudłach (reguła jałowych lig), a `hasEventPlayerStatistics` sugeruje
(niezmierzone), że `/lineups` istnieje dla ~29% meczów hokeja, ~80% kosza i
~10% siatki. Tablice z ostatnich 7 dni dają 262 / 260 / 79 drużyn
(`--board-days 7`) — wariant priorytetowy; jego dry-run nie został
uruchomiony (każdy pełny skan bazy blokował checkpoint trwającego wypełniania
indeksu listingów).
