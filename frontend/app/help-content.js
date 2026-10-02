/**
 * Help & Guides articles, rendered by help-view.js.
 *
 * Written for CRE analysts, not engineers. Every fact here was checked
 * against the code on 2026-10-01 (see docs/tester-pack/HELP_FACTS.md for
 * the file:line behind each claim). When behavior changes, update the
 * article in the same branch -- a help page that's wrong is worse than
 * none.
 *
 * Format: { id, category, title, summary, body }. body is trusted static
 * HTML. Links: <a data-help-link="article-id"> opens another article,
 * <a data-goto="view-name"> jumps to that screen in the app.
 */
window.HELP_ARTICLES = [

// ------------------------------------------------------------ Start here
{
    id: 'getting-started',
    category: 'Start here',
    title: 'Getting started: your first deal in 5 steps',
    summary: 'Upload leases and a rent roll, read the Deal Mismatch Report, export it.',
    body: `
<p>Abstractly checks a seller's rent roll against the actual signed leases, unit by unit, and tells you
where they disagree, what each disagreement is worth in dollars, and which lease page proves it.
This is the whole loop.</p>

<div class="help-callout"><strong>Best first test:</strong> use a deal you've already closed or underwritten,
so you already know what's wrong with its rent roll and can judge what Abstractly finds.</div>

<h3>1. Upload the leases</h3>
<p>Go to <a data-goto="upload">Upload Leases</a> and drop in the lease files. PDFs (including scans), Word
documents and images all work, up to 16&nbsp;MB each, and you can drop many at once. A single PDF that
contains several leases is split automatically. Each lease takes a few seconds to a minute to read.</p>
<p>Upload leases as <strong>PDF, Word or image files</strong>, not Excel or CSV. Spreadsheets are treated as rent roll data.</p>

<h3>2. Import the rent roll</h3>
<p>On the same page, under <strong>Import Rent Roll</strong>, type the <strong>property address</strong> (exactly as it
appears on the leases), then drop in the rent roll. For the Deal Mismatch Report, use the
<strong>Excel (.xlsx) or CSV</strong> export from the property management system.
<a data-help-link="importing-rent-roll">Why the format matters</a>.</p>
<p>Abstractly finds the tenant and rent columns on its own. Vacant units and subtotal rows are skipped, and
the import results list every row it skipped and why.</p>

<h3>3. Open the Deal Mismatch Report</h3>
<p>Click <a data-goto="dealmismatch">Deal Mismatch Report</a> in the sidebar. At the top you'll see how many units were
checked, how many discrepancies were found, and the net effect on income: whether the rent roll
<strong>overstates</strong> or <strong>understates</strong> what the leases support, per year.</p>
<p>Below that is one row per discrepancy, sorted by severity, with the rent roll's value, the lease's value,
the <strong>lease page</strong> the lease value came from, and the annual dollar impact.
<a data-help-link="discrepancy-types">What each discrepancy type means</a>.</p>

<h3>4. Check the big ones against the lease</h3>
<p>For any finding you want to verify, open the lease from the <a data-goto="dashboard">Dashboard</a>. Every extracted
value shows the page number and the exact quote it came from. If Abstractly read something wrong, click the
value and correct it, then press <strong>Refresh</strong> on the report.</p>

<h3>5. Export it</h3>
<p>Use <strong>Download PDF</strong> (to share with an IC, lender or LP) or <strong>Download Excel</strong> (to work the
numbers) at the top of the report. <a data-help-link="exporting">All export options</a>.</p>

<h3>Optional: add the T-12</h3>
<p>To compare the rent roll with what the property actually collected, use <strong>Cross-Check Against a T12</strong>
at the bottom of <a data-goto="upload">Upload Leases</a>. <a data-help-link="t12-cross-check">How the T-12 check works</a>.</p>

<p>Something not working? See <a data-help-link="upload-problems">Fixing upload problems</a> and
<a data-help-link="report-looks-wrong">When the report looks wrong</a>.</p>
`},

{
    id: 'discrepancy-types',
    category: 'Start here',
    title: 'What each discrepancy type means',
    summary: 'Rent mismatch, expired but occupied, unit with no lease, and the rest.',
    body: `
<p>Every row in the Deal Mismatch Report has one of these types. "Overstates" means the rent roll shows
more income than the leases support. "Understates" means it shows less.</p>

<div class="help-table-wrap"><table>
<tr><th>Type</th><th>What it means</th><th>Dollar impact</th></tr>
<tr><td><strong>Rent Mismatch</strong></td><td>The rent on the rent roll differs from the rent in the lease, by more than $5 <em>and</em> more than 1%. Smaller rounding differences are ignored.</td><td>The monthly difference × 12. Overstates if the rent roll is higher.</td></tr>
<tr><td><strong>Expired but Occupied</strong></td><td>The lease's end date has passed, but the rent roll still shows a tenant paying rent. The unit may be month-to-month, renewed without paperwork, or not really earning that rent.</td><td>The rent roll's full rent for the unit × 12. Always overstates.</td></tr>
<tr><td><strong>Unit on Rent Roll, No Lease</strong></td><td>The rent roll lists a unit, but there's no lease for it on file. The rent is unverified, not necessarily wrong. It may just be a lease you haven't uploaded.</td><td>The rent roll's rent × 12, shown without a direction (it's unconfirmed, not proven too high or too low).</td></tr>
<tr><td><strong>Lease on File, Not on Rent Roll</strong></td><td>You uploaded a lease for a unit that doesn't appear on the rent roll at all.</td><td>The lease rent × 12. Understates (a signed lease the rent roll isn't counting).</td></tr>
<tr><td><strong>Lease Dates Mismatch</strong></td><td>The start or end date on the rent roll is different from the lease, by any number of days. One row per date.</td><td>None. A date difference has no dollar value on its own.</td></tr>
<tr><td><strong>Tenant Name Mismatch</strong></td><td>The tenant named on the rent roll isn't the tenant on the lease. This can mean an unrecorded assignment, a roommate change, or the wrong lease filed for the unit.</td><td>None, but always marked <strong>high</strong> severity.</td></tr>
<tr><td><strong>Concession Missing from Rent Roll</strong></td><td>Reserved for lease concessions the rent roll doesn't reflect. Not checked yet in this version, so you won't see it.</td><td>—</td></tr>
</table></div>

<h3>Severity</h3>
<p>Severity follows the monthly dollar impact: <strong>High</strong> is $1,000/month or more, <strong>Medium</strong>
is $250–$999/month (and any finding whose dollar value can't be computed), <strong>Low</strong> is under $250/month.
Tenant name mismatches are always High.</p>

<h3>The "Source" column</h3>
<p>"Page N" is the lease page the lease-side value came from. Open that lease to see the exact quote.
"Unit on Rent Roll, No Lease" rows never have a page, because there's no lease to cite.</p>

<h3>How units are matched</h3>
<p>A rent roll row and a lease are compared when their <strong>property address and unit</strong> match.
If the same unit is written differently in the two places (e.g. "Apt 4B" vs "Unit 4B"), they won't match,
and you'll see a "No Lease" row and a "Not on Rent Roll" row for the same unit.
<a data-help-link="report-looks-wrong">How to fix that</a>.</p>

<h3>T-12 types</h3>
<p>Rows starting with "T12" come from the T-12 cross-check. See <a data-help-link="t12-cross-check">T-12 cross-check</a>.</p>
`},

// ------------------------------------------------------------ The core workflow
{
    id: 'uploading-leases',
    category: 'Core workflow',
    title: 'Uploading leases',
    summary: 'File types, scans, multi-lease PDFs, and how long it takes.',
    body: `
<p>Go to <a data-goto="upload">Upload Leases</a>, then drag files onto the box or click to browse. You can select many files at once.</p>
<h3>What you can upload</h3>
<ul>
<li><strong>PDF</strong>: text-based or scanned. Scans are read with OCR.</li>
<li><strong>Word</strong> (.docx, .doc), <strong>images</strong> (.jpg, .png, .tif) and plain text.</li>
<li>Up to <strong>16&nbsp;MB</strong> and <strong>150 pages</strong> per file.</li>
</ul>
<p>Excel and CSV files are accepted here too, but for leases please use PDF/Word/images. Spreadsheet uploads are
treated as rent roll data by the Deal Mismatch Report.</p>

<h3>Several leases in one PDF</h3>
<p>If a PDF contains more than one lease, Abstractly splits it and creates a separate lease for each, showing which
pages each one came from ("Split into 3 separate leases").</p>

<h3>How long it takes</h3>
<p>Most leases take a few seconds to a minute. Scanned documents and multi-lease files take longer; the progress
message tells you it's still working. If it's still going after several minutes, check the lease list later. It may
finish on its own.</p>

<h3>Scanned documents</h3>
<p>Clean scans work. If some pages are photos with no readable text, Abstractly stops and asks for a better copy
rather than guessing ("…appear to be scanned images with no usable text layer"). Re-scan with OCR turned on, or
upload the original PDF. Fields read from poor-quality scans are marked <strong>Needs OCR</strong>. Check them against
the document.</p>

<h3>No document handy?</h3>
<p><strong>Try a Sample Lease Instead</strong> on the upload page adds a fictional lease marked "Sample" so you can look around.</p>

<p>Problems? <a data-help-link="upload-problems">Fixing upload problems</a>.</p>
`},

{
    id: 'importing-rent-roll',
    category: 'Core workflow',
    title: 'Importing a rent roll',
    summary: 'Formats that work best, the property address, and skipped rows.',
    body: `
<p>On <a data-goto="upload">Upload Leases</a>, scroll to <strong>Import Rent Roll</strong>. One file at a time.</p>

<h3>1. Enter the property address</h3>
<p>Most rent rolls list the building once at the top, not on every row. Type the property address in the box
<strong>exactly as it's written on the leases</strong>. Abstractly combines it with each row's unit number
("123 Main St, Suite 4B") so rows line up with the right lease. This is the most important step for an accurate report.</p>

<h3>2. Choose the right file</h3>
<div class="help-callout warn"><strong>For the Deal Mismatch Report, import the rent roll as Excel (.xlsx) or CSV.</strong>
Other formats (PDF, Word, .xls, photos) import fine and show up in the Rent Roll page, but in this beta
the Deal Mismatch Report only treats .xlsx and .csv files as the rent roll. Most property management
systems (Yardi, AppFolio, RealPage, Entrata) can export to Excel.</div>

<h3>What Abstractly does with it</h3>
<ul>
<li>Finds the header row on its own (within the first 20 rows) and works out which columns hold the tenant, rent and dates. No template needed.</li>
<li>Reads every worksheet in the workbook, not just the first.</li>
<li>Uses <em>actual</em> rent. Market rent, asking rent, pro forma and $/sq ft columns are deliberately ignored.</li>
<li>Skips rows for vacant units, totals and subtotals, and lists each skipped row with the reason ("Row 14 — vacant").</li>
</ul>
<p>Every imported value cites its source as "Row N of your file", so you can trace it back.</p>

<h3>Photos and scans</h3>
<p>Photos and scanned PDFs are read with OCR and need checking. Scanned PDFs are read up to 15 pages.
A spreadsheet export is always more reliable.</p>

<p>Import failed? See <a data-help-link="upload-problems">Fixing upload problems</a>.</p>
`},

{
    id: 'deal-mismatch-report',
    category: 'Core workflow',
    title: 'Reading the Deal Mismatch Report',
    summary: 'The summary tiles, the discrepancy table, and what to do with it.',
    body: `
<p>The <a data-goto="dealmismatch">Deal Mismatch Report</a> compares every rent roll row against the leases on file
and lists every disagreement with its dollar impact. It's the document to hand to a lender, LP or investment committee.</p>

<h3>The summary</h3>
<ul>
<li><strong>Units checked</strong>: how many distinct units appeared on the rent roll or in a lease.</li>
<li><strong>Discrepancies found</strong>: the number of rows below.</li>
<li><strong>Income impact</strong>: the net annual effect. "Rent Roll Overstates +$X" means the rent roll shows
$X/year more income than the leases support. Findings with no direction (unconfirmed units, date or name
differences) are left out of this total, not counted as zero.</li>
</ul>

<h3>The table</h3>
<p>One row per finding, highest severity first: unit, type, the rent roll's value, the lease's value, the lease page it
came from, severity and annual impact. See <a data-help-link="discrepancy-types">what each type means</a>.</p>

<h3>Working through it</h3>
<ol>
<li>Start with <strong>High</strong> severity rows. They carry most of the dollars.</li>
<li>For each, open the lease and check the cited page. If Abstractly misread the lease, correct the field
(<a data-help-link="lease-fields">how</a>) and press <strong>Refresh</strong>.</li>
<li>A cluster of "No Lease" + "Not on Rent Roll" rows for the same units usually means the addresses don't match,
not that leases are missing. See <a data-help-link="report-looks-wrong">When the report looks wrong</a>.</li>
<li>Record what you decided in <a data-goto="discrepancies">Discrepancies</a> (resolve with a note) so the team sees it.</li>
</ol>

<h3>Who can see it</h3>
<p>The report needs the <strong>Analyst</strong> role or higher. Viewers get "Analyst role required".</p>

<h3>The T-12 box on this page</h3>
<div class="help-callout warn"><strong>Known beta issue:</strong> attaching a T-12 file on this page currently fails with
"t12_file requires property_address". Leave it empty and use <strong>Cross-Check Against a T12</strong> on the
<a data-goto="upload">Upload Leases</a> page instead. <a data-help-link="t12-cross-check">Details</a>.</div>
`},

{
    id: 't12-cross-check',
    category: 'Core workflow',
    title: 'T-12 cross-check',
    summary: 'Compare the rent roll with what the property actually collected.',
    body: `
<p>A rent roll says what tenants <em>should</em> pay. A T-12 operating statement says what the property actually
<em>collected</em> over the last twelve months. A large gap between the two is worth explaining before you close.</p>

<h3>How to run it</h3>
<ol>
<li>Go to <a data-goto="upload">Upload Leases</a> and scroll to <strong>Cross-Check Against a T12</strong>.</li>
<li>Enter the <strong>property address</strong> (required). It must match how the property appears on the rent roll and leases.</li>
<li>Upload the T-12 as <strong>.xlsx or .csv</strong>, one file per property.</li>
</ol>
<p>You'll get <strong>Matches</strong> or <strong>Discrepancy Flagged</strong>. A gap is flagged when the rent roll's annual rent and the
T-12's actual rental income differ by more than <strong>5% and more than $3,000 a year</strong>. Flagged results also
appear in <a data-goto="discrepancies">Discrepancies</a> under "T12 Reconciliation".
The T-12 file itself is checked once and not stored.</p>

<h3>What the T-12 needs</h3>
<p>A line for <strong>actual rental income collected</strong> (for example "Rental Income" or "Net Rental Income").
"Gross Potential Rent" alone isn't enough, because that's what the rent roll already claims. Abstractly also reads concessions,
vacancy loss, bad debt and other income when they're present. The header row should be within the first 20 rows.</p>

<div class="help-callout warn"><strong>Known beta issue:</strong> the T-12 box on the Deal Mismatch Report page doesn't work
yet, so use the Upload page as described above.</div>
`},

{
    id: 'exporting',
    category: 'Core workflow',
    title: 'Exporting reports',
    summary: 'PDF and Excel of the Deal Mismatch Report, plus every other export.',
    body: `
<h3>Deal Mismatch Report</h3>
<ul>
<li><strong>Download PDF</strong>: summary (units checked, discrepancies found, net income impact) and the full table with
unit, type, rent roll value, lease value, source page, severity and annual impact. Made for sharing.</li>
<li><strong>Download Excel</strong>: the same rows with extra columns (field, monthly impact, annual impact, income
direction) for your own analysis.</li>
</ul>

<h3>Rent roll</h3>
<p>On <a data-goto="rentroll">Rent Roll</a>: <strong>Download CSV</strong>, <strong>Download Excel</strong> (adds a Portfolio Summary tab),
or <strong>Export to Google Sheets</strong>.</p>

<h3>Leases</h3>
<ul>
<li>From the <a data-goto="dashboard">Dashboard</a> lease library: Excel of all or selected leases, Google Sheets, or a
<strong>Summary Memo</strong> PDF.</li>
<li><strong>Export Report</strong> builds an investment memo (PDF or Excel) with key lease terms, flagged discrepancies and their
resolutions, a T-12 cross-check summary and a rollover schedule.</li>
<li>On a single lease: Export Report, Download Excel, Summary Memo, Google Sheets, or JSON.</li>
</ul>

<h3>Portfolio report</h3>
<p><a data-goto="report">Portfolio Report</a> can be printed / saved as PDF, or downloaded as HTML or CSV.</p>

<p>Exports that build reports (Google Sheets, Export Report, the Deal Mismatch Report) need the Analyst role.</p>
`},

// ------------------------------------------------------------ Working with leases
{
    id: 'lease-fields',
    category: 'Working with leases',
    title: 'Lease fields, citations and corrections',
    summary: 'What gets extracted, the confidence badges, and how to fix a value.',
    body: `
<h3>What Abstractly reads from each lease</h3>
<ul>
<li><strong>Parties:</strong> tenant, landlord, property address</li>
<li><strong>Financial terms:</strong> monthly rent, security deposit, CAM charges, rent escalation, insurance requirements, square footage</li>
<li><strong>Dates and term:</strong> start date, end date, renewal options, default / cure period</li>
<li><strong>Special clauses:</strong> permitted use, exclusivity</li>
</ul>

<h3>Every value shows its source</h3>
<p>Open a lease and each value shows the <strong>page number and the exact quote</strong> it came from, so you can check it
in seconds instead of re-reading the lease. Values from a rent roll show "Row N of your file".</p>

<h3>The badges</h3>
<ul>
<li><strong>High / Medium / Low Confidence</strong>: how sure the extraction is. Check Low ones against the page.</li>
<li><strong>Not Found</strong>: the value isn't in the document (or couldn't be read). Abstractly leaves it blank rather than guess.</li>
<li><strong>Needs OCR</strong>: the value came from a poor-quality scan. Verify it.</li>
</ul>

<h3>Correcting a value</h3>
<p>Click any value to edit it. A corrected value is marked <strong>Manually Edited</strong>. Saving a blank marks it
<strong>Manually Verified — Not Found</strong>. Medium-confidence values also have <strong>Mark as verified</strong> if the value is
right. Every edit is logged and can be undone. Editing needs the Analyst role.</p>
<p>After correcting values, press <strong>Refresh</strong> on the Deal Mismatch Report to recompute it.</p>
`},

{
    id: 'amendments-and-versions',
    category: 'Working with leases',
    title: 'Amendments, new versions and replacing a lease',
    summary: 'Add an amendment, see version history, replace a bad upload.',
    body: `
<h3>Amendments</h3>
<p>Open the lease and drop the amendment into <strong>Version History</strong>. Values from the amendment take over where it changes
the terms, and those values say "(from <em>amendment file</em>)" next to the source.</p>
<h3>Replacing a lease</h3>
<p>On <a data-goto="rentroll">Rent Roll</a>, <strong>Replace</strong> on a row uploads a corrected document for that lease (one lease per file).
The old version is kept in history.</p>
<h3>Uploading the same file twice</h3>
<p>If you upload a file that's already in your portfolio, Abstractly reuses the existing lease instead of creating a duplicate.</p>
<h3>Deleting</h3>
<p>Select leases in the Dashboard lease library to delete them (Analyst role).</p>
`},

// ------------------------------------------------------------ Portfolio tools
{
    id: 'dashboard-and-alerts',
    category: 'Portfolio tools',
    title: 'Dashboard, Action Items, Alerts and Expirations',
    summary: "What's due, what's new, and what needs attention.",
    body: `
<ul>
<li><a data-goto="dashboard">Dashboard</a>: today's briefing, portfolio health score, fields that need review, tenant concentration and
rollover risk, and the lease library (filter, tag, compare, export, delete).</li>
<li><a data-goto="actionitems">Action Items</a>: everything date-driven in the next 90 days, including overdue tasks, lease expirations and renewal-notice deadlines, in date order.</li>
<li><a data-goto="alerts">Alerts</a>: raised automatically for upcoming expirations, new discrepancies, below-market rent and tenant concentration. Dismiss what you've handled.</li>
<li><a data-goto="timeline">Expirations</a>: leases grouped by how soon they expire.</li>
</ul>
`},

{
    id: 'discrepancies-and-tasks',
    category: 'Portfolio tools',
    title: 'Discrepancies, tasks and team notes',
    summary: 'Resolve findings with a note, assign follow-ups, keep a record.',
    body: `
<h3>Discrepancies</h3>
<p><a data-goto="discrepancies">Discrepancies</a> keeps every issue Abstractly has ever flagged (risk flags, cross-lease
differences, rent roll vs lease, rent roll vs T-12) with a permanent log of how each was resolved. Open one to
<strong>resolve</strong> it with a note (or reopen it), comment, or <strong>+ Create Task</strong>. <strong>Run reconciliation</strong> re-checks
the rent roll against the leases. Findings from the Deal Mismatch Report appear here too, labelled "deal_mismatch".</p>
<h3>Tasks</h3>
<p><a data-goto="tasks">Tasks</a> are to-dos with an owner, due date and priority. Create them from a discrepancy or alert, assign them
to a teammate, and complete or dismiss them in bulk.</p>
<h3>Team Notes</h3>
<p><a data-goto="teamnotes">Team Notes</a> shows every comment left on a lease or discrepancy, newest first. Comment from the lease
or discrepancy itself.</p>
`},

{
    id: 'rent-roll-compare-trends',
    category: 'Portfolio tools',
    title: 'Rent Roll, Compare, Trends and Portfolio Report',
    summary: 'Portfolio-wide views of everything you uploaded.',
    body: `
<ul>
<li><a data-goto="rentroll">Rent Roll</a>: one row per lease with totals. Edit cells inline, replace a lease, export to CSV, Excel or Google Sheets.
Click a number to see which lease and page it came from.</li>
<li><a data-goto="comparison">Compare</a>: pick two or more leases and see their terms side by side against the portfolio average.</li>
<li><a data-goto="trends">Portfolio Trends</a>: rollover risk, rent growth and expirations over time. It fills in as you upload more over time.</li>
<li><a data-goto="report">Portfolio Report</a>: a printable portfolio summary (upcoming expirations, rent outliers, risk flags).</li>
</ul>
`},

{
    id: 'ask-a-question',
    category: 'Portfolio tools',
    title: 'Ask a Question',
    summary: 'Ask about your leases in plain English and get cited answers.',
    body: `
<p><a data-goto="qa">Ask a Question</a> answers questions about the leases you've uploaded ("Which leases expire in the next
12 months?", "Who has an exclusivity clause?") with citations back to the leases. You can also ask about a single
lease from its detail page. Answers come from the uploaded documents. Check important answers against the cited source.
If you ask very quickly in a row you may be asked to wait a moment.</p>
`},

{
    id: 'team-and-roles',
    category: 'Portfolio tools',
    title: 'Team, roles and messaging',
    summary: 'Viewer, Analyst, Admin, and what each can do.',
    body: `
<div class="help-table-wrap"><table>
<tr><th>Role</th><th>Can do</th></tr>
<tr><td><strong>Viewer</strong></td><td>Look at everything (leases, citations, rent roll, alerts, discrepancies, reports), download standard exports, ask questions, message.</td></tr>
<tr><td><strong>Analyst</strong></td><td>Everything a viewer can, plus upload and import, edit and verify fields, resolve discrepancies, manage tasks and comments, Google Sheets and investment-memo exports, and the <strong>Deal Mismatch Report</strong>.</td></tr>
<tr><td><strong>Admin</strong></td><td>Everything, plus add team members, change roles, deactivate accounts and reset passwords on <a data-goto="team">Team</a>.</td></tr>
</table></div>
<p>If you click something your role can't do, you'll see "Analyst role required" or "Admin role required". Ask your admin.
There's no email invite yet: an admin creates your account and shares your login.</p>
<h3>Messaging</h3>
<p>The chat button at the bottom right opens direct and group conversations with your team.</p>
`},

// ------------------------------------------------------------ Troubleshooting
{
    id: 'upload-problems',
    category: 'Troubleshooting',
    title: 'Fixing upload problems',
    summary: 'What each upload error means and how to get past it.',
    body: `
<div class="help-table-wrap"><table>
<tr><th>You see</th><th>What to do</th></tr>
<tr><td>"File too large. Maximum size is 16MB."</td><td>Compress the PDF (Acrobat: <em>Reduce File Size</em>, or Preview: <em>Export → Reduce File Size</em>) or split it into smaller files.</td></tr>
<tr><td>"File has too many pages: … exceeds limit of 150."</td><td>Split the PDF. Multi-lease packets can be split by lease.</td></tr>
<tr><td>"Unsupported file type…" / "Invalid file type…"</td><td>Save as PDF (leases) or .xlsx / .csv (rent rolls). Zip files and Apple Numbers/Pages files aren't supported.</td></tr>
<tr><td>"This file is empty."</td><td>The file has no content. Re-export or re-download it.</td></tr>
<tr><td>"This PDF is password-protected…"</td><td>Open it, remove the password (or print to a new PDF) and upload the copy.</td></tr>
<tr><td>"Failed to extract text from this PDF…" / "…may be corrupted or unsupported"</td><td>Open it on your computer. If it opens, print it to a new PDF and upload that.</td></tr>
<tr><td>"…appear to be scanned images with no usable text layer…"</td><td>Some pages are photos with no readable text. Re-scan with OCR on, or upload the original digital lease.</td></tr>
<tr><td>"This looks like a rent roll or portfolio report, not a single lease document…"</td><td>Use <strong>Import Rent Roll</strong> (same page, further down) for rent rolls.</td></tr>
<tr><td>"This doesn't look like a lease — no tenant, landlord, rent, or dates were found"</td><td>Check it's really a lease (not a notice or an estoppel) and that it isn't a blank scan.</td></tr>
<tr><td>"Couldn't find a row with a recognizable tenant name column and rent column…"</td><td>The rent roll needs a tenant (or resident) column and a rent column with a header row near the top. Make sure the header row is within the first 20 rows (delete a long title block above it), or export a plain rent roll from your PMS.</td></tr>
<tr><td>"Rate limit exceeded: maximum 10 extractions per minute."</td><td>Wait a minute and upload the rest. Large batches go through 10 per minute.</td></tr>
<tr><td>"Your team has used all … documents included this month…"</td><td>Your team hit its monthly limit (200 documents by default). Contact us to raise it.</td></tr>
<tr><td>"Your account isn't assigned to a team yet…"</td><td>Ask your admin (or us) to add you to a team.</td></tr>
<tr><td>"Analyst role required"</td><td>Your account is a Viewer. Ask your admin to make you an Analyst.</td></tr>
<tr><td>"The document-extraction service is temporarily unavailable…"</td><td>Wait a minute and try again. If it keeps happening, tell us.</td></tr>
<tr><td>"Processing was interrupted by a server restart…" or a lease stuck on processing</td><td>Delete that lease and upload it again.</td></tr>
<tr><td>Your leases disappeared</td><td>See <a data-help-link="beta-notes">Beta notes</a>. The test server can lose files when it restarts. Re-upload them.</td></tr>
</table></div>
<p>Still stuck? Send us the file name, what you clicked and a screenshot of the message.</p>
`},

{
    id: 'report-looks-wrong',
    category: 'Troubleshooting',
    title: 'When the Deal Mismatch Report looks wrong',
    summary: 'Nothing found, too much found, or units that should have matched.',
    body: `
<h3>Lots of "No Lease" and "Not on Rent Roll" rows for the same units</h3>
<p>The rent roll and the leases describe the address differently, so Abstractly can't pair them. Re-import the rent roll with the
<strong>property address typed exactly as it appears in the leases</strong>. Check the Property Address on a couple of leases (open
the lease; correct it if it was misread), then press <strong>Refresh</strong>.</p>

<h3>"No discrepancies found" but you know there are some</h3>
<ul>
<li>Was the rent roll imported as <strong>.xlsx or .csv</strong>? In this beta, other formats aren't used by this report.
See <a data-help-link="importing-rent-roll">Importing a rent roll</a>.</li>
<li>Were the leases uploaded as PDF/Word/images? Leases uploaded as spreadsheets are treated as rent roll rows.</li>
<li>Do the addresses match (above)?</li>
<li>Was the rent read correctly? Open the lease and check Monthly Rent and its page citation.</li>
</ul>

<h3>A finding that isn't real</h3>
<p>Open the lease at the cited page. If Abstractly misread it, correct the field and Refresh. If the lease really says that,
the rent roll is the one that's wrong. Either way, please tell us; false alarms are the most useful feedback you can give.</p>

<h3>Vacant units</h3>
<p>Vacant rows on the rent roll are skipped on import, so vacant units don't appear in the report.</p>
`},

{
    id: 'beta-notes',
    category: 'Troubleshooting',
    title: 'Beta notes and known issues',
    summary: 'Things that are rough in the beta, and how to work around them.',
    body: `
<ul>
<li><strong>Keep your source files.</strong> The test server can lose uploaded documents when it restarts or redeploys.
If your leases disappear, re-upload them. Nothing is wrong on your side.</li>
<li><strong>T-12 box on the Deal Mismatch Report page</strong> doesn't work yet. Use <strong>Cross-Check Against a T12</strong> on the Upload page.</li>
<li><strong>Rent rolls for the Deal Mismatch Report</strong> must be .xlsx or .csv for now.</li>
<li><strong>Uploading the same file twice</strong> reuses the existing lease, but doesn't tell you it did.</li>
<li><strong>Concessions</strong> aren't checked against the rent roll yet.</li>
</ul>
<p>Found something else? Reply to your invite email with a screenshot. Every report helps.</p>
`},

];
