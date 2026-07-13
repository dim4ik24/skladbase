#!/usr/bin/env node
// Перевіряє повноту locale-файлів frontend/app/src/i18n/locales/{uk,en,ru}.json:
// 1. кожен НЕ-plural ключ uk.json (лист дерева) існує в en.json і ru.json,
//    і навпаки — зайвих ключів нема;
// 2. кожен plural-ключ (._one/_few/_many/_other) звіряється не 1:1, а за
//    plural-категоріями, які реально розрізняє Intl.PluralRules(lang) —
//    en має лише one/other (CLDR), тож en.json НЕ повинен мати _few/_many
//    для plural-ключа, а uk/ru (обидва few/many-мови) — повинні;
// 3. кожна інтерполяція {{x}} зі значення uk присутня в перекладі того самого
//    ключа (для plural-ключів — у кожній наявній для мови категорії).
// uk.json — джерело правди (базова мова, дефолт і фолбек для порожніх ключів).
//
// Використання: node scripts/check-locales.mjs
// Exit code 0 — усе гаразд; 1 — знайдено розбіжності (для CI).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const LOCALES_DIR = path.join(__dirname, "..", "frontend", "app", "src", "i18n", "locales");

const LANGS = ["uk", "en", "ru"];
const TARGET_LANGS = ["en", "ru"]; // перекладаємо з uk у ці мови
const PLURAL_CATEGORIES = ["zero", "one", "two", "few", "many", "other"];
const PLURAL_SUFFIX_RE = new RegExp(`^(.+)_(${PLURAL_CATEGORIES.join("|")})$`);

function loadLocale(lang) {
  const file = path.join(LOCALES_DIR, `${lang}.json`);
  return JSON.parse(readFileSync(file, "utf8"));
}

// Сплющує вкладений об'єкт у Map<"a.b.c", value>. Значення завжди рядки в
// наших locale-файлах (нема масивів/чисел), тож без додаткової перевірки типу.
function flatten(obj, prefix = "", out = new Map()) {
  for (const [key, value] of Object.entries(obj)) {
    const flatKey = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      flatten(value, flatKey, out);
    } else {
      out.set(flatKey, value);
    }
  }
  return out;
}

function interpolations(value) {
  const matches = String(value).matchAll(/\{\{\s*([^}]+?)\s*\}\}/g);
  return new Set([...matches].map((m) => m[1]));
}

function pluralCategoriesFor(lang) {
  return new Set(new Intl.PluralRules(lang).resolvedOptions().pluralCategories);
}

const locales = Object.fromEntries(LANGS.map((lang) => [lang, flatten(loadLocale(lang))]));
const langCategories = Object.fromEntries(LANGS.map((lang) => [lang, pluralCategoriesFor(lang)]));

let errorCount = 0;
function report(message) {
  console.error(`✗ ${message}`);
  errorCount++;
}

// Розбираємо uk-ключі на звичайні та plural-родини (base -> {cat: value}).
const ukPluralFamilies = new Map(); // base -> Map<category, value>
const ukPlainKeys = new Map(); // key -> value

for (const [key, value] of locales.uk) {
  const m = key.match(PLURAL_SUFFIX_RE);
  if (m) {
    const [, base, cat] = m;
    if (!ukPluralFamilies.has(base)) ukPluralFamilies.set(base, new Map());
    ukPluralFamilies.get(base).set(cat, value);
  } else {
    ukPlainKeys.set(key, value);
  }
}

for (const lang of TARGET_LANGS) {
  const langFlat = locales[lang];
  const langKeys = new Set(langFlat.keys());
  const expectedKeys = new Set();

  // 1. Звичайні ключі — 1:1.
  for (const [key, ukValue] of ukPlainKeys) {
    expectedKeys.add(key);
    const translated = langFlat.get(key);
    if (translated === undefined) {
      report(`${lang}.json: бракує ключа "${key}" (є в uk.json)`);
      continue;
    }
    checkInterpolations(lang, key, ukValue, translated);
  }

  // 2. Plural-родини — за категоріями, які реально є в цій мові.
  for (const [base, catMap] of ukPluralFamilies) {
    const neededCats = langCategories[lang];
    for (const cat of neededCats) {
      const key = `${base}_${cat}`;
      expectedKeys.add(key);
      const translated = langFlat.get(key);
      if (translated === undefined) {
        report(`${lang}.json: бракує ключа "${key}" (plural-категорія "${cat}" є для мови "${lang}")`);
        continue;
      }
      // Інтерполяції звіряємо проти БУДЬ-якого uk-варіанта тієї ж родини
      // (усі категорії однієї родини мають однаковий набір змінних, напр. {{count}}).
      const ukReference = catMap.get(cat) ?? catMap.get("other") ?? [...catMap.values()][0];
      checkInterpolations(lang, key, ukReference, translated);
    }
  }

  // 3. Зайві ключі — присутні в lang, але не очікувані (ні як звичайний, ні як потрібна plural-категорія).
  for (const key of langKeys) {
    if (!expectedKeys.has(key)) {
      report(`${lang}.json: зайвий ключ "${key}" (нема в uk.json або зайва plural-категорія для мови "${lang}")`);
    }
  }
}

function checkInterpolations(lang, key, ukValue, translatedValue) {
  const ukVars = interpolations(ukValue);
  if (ukVars.size === 0) return;
  const translatedVars = interpolations(translatedValue);
  for (const v of ukVars) {
    if (!translatedVars.has(v)) {
      report(`${lang}.json["${key}"]: бракує інтерполяції {{${v}}} (є в uk.json: "${ukValue}")`);
    }
  }
}

const totalPlainKeys = ukPlainKeys.size;
const totalPluralFamilies = ukPluralFamilies.size;
if (errorCount === 0) {
  console.log(
    `✓ locales OK — ${totalPlainKeys} звичайних ключів + ${totalPluralFamilies} plural-родин, ` +
      `паритет uk/en/ru (з урахуванням Intl.PluralRules), усі інтерполяції на місці`,
  );
  process.exit(0);
} else {
  console.error(`\n${errorCount} проблем(и) знайдено (з ${totalPlainKeys + totalPluralFamilies} ключів/родин у uk.json)`);
  process.exit(1);
}
