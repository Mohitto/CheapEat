---
name: rn-cli-sqlite
description: Generuje komponenty i logikę bazy danych offline-first (WatermelonDB) dla React Native CLI z integracją logiki projektu CheapEat.
---
# Instrukcje Architektoniczne i Logiczne

1. STOS TECHNOLOGICZNY:
- Używaj wyłącznie czystego React Native CLI (wersja 0.85+). Kategoryczny zakaz generowania kodu dla Expo.
- Ignoruj ograniczenia sprzętowe PC hosta. Architektura ma być skalowalna i projektowana pod maksymalną wydajność docelowego środowiska mobilnego.

2. WARSTWA DANYCH (OFFLINE-FIRST):
- Używaj wyłącznie @nozbe/watermelondb jako bazy danych.
- Wszystkie modele danych muszą być klasami dziedziczącymi po Model i wykorzystywać natywne dekoratory (@field, @text, @relation, @children).
- Konfiguracja abel.config.js musi zawsze zawierać @babel/plugin-proposal-decorators w trybie legacy: true.

3. RYGOR KODU I WYDAJNOŚĆ UI:
- Bezwzględny zakaz używania ny w TypeScript. Każdy model, zmienna i funkcja wymaga ścisłego typowania.
- Listy danych (feed przepisów, koszyki) renderuj wyłącznie przez @shopify/flash-list z obowiązkowym estimatedItemSize. Zastąpienie FlatList jest obligatoryjne.
- Zakaz halucynowania paczek – używaj wyłącznie zweryfikowanych, stabilnych modułów.

4. MECHANIKA PROJEKTU CHEAPEAT:
- Operacje wyliczania najtańszych koszyków (multi-sklep i single-sklep) realizuj jako wyizolowane algorytmy z najniższą możliwą złożonością obliczeniową.
- Integracja OCR paragonów korzysta z Google ML Kit (on-device).
- Rygor sekwencyjny: zawsze zaczynaj od warstwy Modelu (WatermelonDB), przechodząc przez Kontroler/Logikę, a na końcu implementuj Widok (UI).
