/* Lieutenant Island road reports: receives reports from the crossing site and adds each one as a row in this Sheet.

   One-time setup, in the Google account that should own the reports:
   1. Create a Google Sheet (any name), then open Extensions → Apps Script.
   2. Replace everything in Code.gs with this file and save.
   3. Pick "setup" in the function menu and click Run, then approve the permissions Google asks for.
   4. Deploy → New deployment → type "Web app". Execute as: Me. Who has access: Anyone. Click Deploy.
   5. Copy the Web app URL (it ends in /exec) into REPORT_URL in site/index.html.

   Reports land on the "Reports" tab. Untick the box on the "Settings" tab to stop the email for each report.
   After editing this code: Deploy → Manage deployments → edit (pencil) → Version: New version, so the URL stays the same. */

var FIELDS = ['report_id', 'seen_at', 'level', 'edge', 'depth_in', 'depth_how', 'observer', 'forecast_in', 'high_tide', 'reported_at'];

function doPost(e) {
  var p = (e && e.parameter) || {};
  if (!p.report_id || !p.level) return reply_({ ok: false, error: 'missing report_id or level' });
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet = reportsTab_();
    // the site resends reports it isn't sure went through, so skip any already recorded
    var seen = sheet.createTextFinder(String(p.report_id)).matchEntireCell(true).findNext();
    if (!seen) {
      sheet.appendRow([new Date()].concat(FIELDS.map(function (f) { return p[f] || ''; })));
      if (emailOn_()) {
        MailApp.sendEmail(Session.getEffectiveUser().getEmail(),
          'Road report: ' + p.level + (p.observer ? ' from ' + p.observer : ''),
          FIELDS.map(function (f) { return f + ': ' + (p[f] || ''); }).join('\n'));
      }
    }
    return reply_({ ok: true, duplicate: !!seen });
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  return reply_({ ok: true, service: 'Lieutenant Island road reports' });
}

/* run once from the editor: creates both tabs and triggers Google's permission prompt */
function setup() {
  reportsTab_();
  emailOn_();
}

function reportsTab_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet(), sh = ss.getSheetByName('Reports');
  if (!sh) {
    sh = ss.insertSheet('Reports');
    sh.appendRow(['received_at'].concat(FIELDS));
    sh.setFrozenRows(1);
  }
  return sh;
}

function emailOn_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet(), sh = ss.getSheetByName('Settings');
  if (!sh) {
    sh = ss.insertSheet('Settings');
    sh.getRange('A1').setValue('Email me about each report');
    sh.getRange('B1').insertCheckboxes().setValue(true);
  }
  return sh.getRange('B1').getValue() === true;
}

function reply_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
