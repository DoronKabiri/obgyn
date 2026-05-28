"""Build the interactive single-case rupture review HTML.

Portable build script — runs on any machine (including closed networks).
Configure paths via CLI args or environment variables; defaults assume
all input files live next to this script.

Usage:
  python3 build_review.py
  python3 build_review.py --data-dir /path/to/data --out my_review.html
  python3 build_review.py --password MySecret

Requirements: pandas, openpyxl, cryptography  (see requirements.txt)

Author: Doron Kabiri.
"""

import argparse
import base64
import json
import os
import re
import sys


# ---- Dependency check with Hebrew error messages ----
def _check_imports():
    missing = []
    for mod in ('pandas', 'openpyxl', 'cryptography'):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.stderr.write(
            '\n*** חסרות חבילות פייתון: ' + ', '.join(missing) + ' ***\n'
            'התקנה (מהטרמינל):\n'
            '  pip install ' + ' '.join(missing) + '\n'
            'או:\n'
            '  python3 -m pip install ' + ' '.join(missing) + '\n\n')
        sys.exit(2)


_check_imports()

import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def _parse_args():
    here = os.path.abspath(os.path.dirname(__file__))
    p = argparse.ArgumentParser(
        description='Build the rupture-review HTML (portable).')
    p.add_argument('--data-dir', default=os.environ.get(
                   'RUPTURE_DATA_DIR', here),
                   help='Folder with input files. Default: this script\'s '
                        'folder. All inputs must be in this folder unless '
                        'overridden individually.')
    p.add_argument('--in-xlsx', default=None,
                   help='Path to rupture_TRUE_only.xlsx')
    p.add_argument('--cohort-xlsx', default=None,
                   help='Path to rupture_full_cohort_extract.xlsx')
    p.add_argument('--bfr-dir', default=None,
                   help='Folder containing v_BFR_25/26/60/61.csv '
                        '(default: same as --data-dir)')
    p.add_argument('--out', default=None,
                   help='Output HTML path '
                        '(default: <data-dir>/rupture_review_INTERACTIVE_v2.html)')
    p.add_argument('--password', default=os.environ.get(
                   'RUPTURE_PASSWORD', 'Rupture'),
                   help='Password for the encrypted payload (default: Rupture)')
    return p.parse_args()


_args = _parse_args()
DATA_DIR = os.path.abspath(_args.data_dir)
IN_XLSX = _args.in_xlsx or os.path.join(DATA_DIR, 'rupture_TRUE_only.xlsx')
COHORT_XLSX = _args.cohort_xlsx or os.path.join(
    DATA_DIR, 'rupture_full_cohort_extract.xlsx')
OUT_HTML = _args.out or os.path.join(
    DATA_DIR, 'rupture_review_INTERACTIVE_v2.html')
BFR_DIR = _args.bfr_dir or DATA_DIR
BFR_25_CSV = os.path.join(BFR_DIR, 'v_BFR_25.csv')
BFR_26_CSV = os.path.join(BFR_DIR, 'v_BFR_26.csv')
BFR_60_CSV = os.path.join(BFR_DIR, 'v_BFR_60.csv')
BFR_61_CSV = os.path.join(BFR_DIR, 'v_BFR_61.csv')

PASSWORD = _args.password.encode('utf-8')
PBKDF2_ITERATIONS = 250_000


def _verify_inputs():
    required = {
        'rupture_TRUE_only.xlsx': IN_XLSX,
        'rupture_full_cohort_extract.xlsx': COHORT_XLSX,
        'v_BFR_25.csv': BFR_25_CSV,
        'v_BFR_26.csv': BFR_26_CSV,
        'v_BFR_60.csv': BFR_60_CSV,
        'v_BFR_61.csv': BFR_61_CSV,
    }
    missing = [(n, p) for n, p in required.items() if not os.path.exists(p)]
    if missing:
        sys.stderr.write('\n*** חסרים קבצי קלט ***\n')
        for name, p in missing:
            sys.stderr.write(f'  - {name}\n    (לא נמצא ב: {p})\n')
        sys.stderr.write(
            f'\nוודאי שכל הקבצים נמצאים בתיקייה {DATA_DIR}\n'
            'או הפעילי עם --data-dir <נתיב>  /  --bfr-dir <נתיב>\n\n')
        sys.exit(3)


_verify_inputs()
print(f'[ok] קבצי קלט נמצאו ב: {DATA_DIR}')
print(f'[ok] פלט יישמר ב:    {OUT_HTML}')
print(f'[ok] סיסמה:            {_args.password!r}')
print()

# Hebrew labels per source table
TABLE_LABELS = {
    'v_BFR_101': 'היסטוריה מיילדותית',
    'v_BFR_103': 'סיכום שחרור',
    'v_BFR_104': 'הוראות שחרור',
    'v_BFR_105': 'דיון רפואי',
    'v_BFR_106': 'הערכה במיון',
    'v_BFR_107': 'סיכום ביקור / קבלה',
    'v_BFR_108': 'קבלה מיילדותית',
    'v_BFR_109': 'דיון רפואי',
    'v_BFR_110': 'מהלך חדר לידה',
    'v_BFR_111': 'מהלך משכב לידה',
    'v_BFR_113': 'סיכום לידה (מיילדת)',
    'v_BFR_114': 'סיכום לידה (רופא)',
    'v_BFR_116': 'סיכום לידה (רופא)',
    'v_BFR_117': 'דוח ניתוח קיסרי',
    'v_BFR_118': 'המלצות',
    'v_BFR_119': 'בדיקה מיילדותית',
    'v_BFR_120': 'קבלה סיעודית',
    'v_BFR_121': 'בדיקה',
    'v_BFR_124': 'דיון רפואי',
}

CLASS_ORDER = ['TRUE_RUPTURE', 'PROBABLE_RUPTURE', 'AMBIGUOUS',
               'NEEDS_TEXT_REVIEW']
CONF_ORDER = {'high': 0, 'medium': 1, 'low': 2}

# Six-category clinical classification
CATEGORIES = [
    {'key': '1', 'he': 'ללא קרע של הרחם',
     'en': 'NO_RUPTURE', 'color': '#9e9e9e'},
    {'key': '2', 'he': 'דהיסנס',
     'en': 'DEHISCENCE', 'color': '#64b5f6'},
    {'key': '3', 'he': 'קרע של הרחם ללא ניסיון לידה',
     'en': 'RUPTURE_NO_LABOR', 'color': '#e53935'},
    {'key': '4', 'he': 'קרע שאובחן בניתוח קיסרי במהלך ניסיון לידה',
     'en': 'RUPTURE_AT_CS_DURING_LABOR', 'color': '#fb8c00'},
    {'key': '5', 'he': 'קרע שאובחן לאחר הלידה',
     'en': 'RUPTURE_POSTPARTUM', 'color': '#8e24aa'},
    {'key': '6', 'he': 'קרע שאובחן במהלך ניתוח קיסרי אלקטיבי',
     'en': 'RUPTURE_AT_ELECTIVE_CS', 'color': '#00897b'},
]


def fix_mojibake(s):
    if not isinstance(s, str):
        return s
    if any('֐' <= c <= '׿' for c in s):
        return s
    try:
        f = s.encode('latin-1').decode('cp1255')
        if any('֐' <= c <= '׿' for c in f):
            return f
    except Exception:
        pass
    return s


def safe_str(v):
    if v is None:
        return ''
    if isinstance(v, float) and pd.isna(v):
        return ''
    s = str(v)
    if s == 'nan' or s == 'NaT':
        return ''
    return s


def fmt_dt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    try:
        return pd.Timestamp(v).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return safe_str(v)


