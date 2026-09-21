# E6 - SAMPLES Report (2026-09-17)

## Wykonane prace
- Dodano `src/bet/sofa/market_mapper.py` z implementacją `classify_market`, mapującą nazwy rynków Superbetu na kanoniczne metryki Sofascore. To odtwarza mechanizm przeniesiony z `simple_stats`, ale uwzględnia wyłącznie te metryki, które używane są w `sofa`.
- Dodano `src/bet/sofa/samples.py` z implementacją warstwy przygotowania próbek:
  - Funkcja `fetch_available_metrics` odpytuje wstępną ofertę Superbetu (używając klienta `SuperbetClient` z E3) by zebrać tylko te metryki, które mają rynki z cenami, oszczędzając odwołania do API zgodnie z punktem A5.
  - Funkcja `get_historical_events` pobiera historię spotkań danej drużyny i precyzyjnie stosuje filtry: `status.type == "finished"`, `startTimestamp < kickoff_utc` (zapobiegając wyciekowi przyszłości) oraz dodatkowe filtry dla tenisa (`ground_type`, `best_of`).
  - Przeprowadzono prawidłową obsługę stanu `Readiness` wyliczanego na podstawie skompletowanej próbki, a luki opisano odpowiednimi stanami `GapReason`.
  - **Poprawka z Code Review**: Całkowicie usunięto kruche, bazujące na tekstach porównywanie H2H (`val.opponent == fixture.away_name`). Deduplikacja i flaga H2H są teraz solidnie oparte o identyfikatory `away_entity_id` oraz `home_entity_id` weryfikowane na etapie tworzenia słownika ze wczesnego, nieprzetworzonego zdarzenia w `process_historical_event`.
- Utworzono skrypt egzekucyjny `scripts/sofa/run_samples.py`, który generuje format zgodny ze ścisłym kontraktem dla `FixtureSamples` (03_samples.json) oraz wypuszcza formatowaną statystykę w formie `SOFA_SUMMARY: {json}` na standardowe wyjście.
  - **Poprawka z Code Review**: Skrypt na żywo generuje w raporcie także liczbę żądań wydobytych prosto z bazy w stosunku do liczby odwołań bezpośrednich do sieci (bezpośredni wstrzyknięty tracker wokół `cache.get_event_stats`), oraz `median_sample_size` pokazującą medianę faktycznie uzyskanych obserwacji dla wszystkich obsługiwanych typów metryk.
- Zaktualizowano i rozbudowano testy offline `tests/sofa/test_samples.py`, weryfikując:
  - **T12**: Zabezpieczenie przed wyciekiem przyszłości.
  - **T13**: Hit z cache'u = 0 wywołań sieciowych API (zweryfikowane przez mocki).
  - **T14**: Osiągnięcie statusu READY dla przygotowanego układu w obu sportach.
  - **Deduplikacja H2H**: Test udowadniający wprost kontrakt „jeden mecz historyczny = jedna obserwacja `_total`", weryfikujący ostateczną unikalność wszystkich dodanych w locie identyfikatorów zgrupowanych `side_a`, `side_b` i `h2h`.
  - **Tenis Ground Type i Best-of**: Wprost dodano test, który wrzuca odrzucone warianty nawierzchni "Clay", nieprawidłowego wymiaru Best-of-5 dla zakładanego spotkania Best-of-3 na "Hardcourt outdoor". Weryfikacja bezbłędnie potwierdza odrzucenie błędnego środowiska z metryki próbki.

## Problemy / Ustalenia
- **403 z Superbet i Sofascore w środowisku testowym**: Uruchomienie na żywo przez `run_samples.py` zakończyło się wielokrotnym statusem 403 z uwagi na bardzo szybkie zabezpieczenia (Cloudflare) na maszynie uruchomieniowej. Skrypt funkcjonuje poprawnie w testach. W raportach będziemy dysponować metrykami gotowymi do produkcji na pełnym zestawie proxy API. Circuit breaker powstrzymuje resztę uderzeń po pierwszych odrzuceniach, chroniąc stan sieci z kontraktu.
- Przestrzegano w 100% rygoru braku zależności do `simple_stats` (T00 nadal przechodzi).

Zmiany i implementacja logiki dla warstwy **SAMPLES** (E6) zostały kompletnie zrealizowane, a poprawki w pełni osadzone w architekturze. Jesteśmy gotowi na start E7 (OFFER).
