"""Companion's IFs installation checks. Source databases are read-only."""
import math
from pathlib import Path
import sqlite3

REQUIRED_DIRECTORIES = ('DATA', 'RUNFILES')
REQUIRED_FILES = (
    'IFsInit.db',
    'DATA/IFsHistSeries.db', 'DATA/DataDict.db', 'DATA/SAMBase.db',
    'RUNFILES/IFsHistSeries.db', 'RUNFILES/DataDict.db', 'RUNFILES/IFsVar.db',
    'RUNFILES/IFsBase.run.db', 'RUNFILES/IFs.db', 'net8/ifs.exe',
)


def validate_installation(path):
    if not path or not str(path).strip():
        raise ValueError('Select an IFs installation folder.')
    root = Path(str(path).strip()).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('The IFs installation folder does not exist or is not a directory.')
    missing = [name + '/' for name in REQUIRED_DIRECTORIES if not (root / name).is_dir()]
    missing += [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError('Missing required IFs files or folders: ' + ', '.join(missing))
    try:
        db = sqlite3.connect((root / 'IFsInit.db').as_uri() + '?mode=ro', uri=True)
        try:
            years = []
            for pattern in ('LastYearHistory%', 'FirstYearForecast%'):
                row = db.execute('SELECT Value FROM IFsInit WHERE Variable LIKE ? ORDER BY Variable LIMIT 1', (pattern,)).fetchone()
                try:
                    value = float(row[0]) if row and row[0] is not None else float('nan')
                    year = int(value) if math.isfinite(value) and value.is_integer() and value > 0 else None
                except (TypeError, ValueError, OverflowError):
                    year = None
                if year is not None:
                    years.append(year)
            row = db.execute('SELECT Value FROM LoadFull WHERE Variable=? ORDER BY rowid DESC LIMIT 1', ('ModelVersion$',)).fetchone()
            version = str(row[0]).strip() if row and row[0] is not None else ''
        finally:
            db.close()
    except sqlite3.Error as exc:
        raise ValueError('Cannot read IFs base year and version from IFsInit.db: ' + str(exc)) from exc
    if not years:
        raise ValueError('IFsInit.db must contain a valid LastYearHistory or FirstYearForecast base year.')
    if not version:
        raise ValueError('IFsInit.db is missing ModelVersion$ in the LoadFull table.')
    return {'base_year': min(years), 'version': version}
