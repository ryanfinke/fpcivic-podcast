/**
 * FPCA Podcast — private listen analytics
 *
 * Deploy this as a Google Apps Script *Web App* on your PERSONAL account
 * (ryan.finke@gmail.com). It receives playback-milestone events from the podcast
 * website's audio player, logs them to a private Google Sheet, and emails you a
 * monthly funnel (how many started, and what % reached 10s / 25% / 50% / 75% /
 * 100%). Nothing is shown publicly.
 *
 * See SETUP.md for the (one-time) deployment steps.
 */

const NOTIFY_EMAIL = 'ryan.finke@gmail.com';
const SHEET_NAME = 'Events';
// Milestones the website player reports, in funnel order.
const MILESTONES = ['play', '10s', '25', '50', '75', 'complete'];
const MILESTONE_LABEL = {
  '10s': '≥ 10 seconds',
  '25': '25%',
  '50': '50%',
  '75': '75%',
  'complete': '100% (completed)',
};

// ─── Collector (receives events from the website) ───────────────────────────────
function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d && d.ep && d.ev) {
      sheet_().appendRow([
        new Date(),
        String(d.ep).slice(0, 120),
        String(d.ev).slice(0, 20),
        String(d.sid || '').slice(0, 40),
      ]);
    }
  } catch (err) {
    // Never fail loudly — a bad beacon must not error the endpoint.
  }
  return ContentService.createTextOutput('ok');
}

function doGet() {
  return ContentService.createTextOutput('FPCA podcast analytics collector — OK');
}

// ─── One-time setup ─────────────────────────────────────────────────────────────
/**
 * Run ONCE from the editor (authorize when prompted). Creates the private
 * spreadsheet, remembers its id, and installs the monthly email trigger.
 */
function setup() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('SHEET_ID');
  if (!id) {
    // Use the spreadsheet this script is bound to (the one you created manually).
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName(SHEET_NAME);
    if (!sh) {
      sh = ss.getActiveSheet();
      sh.setName(SHEET_NAME);
    }
    if (sh.getLastRow() === 0) {
      sh.appendRow(['Timestamp', 'Episode', 'Milestone', 'SessionId']);
    }
    id = ss.getId();
    props.setProperty('SHEET_ID', id);
    Logger.log('Using existing spreadsheet: ' + ss.getUrl());
  } else {
    Logger.log('Using existing spreadsheet id: ' + id);
  }
  // (Re)install the monthly report trigger: 1st of each month, ~8am.
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'emailMonthlyReport')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('emailMonthlyReport').timeBased().onMonthDay(1).atHour(8).create();
  Logger.log('Monthly report trigger installed (1st of month ~8am). Setup complete.');
}

// ─── Monthly report ─────────────────────────────────────────────────────────────
/** Aggregates the PREVIOUS calendar month and emails the funnel. */
function emailMonthlyReport() {
  const rows = sheet_().getDataRange().getValues();
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const end = new Date(now.getFullYear(), now.getMonth(), 1);

  // episode -> { milestone -> Set(sessionId) }  (unique sessions per milestone)
  const data = {};
  for (let i = 1; i < rows.length; i++) {
    const ts = new Date(rows[i][0]);
    if (ts < start || ts >= end) continue;
    const ep = rows[i][1], ms = rows[i][2], sid = rows[i][3];
    if (!data[ep]) {
      data[ep] = {};
      MILESTONES.forEach(m => (data[ep][m] = {}));
    }
    if (data[ep][ms]) data[ep][ms][sid] = true;
  }

  const size = obj => Object.keys(obj).length;
  const monthLabel = Utilities.formatDate(start, Session.getScriptTimeZone(), 'MMMM yyyy');
  let body = 'FPCA Podcast — website listen funnel for ' + monthLabel + '\n\n' +
    '(Unique website-player sessions. Podcast-app downloads are tracked separately ' +
    'on OP3 — see your OP3 dashboard. Drop-off is only measurable on the website; ' +
    'apps do not report playback progress.)\n\n';

  const eps = Object.keys(data).sort();
  if (eps.length === 0) {
    body += '(No website plays recorded in ' + monthLabel + '.)\n';
  }
  eps.forEach(ep => {
    const plays = Math.max(
      size(data[ep]['play']), size(data[ep]['10s']),
      size(data[ep]['25']), size(data[ep]['50']),
      size(data[ep]['75']), size(data[ep]['complete']));
    body += ep + '\n';
    body += '  Plays: ' + plays + '\n';
    ['10s', '25', '50', '75', 'complete'].forEach(m => {
      const n = size(data[ep][m]);
      const pct = plays ? Math.round((100 * n) / plays) : 0;
      body += '    ' + MILESTONE_LABEL[m] + ': ' + n + '  (' + pct + '% of plays)\n';
    });
    body += '\n';
  });

  body += 'Podcast-app downloads (all apps): https://op3.dev/  → your show dashboard\n';
  MailApp.sendEmail({
    to: NOTIFY_EMAIL,
    subject: 'FPCA Podcast analytics — ' + monthLabel,
    body: body,
  });
}

// ─── Helpers ────────────────────────────────────────────────────────────────────
function sheet_() {
  const id = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (!id) throw new Error('Not set up yet — run setup() once first.');
  return SpreadsheetApp.openById(id).getSheetByName(SHEET_NAME);
}

/** Optional: run manually to send the standard report for the PREVIOUS month. */
function emailReportNow() {
  emailMonthlyReport();
}

/** Test helper: emails the funnel for the CURRENT month-so-far (includes today's
 * rows), so you can verify formatting/delivery without waiting for month-end. */
function emailThisMonthNow() {
  const rows = sheet_().getDataRange().getValues();
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const data = {};
  for (let i = 1; i < rows.length; i++) {
    const ts = new Date(rows[i][0]);
    if (ts < start || ts >= end) continue;
    const ep = rows[i][1], ms = rows[i][2], sid = rows[i][3];
    if (!data[ep]) { data[ep] = {}; MILESTONES.forEach(m => (data[ep][m] = {})); }
    if (data[ep][ms]) data[ep][ms][sid] = true;
  }
  const size = o => Object.keys(o).length;
  const month = Utilities.formatDate(start, Session.getScriptTimeZone(), 'MMMM yyyy');
  let body = 'TEST PREVIEW — this is a manual test of the podcast analytics email.\n' +
    'It shows website listens for ' + month + ' so far (the real report is sent ' +
    'automatically on the 1st of each month for the full prior month).\n\n' +
    'FPCA Podcast — website listen funnel, ' + month + ' (month-to-date)\n\n';
  const eps = Object.keys(data).sort();
  if (eps.length === 0) body += '(No website plays recorded yet.)\n';
  eps.forEach(ep => {
    const plays = Math.max(size(data[ep]['play']), size(data[ep]['10s']), size(data[ep]['25']),
      size(data[ep]['50']), size(data[ep]['75']), size(data[ep]['complete']));
    body += ep + '\n  Plays: ' + plays + '\n';
    ['10s', '25', '50', '75', 'complete'].forEach(m => {
      const n = size(data[ep][m]); const pct = plays ? Math.round((100 * n) / plays) : 0;
      body += '    ' + MILESTONE_LABEL[m] + ': ' + n + '  (' + pct + '% of plays)\n';
    });
    body += '\n';
  });
  MailApp.sendEmail({
    to: NOTIFY_EMAIL,
    subject: 'FPCA Podcast analytics — TEST preview (' + month + ' month-to-date)',
    body: body,
  });
}
