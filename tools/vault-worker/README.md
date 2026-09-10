# העלאה לכספת בלי טוקן אישי (אופציונלי)

ברירת המחדל של הכספת דורשת טוקן GitHub בכל מחשב שממנו מעלים, והטוקן פג אחרי שנה.
החלופה: שירות זעיר (Cloudflare Worker, חינמי) שמחזיק את הטוקן במקום המשתמש. הדף שולח אליו את הקובץ המוצפן עם סיסמת האתר, והשירות כותב לרפו.

## הקמה (פעם אחת, כ-15 דקות)
1. חשבון ב-https://dash.cloudflare.com (חינמי).
2. במחשב: `npm install -g wrangler` ואז `wrangler login`.
3. בתיקייה זו: `wrangler deploy worker.js --name obgyn-vault` (ייווצר כתובת כמו `https://obgyn-vault.<user>.workers.dev`).
4. משתני סביבה (Settings → Variables): `OWNER=DoronKabiri`, `REPO=obgyn`, `DIR=docs`, `ALLOW_ORIGIN=https://doronkabiri.github.io`.
5. סודות: `wrangler secret put GITHUB_TOKEN` (fine-grained, Contents: Read and write על obgyn בלבד) ו-`wrangler secret put VAULT_PASSWORD` (סיסמת האתר).
6. ב-`index.html` למלא את `VAULT_ENDPOINT` בכתובת ה-Worker, להצפין ולהעלות.

מרגע זה ההעלאה והמחיקה מהדף עובדות מכל מחשב עם סיסמת האתר בלבד. ההורדה לא השתנתה.
כשהטוקן ב-GitHub פג (אחרי שנה) מחליפים אותו רק בשירות, לא בכל מחשב.