def load_chronological_text(cohort_baz_set):
    """For each BAZ, list of {date, table, text} sorted ascending."""
    xl = pd.ExcelFile(COHORT_XLSX)
    text_tables = [s for s in xl.sheet_names if s.startswith('v_BFR_')]
    frames = []
    for sh in text_tables:
        if sh == 'v_BFR_112':
            continue
        df = pd.read_excel(xl, sh)
        if 'Sikum' in df.columns:
            tc, dc = 'Sikum', 'Sikum_Date'
        elif 'Description_Text' in df.columns:
            tc = 'Description_Text'
            dc = ('Entry_Date' if 'Entry_Date' in df.columns
                  else ('Description_Date' if 'Description_Date' in df.columns
                        else None))
        else:
            continue
        if dc is None:
            continue
        if 'BIRTH_EVENT_BAZNAT' not in df.columns:
            continue
        df = df[['BIRTH_EVENT_BAZNAT', tc, dc]].copy()
        df.columns = ['BAZ_raw', 'text', 'date']
        df['BAZ'] = (pd.to_numeric(df['BAZ_raw'], errors='coerce')
                     .astype('Int64').astype(str))
        df = df[df['BAZ'].isin(cohort_baz_set)].copy()
        df['source'] = sh
        df = df[['BAZ', 'source', 'date', 'text']]
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    full['date'] = pd.to_datetime(full['date'], errors='coerce')
    full['text'] = full['text'].apply(fix_mojibake)
    full = full.dropna(subset=['text'])
    full['text'] = full['text'].astype(str).str.strip()
    full = full[full['text'] != '']
    full = full.sort_values(['BAZ', 'date'], na_position='last')

    out = {}
    for baz, grp in full.groupby('BAZ', sort=False):
        entries = []
        seen = set()
        for _, r in grp.iterrows():
            txt = r['text']
            key = (r['source'], txt[:300])
            if key in seen:
                continue
            seen.add(key)
            d = r['date']
            entries.append({
                'date': '' if pd.isna(d) else
                        pd.Timestamp(d).strftime('%Y-%m-%d %H:%M'),
                'source': r['source'],
                'label': TABLE_LABELS.get(r['source'], r['source']),
                'text': txt,
            })
        out[baz] = entries
    return out


def _baz_str(v):
    try:
        if pd.isna(v):
            return ''
        return str(int(float(v)))
    except Exception:
        s = safe_str(v)
        return s


def load_obstetric_formula(cohort_baz):
    """From v_BFR_26: latest Record_Date per BAZ → G/P/A/EP/CS/LC/VBAC."""
    df = pd.read_csv(BFR_26_CSV, encoding='utf-8-sig')
    df = df[df['BIRTH_EVENT_BAZNAT'].notna()].copy()
    df['BAZ'] = df['BIRTH_EVENT_BAZNAT'].apply(_baz_str)
    df = df[df['BAZ'].isin(cohort_baz)].copy()
    df['Record_Date'] = pd.to_datetime(df['Record_Date'], errors='coerce')
    df = df.sort_values('Record_Date', na_position='first')
    out = {}
    for baz, grp in df.groupby('BAZ'):
        r = grp.iloc[-1]

        def n(col):
            v = r.get(col)
            try:
                if pd.isna(v):
                    return None
                return int(float(v))
            except Exception:
                return None
        out[baz] = {
            'G': n('NumOfPregnancies_G'),
            'P': n('NumOfBirths_P'),
            'A': n('NumOfAbortions_A'),
            'EP': n('NumOfEp_EP'),
            'CS': n('NumOfCaesars_CS'),
            'LC': n('NumOfLiveChildren_LC'),
            'VBAC': n('VBAC'),
        }
    return out


def _parse_birth_week(raw):
    """Birth-week field in BFR_60 is encoded oddly (numbers don't correspond
    to standard week+day for our cohort — sanity-check vs Pregnancy_Age in
    BFR_25 showed mismatch). Try a sensible parse; return '' otherwise.

    A "sensible" week+day means weeks 20–43 and day 0–6.
    """
    s = safe_str(raw).strip()
    if not s:
        return ''
    m = re.match(r'^\s*(\d+)\s*\+\s*(\d+)\s*$', s)
    if not m:
        return ''
    w, d = int(m.group(1)), int(m.group(2))
    if 20 <= w <= 43 and 0 <= d <= 6:
        return f'{w}+{d}'
    return ''


def load_birth_event_meta(cohort_baz):
    """From v_BFR_60: per BAZ, prefer rows with non-null BIRTH_EVENT_BAZNAT,
    then latest Record_Date.

    Columns of interest: שבוע לידה, אופן התחלת לידה, אתר לידה.
    """
    df = pd.read_csv(BFR_60_CSV, encoding='utf-8-sig')
    # Apply mojibake fix on text cells
    for col in ['Unit', 'תאור שלייה', 'אופן התחלת לידה',
                'אופן לידה', 'אתר לידה', 'הערות']:
        if col in df.columns:
            df[col] = df[col].apply(fix_mojibake)
    df['has_birth_baz'] = df['BIRTH_EVENT_BAZNAT'].notna().astype(int)
    df['Record_Date'] = pd.to_datetime(df['Record_Date'], errors='coerce')
    df['BAZ_event'] = df['BIRTH_EVENT_BAZNAT'].apply(
        lambda v: _baz_str(v) if pd.notna(v) else '')
    df['BAZ_id'] = df['ID_BAZNAT'].apply(_baz_str)
    # Map by BIRTH_EVENT_BAZNAT when present; fall back to ID_BAZNAT
    df['BAZ_map'] = df['BAZ_event']
    df.loc[df['BAZ_map'] == '', 'BAZ_map'] = df.loc[df['BAZ_map'] == '',
                                                   'BAZ_id']
    df = df[df['BAZ_map'].isin(cohort_baz)].copy()
    df = df.sort_values(['BAZ_map', 'has_birth_baz', 'Record_Date'])
    out = {}
    for baz, grp in df.groupby('BAZ_map'):
        r = grp.iloc[-1]
        out[baz] = {
            'week_raw': safe_str(r.get('שבוע לידה')),
            'week_parsed': _parse_birth_week(r.get('שבוע לידה')),
            'labor_onset': safe_str(r.get('אופן התחלת לידה')),
            'birth_site': safe_str(r.get('אתר לידה')),
            'delivery_mode': safe_str(r.get('אופן לידה')),
        }
    return out


def load_admission_week(cohort_baz):
    """Latest Pregnancy_Age per BAZ from BFR_25 (admission record)."""
    df = pd.read_csv(BFR_25_CSV, encoding='utf-8-sig')
    if 'Pregnancy_Age' not in df.columns:
        return {}
    df = df[df['BIRTH_EVENT_BAZNAT'].notna()].copy()
    df['BAZ'] = df['BIRTH_EVENT_BAZNAT'].apply(_baz_str)
    df = df[df['BAZ'].isin(cohort_baz)].copy()
    df['Record_Date'] = pd.to_datetime(df['Record_Date'], errors='coerce')
    df = df.sort_values('Record_Date', na_position='first')
    out = {}
    for baz, grp in df.groupby('BAZ'):
        # Prefer the earliest non-empty Pregnancy_Age (admission, not later)
        nonnull = grp[grp['Pregnancy_Age'].notna()]
        if len(nonnull):
            out[baz] = safe_str(nonnull.iloc[0]['Pregnancy_Age'])
    return out


