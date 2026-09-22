# שליחת קבצי הכספת למייל

סקריפט מקומי שרץ על המק כל שעה (LaunchAgent), בודק אם עלו לכספת קבצים חדשים (כל סוג קובץ), מפענח אותם בסיסמת האתר ושולח כל אחד פעם אחת כקובץ מצורף למייל האישי.

- קוד: `vault_mailer.py` (Python של python.org, עם `cryptography` ו-`certifi`).
- שליחה: דרך ה-CLI המקומי של Gmail (`~/Desktop/Claude Folder/gmail-automation/inbox.py send`), עם ה-venv שלו.
- הגדרות: `~/.config/obgyn-vault-mailer/config.json` (סיסמת האתר, כתובת היעד). הרשאות 600.
- מה כבר נשלח: `~/.config/obgyn-vault-mailer/sent.json` (לפי sha של הקובץ ברפו). קובץ שנכשל 3 פעמים (למשל גדול מדי למייל) מסומן ולא מנוסה שוב; `--resend` כופה ניסיון נוסף.
- יומן: `~/Library/Logs/obgyn-vault-mailer.log`.
- תזמון: `~/Library/LaunchAgents/com.doronkabiri.obgyn-vault-mailer.plist`, כל 3600 שניות וגם בעלייה. עובד רק כשהמק דולק ומחובר.

## הפעלה ידנית
```bash
cd ~/Documents/Claude/Projects/obgyn-summary-site/tools/vault-mailer
python3 vault_mailer.py            # שולח כל קובץ חדש
python3 vault_mailer.py --dry      # רק בודק ומפענח, בלי לשלוח
python3 vault_mailer.py --resend "שם הקובץ.enc"   # שליחה חוזרת
```

## עצירה / הפעלה מחדש של התזמון
```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.doronkabiri.obgyn-vault-mailer.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.doronkabiri.obgyn-vault-mailer.plist
```

אם טוקן ה-Gmail פג (המסך ידווח על כשל שליחה ביומן), מריצים פעם אחת `inbox.py auth` בתיקיית gmail-automation ומאשרים בדפדפן.
