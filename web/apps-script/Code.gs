/**
 * MP Kaartscan naar Google Sheets.
 * Plak dit in de Kaartpricer sheet: Extensies, Apps Script. Zet bij Projectinstellingen een
 * scripteigenschap SECRET met dezelfde waarde als SHEET_HOOK_SECRET in Cloudflare.
 * Implementeren als web-app: uitvoeren als jezelf, toegang voor iedereen.
 */
function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var secret = PropertiesService.getScriptProperties().getProperty('SECRET');
    if (!secret || body.secret !== secret) return reply({ ok: false, error: 'secret' });
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var title = String(body.title || 'Kaartscan').substring(0, 90);
    if (ss.getSheetByName(title)) title = title + ' ' + Utilities.formatDate(new Date(), 'Europe/Amsterdam', 'HH.mm');
    var sheet = ss.insertSheet(title, 0);
    var rows = body.values || [];
    var width = 1;
    rows.forEach(function (r) { width = Math.max(width, r.length); });
    var data = rows.map(function (r) { var x = r.slice(); while (x.length < width) x.push(''); return x; });
    if (data.length) sheet.getRange(1, 1, data.length, width).setValues(data);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, width).setFontWeight('bold');
    sheet.autoResizeColumns(1, Math.min(width, 8));
    return reply({ ok: true, title: title });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}
function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