def load_per_baby(cohort_baz):
    """Per-baby outcomes from BFR_61."""
    df = pd.read_csv(BFR_61_CSV, encoding='utf-8-sig')
    text_cols = ['מצג', 'אופן הלידה', 'לידת מת', 'מין',
                 'נסיון לידה נרתיקית', 'דרך חילוץ']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].apply(fix_mojibake)
    df['BAZ_event'] = df['BIRTH_EVENT_BAZNAT'].apply(
        lambda v: _baz_str(v) if pd.notna(v) else '')
    df['BAZ_id'] = df['ID_BAZNAT'].apply(_baz_str)
    df['BAZ_map'] = df['BAZ_event']
    df.loc[df['BAZ_map'] == '', 'BAZ_map'] = df.loc[df['BAZ_map'] == '',
                                                   'BAZ_id']
    df = df[df['BAZ_map'].isin(cohort_baz)].copy()
    df['birth_time'] = pd.to_datetime(df['זמן לידה'], errors='coerce')
    df['baby_num'] = pd.to_numeric(df['מספר ילוד'], errors='coerce')
    df = df.sort_values(['BAZ_map', 'baby_num', 'birth_time'])
    out = {}

    def numv(v):
        try:
            if pd.isna(v):
                return None
            return int(float(v))
        except Exception:
            return None

    for baz, grp in df.groupby('BAZ_map'):
        babies = []
        seen_nums = set()
        for _, r in grp.iterrows():
            bn = r.get('baby_num')
            bn_int = None if pd.isna(bn) else int(bn)
            if bn_int in seen_nums:
                continue
            if bn_int is not None:
                seen_nums.add(bn_int)
            sb_raw = safe_str(r.get('לידת מת'))
            is_stillbirth = (sb_raw == 'כן')
            babies.append({
                'num': bn_int if bn_int is not None else len(babies) + 1,
                'weight': numv(r.get('משקל')),
                'sex': safe_str(r.get('מין')),
                'presentation': safe_str(r.get('מצג')),
                'delivery_mode': safe_str(r.get('אופן הלידה')),
                'apgar1': numv(r.get('אפגר 1 - סכום ערכים')),
                'apgar5': numv(r.get('אפגר 5 - סכום ערכים')),
                'apgar10': numv(r.get('אפגר 10 - סכום ערכים')),
                'stillbirth': is_stillbirth,
                'tol': safe_str(r.get('נסיון לידה נרתיקית')),
                'birth_time': ('' if pd.isna(r.get('birth_time'))
                               else pd.Timestamp(r.get('birth_time'))
                               .strftime('%Y-%m-%d %H:%M')),
            })
        babies.sort(key=lambda b: b['num'] if b['num'] is not None else 99)
        out[baz] = babies
    return out


def build_case_records():
    df = pd.read_excel(IN_XLSX, sheet_name='ALL_584_classified')
    df['BAZ'] = df['BAZ'].astype(str)

    text_cols = ['birth_site', 'labor_onset', 'delivery_mode', 'unit',
                 'admission_text', 'labor_course_text', 'op_report_text',
                 'birth_summary_text', 'postpartum_text', 'discharge_text',
                 'gestation_BFR60_raw']
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].apply(fix_mojibake)

    df = df[df['class'].isin(CLASS_ORDER)].copy()

    cohort_baz = set(df['BAZ'].astype(str))
    print(f'Loading chronological text for {len(cohort_baz)} cases...')
    text_map = load_chronological_text(cohort_baz)
    coverage = sum(1 for b in cohort_baz if b in text_map and text_map[b])
    print(f'  text coverage: {coverage}/{len(cohort_baz)}')

    print('Loading obstetric formula (BFR_26)...')
    formula_map = load_obstetric_formula(cohort_baz)
    print(f'  formula coverage: {len(formula_map)}/{len(cohort_baz)}')
    print('Loading birth-event metadata (BFR_60)...')
    birthmeta_map = load_birth_event_meta(cohort_baz)
    print(f'  birth-meta coverage: {len(birthmeta_map)}/{len(cohort_baz)}')
    print('Loading admission week (BFR_25)...')
    admweek_map = load_admission_week(cohort_baz)
    print(f'  admission-week coverage: {len(admweek_map)}/{len(cohort_baz)}')
    print('Loading per-baby outcomes (BFR_61)...')
    babies_map = load_per_baby(cohort_baz)
    print(f'  per-baby coverage: {len(babies_map)}/{len(cohort_baz)}')

    df['class_rank'] = df['class'].map({c: i for i, c in enumerate(CLASS_ORDER)})
    df['conf_rank'] = df['class_conf'].map(CONF_ORDER).fillna(9)
    df = df.sort_values(['class_rank', 'conf_rank', 'BAZ']).reset_index(drop=True)

    cases = []
    for _, r in df.iterrows():
        baz = str(r['BAZ'])

        def num(v):
            try:
                if pd.isna(v):
                    return ''
                return str(int(float(v)))
            except Exception:
                return safe_str(v)

        parity = (f"G{num(r.get('parity_G'))}"
                  f"P{num(r.get('parity_P'))}"
                  f"CS{num(r.get('parity_CS'))}")
        if 'GP' in parity or parity == 'GPCS':
            parity = ''

        babies = babies_map.get(baz, [])
        any_stillbirth = '1' if any(b['stillbirth'] for b in babies) else '0'

        apgars5 = [b['apgar5'] for b in babies if b['apgar5'] is not None]
        worst_apgar5 = str(min(apgars5)) if apgars5 else ''

        formula = formula_map.get(baz, {})

        def fmt_formula(f):
            if not f:
                return ''

            def s(k):
                v = f.get(k)
                return str(v) if v is not None else '0'
            out = (f"G{s('G')} P{s('P')} A{s('A')} EP{s('EP')} "
                   f"CS{s('CS')} LC{s('LC')}")
            if f.get('VBAC') and f.get('VBAC') > 0:
                out += ' (VBAC)'
            return out

        meta = birthmeta_map.get(baz, {})

        cases.append({
            'baz': baz,
            'cls': safe_str(r.get('class')),
            'conf': safe_str(r.get('class_conf')),
            'ga': safe_str(r.get('gestational_age')),
            'parity': parity,
            'parity_summary': parity,
            'patient': safe_str(r.get('Patient')).replace('.0', ''),
            'mrn': safe_str(r.get('Medical_Record')).replace('.0', ''),
            'admission_dt': fmt_dt(r.get('admission_dt')),
            'delivery_dt': fmt_dt(r.get('delivery_dt')),
            'birth_site': safe_str(r.get('birth_site')) or meta.get(
                'birth_site', ''),
            'unit': safe_str(r.get('unit')),
            'delivery_mode': safe_str(r.get('delivery_mode')) or meta.get(
                'delivery_mode', ''),
            'labor_onset': safe_str(r.get('labor_onset')) or meta.get(
                'labor_onset', ''),
            'n_babies': str(len(babies)) if babies else num(r.get('n_babies')),
            'any_stillbirth': any_stillbirth,
            'worst_apgar5': worst_apgar5,
            # New clinical-snapshot fields:
            'obstetric_formula': fmt_formula(formula),
            'ga_admission': admweek_map.get(baz, '') or safe_str(
                r.get('gestational_age')),
            'ga_delivery': meta.get('week_parsed', ''),
            'meta_labor_onset': meta.get('labor_onset', ''),
            'meta_birth_site': meta.get('birth_site', ''),
            'meta_delivery_mode': meta.get('delivery_mode', ''),
            'babies': babies,
            'n_text_rows': num(r.get('n_text_rows')),
            'in_known_45': (bool(r.get('in_known_45_cohort'))
                            if not pd.isna(r.get('in_known_45_cohort'))
                            else False),
            'timeline': text_map.get(baz, []),
        })
    return cases


def encrypt_payload(cases_json_bytes):
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                    iterations=PBKDF2_ITERATIONS)
    key = kdf.derive(PASSWORD)
    ct = AESGCM(key).encrypt(iv, cases_json_bytes, None)
    blob = salt + iv + ct
    return base64.b64encode(blob).decode('ascii')


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head>
<meta charset="utf-8">
<meta name="author" content="Doron Kabiri">
<title>סקירת קרעי רחם — סיווג ב-6 קטגוריות (317 מקרים)</title>
<style>
* { box-sizing: border-box; }
html, body { margin:0; padding:0; height:100vh; overflow:hidden;
             font-family: Arial, "David Libre", "Segoe UI", sans-serif;
             direction: rtl; background:#eef1f5; color:#1c2733; }

/* ---------- gate (password) ---------- */
#gate { position:fixed; inset:0; z-index:1000; background:#0e1f33;
        display:flex; align-items:center; justify-content:center;
        color:#fff; }
#gate .panel { background:#15324f; padding:38px 46px; border-radius:14px;
               box-shadow:0 8px 32px rgba(0,0,0,.45); max-width:420px;
               text-align:center; }
#gate h2 { margin:0 0 8px; font-size:22px; }
#gate p  { margin:0 0 18px; color:#bcd0e6; font-size:14px; line-height:1.5; }
#gate input[type=password] {
  width:100%; padding:11px 14px; border-radius:8px; border:1px solid #2a5483;
  background:#0d2540; color:#fff; font-size:16px; text-align:center;
  font-family:inherit; letter-spacing:.5px; }
