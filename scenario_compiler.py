"""Offline IFs scenario compiler. No third-party dependencies or network access."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import io
from datetime import datetime, timezone
from contextlib import closing
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path


class ValidationError(ValueError):
    """The request cannot be resolved against the supplied reference data."""


class ScenarioRows(list):
    """Parameter records plus an opaque trailing IFs comment section."""
    def __init__(self, rows=(), comments='', source=None):
        super().__init__(rows)
        self.comments = comments
        self.source = source


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f"Invalid numeric value: {value!r}") from exc
    if not result.is_finite():
        raise ValidationError("Scenario values must be finite.")
    return result


def integer(value):
    result = number(value)
    if result != result.to_integral_value() or result < 0:
        raise ValidationError(f"Expected a nonnegative integer: {value!r}")
    return int(result)


def records(path, required):
    """Read an explicitly headered CSV/TSV reference; never infer field semantics."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
        stream.seek(0)
        delimiter = '\t' if '\t' in sample.splitlines()[0] else ','
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not reader.fieldnames or not set(required) <= set(reader.fieldnames):
            raise ValidationError(f"{path} requires columns {', '.join(required)}; native format needs an explicit adapter.")
        return list(reader)


@dataclass
class References:
    parameters: dict
    groups: dict
    countries: set
    country_groups: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    installation: str = ""

    @classmethod
    def from_installation(cls, installation):
        if not installation:
            raise ValidationError('Select and save an IFs installation in Companion Settings first.')
        root = Path(installation).expanduser().resolve()
        variable_db = root / 'RUNFILES' / 'IFsVar.db'
        country_db = root / 'DATA' / 'IFs.db'
        groups_file = root / 'DATA' / 'IFS.grp'
        for path in (variable_db, country_db, groups_file):
            if not path.is_file():
                raise ValidationError(f'Missing installation reference: {path}')
        try:
            with closing(sqlite3.connect(variable_db.as_uri() + '?mode=ro', uri=True)) as db:
                entries = db.execute('SELECT NAME,DIMENSION1,DIMENSION2,DIMENSION3 FROM IFsVar').fetchall()
                cursor = db.execute('SELECT * FROM IFsVar')
                columns = [c[0].upper() for c in cursor.description]
                metadata = {row[0]: dict(zip(columns, row)) for row in cursor}
            parameters = {}
            for name, *flags in entries:
                if not isinstance(name, str) or not name or name != name.strip() or name in parameters:
                    raise ValidationError('Invalid or duplicate IFsVar database name.')
                parameters[name] = tuple(integer(flag) for flag in flags)
            with closing(sqlite3.connect(country_db.as_uri() + '?mode=ro', uri=True)) as db:
                country_rows = db.execute('SELECT RegionName,RegionNum FROM RegionIDNewFull').fetchall()
                names = [row[0] for row in country_rows]
            if not names or any(not isinstance(n, str) or not n or n != n.strip() for n in names) or len(set(names)) != len(names):
                raise ValidationError('Invalid or duplicate installation country names.')
            if not parameters:
                raise ValidationError('The installation parameter dictionary is empty.')
            groups = cls.load_groups(groups_file)
            country_indices = {integer(index): name for name, index in country_rows}
            if len(country_indices) != len(names) or 0 in country_indices:
                raise ValidationError('Invalid or duplicate installation country indices.')
            # Country dimensions after the first use actual RegionNum indices.
            groups[1] = country_indices
            country_groups = cls.load_country_groups(country_db, country_indices)
            return cls(parameters, groups, set(names), country_groups, metadata, str(root))
        except sqlite3.Error as exc:
            raise ValidationError(f'Cannot read IFs installation references: {exc}') from exc

    @staticmethod
    def load_country_groups(database, countries):
        """Read full-country presets; never confuse them with IFS.grp dimensions."""
        with closing(sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'GroupIDNewFull', 'GroupingFull'} <= tables:
                return {}  # Older installations may not expose preset groups.
            result = {}
            for identity, name, long_name, alias in db.execute(
                    'SELECT GroupNum,GroupName,LongGroupName,Alias FROM GroupIDNewFull'):
                key = str(integer(identity))
                if key in result or not isinstance(name, str) or not name.strip():
                    raise ValidationError('Invalid or duplicate IFs country group.')
                result[key] = {'id': key, 'name': name, 'long_name': long_name or '',
                               'alias': alias or '', 'countries': [], 'invalid_members': []}
            for label, index, group in db.execute('SELECT Region,RegionNo,GroupNo FROM GroupingFull'):
                item = result.get(str(integer(group)))
                if item is None:
                    raise ValidationError('IFs country membership refers to an unknown group.')
                name = countries.get(integer(index))
                if name is None or name != label:
                    item['invalid_members'].append(str(label))
                elif name not in item['countries']:
                    item['countries'].append(name)
            for item in result.values():
                item['countries'].sort()
            return result

    @classmethod
    def from_companion_settings(cls, settings):
        try:
            installation = json.loads(Path(settings).read_text(encoding='utf-8-sig')).get('installation')
        except (OSError, ValueError, AttributeError) as exc:
            raise ValidationError('Cannot read Companion settings; select and save an IFs installation first.') from exc
        return cls.from_installation(installation)

    @classmethod
    def load(cls, variables, groups, countries):
        parameters = {}
        for row in records(variables, ("NAME", "DIMENSION1", "DIMENSION2", "DIMENSION3")):
            name = row["NAME"].strip()
            if not name or name in parameters:
                raise ValidationError(f"Invalid or duplicate dictionary name: {name!r}")
            parameters[name] = tuple(integer(row[f"DIMENSION{i}"]) for i in (1, 2, 3))
        group_map = cls.load_groups(groups)
        names = Path(countries).read_text(encoding="utf-8-sig").splitlines()
        if not names or any(not n or n != n.strip() for n in names) or len(names) != len(set(names)):
            raise ValidationError("Country reference requires unique exact names, one per line.")
        return cls(parameters, group_map, set(names))

    @staticmethod
    def load_groups(groups):
        group_map = {}
        with Path(groups).open(encoding='utf-8-sig', newline='') as stream:
            native = list(csv.reader(stream))
        if native and len(native[0]) == 1 and native[0][0].strip().isdigit():
            # IFsFunctions.vb initializes i=1 then increments before loading each
            # row: first data row is dimension 2. Column 0 is the member count.
            maximum = integer(native[0][0].strip())
            if len(native) != maximum:
                raise ValidationError('IFS.grp dimension count contradicts its data rows.')
            group_rows = []
            for flag, fields in enumerate(native[1:], 2):
                labels = [value.strip() for value in fields[1:]]
                if integer(fields[0].strip()) != len(labels):
                    raise ValidationError(f'IFS.grp member count mismatch at dimension {flag}.')
                group_rows.extend({'DIMENSION': flag, 'INDEX': index, 'NAME': label}
                                  for index, label in enumerate(labels, 1))
        else:
            group_rows = records(groups, ("DIMENSION", "INDEX", "NAME"))
        for row in group_rows:
            flag, index = integer(row["DIMENSION"]), integer(row["INDEX"])
            label = row["NAME"].strip()
            if flag <= 0 or index <= 0 or not label:
                raise ValidationError("Group dimensions and indices must be positive, with nonempty names.")
            members = group_map.setdefault(flag, {})
            if index in members or label in members.values():
                raise ValidationError(f"Duplicate group member for dimension {flag}.")
            members[index] = label
        return group_map

    def dimensions(self, parameter):
        if parameter not in self.parameters or parameter != parameter.lower():
            raise ValidationError(f"Unknown parameter {parameter!r}; check IFsVar.txt.")
        return self.parameters[parameter]

    def targets(self, parameter, targets):
        flags = self.dimensions(parameter)
        active = [(axis, flag) for axis, flag in enumerate(flags) if flag > 0]
        if len(targets) != len(active):
            raise ValidationError(f"{parameter} requires {len(active)} targets for dimensions {flags}.")
        output = []
        for (axis, flag), target in zip(active, targets):
            if axis == 0 and flag == 1:
                if target not in self.countries and not any(g['name'] == target and g['countries'] and not g['invalid_members'] for g in self.country_groups.values()):
                    raise ValidationError(f"Unknown exact country spelling: {target!r}")
                output.append(target)
            else:
                members = self.groups.get(flag, {})
                if isinstance(target, str) and target in members.values():
                    index = next(i for i, label in members.items() if label == target)
                else:
                    index = integer(target)
                if index not in members:
                    raise ValidationError(f"Index {index} absent from IFS.grp dimension {flag}.")
                output.append(str(index))
        return output


