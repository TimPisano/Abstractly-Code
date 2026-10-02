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
Why the format matters.</p>
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
numbers) at the top of the report. All export options.</p>

<h3>Optional: add the T-12</h3>
<p>To compare the rent roll with what the property actually collected, use <strong>Cross-Check Against a T12</strong>
at the bottom of <a data-goto="upload">Upload Leases</a>. How the T-12 check works.</p>

<p>Something not working? See Fixing upload problems and
When the report looks wrong.</p>
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
How to fix that.</p>

<h3>T-12 types</h3>
<p>Rows starting with "T12" come from the T-12 cross-check. See T-12 cross-check.</p>
`},

];