#gate input[type=password]:focus { outline:2px solid #4fa3e3; }
#gate button { margin-top:14px; padding:10px 22px; border:none;
               background:#2196f3; color:#fff; border-radius:8px;
               font-size:15px; font-weight:600; cursor:pointer;
               font-family:inherit; }
#gate button:hover { background:#1976d2; }
#gate .err { color:#ff8a8a; font-size:13px; margin-top:10px; min-height:18px; }
#gate.shake .panel { animation: shake .45s; }
@keyframes shake {
  10%,90% { transform: translateX(-2px); }
  20%,80% { transform: translateX(4px); }
  30%,50%,70% { transform: translateX(-8px); }
  40%,60% { transform: translateX(8px); }
}

/* ---------- top bar ---------- */
#topbar { position:fixed; top:0; right:0; left:0; height:58px; z-index:20;
          background:linear-gradient(180deg,#1a3a5c 0%,#143049 100%);
          color:#fff; display:flex; align-items:center;
          padding:0 16px; gap:12px; box-shadow:0 1px 6px rgba(0,0,0,.18);
          font-size:14px; }
#topbar h1 { font-size:16px; font-weight:600; margin:0 0 0 10px;
             white-space:nowrap; }
#topbar .pos { font-weight:600; font-size:15px; min-width:90px;
               text-align:center; }
#topbar .prog { background:#0d2540; padding:5px 12px; border-radius:14px;
                font-size:13px; min-width:150px; text-align:center; }
#topbar input, #topbar select {
  background:#0d2540; color:#fff; border:1px solid #2a5483; border-radius:6px;
  padding:5px 8px; font-size:13px; font-family:inherit; }
#topbar input::placeholder { color:#a4bcd8; }
#topbar button {
  background:#2196f3; color:#fff; border:none; border-radius:6px;
  padding:6px 12px; font-size:13px; cursor:pointer; font-family:inherit;
  font-weight:600; }
#topbar button:hover { background:#1976d2; }
#topbar .btn-export { background:#43a047; }
#topbar .btn-export:hover { background:#388e3c; }
#topbar .btn-summary { background:#7e57c2; }
#topbar .btn-summary:hover { background:#5e35b1; }
#topbar .btn-reset { background:#c62828; }
#topbar .btn-reset:hover { background:#8e0000; }
#topbar .help { margin-right:auto; font-size:12px; color:#a4bcd8; }
#topbar .help kbd {
  background:#0d2540; padding:2px 6px; border-radius:3px; font-size:11px;
  border:1px solid #2a5483; margin:0 2px; }

/* ---------- layout ---------- */
#main { position:fixed; top:58px; bottom:0; right:0; left:0;
        display:flex; overflow:hidden; }
#sidebar { width:320px; min-width:320px; max-width:320px;
           background:#fff; border-left:1px solid #d0d4d9;
           overflow-y:auto; }
#sidebar .group-hdr {
  background:#eef2f6; padding:8px 12px; font-size:12px; font-weight:600;
  color:#445; border-bottom:1px solid #d0d4d9; position:sticky; top:0;
  z-index:2; }
#sidebar .item {
  padding:8px 10px; border-bottom:1px solid #eef0f3; cursor:pointer;
  font-size:13px; line-height:1.4; display:flex; align-items:center;
  gap:8px; border-right:4px solid transparent; }
#sidebar .item:hover { background:#f5f8fb; }
#sidebar .item.active { background:#cfe3f7; font-weight:600; }
#sidebar .item .swatch {
  width:10px; height:10px; border-radius:50%; flex-shrink:0; }
#sidebar .item .baz { font-weight:600; font-family: "Menlo","Courier New",
                      monospace; font-size:12px; min-width:64px; }
#sidebar .item .lbl { flex:1; color:#555; font-size:11.5px;
                      overflow:hidden; text-overflow:ellipsis;
                      white-space:nowrap; unicode-bidi:plaintext; }
#sidebar .item .dec-badge {
  font-size:11px; font-weight:700; padding:2px 7px; border-radius:10px;
  color:#fff; flex-shrink:0; }

/* ---------- main view ---------- */
#case { flex:1; overflow-y:auto; padding:20px 28px 230px; }
#case.empty { display:flex; align-items:center; justify-content:center;
              font-size:16px; color:#777; }

