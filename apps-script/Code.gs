/* Lieutenant Island road reports: receives reports from the crossing site and adds each one as a row in this Sheet.

   One-time setup, in the Google account that should own the reports:
   1. Create a Google Sheet (any name), then open Extensions → Apps Script.
   2. Replace everything in Code.gs with this file and save.
   3. Pick "setup" in the function menu and click Run, then approve the permissions Google asks for.
   4. Deploy → New deployment → type "Web app". Execute as: Me. Who has access: Anyone. Click Deploy.
   5. Copy the Web app URL (it ends in /exec) into REPORT_URL in site/index.html.

   Reports land on the "Reports" tab. Untick the box on the "Settings" tab to stop the email for each report.
   After editing this code: Deploy → Manage deployments → edit (pencil) → Version: New version, so the URL stays the same. */

var FIELDS = ['report_id', 'seen_at', 'level', 'edge', 'depth_in', 'depth_how', 'observer', 'forecast_in', 'high_tide', 'reported_at',
  // added 2026-09-16, always at the end so earlier rows keep their columns: what the page would have said 6 and 24 hours
  // before the time seen, and the printed tide chart, all as inches over the road (negative = below it)
  'forecast_6h_in', 'forecast_24h_in', 'chart_in'];
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
  // grade against the forecast from 6 hours before: forecast_in is worked out when the report is sent, by which time it
  // leans on the gauge's reading of the very tide being reported. Reports from a phone still running the older page
  // don't carry it, so those fall back to forecast_in
  var early = num_(p.forecast_6h_in), fc = early != null ? early : num_(p.forecast_in), chart = num_(p.chart_in);
  var fcWet = fc != null && fc > 0;

  // the same start on every report, so they're easy to search for or filter into a label
  var subject = 'Lt Island - Road Report (' + (p.observer || 'no name') + (when ? ', ' + when.date : '') + ')';

  var lines = [who + ' reported the road ' + (wet ? 'wet' : 'dry') + (when ? ' at ' + when.time + ' on ' + when.longDay : '') + '.', '',
    'Seen at the road:',
    '  • ' + (wet ? 'Wet' : 'Dry') + (p.depth_in ? ', about ' + p.depth_in + (Number(p.depth_in) === 1 ? ' inch' : ' inches') + ' over the road (' + (p.depth_how === 'measured' ? 'measured' : 'estimated') + ')' : '')];
  if (p.edge === 'rising') lines.push('  • The water was only just coming over the road');
  if (p.edge === 'falling') lines.push('  • The water had only just gone off the road');
  if (fc != null) {
    lines.push('', 'The forecast for ' + (when ? when.time : 'that time') + (early != null ? ', as it stood 6 hours before:' : ':'),
      '  • ' + roadText_(fc, true),
      '  • ' + verdict_(wet, fcWet, fc, p.depth_in ? Number(p.depth_in) : null));
  }
  if (chart != null) lines.push('', 'The printed tide chart had the water ' + roadText_(chart, false) + '.');
  lines.push('', 'Sent at ' + sentAt_(p.reported_at, p.seen_at) + '.');
  if (sheetUrl) lines.push('All reports: ' + sheetUrl);
  return { subject: subject, body: lines.join('\n') };
}

/* the same comparison the site shows after someone sends a report */
function verdict_(wet, fcWet, fc, depth) {
  if (wet && fcWet && depth != null) {
    var off = depth - fc;
    return Math.abs(off) <= 3 ? 'Close to the forecast depth' : inches_(Math.abs(off)) + ' ' + (off > 0 ? 'deeper' : 'shallower') + ' than the forecast';
  }
  if (wet === fcWet) return Math.abs(fc) <= 6 ? 'Matches the forecast, with the water close to the road’s height' : 'Matches the forecast';
  if (Math.abs(fc) <= 6) return 'Different from the forecast, but close to the road’s height, so it helps pin down how high the road really is';
  if (Math.abs(fc) > 24) return 'Far from the forecast, so the time may be off';
  return 'Different from the forecast, worth a look';
}

/* inches over the road (negative = below) as words: "about 3 inches over the road", or "just below the road" within an inch */
function roadText_(x, capital) {
  var t = (Math.abs(x) < 1 ? 'just' : 'about ' + inches_(Math.abs(x))) + (x > 0 ? ' over' : ' below') + ' the road';
  return capital ? t.charAt(0).toUpperCase() + t.slice(1) : t;
}

function num_(v) {
  return v === '' || v == null || isNaN(Number(v)) ? null : Number(v);
}

function inches_(x) {
  return x < 1 ? 'under an inch' : x >= 24 ? (x / 12).toFixed(1) + ' feet' : Math.round(x) === 1 ? '1 inch' : Math.round(x) + ' inches';
}

/* "2026-09-16T12:30" (Wellfleet time, as the site sends it) → 12:30pm, 9/16/2026, Wednesday, September 16 */
function wallTime_(s) {
  var a = String(s).split(/[-T: ]/).map(Number);
  var day = new Date(Date.UTC(a[0], a[1] - 1, a[2])).getUTCDay();
  return {
    time: (a[3] % 12 || 12) + ':' + ('0' + a[4]).slice(-2) + (a[3] < 12 ? 'am' : 'pm'),
    date: a[1] + '/' + a[2] + '/' + a[0],
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
  // a sheet made by an earlier version of this script: add headings for any columns that have been added since
  var want = ['received_at'].concat(FIELDS), have = sh.getLastColumn();
  if (have < want.length) sh.getRange(1, have + 1, 1, want.length - have).setValues([want.slice(have)]);
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
