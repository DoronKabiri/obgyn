# Rupture Review Builder

חבילה ניידת לבניית קובץ ה-HTML האינטראקטיבי לסקירת מקרי קרע רחם.

הסקריפט רץ לוקאלית בלבד, ללא חיבור לאינטרנט. מתאים לרשת סגורה.

## דרישות

- Python 3.8+ (מומלץ 3.10 ומעלה)
- 3 חבילות פייתון:
  - `pandas`
  - `openpyxl`
  - `cryptography`

## התקנה ראשונית

מהטרמינל, באותה תיקייה שבה הסקריפט:

```bash
pip install -r requirements.txt
```

או ידנית:

```bash
pip install pandas openpyxl cryptography
```

אם `pip` לא זמין, נסי:

```bash
python3 -m pip install pandas openpyxl cryptography
```

הסקריפט בודק את התלויות אוטומטית בהפעלה ויודיע אם משהו חסר.

## קבצי קלט נדרשים

יש להעתיק 6 קבצים לאותה תיקייה (או לציין מיקום אחר דרך `--data-dir`):

| קובץ | מקור |
|---|---|
| `rupture_TRUE_only.xlsx` | פלט הסיווג של 584 הקיסים |
| `rupture_full_cohort_extract.xlsx` | טקסט מ-20 הטבלאות לכל קייס |
| `v_BFR_25.csv` | נתוני קבלה (שבוע הריון) |
| `v_BFR_26.csv` | נוסחה מיילדותית |
| `v_BFR_60.csv` | פרטי לידה |
| `v_BFR_61.csv` | פרטי יילוד (אפגר, משקל וכו') |

## הפעלה

באותה תיקייה כמו הסקריפט, פשוט:

```bash
python3 build_review.py
```

הסקריפט יבדוק שכל קבצי הקלט נמצאים, יראה הודעת `[ok]` לכל אחד, ויבנה את ה-HTML.

הפלט: `rupture_review_INTERACTIVE_v2.html` (בערך 11 MB).

## אפשרויות מתקדמות

```bash
# קבצי קלט בתיקייה אחרת
python3 build_review.py --data-dir /path/to/data

# קבצי BFR בתיקייה נפרדת מקבצי האקסל
python3 build_review.py --data-dir ./excel_files --bfr-dir ./bfr_csvs

# מיקום פלט מותאם
python3 build_review.py --out /tmp/my_review.html

# סיסמה אחרת (ברירת מחדל: Rupture)
python3 build_review.py --password MySecretPassword
```

או דרך משתני סביבה:

```bash
export RUPTURE_DATA_DIR=/path/to/data
export RUPTURE_PASSWORD=MySecret
python3 build_review.py
```

## שימוש בקובץ ה-HTML

1. פתחי את `rupture_review_INTERACTIVE_v2.html` בדפדפן (Chrome/Safari/Firefox)
2. הזיני את הסיסמה (ברירת מחדל: **Rupture**)
3. סקירת 317 קיסים, סיווג ב-6 קטגוריות
4. ההחלטות נשמרות אוטומטית בדפדפן
5. בסוף לחיצה על "ייצוא CSV" מורידה את ההחלטות

הקובץ עובד offline. אפשר להעביר אותו בין מחשבים — הסיסמה תקפה תמיד.

## פתרון תקלות

**`ModuleNotFoundError: No module named 'cryptography'`** — התקיני: `pip install cryptography`

**`*** חסרים קבצי קלט ***`** — בדקי שכל 6 הקבצים בתיקייה הנכונה (השם בדיוק כמו ברשימה למעלה).

**הסקריפט רץ אבל ה-HTML ריק** — בדקי שאין שגיאות בפלט. ודאי שגרסת Python היא 3.8 ומעלה: `python3 --version`.

**הדפדפן לא קופץ אחרי בניית הקובץ** — פתחי ידנית עם:
```bash
open rupture_review_INTERACTIVE_v2.html   # macOS
xdg-open rupture_review_INTERACTIVE_v2.html   # Linux
start rupture_review_INTERACTIVE_v2.html   # Windows
```

## מבנה החבילה

```
rupture_review_builder/
├── README.md           ← הקובץ הזה
├── requirements.txt    ← רשימת חבילות פייתון
└── build_review.py     ← הסקריפט הראשי
```

## הערות אבטחה

- הסקריפט לא פונה לאינטרנט בשום שלב
- הסיסמה (Rupture כברירת מחדל) מצפינה את הקובץ ב-AES-256-GCM עם PBKDF2 (250K איטרציות)
- אם משנה סיסמה — שמרי אותה. אין דרך לשחזר את הקובץ בלעדיה
- ההחלטות נשמרות ב-localStorage של הדפדפן בלבד
- ב-Incognito/Private mode ההחלטות יימחקו עם סגירת הטאב

---

Author: Doron Kabiri