.cls-TRUE_RUPTURE       { background:#ffd9d9; }
.cls-PROBABLE_RUPTURE   { background:#ffe6cc; }
.cls-AMBIGUOUS          { background:#fff2cc; }
.cls-NEEDS_TEXT_REVIEW  { background:#e0e0e0; }
.swatch.cls-TRUE_RUPTURE       { background:#d32f2f; }
.swatch.cls-PROBABLE_RUPTURE   { background:#f57c00; }
.swatch.cls-AMBIGUOUS          { background:#fbc02d; }
.swatch.cls-NEEDS_TEXT_REVIEW  { background:#9e9e9e; }

.ident { padding:12px 16px; border-radius:10px; margin-bottom:16px;
         display:flex; flex-wrap:wrap; gap:10px 20px; align-items:baseline;
         font-size:14px; border:1px solid rgba(0,0,0,.08);
         border-right:6px solid transparent; border-left:6px solid transparent;
         transition: border-color .15s; }
.ident .baz { font-family:"Menlo","Courier New",monospace; font-size:18px;
              font-weight:700; }
.ident .cls-pill {
  padding:3px 10px; border-radius:12px; font-weight:600; font-size:12px;
  border:1px solid rgba(0,0,0,.15); background:#fff; }
.ident .kv { color:#444; }
.ident .kv b { color:#000; }

.box { background:#fff; border:1px solid #d8dde2; border-radius:10px;
       padding:14px 16px; margin-bottom:14px; }
.box .ttl { font-size:12px; font-weight:600; color:#666;
            margin-bottom:8px; text-transform:uppercase;
            letter-spacing:.5px; }

.box-newborn { background:#f1f8f3;
               border:1px solid #d8dde2;
               border-right:5px solid #43a047;
               border-left:5px solid #43a047; }
.box-newborn .ttl { color:#2e7d32; font-size:13px; font-weight:700;
                    text-transform:none; letter-spacing:0;
                    margin-bottom:10px; }
.ob-table { width:100%; border-collapse:collapse; font-size:14px;
            unicode-bidi:plaintext; }
.ob-table th { text-align:right; font-weight:600; color:#445;
               padding:5px 10px 5px 14px; vertical-align:top;
               width:170px; white-space:nowrap;
               background:transparent; border:none; }
.ob-table td { padding:5px 6px; vertical-align:top; color:#1c2733;
               unicode-bidi:plaintext; }
.ob-table tr + tr th, .ob-table tr + tr td { border-top:1px solid #e2eae3; }
.ob-table .ob-sep { padding:0; border-top:2px solid #b9d6bd; height:6px; }
.ob-table .baby-row { font-size:14.5px; line-height:1.55;
                       padding:7px 6px; unicode-bidi:plaintext; }
.stillbirth-pill { display:inline-block; background:#c62828; color:#fff;
                    font-weight:700; font-size:11.5px; padding:2px 8px;
                    border-radius:10px; margin-right:6px;
                    letter-spacing:.3px; }

/* ---------- timeline ---------- */
.timeline { margin-top:10px; }
.timeline-hdr {
  font-size:16px; font-weight:700; color:#1a3a5c; margin:22px 0 12px;
  padding-bottom:8px; border-bottom:2px solid #1a3a5c; }
.entry {
  background:#fff; border:1px solid #d8dde2; border-radius:8px;
  margin-bottom:12px; overflow:hidden;
  box-shadow:0 1px 2px rgba(0,0,0,.03); }
.entry-hdr {
  background:#eef2f6; padding:7px 14px; font-size:12.5px; color:#445;
  display:flex; gap:14px; align-items:center; border-bottom:1px solid #d8dde2;
  unicode-bidi:plaintext; }
.entry-hdr .when { font-family:"Menlo","Courier New",monospace;
                   font-weight:600; color:#1a3a5c; }
.entry-hdr .src  { color:#1a3a5c; font-weight:600; margin-right:auto; }
.entry-hdr .src-code { color:#999; font-size:11px;
                       font-family:"Menlo","Courier New",monospace; }
.entry-body {
  padding:14px 18px; unicode-bidi:plaintext; white-space:pre-wrap;
  font-size:14.5px; line-height:1.62;
  font-family: Arial, "David Libre", sans-serif; color:#1c2733; }

/* ---------- decision panel ---------- */
#decision-panel {
  position:fixed; bottom:0; right:0; left:0; z-index:15;
  background:#fff; border-top:2px solid #d0d4d9; padding:12px 24px;
  display:flex; gap:10px; align-items:stretch; flex-wrap:wrap;
  box-shadow:0 -3px 10px rgba(0,0,0,.08); }
#decision-panel .btn-group {
  display:flex; gap:8px; flex:1 1 auto; flex-wrap:wrap; align-items:stretch; }
#decision-panel .btn {
  border:2px solid; background:#fff; border-radius:9px;
  padding:7px 12px; font-size:13px; font-weight:600; cursor:pointer;
  min-width:155px; font-family:inherit; display:flex; flex-direction:column;
  align-items:flex-start; gap:2px; text-align:right;
  transition: transform .08s, box-shadow .15s; }
#decision-panel .btn:hover { transform: translateY(-1px);
                              box-shadow:0 2px 6px rgba(0,0,0,.12); }
#decision-panel .btn .lbl-row {
  display:flex; gap:8px; align-items:center; width:100%; }
#decision-panel .btn .key {
  font-size:11px; color:#fff; font-weight:700; background:#444;
  padding:2px 7px; border-radius:10px; flex-shrink:0; }
#decision-panel .btn .name { font-size:13.5px; line-height:1.3;
                              flex:1; unicode-bidi:plaintext; }
#decision-panel .btn.skip { border-style:dashed; min-width:120px; }
#decision-panel .notes-row {
  display:flex; flex:1 1 100%; gap:10px; align-items:flex-start; }
#decision-panel textarea {
  flex:1; min-height:50px; max-height:80px;
  border:1px solid #ccc; border-radius:6px;
  padding:7px 10px; font-family:inherit; font-size:13px; resize:vertical;
  direction:rtl; unicode-bidi:plaintext; }

/* ---------- decision color accents on case ---------- */
.case-flash { animation: flash .25s; }
@keyframes flash { 0% { background:#fff; } 50% { background:#fffbe6; }
                   100% { background:#fff; } }

/* sidebar item border by decision color is set inline */

/* ---------- completion overlay ---------- */
#completion {
  position:fixed; inset:0; z-index:50; background:rgba(15,30,50,.78);
  display:none; align-items:center; justify-content:center;
  backdrop-filter: blur(3px); }
#completion.show { display:flex; }
#completion .modal {
  background:#fff; max-width:680px; width:92%; max-height:90vh; overflow:auto;
  border-radius:14px; padding:30px 36px; box-shadow:0 10px 40px rgba(0,0,0,.4); }
#completion h2 { margin:0 0 6px; font-size:24px; color:#1a3a5c; }
#completion .sub { color:#5b6b7c; margin:0 0 18px; font-size:14px; }
#completion table { width:100%; border-collapse:collapse; margin:12px 0 20px; }
#completion th, #completion td { padding:8px 10px; text-align:right;
                                  border-bottom:1px solid #e6e9ee;
                                  font-size:14px; }
#completion th { background:#f5f8fb; color:#445; font-size:12px; }
#completion .count { font-weight:700; font-family:"Menlo","Courier New",
                     monospace; }
#completion .color-dot { display:inline-block; width:11px; height:11px;
                          border-radius:50%; margin-left:6px;
                          vertical-align:middle; }
#completion .steps { background:#fff7e0; border:1px solid #f0d674;
                     border-radius:10px; padding:14px 20px; margin:10px 0; }
#completion .steps h3 { margin:0 0 8px; font-size:15px; color:#7a5a00; }
#completion .steps ol { margin:0; padding-right:22px; line-height:1.65; }
#completion .steps li { margin-bottom:6px; font-size:14px; }
#completion .steps b { color:#1a3a5c; }
#completion .actions { display:flex; gap:10px; justify-content:flex-end;
                        margin-top:14px; }
#completion .actions button {
  padding:9px 18px; border:none; border-radius:7px; cursor:pointer;
  font-size:14px; font-weight:600; font-family:inherit; }
#completion .btn-close { background:#e0e0e0; color:#333; }
#completion .btn-export { background:#43a047; color:#fff; }
#completion .btn-export:hover { background:#388e3c; }

/* ---------- misc ---------- */
::-webkit-scrollbar { width:10px; height:10px; }
::-webkit-scrollbar-thumb { background:#c0c4cc; border-radius:5px; }
::-webkit-scrollbar-thumb:hover { background:#9aa0a8; }

@media (max-width: 1100px) {
  #sidebar { width:240px; min-width:240px; max-width:240px; }
  #decision-panel .btn { min-width:120px; font-size:12px; }
}
</style>
</head>
<body>

<!-- ===== password gate ===== -->
<div id="gate">
  <div class="panel">
    <h2>🔒 סקירת קרעי רחם</h2>
    <p>הקובץ מוצפן ומכיל מידע רפואי רגיש (PHI).<br>
       הקלידי סיסמה לפתיחה.</p>
    <input type="password" id="pw" autocomplete="off" placeholder="סיסמה">
    <div><button id="pw-btn">פתיחה</button></div>
    <div class="err" id="pw-err"></div>
  </div>
</div>

<!-- ===== app (hidden until decrypted) ===== -->
<div id="app" style="display:none">

<div id="topbar">
  <h1>סקירת קרעי רחם — סיווג ב-6 קטגוריות</h1>
  <span class="pos" id="pos">— / 317</span>
  <span class="prog" id="prog">0 / 317 נסקרו</span>
  <input id="search" placeholder="חיפוש BAZ..." size="10">
  <select id="filter">
    <option value="all">הכל</option>
    <option value="unreviewed">ללא החלטה</option>
    <option value="1">1 · ללא קרע</option>
    <option value="2">2 · דהיסנס</option>
    <option value="3">3 · קרע ללא ניסיון לידה</option>
    <option value="4">4 · קרע ב-CS במהלך לידה</option>
    <option value="5">5 · קרע לאחר לידה</option>
    <option value="6">6 · קרע ב-CS אלקטיבי</option>
    <option value="s">דילוג</option>
    <option value="cls:TRUE_RUPTURE">סוג: TRUE_RUPTURE</option>
    <option value="cls:PROBABLE_RUPTURE">סוג: PROBABLE_RUPTURE</option>
    <option value="cls:AMBIGUOUS">סוג: AMBIGUOUS</option>
    <option value="cls:NEEDS_TEXT_REVIEW">סוג: NEEDS_TEXT_REVIEW</option>
  </select>
  <button onclick="exportCSV()" class="btn-export">⬇ ייצוא CSV</button>
  <button onclick="showCompletion()" class="btn-summary">סקירה הושלמה?</button>
  <button onclick="resetAll()" class="btn-reset">🗑 איפוס</button>
  <span class="help">
    <kbd>j</kbd>/<kbd>←</kbd> הבא · <kbd>k</kbd>/<kbd>→</kbd> קודם ·
    <kbd>1</kbd>–<kbd>6</kbd> סיווג · <kbd>0</kbd>/<kbd>s</kbd> דילוג ·
    <kbd>/</kbd> חיפוש
  </span>
</div>

<div id="main">
  <aside id="sidebar"></aside>
  <section id="case" class="empty">בחרי מקרה מהרשימה או הקישי j/k להתחלה.</section>
</div>

<div id="decision-panel" style="display:none">
  <div class="btn-group" id="btn-group"></div>
  <div class="notes-row">
    <textarea id="notes" placeholder="הערות (נשמר אוטומטית)..."
              oninput="saveNotes()"></textarea>
  </div>
</div>

<div id="completion">
  <div class="modal">
    <h2 id="comp-title">🎉 סיימת לסווג את כל 317 הקיסים</h2>
    <p class="sub" id="comp-sub">סיכום הסיווגים לפי קטגוריות:</p>
    <table id="comp-table"></table>
    <div class="steps">
      <h3>📋 השלבים הבאים</h3>
      <ol>
        <li>לחצי על הכפתור <b>⬇ ייצוא CSV</b> למעלה.</li>
        <li>הקובץ ירד אוטומטית כ-<code>rupture_review_v2_decisions.csv</code>
            לתיקיית Downloads.</li>
        <li>שלחי את הקובץ חזרה לסשן Claude. נשתמש בו לבניית הקוהורט הסופי
            לפי 4 הקבוצות הקליניות (rupture-no-labor,
            rupture-at-CS-during-labor, rupture-postpartum,
            rupture-at-elective-CS) ולשליפת היסטוריה מלאה + ניתוח השוואתי
            בין הקבוצות.</li>
        <li>אם רוצה להתחיל מחדש בעתיד — יש כפתור
            <b>🗑 איפוס</b> בסרגל העליון.</li>
      </ol>
    </div>
    <div class="actions">
      <button class="btn-close" onclick="hideCompletion()">סגור</button>
      <button class="btn-export" onclick="exportCSV()">⬇ ייצוא CSV</button>
    </div>
  </div>
</div>

</div>  <!-- /#app -->

<script>window.PAYLOAD = "__PAYLOAD_B64__";</script>
<script>
/* ========== category definitions (mirrors Python CATEGORIES) ========== */
const CATEGORIES = __CATEGORIES_JSON__;
const CAT_BY_KEY = Object.fromEntries(CATEGORIES.map(c => [c.key, c]));
const STORAGE_KEY = 'rupture_review_v2_cls6';
const SESSION_PW_KEY = 'rupture_review_v2_pw_ok';
const PBKDF2_ITERATIONS = 250000;
const N_EXPECTED = 317;

/* ========== password gate ========== */
async function decryptPayload(pw) {
  const raw = Uint8Array.from(atob(window.PAYLOAD), c => c.charCodeAt(0));
  const salt = raw.slice(0, 16);
  const iv = raw.slice(16, 28);
  const ct = raw.slice(28);
  const baseKey = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(pw),
    {name: 'PBKDF2'}, false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    {name: 'PBKDF2', salt: salt, iterations: PBKDF2_ITERATIONS,
     hash: 'SHA-256'},
    baseKey, {name: 'AES-GCM', length: 256}, false, ['decrypt']);
  const pt = await crypto.subtle.decrypt({name: 'AES-GCM', iv: iv}, key, ct);
  return JSON.parse(new TextDecoder().decode(pt));
}

async function tryUnlock(pw) {
  const gate = document.getElementById('gate');
  const err = document.getElementById('pw-err');
  err.textContent = '';
  try {
    const cases = await decryptPayload(pw);
    window.CASES = cases;
    try { sessionStorage.setItem(SESSION_PW_KEY, pw); } catch (e) {}
    gate.style.display = 'none';
    document.getElementById('app').style.display = '';
    initApp();
  } catch (e) {
    err.textContent = 'סיסמה שגויה';
    gate.classList.remove('shake');
    void gate.offsetWidth;
    gate.classList.add('shake');
    document.getElementById('pw').focus();
    document.getElementById('pw').select();
  }
}

document.getElementById('pw-btn').addEventListener('click', () => {
  tryUnlock(document.getElementById('pw').value);
});
document.getElementById('pw').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') tryUnlock(e.target.value);
});

(async function autoUnlock() {
  try {
    const saved = sessionStorage.getItem(SESSION_PW_KEY);
    if (saved) await tryUnlock(saved);
    else document.getElementById('pw').focus();
  } catch (e) { document.getElementById('pw').focus(); }
})();

/* ========== app ========== */
let state, currentIdx, filteredIndices, N;

function initApp() {
  N = window.CASES.length;
  state = loadState();
  filteredIndices = window.CASES.map((_, i) => i);

  buildDecisionPanel();
  bindUI();
  renderSidebar();

  const firstUnreviewed = window.CASES.findIndex(c =>
    !state[c.baz] || !state[c.baz].decision);
  if (firstUnreviewed >= 0) goTo(firstUnreviewed);
  else if (N) goTo(0);

  console.log('Loaded ' + N + ' cases.');
}

function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    return s && typeof s === 'object' ? s : {};
  } catch (e) { return {}; }
}
function saveState() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
  catch (e) { console.error('save failed', e); }
}
function getRec(baz) {
  if (!state[baz]) state[baz] = {decision: null, notes: ''};
  return state[baz];
}
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ---------- decision panel buttons ---------- */
function buildDecisionPanel() {
  const grp = document.getElementById('btn-group');
  grp.innerHTML = '';
  for (const cat of CATEGORIES) {
    const btn = document.createElement('button');
    btn.className = 'btn cat-' + cat.key;
    btn.style.borderColor = cat.color;
    btn.style.color = cat.color;
    btn.dataset.key = cat.key;
    btn.innerHTML =
      '<div class="lbl-row">' +
        '<span class="key" style="background:' + cat.color + '">' +
          cat.key + '</span>' +
        '<span class="name">' + esc(cat.he) + '</span>' +
      '</div>';
    btn.onclick = () => setDecision(cat.key);
    grp.appendChild(btn);
  }
  // skip
  const sb = document.createElement('button');
  sb.className = 'btn skip';
  sb.style.borderColor = '#999';
  sb.style.color = '#666';
  sb.dataset.key = 's';
  sb.innerHTML =
    '<div class="lbl-row">' +
      '<span class="key" style="background:#777">0 / s</span>' +
      '<span class="name">דילוג</span>' +
    '</div>';
  sb.onclick = () => setDecision('s');
  grp.appendChild(sb);
}

