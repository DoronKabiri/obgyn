# העלאה לכספת בלי טוקן אישי בכל מחשב

שירות זעיר ב-Cloudflare Workers (חינמי) שמחזיק את טוקן ה-GitHub במקום הדפדפן. הדף שולח אליו את הקובץ המוצפן יחד עם סיסמת האתר, והשירות כותב לרפו. ההורדה מהכספת לא משתנה.

## מסלול א: דרך האתר של Cloudflare (בלי התקנות)
1. חשבון ב-https://dash.cloudflare.com (חינמי).
2. Workers & Pages → Create → Create Worker. שם: `obgyn-vault` → Deploy.
3. Edit code → למחוק את הקוד לדוגמה, להדביק את תוכן `worker.js` → Deploy.
4. Settings → Variables and Secrets → Add:
   - Text: `OWNER` = `DoronKabiri`, `REPO` = `obgyn`, `DIR` = `docs`, `ALLOW_ORIGIN` = `https://doronkabiri.com`
   - Secret: `GITHUB_TOKEN` = טוקן fine-grained (Repository access: obgyn בלבד; Contents: Read and write; תוקף שנה)
   - Secret: `VAULT_PASSWORD` = סיסמת האתר
5. להעתיק את כתובת ה-Worker (למשל `https://obgyn-vault.<שם>.workers.dev`) ולמלא אותה ב-`VAULT_ENDPOINT` ב-`index.html`, ואז להעלות את index.html לרפו.

## מסלול ב: שורת פקודה
`npm install -g wrangler` → `wrangler login` → בתיקייה זו `wrangler deploy` → `wrangler secret put GITHUB_TOKEN` → `wrangler secret put VAULT_PASSWORD`. המשתנים הרגילים כבר ב-`wrangler.toml`.

## חידוש
כשהטוקן ב-GitHub פג (אחרי שנה) מחליפים רק את הסוד `GITHUB_TOKEN` ב-Cloudflare. הדפדפנים לא נוגעים.
