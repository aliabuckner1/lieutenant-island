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
var TZ = 'America/New_York';
var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

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
        var mail = emailFor_(p, SpreadsheetApp.getActiveSpreadsheet().getUrl());
        MailApp.sendEmail(Session.getEffectiveUser().getEmail(), mail.subject, mail.body);
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

/* ---- the notification email: a skimmable subject, then what was seen next to what the forecast said ---- */
function emailFor_(p, sheetUrl) {
  var who = p.observer || 'Someone', wet = p.level !== 'dry';
  var when = p.seen_at ? wallTime_(p.seen_at) : null;
  var fc = p.forecast_in === '' || p.forecast_in == null ? null : Number(p.forecast_in);
  var fcWet = fc != null && fc > 0;
  var surprise = fc != null && wet !== fcWet;

  var subject = who + ' reported the road ' + (wet ? 'wet' : 'dry') + (when ? ' at ' + when.time + ' ' + when.shortDay : '') +
    (surprise ? ' — forecast said ' + (fcWet ? 'wet' : 'dry') : '');

  var lines = [who + ' reported the road ' + (wet ? 'wet' : 'dry') + (when ? ' at ' + when.time + ' on ' + when.longDay : '') + '.', '',
    'Seen at the road:',
    '  • ' + (wet ? 'Wet' : 'Dry') + (p.depth_in ? ', about ' + p.depth_in + ' in deep (' + (p.depth_how === 'measured' ? 'measured' : 'estimated') + ')' : '')];
  if (p.edge === 'rising') lines.push('  • The water was only just coming over the road');
  if (p.edge === 'falling') lines.push('  • The water had only just gone off the road');
  if (fc != null) {
    lines.push('', 'The forecast for ' + (when ? when.time : 'that time') + ':',
      '  • ' + (fcWet ? 'About ' + inches_(fc) + ' over the road' : 'About ' + inches_(-fc) + ' below the road'),
      '  • ' + verdict_(wet, fcWet, fc, p.depth_in ? Number(p.depth_in) : null));
  }
  lines.push('', 'Sent at ' + sentAt_(p.reported_at, p.seen_at) + '.');
  if (sheetUrl) lines.push('All reports: ' + sheetUrl);
  return { subject: subject, body: lines.join('\n') };
}

/* the same comparison the site shows after someone sends a report */
function verdict_(wet, fcWet, fc, depth) {
  if (wet && fcWet && depth != null) {
    var off = depth - fc;
    return Math.abs(off) <= 3 ? 'Close to the forecast depth' : Math.round(Math.abs(off)) + ' in ' + (off > 0 ? 'deeper' : 'shallower') + ' than the forecast';
  }
  if (wet === fcWet) return Math.abs(fc) <= 6 ? 'Matches the forecast, with the water close to the road’s height' : 'Matches the forecast';
  if (Math.abs(fc) <= 6) return 'Different from the forecast, but close to the road’s height, so it helps pin down how high the road really is';
  if (Math.abs(fc) > 24) return 'Far from the forecast, so the time may be off';
  return 'Different from the forecast, worth a look';
}

function inches_(x) {
  return x < 1 ? 'under 1 in' : x >= 24 ? (x / 12).toFixed(1) + ' ft' : Math.round(x) + ' in';
}

/* "2026-09-16T12:30" (Wellfleet time, as the site sends it) → 12:30pm, Wed Sep 16, Wednesday, September 16 */
function wallTime_(s) {
  var a = String(s).split(/[-T: ]/).map(Number);
  var day = new Date(Date.UTC(a[0], a[1] - 1, a[2])).getUTCDay();
  return {
    time: (a[3] % 12 || 12) + ':' + ('0' + a[4]).slice(-2) + (a[3] < 12 ? 'am' : 'pm'),
    shortDay: DAYS[day].slice(0, 3) + ' ' + MONTHS[a[1] - 1].slice(0, 3) + ' ' + a[2],
    longDay: DAYS[day] + ', ' + MONTHS[a[1] - 1] + ' ' + a[2]
  };
}

function sentAt_(iso, seenAt) {
  if (!iso) return 'an unknown time';
  var d = new Date(iso);
  var sameDay = seenAt && String(seenAt).slice(0, 10) === Utilities.formatDate(d, TZ, 'yyyy-MM-dd');
  return Utilities.formatDate(d, TZ, 'h:mma').toLowerCase() + (sameDay ? '' : ' on ' + Utilities.formatDate(d, TZ, 'EEEE, MMMM d'));
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