/* ---------- sidebar ---------- */
function renderSidebar() {
  const sb = document.getElementById('sidebar');
  const f = document.getElementById('filter').value;
  const q = document.getElementById('search').value.trim();

  let groups = {};
  filteredIndices = [];
  window.CASES.forEach((c, i) => {
    if (q && !c.baz.includes(q)) return;
    const dec = (state[c.baz] && state[c.baz].decision) || null;
    if (f === 'unreviewed' && dec) return;
    if (/^[1-6s]$/.test(f) && dec !== f) return;
    if (f.startsWith('cls:') && c.cls !== f.slice(4)) return;
    filteredIndices.push(i);
    if (!groups[c.cls]) groups[c.cls] = [];
    groups[c.cls].push(i);
  });

  let html = '';
  const ordered = ['TRUE_RUPTURE','PROBABLE_RUPTURE','AMBIGUOUS',
                   'NEEDS_TEXT_REVIEW'];
  for (const cls of ordered) {
    if (!groups[cls]) continue;
    html += '<div class="group-hdr">' + cls + ' (' + groups[cls].length +
            ')</div>';
    for (const i of groups[cls]) {
      const c = window.CASES[i];
      const dec = (state[c.baz] && state[c.baz].decision) || '';
      let decBadge = '';
      let borderCol = 'transparent';
      let borderStyle = 'solid';
      if (dec) {
        const cat = CAT_BY_KEY[dec];
        if (cat) {
          decBadge = '<span class="dec-badge" style="background:' +
                     cat.color + '">' + cat.key + '</span>';
          borderCol = cat.color;
        } else if (dec === 's') {
          decBadge = '<span class="dec-badge" style="background:#999">⊘</span>';
          borderCol = '#999';
          borderStyle = 'dashed';
        }
      }
      const lbl = (c.ga ? c.ga + ' · ' : '') + (c.parity || '') +
                  (c.evidence ? ' · ' + c.evidence.slice(0, 40) : '');
      html += '<div class="item ' + (i === currentIdx ? 'active' : '') +
              '" style="border-right:4px ' + borderStyle + ' ' + borderCol +
              '" onclick="goTo(' + i + ')">' +
              '<span class="swatch cls-' + c.cls + '"></span>' +
              '<span class="baz">' + esc(c.baz) + '</span>' +
              '<span class="lbl">' + esc(lbl) + '</span>' +
              decBadge + '</div>';
    }
  }
  if (!filteredIndices.length) {
    html = '<div style="padding:14px;color:#888;font-size:13px">' +
           'אין מקרים תואמים לסינון.</div>';
  }
  sb.innerHTML = html;

  const reviewed = Object.values(state).filter(v => v && v.decision).length;
  document.getElementById('prog').textContent =
    reviewed + ' / ' + N + ' נסקרו';

  if (currentIdx >= 0) {
    const active = sb.querySelector('.item.active');
    if (active) active.scrollIntoView({block: 'nearest', behavior: 'auto'});
  }
}

