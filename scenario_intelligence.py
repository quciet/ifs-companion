"""Installed IFs baseline, preset and audited semantic interpretation. Read-only."""
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import tempfile
import itertools
import re
from contextlib import closing
from decimal import Decimal
from functools import lru_cache

from scenario_compiler import ValidationError, ScenarioRows, number, integer


# Explicit, audited links; never infer polarity by stripping a suffix from a name.
# Sources: installed IFsVar definitions and IFs.Core/Models/SocioPol.Forecast.vb.
RULES = {
    'govcorruptm': ('corruption', 'GOVCORRUPT', -1),
    'ginidomm': ('domestic income inequality', 'GINIDOM', 1),
    'labparm': ('labour participation', 'LAB', 1),
    'gdsm': ('government expenditure', 'GDS', 1),
    'xsm': ('exports', 'XS', 1),
    'protecm': ('protectionism', '', 1),
    'mtarifftaxrm': ('import tariff tax rate', '', 1),
    'hlmortm': ('mortality', '', 1),
    'goveffectm': ('government effectiveness', 'GOVEFFECT', 1),
    'democm': ('democracy', 'DEMOCPOLITY', 1),
    'democpolyarchym': ('electoral democracy', '', 1),
    'marmsm': ('arms imports', 'MARMS', 1),
    'svmulm': ('societal violence', '', 1),
    'sfinsecurepopimpm': ('population impacted by insecurity', '', 1),
    'govindsecurm': ('government security', 'GOVINDSECUR', 1),
    'cpowf': ('conventional power conversion', '', 1),
    'endemm': ('energy demand', '', 1),
    'econfreem': ('economic freedom', '', 1),
    'govnucwpadd': ('nuclear stockpile additions', 'GOVNUCWP', 1),
    'migrateinm': ('inward migration', '', 1),
    'migrateoutm': ('outward migration', '', 1),
}

NARRATIVE_TERMS = {
    'govcorruptm': ('corruption', 'government corruption', 'corrupt'),
    'labparm': ('labour participation', 'labor participation'),
    'xsm': ('global exports', 'exports'),
    'protecm': ('trade protectionism', 'protectionism'),
    'mtarifftaxrm': ('import tariffs', 'tariffs'),
    'hlmortm': ('intentional injuries and mortality', 'intentional-injury mortality', 'mortality'),
    'goveffectm': ('government effectiveness',),
    'democm': ('democracy',), 'democpolyarchym': ('electoral democracy',),
    'ginidomm': ('domestic income inequality', 'income inequality'),
    'marmsm': ('arms imports',), 'endemm': ('energy demand',),
    'econfreem': ('economic freedom',),
}


def narrative_direction(parameter, targets, refs, text):
    terms = NARRATIVE_TERMS.get(parameter, ())
    if parameter == 'gdsm':
        military = len(targets) > 1 and refs.targets(parameter, targets)[1] == '1'
        terms = ('military expenditure', 'military spending') if military else ('government expenditure',)
    matches = []
    for direction, prefix in (('increase', r'more|higher|greater|increase[ds]?|increasing|increased'),
                              ('decrease', r'less|lower|reduced|reduce[ds]?|reducing|decreased')):
        for term in terms:
            matches.extend((m.start(), direction) for m in re.finditer(r'\b(?:'+prefix+r')\s+'+re.escape(term)+r'\b', text, re.IGNORECASE))
    if parameter in ('democm', 'democpolyarchym'):
        matches.extend((m.start(), 'decrease') for m in re.finditer(r'(?:^|[.!;]\s*)democratic regression\b', text, re.IGNORECASE))
    if parameter == 'govindsecurm':
        matches.extend((m.start(), 'decrease') for m in re.finditer(r'\bmore insecurity\b', text, re.IGNORECASE))
    return max(matches)[1] if matches else None


def clean(value):
    return None if value is None or value == '' else value


def baseline_path(refs):
    if not refs.installation:
        raise ValidationError('An installed IFs baseline is required for this operation.')
    return Path(refs.installation)/'RUNFILES/IFsBase.run.db'


def fingerprint(path):
    path = Path(path)
    return [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in
            (path, Path(str(path)+'-wal')) if p.is_file()]