class Compiler:
    def __init__(self, references, base_year=2022):
        self.references = references
        self.base_year = integer(base_year)

    def build(self, entries):
        rows, seen = [], set()
        for entry in entries:
            parameter = entry["parameter"]
            targets = self.references.targets(parameter, entry.get("targets", []))
            key = (parameter, *targets)
            if key in seen:
                raise ValidationError(f"Duplicate scenario target: {key}")
            seen.add(key)
            values = [str(number(v)) for v in entry["values"]]
            if not values:
                raise ValidationError("Provide values beginning at the base year; no implicit filling.")
            rows.append(["CUSTOM", parameter, *targets, *values])
        return ScenarioRows(rows)

    def read(self, path):
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            return self.parse(stream.read(), Path(path).name)

    def parse(self, text, source=None):
        lines = text.lstrip('\ufeff').splitlines(keepends=True)
        boundary = next((i for i, line in enumerate(lines)
                         if line.rstrip('\r\n') == 'COMMENT,START'), len(lines))
        try:
            rows = ScenarioRows(csv.reader(lines[:boundary], strict=True), ''.join(lines[boundary + 1:]), source)
        except csv.Error as exc:
            raise ValidationError(f'Invalid scenario CSV: {exc}') from exc
        seen = set()
        for line, row in enumerate(rows, 1):
            if not row or row[0] != "CUSTOM":
                continue  # Preserve scenario metadata and other directives.
            if len(row) < 2:
                raise ValidationError(f"Malformed CUSTOM row at line {line}.")
            count = sum(flag > 0 for flag in self.references.dimensions(row[1]))
            row[2:2 + count] = self.references.targets(row[1], row[2:2 + count])
            key = tuple(row[1:2 + count])
            if key in seen:
                raise ValidationError(f"Ambiguous duplicate CUSTOM target at line {line}.")
            seen.add(key)
            if len(row) <= 2 + count:
                raise ValidationError(f"Missing base-year value at line {line}.")
            for value in row[2 + count:]:
                number(value)
        return rows

    def modify(self, rows, changes):
        result = ScenarioRows((list(row) for row in rows), getattr(rows, 'comments', ''), getattr(rows, 'source', None))
        for change in changes:
            parameter = change["parameter"]
            targets = self.references.targets(parameter, change.get("targets", []))
            prefix = ["CUSTOM", parameter, *targets]
            matches = [row for row in result if row[:len(prefix)] == prefix]
            if len(matches) != 1:
                raise ValidationError(f"Expected one matching row for {parameter} {targets}; found {len(matches)}.")
            start, end = integer(change["start_year"]), integer(change["end_year"])
            row = matches[0]
            if not self.base_year <= start <= end < self.base_year + len(row) - len(prefix):
                raise ValidationError("Requested years are reversed or outside the existing trajectory.")
            operation = change["operation"]
            if operation not in ("multiply", "add", "zero"):
                raise ValidationError(f"Unknown operation: {operation}")
            operand = number(change["value"]) if operation != "zero" else Decimal(0)
            for year in range(start, end + 1):
                column = len(prefix) + year - self.base_year
                value = number(row[column])
                row[column] = str(value * operand if operation == "multiply" else value + operand if operation == "add" else operand)
        return result

    def render(self, rows, *, purpose, regeneration_prompt, model_context):
        """Generate mandatory provenance from the exact final validated records."""
        for label, value in [('Purpose', purpose), ('Regeneration prompt', regeneration_prompt)]:
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f'{label} is required before export.')
        if not isinstance(model_context, dict) or not str(model_context.get('version', '')).strip():
            raise ValidationError('Model context requires the IFs version.')
        if integer(model_context.get('base_year', -1)) != self.base_year:
            raise ValidationError('Model context base year contradicts the compiler.')
        # Validate data before export; comments describe intent, not duplicate data.
        entries = []
        for row in rows:
            if row and row[0] == 'COMMENT':
                raise ValidationError('Pass comments through ScenarioRows, not CSV records.')
            if row and row[0] == 'CUSTOM':
                if len(row) < 2:
                    raise ValidationError('Malformed CUSTOM record.')
                count = sum(flag > 0 for flag in self.references.dimensions(row[1]))
                entries.append({'parameter': row[1], 'targets': row[2:2 + count],
                                'values': row[2 + count:]})
        self.build(entries)
        parameters = list(dict.fromkeys(entry['parameter'] for entry in entries))
        created = datetime.now(timezone.utc).isoformat(timespec='seconds')
        buffer = io.StringIO(newline='')
        csv.writer(buffer, lineterminator='\n').writerows(rows)
        buffer.write('COMMENT,START\n')
        previous = getattr(rows, 'comments', '')
        if previous:
            buffer.write('--- Preserved source comments ---\n')
            buffer.write(previous)
            if not previous.endswith('\n'):
                buffer.write('\n')
        buffer.write('\n--- Scenario Builder generation record ---\n')
        buffer.write(f'Created: {created} (UTC)\n')
        buffer.write(f'Purpose: {purpose.strip()}\n')
        buffer.write(f'Parameters used: {", ".join(parameters) or "None"}.\n')
        buffer.write(f'IFs version: {model_context["version"]}\nBase year: {self.base_year}\n')
        buffer.write(f'Source scenario: {getattr(rows, "source", None) or "New scenario"}\n')
        buffer.write(f'Regeneration prompt:\n{regeneration_prompt.strip()}\n')
        return buffer.getvalue()

    def save(self, rows, output, *, purpose, regeneration_prompt, model_context):
        output = Path(output)
        if output.suffix.lower() != ".sce":
            raise ValidationError("Output must have a .sce extension.")
        content = self.render(rows, purpose=purpose, regeneration_prompt=regeneration_prompt,
                              model_context=model_context)
        # Exclusive creation protects originals and previously generated flavors.
        try:
            with output.open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
        except FileExistsError as exc:
            raise ValidationError(f"Output already exists; choose a distinct filename: {output}") from exc
        return output.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="Local JSON job specification")
    args = parser.parse_args()
    try:
        job = json.loads(args.request.read_text(encoding="utf-8-sig"))
        # Relative paths resolve beside the job, independently of notebook/IDE cwd.
        def local(value):
            return args.request.resolve().parent / value
        refs = References.from_companion_settings(local(job['companion_settings']))
        compiler = Compiler(refs, job.get("base_year", 2022))
        if "source" in job:
            rows = compiler.modify(compiler.read(local(job["source"])), job["changes"])
        else:
            rows = compiler.build(job["entries"])
        output = compiler.save(rows, local(job['output']), purpose=job['purpose'],
                               regeneration_prompt=job['regeneration_prompt'], model_context=job['model_context'])
        print(f"Saved {output}")
    except (ValidationError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Compilation halted: {exc}\n")


if __name__ == "__main__":
    main()