/* ---------- main view ---------- */
function renderCase(i) {
  const view = document.getElementById('case');
  const panel = document.getElementById('decision-panel');
  if (i < 0 || i >= N) {
    view.className = 'empty';
    view.innerHTML = 'בחרי מקרה מהרשימה.';
    panel.style.display = 'none';
    return;
  }
  currentIdx = i;
  const c = window.CASES[i];
  const rec = getRec(c.baz);
  view.className = '';

  // decision color accent
  let accent = 'transparent';
  let accentStyle = 'solid';
  if (rec.decision && CAT_BY_KEY[rec.decision]) {
    accent = CAT_BY_KEY[rec.decision].color;
  } else if (rec.decision === 's') {
    accent = '#999'; accentStyle = 'dashed';
  }

  const ident =
    '<div id="ident-row" class="ident cls-' + c.cls + '"' +
    ' style="border-right-color:' + accent + ';border-left-color:' +
    accent + ';border-right-style:' + accentStyle +
    ';border-left-style:' + accentStyle + '">' +
    '<span class="baz">' + esc(c.baz) + '</span>' +
    '<span class="cls-pill">' + esc(c.cls) + ' · ' +
      esc(c.conf || '') + '</span>' +
    (c.ga ? '<span class="kv">שבוע <b>' + esc(c.ga) + '</b></span>' : '') +
    (c.parity ? '<span class="kv">' + esc(c.parity) + '</span>' : '') +
    (c.birth_site ? '<span class="kv">' + esc(c.birth_site) + '</span>' : '') +
    (c.unit ? '<span class="kv">' + esc(c.unit) + '</span>' : '') +
    (c.delivery_mode ? '<span class="kv">' + esc(c.delivery_mode) +
      '</span>' : '') +
    (c.admission_dt ? '<span class="kv">קבלה: <b>' +
      esc(c.admission_dt) + '</b></span>' : '') +
    (c.delivery_dt ? '<span class="kv">לידה: <b>' +
      esc(c.delivery_dt) + '</b></span>' : '') +
    (c.patient ? '<span class="kv">Patient ' + esc(c.patient) +
      '</span>' : '') +
    (c.mrn ? '<span class="kv">MRN ' + esc(c.mrn) + '</span>' : '') +
    (c.in_known_45 ?
      '<span class="kv" style="color:#1976d2"><b>★ ב-45 הידועים</b></span>'
      : '') +
    '</div>';

  const dash = '—';
  function val(v) {
    if (v === null || v === undefined) return dash;
    const s = String(v).trim();
    if (!s || s === 'nan' || s === 'NaT') return dash;
    return esc(s);
  }
  function apgar(b) {
    function f(v) {
      if (v === null || v === undefined || v === '') return dash;
      return String(v);
    }
    return f(b.apgar1) + '/' + f(b.apgar5) + '/' + f(b.apgar10);
  }
  function sexHe(s) {
    if (!s) return dash;
    if (s === 'זכר') return 'זכר';
    if (s === 'נקבה') return 'נקבה';
    return esc(s);
  }
  function weightStr(w) {
    if (w === null || w === undefined || w === '') return dash;
    return String(w) + ' גר׳';
  }

  let newborn = '';
  const hasFormula = c.obstetric_formula;
  const hasMeta = c.ga_admission || c.ga_delivery || c.meta_labor_onset ||
                  c.meta_birth_site || c.delivery_dt;
  if ((c.babies && c.babies.length) || hasFormula || hasMeta) {
    let rows = '';
    rows += '<tr><th>נוסחה מיילדותית</th><td>' +
            val(c.obstetric_formula) + '</td></tr>';
    rows += '<tr><th>שבוע הריון בקבלה</th><td>' +
            val(c.ga_admission) + '</td></tr>';
    rows += '<tr><th>שבוע לידה</th><td>' +
            val(c.ga_delivery) + '</td></tr>';
    rows += '<tr><th>אופן התחלת לידה</th><td>' +
            val(c.meta_labor_onset || c.labor_onset) + '</td></tr>';
    rows += '<tr><th>אתר לידה</th><td>' +
            val(c.meta_birth_site || c.birth_site) + '</td></tr>';
    rows += '<tr><th>זמן לידה</th><td>' +
            val(c.delivery_dt) + '</td></tr>';

    let babyRows = '';
    if (c.babies && c.babies.length) {
      babyRows = c.babies.map(b => {
        const parts = [];
        parts.push(weightStr(b.weight));
        parts.push(sexHe(b.sex));
        if (b.presentation) parts.push(esc(b.presentation));
        if (b.delivery_mode) parts.push(esc(b.delivery_mode));
        parts.push('אפגר ' + apgar(b));
        if (b.tol) parts.push('TOL: ' + esc(b.tol));
        let line = '<b>יילוד ' + (b.num || '?') + ':</b> ' +
                   parts.join(' · ');
        if (b.stillbirth) {
          line += ' <span class="stillbirth-pill">לידת מת</span>';
        }
        return '<tr><td colspan="2" class="baby-row">' + line + '</td></tr>';
      }).join('');
    }

    newborn = '<div class="box box-newborn">' +
      '<div class="ttl">נתוני לידה ויילוד' +
        (c.babies && c.babies.length ?
          ' (' + c.babies.length + ' יילוד' +
          (c.babies.length > 1 ? 'ים' : '') + ')' : '') +
        '</div>' +
      '<table class="ob-table">' + rows +
        (babyRows ? '<tr><td colspan="2" class="ob-sep"></td></tr>' +
                    babyRows : '') +
      '</table></div>';
  }

  let timeline = '<div class="timeline-hdr">ציר זמן כרונולוגי (' +
                 (c.timeline ? c.timeline.length : 0) + ' רשומות)</div>';
  if (!c.timeline || !c.timeline.length) {
    timeline += '<div style="color:#888;padding:8px">' +
                'אין טקסט חופשי זמין למקרה זה.</div>';
  } else {
    timeline += c.timeline.map(e =>
      '<div class="entry">' +
        '<div class="entry-hdr">' +
          '<span class="when">' + esc(e.date || '— ללא תאריך —') +
            '</span>' +
          '<span class="src">' + esc(e.label) + '</span>' +
          '<span class="src-code">' + esc(e.source) + '</span>' +
        '</div>' +
        '<div class="entry-body">' + esc(e.text) + '</div>' +
      '</div>').join('');
  }

  view.innerHTML = ident + newborn +
                   '<div class="timeline">' + timeline + '</div>';

  // decision panel: highlight active button
  panel.style.display = 'flex';
  panel.querySelectorAll('.btn').forEach(b => {
    const k = b.dataset.key;
    const active = (rec.decision === k);
    if (active) {
      const col = CAT_BY_KEY[k] ? CAT_BY_KEY[k].color : '#999';
      b.style.background = col + '22';
      b.style.boxShadow = '0 0 0 2px ' + col + ' inset';
    } else {
      b.style.background = '#fff';
      b.style.boxShadow = 'none';
    }
  });
  document.getElementById('notes').value = rec.notes || '';

  document.getElementById('pos').textContent = (i + 1) + ' / ' + N;
  view.scrollTop = 0;
  renderSidebar();
}