def decoder_path():
    roots = [Path(__file__).resolve().parent]
    if os.environ.get('IFS_COMPANION_APP_DIR'):
        roots.insert(0, Path(os.environ['IFS_COMPANION_APP_DIR']))
    for root in roots:
        for relative in ('decoder-runtime/Decoder.exe', 'engine/decoder-runtime/Decoder.exe', 'engine/_internal/decoder-runtime/Decoder.exe',
                         '_internal/decoder-runtime/Decoder.exe'):
            path = root/relative
            if path.is_file():
                return path
    raise ValidationError('Companion baseline decoder is unavailable. Reinstall Companion 0.3.0 or newer.')


@lru_cache(maxsize=24)
def decoded(path, stamp, parameter, decoder):
    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro', uri=True)) as db:
        dims = [r[0] for r in db.execute('SELECT DimensionId FROM ifs_var_dim WHERE VariableName=? ORDER BY Seq', (parameter,))]
        payload = db.execute('SELECT Data FROM ifs_var_blob WHERE VariableName=?', (parameter,)).fetchone()
    if not payload or payload[0] is None:
        raise ValidationError('No saved baseline payload for '+parameter+'. No baseline value will be assumed.')
    with tempfile.TemporaryDirectory(prefix='ifs-scenario-baseline-') as folder:
        source, target = Path(folder)/'input.parquet', Path(folder)/'output.bin'
        source.write_bytes(payload[0])
        result = subprocess.run([decoder, str(source), str(target)], capture_output=True, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode or not target.is_file():
            raise ValidationError('The installed baseline payload could not be decoded for '+parameter+'.')
        data = target.read_bytes()
    if len(data) < 8:
        raise ValidationError('Truncated baseline decoder result.')
    axes, count = struct.unpack_from('<ii', data)
    if axes != len(dims) or not 1 <= axes <= 4:
        raise ValidationError('Baseline axes disagree with metadata.')
    record = struct.Struct('<'+'h'*axes+'f')
    if len(data) != 8+count*record.size:
        raise ValidationError('Baseline record count mismatch.')
    values = {}
    for entry in record.iter_unpack(data[8:]):
        key, value = tuple(entry[:-1]), entry[-1]
        if key in values:
            raise ValidationError('Duplicate baseline coordinates.')
        values[key] = value
    return dims, values


class Baseline:
    def __init__(self, refs, base_year, decoder=None):
        self.refs, self.base_year, self.decoder = refs, base_year, decoder
        self.path = baseline_path(refs)
        self.stamp = json.dumps(fingerprint(self.path))
        self.frames = {}
        self.country_indices = {name: i for i, name in refs.groups.get(1, {}).items()}

    def value(self, parameter, targets, year=None):
        if parameter.isupper() and parameter in self.refs.parameters:
            flags = self.refs.parameters[parameter]
            active = [(axis, f) for axis, f in enumerate(flags) if f]
            if len(active) != len(targets):
                raise ValidationError('Wrong baseline variable dimensions for '+parameter+'.')
            normalized = []
            for (axis, flag), target in zip(active, targets):
                if axis == 0 and flag == 1:
                    if target not in self.refs.countries:
                        raise ValidationError('Baseline variable requires an exact country.')
                    normalized.append(target)
                else:
                    index = integer(target)
                    if index not in self.refs.groups.get(flag, {}):
                        raise ValidationError('Unknown baseline dimension index.')
                    normalized.append(str(index))
            targets = normalized
        else:
            targets = self.refs.targets(parameter, targets)
            flags = self.refs.dimensions(parameter)
        expected = [0, *[f for f in flags if f]]
        if parameter not in self.frames:
            self.frames[parameter] = decoded(str(self.path.resolve()), self.stamp, parameter,
                                             str(self.decoder or decoder_path()))
        dims, values = self.frames[parameter]
        if dims != expected:
            raise ValidationError('Baseline dimensions differ from installed IFsVar for '+parameter+'.')
        coordinates = []
        for axis, flag in enumerate(flags):
            if not flag:
                continue
            target = targets[len(coordinates)]
            if axis == 0 and flag == 1:
                index = self.country_indices.get(target)
                if index is None:
                    raise ValidationError('Read baseline countries individually, not a group aggregate.')
                coordinates.append(index)
            else:
                coordinates.append(integer(target))
        key = (year if year is not None else self.base_year, *coordinates)
        if key not in values:
            raise ValidationError('Baseline has no saved value for '+parameter+' '+str(targets)+' in '+str(key[0])+'.')
        return number(values[key])

    def nuclear_states(self):
        return [{'country': country, 'base_year_stock': str(value)} for country in sorted(self.refs.countries)
                if (value := self.value('GOVNUCWP', [country])) > 0]


def details(refs, parameter):
    meta = refs.metadata.get(parameter, {})
    rule = RULES.get(parameter)
    linked = refs.metadata.get(rule[1], {}) if rule and rule[1] else {}
    return {
        'definition': meta.get('DEFINITION'), 'explanation': meta.get('PARAMETER EXPLANATION'),
        'units': meta.get('UNITS'), 'minimum': clean(meta.get('MINIMUM')), 'maximum': clean(meta.get('MAXIMUM')),
        'shift_down': clean(meta.get('SHIFT DOWN')), 'shift_up': clean(meta.get('SHIFT UP')),
        'shift_years': clean(meta.get('SHIFT YEARS')), 'aggregation': meta.get('AGGREGATION'),
        'common_target': bool(meta.get('COMMONTARGET')),
        'semantic_rule': None if not rule else {'outcome': rule[0], 'affected_variable': rule[1],
            'polarity': rule[2], 'affected_definition': linked.get('DEFINITION'),
            'interpretation': 'Higher input means less '+rule[0] if rule[2] < 0 else 'Higher input means more '+rule[0]},
        'quantity': 'annual_addition_to_stock' if parameter == 'govnucwpadd' else
            ('multiplier' if 'mul' in str(meta.get('UNITS', '')).casefold() else 'parameter_input'),
        'baseline_file': str(baseline_path(refs)) if refs.installation else None,
    }


def expand_subgroups(entries, refs):
    """ALL is a selector, not a stored baseline bucket. Resolve real indices."""
    result = []
    for entry in entries:
        flags = refs.dimensions(entry['parameter'])
        targets = entry.get('targets', [])
        active = [(axis, f) for axis, f in enumerate(flags) if f]
        if len(active) != len(targets):
            raise ValidationError('Wrong number of dimension targets for '+entry['parameter']+'.')
        choices = []
        for (axis, flag), target in zip(active, targets):
            members = refs.groups.get(flag, {})
            is_all = not (axis == 0 and flag == 1) and (target == 'ALL' or
                str(target) in {str(i) for i, name in members.items() if name == 'ALL'})
            choices.append([i for i, name in members.items() if name != 'ALL'] if is_all else [target])
        for selected in itertools.product(*choices):
            result.append({**entry, 'targets': list(selected)})
            if len(result) > 10000:
                raise ValidationError('Expanded dimensions exceed 10,000 entries.')
    return result


def preset_entry(entry, refs, baseline):
    parameter, targets = entry['parameter'], entry.get('targets', [])
    preset = entry['preset']
    level = preset.get('level')
    if level not in ('high', 'low', 'base') or any(k in entry for k in ('values', 'ramp')):
        raise ValidationError('Choose one IFs preset (high, low, base) or a custom trajectory.')
    meta = details(refs, parameter)
    start = baseline.value(parameter, targets)
    if level == 'base':
        shift, years = Decimal(0), 0
    else:
        shift = meta['shift_up' if level == 'high' else 'shift_down']
        if shift is None or number(shift) == 0:
            raise ValidationError('IFs does not supply a '+level+' shift for '+parameter+'. Ask for a custom assumption.')
        years = meta['shift_years']
        if years is None:
            raise ValidationError('IFs has no default shift duration for '+parameter+'. Ask for a duration.')
        shift, years = number(shift), integer(years)
    finish = start+shift
    if meta['minimum'] is not None:
        finish = max(finish, number(meta['minimum']))
    if meta['maximum'] is not None:
        finish = min(finish, number(meta['maximum']))
    hold = integer(preset.get('hold_until', baseline.base_year+max(years, 1)))
    if not baseline.base_year+years <= hold <= 2500:
        raise ValidationError('Preset horizon must cover the IFs shift duration and end by 2500.')
    if not years:
        values = [str(finish)]*(hold-baseline.base_year+1)
        if level == 'base':
            # Base means retain the saved baseline trajectory, not freeze its first value.
            values = [str(baseline.value(parameter, targets, y)) for y in range(baseline.base_year, hold+1)]
    else:
        values = [str(start+(finish-start)*Decimal(min(i, years))/years) for i in range(hold-baseline.base_year+1)]
    result = {**entry, 'values': values}
    result.pop('preset')
    receipt = {'parameter': parameter, 'targets': targets, 'level': level, 'baseline': str(start),
               'endpoint': str(finish), 'years': years, 'source': str(baseline.path)}
    return result, receipt


def semantic_entries(entries, refs, narrative='', reference_values=None):
    """Check declared outcome direction; convert cumulative additions to annual flows."""
    prepared, receipts = [], []
    for entry_index, entry in enumerate(entries):
        parameter = entry['parameter']
        effect = entry.get('effect')
        if refs.metadata and (not isinstance(effect, dict) or effect.get('direction') not in ('increase', 'decrease', 'unchanged', 'mixed')):
            raise ValidationError('State the intended outcome direction for '+parameter+' before creating a draft.')
        if not effect:
            prepared.append(entry)
            continue
        rule = RULES.get(parameter)
        values = [number(v) for v in entry['values']]
        desired = effect['direction']
        # Conservative explicit phrase checks supplement the AI's declared intent.
        # They are not a general-purpose narrative understanding claim.
        explicit_direction = narrative_direction(parameter, entry.get('targets', []), refs, narrative)
        if explicit_direction:
            desired = explicit_direction
        quantity = effect.get('quantity', 'parameter_input')
        if parameter == 'cpowf' and any(t in str(effect.get('outcome', '')).casefold() for t in ('nuclear', 'personnel', 'participation', 'headcount')):
            raise ValidationError('cpowf controls conventional-power conversion, not nuclear stockpiles or military personnel.')
        if parameter == 'govnucwpadd':
            if quantity not in ('annual_addition', 'cumulative_addition'):
                raise ValidationError('govnucwpadd is an annual addition. Choose annual_addition or cumulative_addition explicitly.')
            if quantity == 'cumulative_addition':
                if values[0] != 0:
                    raise ValidationError('A cumulative additional stock trajectory must begin at zero.')
                cumulative = values
                values = [Decimal(0), *[cumulative[i]-cumulative[i-1] for i in range(1, len(cumulative))]]
                entry = {**entry, 'values': [str(v) for v in values]}
                receipt = 'Cumulative stock additions converted to annual increments; holding the stock target produces zero further additions.'
            else:
                receipt = 'Annual additions repeat each year; this is not a stockpile target.'
            check_values = cumulative if quantity == 'cumulative_addition' else values
            deltas = check_values[1:] if quantity == 'annual_addition' else [v-check_values[0] for v in check_values[1:]]
        else:
            deltas = [v-values[0] for v in values[1:]]
            receipt = details(refs, parameter)['semantic_rule']['interpretation']+'.' if rule else 'Outcome polarity is not independently verified; review this custom control.'
        reference = reference_values[entry_index] if reference_values is not None else None
        if reference is not None:
            if parameter == 'govnucwpadd' and quantity != 'annual_addition':
                raise ValidationError('Attached nuclear edits must specify annual_addition; cumulative stock targets require a new trajectory.')
            if len(values) != len(reference):
                raise ValidationError('Reference trajectory length mismatch.')
            deltas = [v-number(old) for v, old in zip(values, reference)]
        if rule:
            signed = [d*rule[2] for d in deltas]
            if ((desired == 'increase' and (any(d < 0 for d in signed) or not any(d > 0 for d in signed))) or
                (desired == 'decrease' and (any(d > 0 for d in signed) or not any(d < 0 for d in signed))) or
                (desired == 'unchanged' and any(d != 0 for d in signed))):
                raise ValidationError('Direction conflict for '+parameter+': intended '+desired+' in '+rule[0]+'. '+details(refs, parameter)['semantic_rule']['interpretation']+'.')
        meta = details(refs, parameter)
        if any((meta['minimum'] is not None and v < number(meta['minimum'])) or
               (meta['maximum'] is not None and v > number(meta['maximum'])) for v in values):
            raise ValidationError('Proposed values exceed installed IFs bounds for '+parameter+'.')
        prepared.append(entry)
        receipts.append({'parameter': parameter, 'direction': desired, 'quantity': quantity,
                         'verified': bool(rule), 'intent_source': 'explicit narrative phrase' if explicit_direction else 'declared proposal intent',
                         'interpretation': receipt})
    return prepared, receipts


def compact_groups(rows, refs, baseline, scopes):
    """Only compact uniform rows when the native IFs group transform is equivalent."""
    result = ScenarioRows([list(r) for r in rows], rows.comments, rows.source)
    receipts = []
    groups = [refs.country_groups[g['id']] for g in scopes if g.get('id') in refs.country_groups]
    # Infer a compact group only for an exact membership match, never a superset.
    country_sets = {frozenset(r[2] for r in result if r and r[0] == 'CUSTOM' and r[1] == p)
                    for p in {r[1] for r in result if r and r[0] == 'CUSTOM' and refs.dimensions(r[1])[0] == 1}}
    for members in country_sets:
        if len(members) < 2 or any(set(g['countries']) == members for g in groups):
            continue
        matches = [g for g in refs.country_groups.values() if not g['invalid_members'] and set(g['countries']) == members]
        if matches:
            groups.append(min(matches, key=lambda g: (g['name'] != 'World', len(g['name']), g['name'])))
    for group in groups:
        members = set(group['countries'])
        parameters = {r[1] for r in result if r and r[0] == 'CUSTOM' and refs.dimensions(r[1])[0] == 1}
        for parameter in sorted(parameters):
            meta = details(refs, parameter)
            candidates = [r for r in result if len(r) > 2 and r[0] == 'CUSTOM' and r[1] == parameter and r[2] in members]
            dimensions = sum(f > 0 for f in refs.dimensions(parameter))
            for tail in {tuple(r[3:2+dimensions]) for r in candidates}:
                selected = [r for r in candidates if tuple(r[3:2+dimensions]) == tail]
                reason = None
                if group['name'] in refs.countries:
                    reason = 'Group name collides with a country name in the native loader.'
                elif len(selected) != len(members):
                    reason = 'Only part of the preset group is targeted.'
                elif len({tuple(number(v) for v in r[2+dimensions:]) for r in selected}) != 1:
                    reason = 'Country-specific trajectories retained.'
                elif meta['common_target'] or str(meta['aggregation']).upper() not in ('AVG', 'POP'):
                    reason = 'Native aggregation/common-target semantics require explicit country rows.'
                else:
                    try:
                        for i in range(len(selected[0])-2-dimensions):
                            values = {baseline.value(parameter, r[2:2+dimensions], baseline.base_year+i) for r in selected}
                            if len(values) != 1:
                                reason = 'Country baselines differ; native group allocation would change the intervention.'
                                break
                    except (ValidationError, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
                        reason = 'Explicit rows retained: '+str(error)
                if not reason:
                    first = selected[0]
                    replacement = [*first[:2], group['name'], *first[3:]]
                    selected_ids = {id(r) for r in selected}
                    index = next(i for i, r in enumerate(result) if id(r) in selected_ids)
                    result[:] = [r for r in result if id(r) not in selected_ids]
                    result.insert(index, replacement)
                receipts.append({'parameter': parameter, 'group': group['name'], 'native_group': not reason,
                                 'reason': reason or 'Same inputs and baseline values; native group shift is equivalent.'})
    return result, receipts


def expand_native_source(rows, refs, baseline):
    normalized = ScenarioRows(comments=rows.comments, source=rows.source)
    for row in rows:
        if row and row[0] == 'CUSTOM':
            count = sum(f > 0 for f in refs.dimensions(row[1]))
            entries = expand_subgroups([{'parameter': row[1], 'targets': row[2:2+count], 'values': row[2+count:]}], refs)
            for entry in entries:
                normalized.append(['CUSTOM', row[1], *refs.targets(row[1], entry['targets']), *entry['values']])
        else:
            normalized.append(row)
    result = ScenarioRows(comments=rows.comments, source=rows.source)
    groups = {g['name']: g for g in refs.country_groups.values()}
    seen = set()
    for row in normalized:
        if len(row) < 3 or row[0] != 'CUSTOM' or refs.dimensions(row[1])[0] != 1 or row[2] not in groups or row[2] in refs.countries:
            expanded = [row]
        else:
            group, parameter = groups[row[2]], row[1]
            count = sum(f > 0 for f in refs.dimensions(parameter))
            meta = details(refs, parameter)
            if meta['common_target'] or str(meta['aggregation']).upper() not in ('AVG', 'POP'):
                raise ValidationError('Native group '+group['name']+' uses aggregation/common-target semantics for '+parameter+'. Country-specific resolution is required before editing.')
            for i in range(len(row)-2-count):
                values = {baseline.value(parameter, [c, *row[3:2+count]], baseline.base_year+i) for c in group['countries']}
                if len(values) != 1:
                    raise ValidationError('Native group baseline values differ for '+parameter+'; do not treat this as identical country inputs.')
            expanded = [[*row[:2], c, *row[3:]] for c in group['countries']]
        for item in expanded:
            if item and item[0] == 'CUSTOM':
                count = sum(f > 0 for f in refs.dimensions(item[1]))
                key = tuple(item[1:2+count])
                if key in seen:
                    raise ValidationError('Overlapping native source definitions need explicit resolution: '+str(key))
                seen.add(key)
            result.append(item)
    return result
