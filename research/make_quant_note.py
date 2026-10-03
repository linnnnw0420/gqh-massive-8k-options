"""Render an explicitly incomplete two-page quant note from public aggregates.

Importing or validating this module creates no PDF and accesses no API. The root
workflow must render and visually inspect the resulting PDF before submission.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
import html
import json
import math
from pathlib import Path

HORIZONS = ['1', '2', '3', '5', '10', '21', '42', '63', 'expiry']
STUDIES = ('original', 'corrected')
PENDING_WORDS = ('pending', 'placeholder', 'todo', 'tbd', 'unset')
# pandas orient='split' snapshots independently round each quantity to ten
# decimal places. A - B - difference can therefore differ by 1.5e-10 before
# binary floating-point error. This fixed absolute tolerance changes no value.
SNAPSHOT_DECIMAL_IDENTITY_ATOL = 2e-10


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must contain a finite measured value, not a placeholder.')
    return value


def _text(value, label, maximum=65):
    if not isinstance(value, str) or not value.strip() or any(word in value.lower() for word in PENDING_WORDS):
        raise ValueError(f'{label} is missing or contains a pending placeholder.')
    if len(value.split()) > maximum:
        raise ValueError(f'{label} exceeds its {maximum}-word layout budget.')
    return value


def _public_path(public_dir, relative):
    path = (Path(public_dir) / relative).resolve()
    if not path.is_relative_to(Path(public_dir).resolve()) or path.suffix.lower() != '.csv':
        raise ValueError('NAV input must be a CSV inside the declared public aggregate directory.')
    return path


def portfolio_names(payload):
    return STUDIES + (('causal',) if 'causal' in payload.get('portfolios',{}) else ())


def portfolio_label(name):
    return {'original':'V1 legacy','corrected':'V2 legacy','causal':'V3 causal'}[name]


def validate_payload(payload, public_dir):
    if payload.get('schema') != 'gqh_quant_note_v1':
        raise ValueError('Unexpected quant-note payload schema.')
    if payload.get('oos_status') != 'NOT_RUN' or payload.get('unseen_classifier_status') != 'NOT_READY':
        raise ValueError('This draft generator requires the explicit unfinished OOS/readiness status.')
    _text(payload.get('hypothesis_commit'), 'hypothesis_commit', 3)
    _text(payload.get('generated_utc'), 'generated_utc', 2)
    for name in STUDIES:
        study = payload['studies'][name]
        if study.get('status') != 'COMPLETE_IS_AGGREGATES':
            raise ValueError(f'{name} IS aggregates must be completed before PDF generation.')
        for field in ('eligible_disclosures', 'n_event', 'n_ordinary', 'variants', 'original_nav_gaps'):
            value = _number(study[field], name + '.' + field)
            if value < 0 or value != int(value):
                raise ValueError(f'{name}.{field} must be a nonnegative count.')
        _number(study['theta'], name + '.theta')
        for field in ('iid_interval', 'issuer_range', 'date_range'):
            pair = study[field]
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(name + '.' + field + ' requires two measured endpoints.')
            if _number(pair[0], field) > _number(pair[1], field):
                raise ValueError(field + ' is reversed.')
        rows = study['horizons']
        if len(rows) != 9 or [str(row['horizon']) for row in rows] != HORIZONS:
            raise ValueError('Every version must retain the nine fixed horizons in official order.')
        for row in rows:
            for field in ('event_cc_mean', 'ordinary_cc_mean', 'cc_difference', 'theta'):
                _number(row[field], name + '.' + str(row['horizon']) + '.' + field)
            for field in ('n_event','n_ordinary'):
                number=_number(row[field],name+'.horizon.'+field)
                if number<0 or int(number)!=number:
                    raise ValueError('Every horizon requires finite-sample counts.')
            for field in ('cc_iid_interval','theta_iid_interval'):
                pair=row[field]
                if not isinstance(pair,list) or len(pair)!=2 or _number(pair[0],field)>_number(pair[1],field):
                    raise ValueError('Every horizon requires an ordered measured uncertainty interval.')
            if not math.isclose(row['event_cc_mean'] - row['ordinary_cc_mean'], row['cc_difference'], rel_tol=0, abs_tol=SNAPSHOT_DECIMAL_IDENTITY_ATOL):
                raise ValueError('Event-minus-ordinary official net difference is inconsistent.')
        if not math.isclose(rows[5]['theta'], study['theta'], rel_tol=0, abs_tol=SNAPSHOT_DECIMAL_IDENTITY_ATOL):
            raise ValueError('Primary theta and the 21-session horizon disagree.')
        if (rows[5]['n_event'],rows[5]['n_ordinary'])!=(study['n_event'],study['n_ordinary']):
            raise ValueError('Primary sample counts and the 21-session horizon disagree.')
        if any(not math.isclose(a,b,rel_tol=0,abs_tol=SNAPSHOT_DECIMAL_IDENTITY_ATOL)
               for a,b in zip(rows[5]['theta_iid_interval'],study['iid_interval'])):
            raise ValueError('Primary uncertainty and the 21-session interval disagree.')
    if set(payload['portfolios']) != set(portfolio_names(payload)):
        raise ValueError('Unexpected portfolio version in the public report.')
    if 'causal' in payload['portfolios']:
        repair=payload.get('portfolio_repair',{})
        if (payload.get('portfolio_headline')!='causal'
                or repair.get('event_evidence_version')!='corrected_is_v2'
                or repair.get('selection_basis')!='OBJECTIVE_TIMING_REPAIR_NOT_PERFORMANCE'):
            raise ValueError('Causal portfolio must be the explicit current timing repair, with unchanged V2 event evidence.')
    elif payload.get('portfolio_headline','corrected') not in STUDIES:
        raise ValueError('Headline portfolio is not present.')
    for name in portfolio_names(payload):
        portfolio = payload['portfolios'][name]
        if portfolio['status'] not in {'COMPLETE_STANDING_NBBO_ASSUMPTION', 'CONDITIONAL_STANDING_NBBO', 'UNAVAILABLE'}:
            raise ValueError('Portfolio metrics must be labeled conditional or unavailable.')
        _number(portfolio['initial_nav'], name + '.initial_nav')
        if portfolio['initial_nav'] <= 0:
            raise ValueError('Initial capital must be positive.')
        for field in ('cagr', 'annualized_volatility','sharpe', 'maximum_drawdown', 'stock_turnover',
                      'daily_return_skew_unbiased','worst_month_return'):
            if portfolio['status'] != 'UNAVAILABLE':
                if not (field in {'sharpe','daily_return_skew_unbiased'} and portfolio[field] is None
                        and portfolio.get('sharpe_unavailable_reason')=='ZERO_RETURN_VARIANCE'):
                    _number(portfolio[field], name + '.portfolio.' + field)
            elif portfolio.get(field) is not None:
                raise ValueError('Unavailable risk metrics must remain null, never zero-filled.')
        if portfolio.get('nav_csv'):
            rows = read_public_nav(_public_path(public_dir, portfolio['nav_csv']))
            if portfolio['status'] != 'UNAVAILABLE' and any(not math.isfinite(nav) for _, nav in rows):
                raise ValueError('Complete-path metrics cannot accompany a gapped NAV series.')
            if portfolio['status'] != 'UNAVAILABLE' and portfolio['sharpe'] is None:
                levels=[portfolio['initial_nav']]+[nav for _,nav in rows]
                returns=[b/a-1 for a,b in zip(levels,levels[1:])]
                if max(returns)!=min(returns):
                    raise ValueError('Undefined-Sharpe exception requires zero return variance.')
        elif portfolio['status'] != 'UNAVAILABLE':
            raise ValueError('Available portfolio metrics require their public derived NAV CSV.')
        if portfolio['status']!='UNAVAILABLE':
            month=portfolio.get('worst_month')
            if not isinstance(month,str) or len(month)!=7 or month[:4] not in {'2024','2025'} or month[4]!='-' or month[5:] not in {f'{n:02d}' for n in range(1,13)}:
                raise ValueError('Measured worst month must identify a complete IS calendar month.')
    for field, maximum in (('correction_summary', 46), ('cost_summary', 45), ('capacity_summary', 52),
                           ('factor_summary', 45), ('conclusion', 32)):
        _text(payload.get(field), field, maximum)
    return payload


def read_public_nav(path):
    """Read only derived date/NAV columns; preserve gaps and reject date drift."""
    with Path(path).open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        if not {'date', 'nav'} <= set(reader.fieldnames or []):
            raise ValueError('Public equity curve requires date and nav columns.')
        rows = []
        for row in reader:
            date = datetime.fromisoformat(row['date'][:10])
            if not datetime(2024, 1, 1) <= date <= datetime(2025, 12, 31):
                raise ValueError('Public equity curve extends outside IS.')
            nav = float(row['nav']) if row['nav'].strip().lower() not in ('', 'nan', 'null', 'none') else math.nan
            if math.isfinite(nav) and nav <= 0:
                raise ValueError('NAV must be positive or explicitly missing.')
            rows.append((date, nav))
    if not rows or any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('Public NAV dates must be nonempty, unique and increasing.')
    return rows


def _percent(value, digits=2):
    return 'N/A' if value is None else f'{100 * value:+.{digits}f}'


def _range(pair):
    return f'[{100 * pair[0]:+.2f}, {100 * pair[1]:+.2f}]'


def _curve_drawing(payload, public_dir):
    from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
    from reportlab.lib import colors
    width, height = 504, 103
    drawing = Drawing(width, height)
    series = []
    palette = {'original': colors.HexColor('#215B83'), 'corrected': colors.HexColor('#A34816'), 'causal':colors.HexColor('#247346')}
    for name in portfolio_names(payload):
        portfolio = payload['portfolios'][name]
        if portfolio.get('nav_csv'):
            series.append((name, [(date, 100 * (nav / portfolio['initial_nav'] - 1))
                                  for date, nav in read_public_nav(_public_path(public_dir, portfolio['nav_csv']))]))
    if not series:
        drawing.add(String(0, 45, 'Equity curves unavailable: no complete valuation claim.', fontName='Helvetica', fontSize=11))
        return drawing
    dates = [date for _, points in series for date, _ in points]
    values = [value for _, points in series for _, value in points if math.isfinite(value)] + [0]
    lo, hi = min(values), max(values)
    span = max(hi - lo, .25); lo -= span * .07; hi += span * .07
    left, right, bottom, top = 44, 495, 20, 80
    first, last = min(dates), max(dates)
    denominator = max((last - first).days, 1)
    x = lambda date: left + (right - left) * (date - first).days / denominator
    y = lambda value: bottom + (top - bottom) * (value - lo) / (hi - lo)
    drawing.add(Line(left, bottom, right, bottom, strokeColor=colors.grey))
    drawing.add(Line(left, y(0), right, y(0), strokeColor=colors.lightgrey))
    for value in (min(values), max(values)):
        drawing.add(String(0, y(value) - 3, f'{value:.1f}%', fontName='Helvetica', fontSize=11))
    drawing.add(String(left, 4, first.strftime('%Y-%m'), fontName='Helvetica', fontSize=11))
    drawing.add(String(right - 45, 4, last.strftime('%Y-%m'), fontName='Helvetica', fontSize=11))
    for name, points in series:
        segment = []
        for date, value in points:
            if math.isfinite(value):
                segment.extend([x(date), y(value)])
            else:
                if len(segment) >= 4:
                    drawing.add(PolyLine(segment, strokeColor=palette[name], strokeWidth=1.2))
                segment = []  # Missing dates are never joined across a gap.
        if len(segment) >= 4:
            drawing.add(PolyLine(segment, strokeColor=palette[name], strokeWidth=1.2))
    for index,name in enumerate(portfolio_names(payload)):
        drawing.add(String(45+160*index, 91, portfolio_label(name), fillColor=palette[name], fontName='Helvetica', fontSize=11))
    return drawing


def make_pdf(public_dir, output, *, preflight_only=False):
    """Root must visually verify the produced artifact; this is not submission."""
    public_dir = Path(public_dir).resolve()
    payload = validate_payload(json.loads((public_dir / 'finalreport_payload.json').read_text()), public_dir)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Table, TableStyle, PageBreak
    from reportlab.pdfgen.canvas import Canvas

    class TwoPageCanvas(Canvas):
        def showPage(self):
            if self.getPageNumber() > 2:
                raise ValueError('Quant note exceeded two pages; shorten content instead of shrinking fonts.')
            super().showPage()

    styles = {
        'body': ParagraphStyle('Body', fontName='Helvetica', fontSize=11, leading=12, spaceAfter=2),
        'title': ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=15, leading=17, spaceAfter=5),
        'heading': ParagraphStyle('Heading', fontName='Helvetica-Bold', fontSize=11, leading=13, spaceBefore=4, spaceAfter=3),
        'status': ParagraphStyle('Status', fontName='Helvetica-Bold', fontSize=11, leading=13, textColor=colors.HexColor('#A32620'), spaceAfter=5),
    }
    story = []
    def p(text, kind='body'):
        story.append(Paragraph(text, styles[kind]))
    def table(rows, widths):
        cells = [[Paragraph(str(cell), styles['body']) for cell in row] for row in rows]
        item = Table(cells, colWidths=widths, hAlign='LEFT')
        item.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E9EFF3')),
                                  ('LINEBELOW', (0, 0), (-1, 0), .5, colors.grey), ('LEFTPADDING', (0, 0), (-1, -1), 3),
                                  ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 1),
                                  ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
        story.append(item)
    p('Covered-call increments around buyer agreement disclosures', 'title')
    p('DRAFT / INCOMPLETE — OOS NOT RUN; UNSEEN CLASSIFIER NOT READY', 'status')
    p('Systematic Trading / Massive 8-K subtrack · IS: 2024–2025 · Hypothesis commit: '
      + html.escape(payload['hypothesis_commit']))
    p('<b>Hypothesis and counterargument.</b> A first definitive buyer operating-control agreement may attract upside option demand; '
      'selling a covered call could earn a larger net increment over stock than on ordinary same-issuer dates. '
      'Deal uncertainty and constrained arbitrage motivate the conjecture, not an established edge. Premiums may compensate real tail risk, '
      'and information may already be priced before our delayed entry. [1–3]')
    p('<b>Frozen method.</b> Union of acquisition_agreement and merger_agreement; official static TOP100. '
      'Prior-session chains select the 3–6-month expiry nearest 120 days and 5% OTM call; entry is the first full-session close after acceptance. '
      'Exit is event session + 21 sessions or earlier expiry; outcomes past the window are censored. Stock is a parity bond + call - put proxy, with a short OTM call. '
      'The 5% premium haircut applies at entry/exit to three covered-call legs (two stock-proxy legs); doubled costs remain visible. Seed-fixed controls preserve issuer/event-clock templates.')
    p(html.escape(payload['correction_summary']))
    p('Primary evidence: theta = (CC - stock)event - (CC - stock)ordinary', 'heading')
    rows = [['IS version', 'Finite N<br/>event/ord.', 'Theta<br/>pp', 'IID 95%<br/>pp', 'Issuer range<br/>pp', 'Date range<br/>pp']]
    for name in STUDIES:
        study = payload['studies'][name]
        rows.append([name.title(), f"{study['n_event']}/{study['n_ordinary']}", _percent(study['theta']),
                     _range(study['iid_interval']), _range(study['issuer_range']), _range(study['date_range'])])
    table(rows, [72, 66, 52, 104, 105, 105])
    p('Cluster ranges are exploratory 2,000-draw sensitivities, not calibrated small-sample confidence intervals. '
      'Issuer and overlapping-date clusters are separate; dependence limits independent evidence.')
    p('Corrected V2: every fixed IS horizon, with IID 95% intervals', 'heading')
    rows = [['Days', 'Finite N<br/>E / O', 'Net CC means<br/>E / O (%)', 'CC gap (pp)<br/>[IID 95% interval]', 'Theta (pp)<br/>[IID 95% interval]']]
    for row in payload['studies']['corrected']['horizons']:
        rows.append([str(row['horizon']).title(),f"{row['n_event']} / {row['n_ordinary']}",
                     _percent(row['event_cc_mean'])+' / '+_percent(row['ordinary_cc_mean']),
                     _percent(row['cc_difference'])+'<br/>'+_range(row['cc_iid_interval']),
                     _percent(row['theta'])+'<br/>'+_range(row['theta_iid_interval'])])
    table(rows,[40,65,116,141,142])
    p('E/O = event/ordinary. IID intervals ignore dependence; primary cluster ranges above qualify them. '
      'Original V1 horizon intervals/counts remain in aggregate CSVs. No best horizon is selected. <b>OOS: all nine horizons NOT RUN.</b>')
    story.append(PageBreak())

    p('Portfolio, implementation and limits', 'title')
    if 'causal' in payload['portfolios']:
        p('<b>Current portfolio: V3 timing repair.</b> Prior-close financial state informs current-open decisions; closing fills retain the starter proxy. '
          'V2 event results and legacy portfolios are preserved. This objective post-IS clock repair does not validate live execution.')
    p('Conditional quote NAV; each ledger retains its own cashflows', 'heading')
    story.append(_curve_drawing(payload, public_dir))
    rows = [['IS ledger', 'CAGR %', 'Ann. vol %', 'Sharpe', 'Max DD %', 'Turnover x']]
    for name in portfolio_names(payload):
        row = payload['portfolios'][name]
        rows.append([portfolio_label(name), _percent(row['cagr']),
                     'N/A' if row['annualized_volatility'] is None else f"{100*row['annualized_volatility']:.2f}",
                     'N/A' if row['sharpe'] is None else f"{row['sharpe']:.2f}",
                     'N/A' if row['maximum_drawdown'] is None else f"{100 * row['maximum_drawdown']:.2f}",
                     'N/A' if row['stock_turnover'] is None else f"{row['stock_turnover']:.2f}"])
    table(rows, [100,75,75,68,92,94])
    p('252-session annualization; rf=0, idle cash retained; turnover is two-sided stock-reference dollars / mean NAV. '
      'Daily-bar NAV gaps prevent unconditional risk estimates. Standing-NBBO results assume the latest same-session quote state persists when valid; '
      'strict 60/300-second age screens remain reported. No gap fill, future mark or retrospective risk-gate replay is used.')
    latest=payload['portfolios'][payload.get('portfolio_headline','corrected')]
    shape=('Current conditional daily skew '+f"{latest['daily_return_skew_unbiased']:.2f}"+'; worst month '
           +str(latest['worst_month'])+' '+_percent(latest['worst_month_return'])+'%. '
           if latest['daily_return_skew_unbiased'] is not None and latest['worst_month_return'] is not None
           else 'Current skew/worst-month evidence is unavailable. ')
    p('<b>Risk.</b> '+shape+'One contract; $1m initial NAV; name/sector/total stock-reference gross limits 10%/25%/100%; '
      'pause/resume entries at 10%/5% drawdown. Missing marks and overnight jumps undermine these proxy controls. '
      'Gross payoff is min(S,U), but uncapped percentage liquidation fees create an extreme-price loss artifact beyond entry debit. '
      'American assignment, dividends, financing and multileg fills are not fully modeled.')
    p('<b>Costs and capacity.</b> '+html.escape(payload['cost_summary'])+' '+html.escape(payload['capacity_summary']))
    p('<b>Factor diagnostic.</b> '+html.escape(payload['factor_summary']))
    variants = payload['studies']['original']['variants']
    p('<b>Research limits.</b> '+str(variants)+' fixed grid cells per version are correlated diagnostics, including pre-filing checks; '
      'all variants and failures are retained. Static-universe survivorship, historical taxonomy revisions, concurrent news and small dependent samples '
      'limit attribution. H6 completion was rejected before backtesting: too few clean events and a weaker mechanism. Long calls were considered, never tested. '
      'AI assisted code/source review; evidence and tests are retained. OOS has not been evaluated; unseen-window readiness and stable edge are unproven.')
    p('<b>Conclusion.</b> '+html.escape(payload['conclusion']))
    p('References and reproduction', 'heading')
    p('[1] Israelov &amp; Nielsen (2015), <i>Covered Calls Uncovered</i>. '
      '[2] Gârleanu et al. (2009), <i>Demand-Based Option Pricing</i>. '
      '[3] Ben-Rephael et al. (2022), <i>Who Pays Attention to SEC Form 8-K?</i>. '
      '[4] Christoffersen et al. (2018), <i>Illiquidity Premia in the Equity Options Market</i>. '
      'REFERENCES.md retains links and evidence limits; README covers reproduction, hashes and private licensed-data acquisition.')
    page_heights = [0.]
    for item in story:
        if isinstance(item, PageBreak):
            page_heights.append(0.)
            continue
        _, height = item.wrap(504, 662)
        page_heights[-1] += height + item.getSpaceBefore() + item.getSpaceAfter()
    if len(page_heights) != 2 or max(page_heights) > 662:
        raise ValueError(f'Two-page layout overflow: {page_heights}; shorten content, never reduce fonts.')
    if preflight_only:
        return {'pages': 2, 'body_heights_points': page_heights, 'font_minimum_points': 11, 'margin_inches': .75}
    output = Path(output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    def footer(canvas, doc):
        canvas.setFont('Helvetica', 11)
        canvas.drawString(54, 60, 'Draft / incomplete — OOS not run')
        canvas.drawRightString(558, 60, str(doc.page))
    document = BaseDocTemplate(str(output), pagesize=letter, leftMargin=54, rightMargin=54,
                               topMargin=54, bottomMargin=54, title='GQH agreement covered-call research: incomplete IS note',
                               author='GQH participant', allowSplitting=0)
    frame = Frame(54, 76, 504, 662, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document.addPageTemplates(PageTemplate(id='two_page_note', frames=[frame], onPage=footer))
    try:
        document.build(story, canvasmaker=TwoPageCanvas)
    except Exception:
        if output.exists():
            output.unlink()
        raise
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(make_pdf(args.public_dir, args.output))