/* ---------- nav ---------- */
function goTo(i) {
  if (i < 0 || i >= N) return;
  renderCase(i);
}
function nextInFilter() {
  const pos = filteredIndices.indexOf(currentIdx);
  if (pos === -1) {
    if (filteredIndices.length) goTo(filteredIndices[0]);
    return;
  }
  if (pos + 1 < filteredIndices.length) goTo(filteredIndices[pos + 1]);
}
function prevInFilter() {
  const pos = filteredIndices.indexOf(currentIdx);
  if (pos === -1) {
    if (filteredIndices.length) goTo(filteredIndices[0]);
    return;
  }
  if (pos - 1 >= 0) goTo(filteredIndices[pos - 1]);
}
function nextUnreviewed() {
  for (let off = 1; off <= N; off++) {
    const j = (currentIdx + off) % N;
    if (!state[window.CASES[j].baz] ||
        !state[window.CASES[j].baz].decision) {
      goTo(j); return;
    }
  }
  // none unreviewed — show completion
  showCompletion();
}

function setDecision(k) {
  if (currentIdx < 0) return;
  const baz = window.CASES[currentIdx].baz;
  const rec = getRec(baz);
  rec.decision = k;
  saveState();
  renderCase(currentIdx);
  // Auto-advance after a 6-category choice. Not after skip.
  // Not when notes are focused.
  if (/^[1-6]$/.test(k) &&
      document.activeElement !== document.getElementById('notes')) {
    setTimeout(() => {
      nextUnreviewed();
    }, 200);
  }
  // If all reviewed, surface completion overlay automatically (once).
  const reviewed = Object.values(state).filter(v => v && v.decision).length;
  if (reviewed === N) setTimeout(() => showCompletion(), 350);
}

function saveNotes() {
  if (currentIdx < 0) return;
  const baz = window.CASES[currentIdx].baz;
  getRec(baz).notes = document.getElementById('notes').value;
  saveState();
}

/* ---------- reset ---------- */
function resetAll() {
  if (!confirm('האם למחוק את כל הסימונים וההערות?')) return;
  try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
  location.reload();
}

/* ---------- keyboard ---------- */
function bindUI() {
  document.getElementById('filter')
    .addEventListener('change', () => renderSidebar());
  document.getElementById('search')
    .addEventListener('input', () => renderSidebar());

  document.addEventListener('keydown', (e) => {
    if (e.target.matches('textarea, input')) return;
    if (e.key === 'j' || e.key === 'ArrowLeft') {
      e.preventDefault(); nextInFilter();
    } else if (e.key === 'k' || e.key === 'ArrowRight') {
      e.preventDefault(); prevInFilter();
    } else if (/^[1-6]$/.test(e.key)) {
      e.preventDefault(); setDecision(e.key);
    } else if (e.key === '0' || e.key === 's' || e.key === 'S') {
      e.preventDefault(); setDecision('s');
    } else if (e.key === '/') {
      e.preventDefault(); document.getElementById('search').focus();
    } else if (e.key === 'Escape') {
      hideCompletion();
    }
  });
}

/* ---------- completion overlay ---------- */
function showCompletion() {
  // build summary table
  const counts = {};
  for (const cat of CATEGORIES) counts[cat.key] = 0;
  counts['s'] = 0;
  counts['_none'] = 0;
  for (const c of window.CASES) {
    const d = (state[c.baz] && state[c.baz].decision) || null;
    if (d && counts.hasOwnProperty(d)) counts[d] += 1;
    else if (!d) counts['_none'] += 1;
  }
  const reviewed = N - counts['_none'];
  document.getElementById('comp-title').textContent =
    (reviewed === N
      ? '🎉 סיימת לסווג את כל ' + N + ' הקיסים'
      : 'סקירה — סטטוס נוכחי (' + reviewed + ' / ' + N + ')');
  document.getElementById('comp-sub').textContent =
    'סיכום הסיווגים לפי קטגוריות:';

  let rows = '<tr><th>קטגוריה</th><th>תווית</th>' +
             '<th style="text-align:left">כמות</th></tr>';
  for (const cat of CATEGORIES) {
    rows += '<tr>' +
      '<td><span class="color-dot" style="background:' + cat.color +
        '"></span>' + cat.key + '</td>' +
      '<td>' + esc(cat.he) + '</td>' +
      '<td style="text-align:left" class="count">' +
        counts[cat.key] + '</td></tr>';
  }
  rows += '<tr><td><span class="color-dot" style="background:#999"></span>' +
          's</td><td>דילוג</td><td style="text-align:left" class="count">' +
          counts['s'] + '</td></tr>';
  if (counts['_none']) {
    rows += '<tr><td><span class="color-dot" ' +
            'style="background:#ddd;border:1px solid #aaa"></span>—</td>' +
            '<td>לא סווגו עדיין</td>' +
            '<td style="text-align:left" class="count">' +
            counts['_none'] + '</td></tr>';
  }
  document.getElementById('comp-table').innerHTML = rows;
  document.getElementById('completion').classList.add('show');
}
function hideCompletion() {
  document.getElementById('completion').classList.remove('show');
}

/* ---------- CSV export ---------- */
function exportCSV() {
  const cols = ['BAZ', 'class_now', 'gestational_age', 'parity_summary',
                'worst_apgar5', 'any_stillbirth', 'decision_key',
                'decision_label', 'decision_hebrew', 'notes'];
  const rows = [cols.join(',')];
  window.CASES.forEach(c => {
    const rec = state[c.baz] || {};
    const dec = rec.decision || '';
    let en = '', he = '';
    if (CAT_BY_KEY[dec]) {
      en = CAT_BY_KEY[dec].en;
      he = CAT_BY_KEY[dec].he;
    } else if (dec === 's') {
      en = 'SKIP'; he = '';
    }
    const row = [
      c.baz, c.cls, c.ga, c.parity_summary || c.parity || '',
      c.worst_apgar5 || '', c.any_stillbirth || '',
      dec, en, he, rec.notes || ''
    ].map(v => {
      const s = String(v == null ? '' : v);
      if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
      return s;
    });
    rows.push(row.join(','));
  });
  const BOM = '﻿';
  const blob = new Blob([BOM + rows.join('\n')],
    {type: 'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'rupture_review_v2_decisions.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
</script>
</body></html>
"""


def main():
    print('Building case records...')
    cases = build_case_records()
    print(f'  total cases: {len(cases)}')
    counts = {}
    for c in cases:
        counts[c['cls']] = counts.get(c['cls'], 0) + 1
    print('  by class:', counts)

    timeline_total = sum(len(c['timeline']) for c in cases)
    print(f'  timeline entries (across all): {timeline_total}')
    with_text = sum(1 for c in cases if c['timeline'])
    print(f'  cases with text: {with_text}/{len(cases)}')

    print('Serializing JSON...')
    cases_json = json.dumps(cases, ensure_ascii=False, separators=(',', ':'))
    print(f'  json bytes: {len(cases_json):,}')

    print('Encrypting payload (AES-GCM, PBKDF2 250k)...')
    payload_b64 = encrypt_payload(cases_json.encode('utf-8'))
    print(f'  encrypted b64 length: {len(payload_b64):,}')

    # Sanity: round-trip decrypt
    raw = base64.b64decode(payload_b64)
    salt, iv, ct = raw[:16], raw[16:28], raw[28:]
    kdf2 = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=PBKDF2_ITERATIONS)
    key2 = kdf2.derive(PASSWORD)
    pt = AESGCM(key2).decrypt(iv, ct, None)
    decoded = json.loads(pt.decode('utf-8'))
    assert len(decoded) == len(cases), 'round-trip count mismatch'
    print(f'  round-trip OK: {len(decoded)} cases')

    categories_json = json.dumps(CATEGORIES, ensure_ascii=False)

    html = (HTML_TEMPLATE
            .replace('__PAYLOAD_B64__', payload_b64)
            .replace('__CATEGORIES_JSON__', categories_json))
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    size_mb = os.path.getsize(OUT_HTML) / 1024 / 1024
    print(f'\nWrote: {OUT_HTML}')
    print(f'  size: {size_mb:.2f} MB')
    print(f'  cases embedded (encrypted): {len(cases)}')


if __name__ == '__main__':
    main()
